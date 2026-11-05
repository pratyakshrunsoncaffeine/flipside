"""flip setup and flip chat against a recording fake of the Switch gateway."""

import argparse
import json
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from flipside.room import chat, setup
from flipside.room.daemon import check_config, load_config
from flipside.room.switch_client import Http


class FakeSwitch(Http):
    """Every Http instance shares one call log; responses are keyed by path."""

    calls: ClassVar[list[tuple[str, str, Any, str | None]]] = []
    agents: ClassVar[Iterator[str]] = iter([])

    def __init__(self, base: str = "", bearer: str | None = None) -> None:
        super().__init__(base or "http://fake", bearer)

    def _log(self, method: str, path: str, body: Any) -> None:
        FakeSwitch.calls.append((method, path, body, self.bearer))

    def get(self, path: str) -> Any:
        self._log("GET", path, None)
        return {}

    def put(self, path: str, body: dict[str, Any]) -> Any:
        self._log("PUT", path, body)
        return {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self._log("POST", path, body)
        if path == "/gateway/api-keys":
            return {"key": "owner-token"}
        if path == "/agents/register-known":
            return {"id": next(FakeSwitch.agents), "api_key": "agent-secret"}
        if path == "/gateway/chats":
            return {"chat": {"roomId": f"room-{body['name']}"}}  # type: ignore[index]
        return {}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> type[FakeSwitch]:
    FakeSwitch.calls = []
    FakeSwitch.agents = iter(["agent-a", "agent-r"])
    monkeypatch.setattr(setup, "Http", FakeSwitch)
    return FakeSwitch


def ns(tmp: Path, **kw: Any) -> argparse.Namespace:
    creds = tmp / "creds.json"
    creds.write_text(
        json.dumps({"me": {"email": "me@x", "password": "pw"}}), encoding="utf-8", newline=""
    )
    os.chmod(creds, 0o600)
    base = dict(
        base="http://switch",
        creds=creds,
        as_="me",
        repo=str(tmp),
        work=None,
        base_ref="origin/main",
        github=None,
        pr_json=None,
        head=None,
        join=None,
    )
    return argparse.Namespace(**{**base, **kw})


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def three_steps(tmp: Path) -> tuple[Path, Path, str, str]:
    owner_a = (FakeSwitch(), "u-author", "Priya S")
    owner_r = (FakeSwitch(), "u-reviewer", "Omar")
    a_out, r_out = tmp / "author.json", tmp / "reviewer.json"
    line_a = setup.setup_author_start(
        ns(tmp, pr=142, out=str(a_out), agent_name="fs-author"), owner_a
    )
    out_r = setup.setup_reviewer(
        ns(tmp, pr=142, out=str(r_out), agent_name="fs-reviewer", github="acme/shop", join=line_a),
        owner_r,
    )
    line_r = out_r.splitlines()[0]
    setup.setup_author_finish(argparse.Namespace(join=line_r, out=str(a_out)), FakeSwitch())
    return a_out, r_out, line_a, line_r


def test_three_steps_give_two_complete_private_configs(
    fake: type[FakeSwitch], tmp_path: Path
) -> None:
    a_out, r_out, line_a, line_r = three_steps(tmp_path)
    a, r = (
        json.loads(a_out.read_text(encoding="utf-8")),
        json.loads(r_out.read_text(encoding="utf-8")),
    )
    check_config(a)
    check_config(r)
    if os.name == "posix":
        assert mode(a_out) == 0o600 and mode(r_out) == 0o600
    assert a["shared"] == r["shared"] == "room-pr-142"
    assert a["private"] == "room-pr-142-author"
    assert a["reviewer_agent"] == "agent:agent-r" and r["author_agent"] == "agent:agent-a"
    assert r["pr_author"] == a["author_user"] == "user:u-author"
    assert r["author_agent_name"] == "fs-author" and r["github"] == "acme/shop"
    assert Path(a["work"]).parts[-3:] == (".git", "flipside", "work-author")
    # The join lines carry ids only: no key, password or token.
    for line in (line_a, line_r):
        assert "secret" not in line and "pw" not in line and "token" not in line


def test_policies_and_membership(fake: type[FakeSwitch], tmp_path: Path) -> None:
    three_steps(tmp_path)
    puts = {path: body for m, path, body, _ in fake.calls if m == "PUT"}
    r_rules = puts["/gateway/agents/agent-r/addressing-policy"]["policy"]["rules"]
    a_rules = puts["/gateway/agents/agent-a/addressing-policy"]["policy"]["rules"]
    assert r_rules[1] == {"rooms": ["room-pr-142"], "users": "*", "agents": ["agent-a"]}
    assert a_rules[1] == {"rooms": ["room-pr-142"], "users": [], "agents": ["agent-r"]}
    assert a_rules[0] == r_rules[0] == setup.OWNER_RULE
    posts = [(path, body) for m, path, body, _ in fake.calls if m == "POST"]
    assert ("/gateway/chats/room-pr-142/members", {"userId": "u-author"}) in posts
    assert ("/gateway/rooms/room-pr-142/agents", {"agent_ids": ["agent-a"]}) in posts
    # Each room opens with Flipside's own first message, not Switch's generic greeting.
    greetings = {b["name"]: b["greeting"] for p, b in posts if p == "/gateway/chats"}
    assert greetings == {
        "pr-142": setup.shared_greeting(142),
        "pr-142-author": setup.private_greeting(142),
    }
    # reviewer-agent's policy is set before author-agent joins the room.
    order = [path for _, path, _, _ in fake.calls]
    assert order.index("/gateway/agents/agent-r/addressing-policy") < order.index(
        "/gateway/rooms/room-pr-142/agents"
    )


def test_join_line_round_trip_and_checks() -> None:
    line = setup.join_line(role="author", pr=7, name="Priya S", agent="a1")
    assert setup.parse_join(line, "author") == {
        "role": "author",
        "pr": "7",
        "name": "Priya S",
        "agent": "a1",
    }
    with pytest.raises(setup.SetupError, match="reviewer's join line"):
        setup.parse_join(line, "reviewer")
    with pytest.raises(setup.SetupError, match="not a flip-join"):
        setup.parse_join("hello", "author")


def test_wrong_pr_join_line_is_refused(fake: type[FakeSwitch], tmp_path: Path) -> None:
    line_a = setup.join_line(role="author", pr=9, user="u", name="n", agent="a", agent_name="x")
    with pytest.raises(setup.SetupError, match="PR #9"):
        setup.setup_reviewer(
            ns(
                tmp_path,
                pr=142,
                out=str(tmp_path / "r.json"),
                agent_name="r",
                github="o/r",
                join=line_a,
            ),
            (FakeSwitch(), "u", "n"),
        )


@pytest.mark.skipif(os.name != "posix", reason="Windows has no mode bits; access is by ACL")
def test_creds_readable_by_others_is_refused(tmp_path: Path) -> None:
    creds = tmp_path / "c.json"
    creds.write_text(
        json.dumps({"me": {"email": "e", "password": "p"}}), encoding="utf-8", newline=""
    )
    os.chmod(creds, 0o644)
    with pytest.raises(setup.SetupError, match="chmod 600"):
        setup.load_creds(creds, "me")


def test_private_creds_load_on_every_os(tmp_path: Path) -> None:
    creds = tmp_path / "c.json"
    creds.write_text(
        json.dumps({"me": {"email": "e", "password": "p"}}), encoding="utf-8", newline=""
    )
    os.chmod(creds, 0o600)
    assert setup.load_creds(creds, "me") == {"email": "e", "password": "p"}


def test_main_reports_missing_flags(capsys: pytest.CaptureFixture[str]) -> None:
    assert setup.main(["reviewer", "--pr", "1"]) == 1
    err = capsys.readouterr().err
    assert "--creds" in err and "--as" in err and "--github" in err and "--join" in err


def test_check_config_names_missing_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="private, reviewer_agent"):
        check_config({"role": "author", "pr_number": 1})
    with pytest.raises(ValueError, match="role must be"):
        check_config({"role": "x"})
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"role": "reviewer"}), encoding="utf-8", newline="")
    os.chmod(p, 0o600)
    with pytest.raises(SystemExit, match="missing"):
        load_config(p)


