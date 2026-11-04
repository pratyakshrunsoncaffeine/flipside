"""Secret scan. Every value here is synthetic and not a real credential."""

import pytest

from flipside.seal.secrets import entropy, scan

FAKE = {
    "aws_access_key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "github_token": "ghp_" + "a" * 18 + "B" * 18,
    "github_pat": "github_pat_" + "x1" * 35,
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF123_-xyz789",
    "slack_token": "xoxb-" + "1234567890-abcdefghij",
    "api_key": "sk-ant-" + "Q" * 10 + "w" * 10 + "9" * 15,
}


@pytest.mark.parametrize(("kind", "value"), list(FAKE.items()))
def test_kinds(kind: str, value: str) -> None:
    hits = scan(f"before {value} after")
    assert [h.kind for h in hits] == [kind]
    assert hits[0].start == 7


def test_private_key_block_with_and_without_end() -> None:
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
    assert [h.kind for h in scan(block)] == ["private_key"]
    assert scan(block)[0].end == len(block)
    assert [h.kind for h in scan("x -----BEGIN OPENSSH PRIVATE KEY-----\nAAAA")] == ["private_key"]


def test_env_value_needs_entropy() -> None:
    assert [h.kind for h in scan("DB_PASSWORD=Zx9q2LmP7vR4tY8kW3nB")] == ["env_value"]
    assert scan("DEBUG=aaaaaaaaaaaaaaaaaaaa") == []
    assert scan("SESSION_TTL = 86400") == []


def test_clean_text() -> None:
    assert scan("test_export_csv failed with SessionExpired; raising SESSION_TTL") == []


def test_entropy() -> None:
    assert entropy("") == 0.0
    assert entropy("ab") == 1.0
