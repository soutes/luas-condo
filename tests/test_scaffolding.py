import json
import os
import re
import yaml

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_docker_compose_structure():
    compose_path = os.path.join(ROOT_DIR, "docker-compose.yml")
    assert os.path.exists(compose_path), "docker-compose.yml must exist"
    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    services = data.get("services", {})
    expected_services = ["db", "backend", "mock-bitrix", "frontend", "prometheus", "grafana"]
    for svc in expected_services:
        assert svc in services, f"Service '{svc}' must be defined in docker-compose.yml"

    # Verify expected port exposures
    ports_map = {}
    for name, svc in services.items():
        raw_ports = svc.get("ports", [])
        ports_map[name] = [str(p) for p in raw_ports]

    def has_port(svc_name, host_port):
        for p in ports_map.get(svc_name, []):
            if str(host_port) in p:
                return True
        return False

    assert has_port("db", 5432), "db service must expose port 5432"
    assert has_port("backend", 8000), "backend service must expose port 8000"
    assert has_port("mock-bitrix", 8080), "mock-bitrix service must expose port 8080"
    assert has_port("frontend", 5173), "frontend service must expose port 5173"
    assert has_port("prometheus", 9090), "prometheus service must expose port 9090"
    assert has_port("grafana", 3001), "grafana service must expose port 3001"

    frontend_volumes = services.get("frontend", {}).get("volumes", [])
    assert "/app/node_modules" in frontend_volumes, "frontend service must mount /app/node_modules as anonymous volume to prevent host shadowing"

def test_scaffolding_files_exist():
    required_files = [
        "docker-compose.yml",
        ".env.example",
        "backend/Dockerfile",
        "backend/requirements.txt",
        "backend/pyproject.toml",
        "frontend/Dockerfile",
        "frontend/package.json",
        "mock_bitrix/Dockerfile",
        "mock_bitrix/requirements.txt",
    ]
    for rel_path in required_files:
        full_path = os.path.join(ROOT_DIR, rel_path)
        assert os.path.exists(full_path), f"File {rel_path} must exist"
        assert os.path.getsize(full_path) > 0, f"File {rel_path} must not be empty"

def test_frontend_package_json_valid():
    pkg_path = os.path.join(ROOT_DIR, "frontend", "package.json")
    if os.path.exists(pkg_path):
        with open(pkg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "name" in data
        assert "scripts" in data

def test_no_emojis_in_scaffolding():
    # Simple regex to catch standard emoji unicode ranges
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF]+",
        flags=re.UNICODE
    )
    for root, _, files in os.walk(ROOT_DIR):
        if ".git" in root or ".venv" in root or "node_modules" in root:
            continue
        for f in files:
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    content = fp.read()
                    match = emoji_pattern.search(content)
                    assert match is None, f"Emoji detected in file {path}: {match.group(0)}"
            except UnicodeDecodeError:
                pass