# --- flip chat ---------------------------------------------------------------

CFG = {
    "role": "reviewer",
    "agent_name": "fs-reviewer",
    "agent_id": "agent-r",
    "author_agent_name": "fs-author",
    "author_agent": "agent:agent-a",
    "shared": "room-1",
}


def test_mention_tags_own_or_author_agent_only_at_start() -> None:
    assert chat.mention_for(CFG, "@fs-author paste the session") == "agent-a"
    assert chat.mention_for(CFG, "@fs-reviewer status") == "agent-r"
    assert chat.mention_for(CFG, "@fs-authorx hi") is None
    assert chat.mention_for(CFG, "hi @fs-author") is None


def test_open_cards_only_my_agent_and_private_room() -> None:
    rows = [
        {"requestId": "c1", "agentId": "agent-a", "roomId": "priv", "state": "open"},
        {"requestId": "c2", "agentId": "agent-a", "roomId": "other", "state": "open"},
        {"requestId": "c3", "agentId": "agent-a", "roomId": "priv", "state": "answered"},
        {"requestId": "c4", "agentId": "agent-x", "roomId": "priv", "state": "open"},
    ]

    class H:
        def get(self, path: str) -> Any:
            return rows

    cfg = {"role": "author", "agent_id": "agent-a", "private": "priv"}
    assert [c["requestId"] for c in chat.open_cards(H(), cfg)] == ["c1"]  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="0 open cards"):
        chat.find_card([], "zz")


