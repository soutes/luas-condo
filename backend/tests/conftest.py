"""
Shared pytest configuration for the backend test-suite.
Sets the write-API token used by authenticated test clients.
No emojis used.
"""

import pytest

WRITE_TOKEN = "test-write-token-0123456789abcdef"
WRITE_HEADERS = {"Authorization": f"Bearer {WRITE_TOKEN}"}


@pytest.fixture(autouse=True)
def _write_token_env(monkeypatch):
    monkeypatch.setenv("API_WRITE_TOKEN", WRITE_TOKEN)
