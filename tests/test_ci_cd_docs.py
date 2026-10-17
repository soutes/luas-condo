"""
Tests for CI/CD workflow, course documentation, AGENTS.md and rubric verification.
Follows TDD methodology.
Zero emojis used.
"""

from pathlib import Path
import re
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF]+",
    flags=re.UNICODE,
)


def assert_no_emojis(text: str, filename: str):
    match = EMOJI_PATTERN.search(text)
    assert match is None, f"Emoji detected in {filename}: {match.group(0)}"


def test_docs_and_workflow_files_exist():
    required_files = [
        ROOT_DIR / "docs" / "team.md",
        ROOT_DIR / "docs" / "process.md",
        ROOT_DIR / "docs" / "architecture.md",
        ROOT_DIR / "AGENTS.md",
        ROOT_DIR / ".github" / "workflows" / "ci.yml",
        ROOT_DIR / "README.md",
    ]
    for file_path in required_files:
        assert file_path.exists(), f"Required file missing: {file_path.relative_to(ROOT_DIR)}"


def test_agents_markdown_modular_structure():
    agents_file = ROOT_DIR / "AGENTS.md"
    assert agents_file.exists(), "AGENTS.md missing"
    content = agents_file.read_text(encoding="utf-8")
    assert_no_emojis(content, "AGENTS.md")

    # Modular pointer assertions
    assert "docs/team.md" in content or "docs\\team.md" in content
    assert "docs/process.md" in content or "docs\\process.md" in content
    assert "docs/architecture.md" in content or "docs\\architecture.md" in content

    # Agent role mentions
    assert "Extractor" in content
    assert "Legal Auditor" in content
    assert "Submitter" in content
    assert "On-Call Responder" in content or "On-Call Agent" in content


def test_docs_team_specification():
    team_file = ROOT_DIR / "docs" / "team.md"
    assert team_file.exists(), "docs/team.md missing"
    content = team_file.read_text(encoding="utf-8")
    assert_no_emojis(content, "docs/team.md")

    # All 4 agent roles defined with responsibilities and tools
    assert "Extractor Agent" in content
    assert "Legal Auditor Agent" in content
    assert "Submitter Agent" in content
    assert "On-Call Responder Agent" in content
    assert "Responsibilities" in content or "responsibilities" in content.lower()
    assert "Tools" in content or "tools" in content.lower()
    assert "Communication" in content or "communication" in content.lower()


def test_docs_process_specification():
    process_file = ROOT_DIR / "docs" / "process.md"
    assert process_file.exists(), "docs/process.md missing"
    content = process_file.read_text(encoding="utf-8")
    assert_no_emojis(content, "docs/process.md")

    # Key process lifecycle elements
    assert "Lifecycle" in content or "lifecycle" in content.lower()
    assert "Human-in-the-Loop" in content or "human-in-the-loop" in content.lower()
    assert "Escalation" in content or "escalation" in content.lower()
    assert "Self-Healing" in content or "self-healing" in content.lower()


def test_docs_architecture_specification():
    arch_file = ROOT_DIR / "docs" / "architecture.md"
    assert arch_file.exists(), "docs/architecture.md missing"
    content = arch_file.read_text(encoding="utf-8")
    assert_no_emojis(content, "docs/architecture.md")

    # Components and architectural highlights
    assert "FastAPI" in content
    assert "React" in content
    assert "PostgreSQL" in content
    assert "OpenTelemetry" in content
    assert "Prometheus" in content
    assert "Grafana" in content
    assert "Docker" in content
    assert "LGPD" in content or "PII" in content


def test_github_actions_ci_cd_workflow():
    workflow_file = ROOT_DIR / ".github" / "workflows" / "ci.yml"
    assert workflow_file.exists(), ".github/workflows/ci.yml missing"
    content = workflow_file.read_text(encoding="utf-8")
    assert_no_emojis(content, ".github/workflows/ci.yml")

    # Validate valid YAML syntax
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "ci.yml must parse to a valid dictionary"

    # Verify triggers: PR and push to main or workflow_dispatch
    triggers = data.get("on") or data.get(True) or {}
    if isinstance(triggers, list):
        assert "pull_request" in triggers
    elif isinstance(triggers, dict):
        assert "pull_request" in triggers or "push" in triggers or "workflow_dispatch" in triggers

    jobs = data.get("jobs", {})
    assert "test" in jobs, "Workflow must contain a 'test' job for automated testing"

    # Verify automated dev deployment and manual prod deployment with rollback
    has_deploy_dev = "deploy-dev" in jobs or "deploy_dev" in jobs
    has_deploy_prod = "deploy-prod" in jobs or "deploy_prod" in jobs
    assert has_deploy_dev, "Workflow must contain an automated deployment job to dev"
    assert has_deploy_prod, "Workflow must contain a deployment job to production"

    # Rollback capability check
    workflow_str = str(content)
    assert "rollback" in workflow_str.lower(), "Workflow must include rollback parameter or step"
    assert "playwright install" in workflow_str.lower(), "Workflow must install Playwright browser dependencies"


def test_readme_course_rubric_and_criteria_coverage():
    readme_file = ROOT_DIR / "README.md"
    assert readme_file.exists(), "README.md missing"
    content = readme_file.read_text(encoding="utf-8")
    assert_no_emojis(content, "README.md")

    # Course criteria 1 to 12 (all 24 points)
    criteria_checks = [
        ("Problem Description", "8.245"),
        ("Product Specification", "github.com/soutes/luas-condo/issues"),
        ("Agent Team", "docs/team.md"),
        ("Context Management", "AGENTS.md"),
        ("Application", "docker compose up"),
        ("Testing", "pytest"),
        ("Containerization", "docker-compose"),
        ("Deployment", "runbook"),
        ("CI/CD", ".github/workflows/ci.yml"),
        ("Observability", "OpenTelemetry"),
        ("Alerting", "CondoSubmissionFailed"),
        ("On-Call Agent", "self-healing"),
    ]

    for label, keyword in criteria_checks:
        assert keyword.lower() in content.lower(), f"README.md missing criteria coverage for {label} ({keyword})"

    # Verify English language
    assert "Condominium" in content or "Condo" in content
    assert "Reimbursement" in content
    assert "Overview" in content or "Quickstart" in content