def test_render_multiline() -> None:
    m = {"seq": 3, "sender": {"name": "Priya"}, "body": "Q1: first\nsecond"}
    assert chat.render(m) == "   3 Priya: Q1: first\n       second"


def test_pr_source_github_or_pr_json(tmp_path: Path) -> None:
    pr = tmp_path / "pr.json"
    pr.write_text(
        json.dumps({"number": 5, "title": "t", "body": "b", "author": "a", "files": []}),
        encoding="utf-8",
        newline="",
    )
    assert setup.pr_source(ns(tmp_path, pr=5, github="o/r")) == {"github": "o/r"}
    got = setup.pr_source(ns(tmp_path, pr=5, pr_json=str(pr), head="abc"))
    assert got["head"] == "abc" and got["pr"]["number"] == 5
    with pytest.raises(setup.SetupError, match="exactly one"):
        setup.pr_source(ns(tmp_path, pr=5, github="o/r", pr_json=str(pr)))
    with pytest.raises(setup.SetupError, match="needs --head"):
        setup.pr_source(ns(tmp_path, pr=5, pr_json=str(pr)))
    with pytest.raises(setup.SetupError, match="not #6"):
        setup.pr_source(ns(tmp_path, pr=6, pr_json=str(pr), head="abc"))


def test_show_prints_the_card_text(capsys: pytest.CaptureFixture[str]) -> None:
    card = {
        "requestId": "abc123",
        "agentId": "agent-a",
        "sessionId": "s",
        "roomId": "priv",
        "state": "open",
        "title": "Disclose step 5 chunk 0 to #pr-7?",
        "detail": "raising TIMEOUT_SECONDS to 120\n\nsha256 0123abcd",
    }

    class H(Http):
        def get(self, path: str) -> Any:
            return [card]

    cfg = {"role": "author", "agent_id": "agent-a", "private": "priv"}
    a = chat.parser().parse_args(["--config", "x", "show", "abc"])
    assert chat.run(cfg, a, H("http://fake")) == 0
    out = capsys.readouterr().out
    assert "Disclose step 5 chunk 0" in out and "TIMEOUT_SECONDS to 120" in out


def test_private_greeting_states_the_boundary_without_overclaiming() -> None:
    """The seal and its public manifest reach the shared room without a card (issue #58)."""
    text = setup.private_greeting(142)
    assert "Nothing from your session leaves" not in text
    assert "#pr-142" in text
    assert "seal" in text and "manifest" in text
