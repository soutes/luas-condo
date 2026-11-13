"""
Consistency tests for the monitoring, tracing, compose and CI/CD configuration.
They guard the wiring between files (rules loaded, alerts routed to the responder,
traces exported, deploy steps real, webhook not public).
No emojis used.
"""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(relative: str) -> dict:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def test_prometheus_loads_alert_rules_and_targets_alertmanager():
    prom = load_yaml("monitoring/prometheus.yml")
    assert "/etc/prometheus/alert_rules.yml" in prom["rule_files"]
    targets = [
        t
        for am in prom["alerting"]["alertmanagers"]
        for sc in am["static_configs"]
        for t in sc["targets"]
    ]
    assert "alertmanager:9093" in targets


def test_compose_mounts_rules_and_runs_alertmanager_and_jaeger():
    compose = load_yaml("docker-compose.yml")
    services = compose["services"]
    assert "./monitoring/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro" in services["prometheus"]["volumes"]
    assert "./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" in services["alertmanager"]["volumes"]
    assert "jaeger" in services
    assert any("16686" in p for p in services["jaeger"]["ports"])


def test_alertmanager_routes_to_authenticated_oncall_webhook():
    am = load_yaml("monitoring/alertmanager.yml")
    assert am["route"]["receiver"] == "oncall-agent"
    receiver = next(r for r in am["receivers"] if r["name"] == "oncall-agent")
    hook = receiver["webhook_configs"][0]
    assert hook["url"] == "http://backend:8000/api/alerts/webhook"
    auth = hook["http_config"]["authorization"]
    assert auth["type"] == "Bearer"
    assert auth["credentials_file"] == "/tmp/alert_webhook_token"


def test_alertmanager_service_receives_token_and_backend_checks_it():
    services = load_yaml("docker-compose.yml")["services"]
    assert "ALERT_WEBHOOK_TOKEN" in services["alertmanager"]["environment"]
    assert "ALERT_WEBHOOK_TOKEN" in services["backend"]["environment"]


def test_backend_exports_traces_to_jaeger_otlp_http():
    env = load_yaml("docker-compose.yml")["services"]["backend"]["environment"]
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"].startswith("${OTEL_EXPORTER_OTLP_ENDPOINT:-http://jaeger:4318")
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "opentelemetry-exporter-otlp-proto-http" in requirements


def test_base_compose_is_self_contained_and_vm_override_joins_web():
    base = load_yaml("docker-compose.yml")
    assert "networks" not in base or "web" not in base["networks"], "base compose must not require the external web network"
    for svc in base["services"].values():
        assert "web" not in (svc.get("networks") or [])
    vm = load_yaml("docker-compose.vm.yml")
    assert vm["networks"]["web"]["external"] is True
    assert "web" in vm["services"]["backend"]["networks"]
    assert "web" in vm["services"]["frontend"]["networks"]


def test_caddy_does_not_expose_alert_webhook_publicly():
    caddy = (ROOT / "deploy" / "condo.caddy").read_text(encoding="utf-8")
    alerts_block = caddy.index("handle /api/alerts*")
    generic_api_block = caddy.index("handle /api*")
    assert alerts_block < generic_api_block
    assert "respond 404" in caddy[alerts_block:generic_api_block]


def test_ci_deploy_jobs_run_real_deployment_not_placeholders():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    data = load_yaml(".github/workflows/ci.yml")
    for job_name in ("deploy-dev", "deploy-prod"):
        steps = data["jobs"][job_name]["steps"]
        runs = "\n".join(step.get("run", "") for step in steps)
        assert "deploy/ci-deploy.sh" in runs, f"{job_name} must call the SSH deploy script"
    # Workflow inputs must reach scripts through env vars, never interpolated into shell code.
    for job in data["jobs"].values():
        for step in job["steps"]:
            run = step.get("run", "")
            assert "${{ github.event.inputs" not in run, "inputs must not be interpolated into run scripts"
    assert "rollback_commit" in workflow


def test_deploy_scripts_validate_target_and_rollback_on_unhealthy():
    deploy = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert re.search(r"\^\[0-9a-fA-F\]\{7,40\}\$", deploy)
    assert "rolling back to" in deploy.lower()
    assert "/api/health" in deploy
    ci_deploy = (ROOT / "deploy" / "ci-deploy.sh").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=yes" in ci_deploy
