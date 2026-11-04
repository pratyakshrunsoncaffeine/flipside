"""author-agent and reviewer-agent state machines (docs/BUILD.md sections 4, 7, 8).

Both agents are event-sourced: each ``step()`` re-reads the room transcript and acts
only on what its own earlier posts have not covered yet, so a restarted agent resumes
without duplicate posts. Every decision is deterministic Python; no LLM.
"""

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flipside.room.brief import build_brief
from flipside.room.protocol import (
    AUTHOR_AGENT,
    REVIEWER_AGENT,
    Msg,
    accept,
    decode,
    encode,
    parse_answer,
    parse_request,
)
from flipside.room.rules import Gap, PRData, Selection, asked, contradictions, gaps, select
from flipside.room.transport import Transport
from flipside.seal.canon import canon
from flipside.seal.git import git, parse_trailer, trailer_values
from flipside.seal.manifest import ManifestError, load_manifest
from flipside.seal.prove import (
    ProveError,
    Rebuilt,
    disclosure,
    leaf_secret_hits,
    load_state,
    rebuild,
)
from flipside.seal.seal import state_dir
from flipside.seal.verify import verify

Log = Callable[[str], None]
AUTHOR_AGENT_NAME, REVIEWER_AGENT_NAME = "flipside-author-agent", "flipside-reviewer-agent"
DEFAULT_TIMEOUT = 1800.0
_OFFER = re.compile(r"^@\S+\s+offer\s+Q(\d+)\s+(step|leaf)\s+(\d+)\s*$")


def default_timeout() -> float:
    """The page-rule timeout in seconds: ``FLIP_ANSWER_TIMEOUT`` or 30 minutes."""
    raw = os.environ.get("FLIP_ANSWER_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    value = float(raw)
    if value <= 0:
        raise ValueError(f"FLIP_ANSWER_TIMEOUT must be positive, got {raw!r}")
    return value


def write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` in one step, so a killed process never leaves half a file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


def find_seal(repo: Path, base: str, head: str) -> str | None:
    """The newest commit in base..head with exactly one valid Flipside-Seal trailer."""
    for sha in git(repo, "rev-list", f"{base}..{head}").split():
        values = trailer_values(repo, sha)
        if len(values) == 1 and parse_trailer(values[0]):
            return sha
    return None


APPROVE = ("approve", "accept")


def card_id(commit: str, i: int) -> str:
    """Deterministic card id, one per leaf: a restarted author-agent never opens a second
    card, and two questions asking for the same leaf share one card (the same bytes)."""
    return hashlib.sha256(f"flipside/card/{commit}/{i}".encode()).hexdigest()[:32]


def _short(sha: str) -> str:
    return sha[:7]


@dataclass
class AuthorConfig:
    pr: int
    shared: str
    private: str
    repo: Path
    root: str
    commit: str
    reviewer_agent: str
    author_user: str
    author_name: str
    state_path: Path | None = None
    agent_name: str = AUTHOR_AGENT_NAME


@dataclass
class AuthorAgent:
    """Seals are published, requests are checked, cards are opened, approved leaves are
    proved and disclosed. Acts only on requests from reviewer-agent's sender id."""

    t: Transport
    cfg: AuthorConfig
    log: Log = print
    cards: dict[str, int] = field(default_factory=dict)
    dropped: set[str] = field(default_factory=set)
    _rebuilt: Rebuilt | None = None

    def __post_init__(self) -> None:
        if self.cfg.state_path and self.cfg.state_path.exists():
            raw = json.loads(self.cfg.state_path.read_text(encoding="utf-8"))
            self.cards = {
                k: int(v[-1] if isinstance(v, list) else v) for k, v in raw.get("cards", {}).items()
            }
            self.dropped = set(raw.get("dropped", []))

    def _save(self) -> None:
        if self.cfg.state_path:
            write_atomic(
                self.cfg.state_path,
                json.dumps(
                    {
                        "cards": dict(self.cards),
                        "dropped": sorted(self.dropped),
                    },
                    sort_keys=True,
                ),
            )

    @property
    def rebuilt(self) -> Rebuilt:
        """Every leaf, rebuilt from the session. Raises ProveError(SESSION_CHANGED) when the
        sealed part of the session no longer matches; nothing else in step() needs it."""
        if self._rebuilt is None:
            self._rebuilt = rebuild(self.cfg.repo, self.cfg.root)
        return self._rebuilt

    @property
    def manifest(self) -> bytes:
        """The public manifest stored at seal time; readable even if the session changed."""
        return (state_dir(self.cfg.repo) / f"{self.cfg.root}.manifest.json").read_bytes()

    @property
    def n(self) -> int:
        return int(load_state(self.cfg.repo, self.cfg.root)["n"])

    def roles(self) -> dict[str, str]:
        return {AUTHOR_AGENT: self.t.me, REVIEWER_AGENT: self.cfg.reviewer_agent}

    def step(self) -> int:
        """Act once on the current transcript. Returns the number of posts or cards."""
        acts = 0
        msgs = self.t.read(self.cfg.shared)
        mine = [x for m in msgs if (x := accept(m, self.roles())) and m.sender == self.t.me]
        if not any(o["t"] == "seal" and o.get("commit") == self.cfg.commit for o in mine):
            self.publish_seal()
            acts += 1
        done = {
            (o["q"], o["i"])
            for o in mine
            if o["t"] in ("disclosure", "withheld") and o.get("commit") == self.cfg.commit
        }
        # A leaf's decision, read back from the room: once disclosed or withheld for one
        # question, the same bytes get the same answer for every other question.
        decided: dict[int, str] = {}
        for o in mine:
            if o.get("commit") != self.cfg.commit:
                continue
            if o["t"] == "disclosure":
                decided[int(o["i"])] = "approve"
            elif o["t"] == "withheld":
                decided.setdefault(int(o["i"]), str(o["reason"]))
        n = self.n
        wanted: list[tuple[int, int]] = []
        for m in msgs:
            wanted += self.wanted(m, n)
        wanted += self.owner_offers()
        pending = list(dict.fromkeys(w for w in wanted if w not in done))
        for oc in self.t.outcomes():
            if oc.card not in self.cards:
                continue
            i = self.cards[oc.card]
            if oc.answered_by != self.cfg.author_user:
                self.log(f"author-agent ignored card {oc.card[:8]} answered by {oc.answered_by}")
                continue
            decided.setdefault(i, "approve" if oc.answer in APPROVE else "author")
        for q, i in pending:
            if i not in decided:
                if card_id(self.cfg.commit, i) in self.cards:
                    continue  # the author has not answered this leaf's card yet
                reason = self.consider(q, i)
                acts += 1
                if reason is None:
                    continue
                decided[i] = reason
            else:
                self.apply(q, i, decided[i])
                acts += 1
            done.add((q, i))
        self._save()
        return acts

    def owner_offers(self) -> list[tuple[int, int]]:
        """Leaves the author offers in their private room: ``@<agent> offer Q<k> step <t>``
        (every chunk of main-session step t) or ``@<agent> offer Q<k> leaf <i>``.
        Only the author's own messages that Switch delivered as addressed count."""
        out: list[tuple[int, int]] = []
        leaves = load_manifest(self.manifest)
        for m in self.t.read(self.cfg.private):
            if m.sender != self.cfg.author_user or m.addressed is False:
                continue
            if not m.body.startswith(f"@{self.cfg.agent_name} "):
                continue
            hit = _OFFER.match(m.body.strip())
            if not hit:
                continue
            q, kind, k = int(hit.group(1)), hit.group(2), int(hit.group(3))
            if kind == "leaf":
                out += [(q, k)] if 0 <= k < len(leaves) else []
            else:
                out += [
                    (q, i) for i, lf in enumerate(leaves) if lf["session"] == 0 and lf["step"] == k
                ]
        return out

    def wanted(self, m: Msg, n: int) -> list[tuple[int, int]]:
        """Leaves a message validly requests. Logs and drops everything else once."""
        if m.sender != self.cfg.reviewer_agent:
            return []
        obj = decode(m.body)
        if obj is None or obj["t"] != "request":
            return []
        reason = ""
        req = parse_request(obj, n)
        if m.addressed is False:
            reason = "not addressed to author-agent"
        elif req is None:
            reason = "fails the request schema (free text or bad leaves)"
        elif req.commit != self.cfg.commit:
            reason = f"names commit {_short(req.commit)}, not the seal commit"
        if reason or req is None:
            if m.id not in self.dropped:
                self.dropped.add(m.id)
                self.log(f"author-agent DROPPED request {m.id}: {reason}")
            return []
        return [(req.q, i) for i in req.leaves]

    def publish_seal(self) -> None:
        manifest, n = self.manifest, self.n
        uri = self.t.upload(self.cfg.shared, "manifest.json", manifest)
        obj = {
            "t": "seal",
            "v": 1,
            "pr": self.cfg.pr,
            "commit": self.cfg.commit,
            "root": self.cfg.root,
            "n": n,
            "manifest": hashlib.sha256(manifest).hexdigest(),
            "mxc": uri,
        }
        line = (
            f"Seal for PR #{self.cfg.pr} · root {_short(self.cfg.root)} · {n} "
            f"leaves · commit {_short(self.cfg.commit)} · manifest attached"
        )
        mid = self.t.post(self.cfg.shared, encode(line, obj))
        self.log(f"author-agent posted seal {mid}")

    def apply(self, q: int, i: int, decision: str) -> None:
        """Act on a leaf's decision for question q: disclose, or withhold with the reason."""
        if decision == "approve":
            self.disclose(q, i)
        else:
            self.withhold(q, i, decision)

    def consider(self, q: int, i: int) -> str | None:
        """Secret-scan leaf i, then withhold it (returns the reason) or open the author's
        approval card (returns None)."""
        try:
            hits = leaf_secret_hits(self.rebuilt, i)
        except ProveError as e:
            self.log(f"author-agent cannot rebuild leaf {i}: {e}")
            self.withhold(q, i, "session_changed")
            return "session_changed"
        if hits:
            self.withhold(q, i, "secret_scan")
            return "secret_scan"
        leaf = self.rebuilt.sealed.leaves[i]
        cid = card_id(self.cfg.commit, i)
        title = f"Disclose step {leaf['step']} chunk {leaf['chunk']} to #pr-{self.cfg.pr}?"
        detail = f"{leaf['text']}\n\nsha256 {hashlib.sha256(canon(leaf)).hexdigest()[:12]}"
        self.t.open_card(self.cfg.private, cid, title, detail)
        self.cards[cid] = i
        self.log(f"author-agent opened card {cid[:8]} for leaf {i} (first asked in Q{q})")
        return None

    def disclose(self, q: int, i: int) -> None:
        """Re-check the sealed prefix (F1) and disclose; a changed session is withheld."""
        try:
            self._rebuilt = rebuild(self.cfg.repo, self.cfg.root)
        except ProveError as e:
            self.log(f"author-agent cannot prove leaf {i}: {e}")
            self.withhold(q, i, "session_changed")
            return
        d = disclosure(self.rebuilt, i, self.cfg.commit)
        lf = d["leaf"]
        line = (
            f"Q{q} · step {lf['step']}, chunk {lf['chunk']} · approved by "
            f"@{self.cfg.author_name} · proof against seal {_short(self.cfg.root)} "
            f"(commit {_short(self.cfg.commit)})"
        )
        mid = self.t.post(self.cfg.shared, encode(line, {**d, "t": "disclosure", "q": q}))
        self.log(f"author-agent posted disclosure {mid} for Q{q} leaf {i}")

    def withhold(self, q: int, i: int, reason: str) -> None:
        obj = {"t": "withheld", "v": 1, "commit": self.cfg.commit, "q": q, "i": i, "reason": reason}
        why = {
            "author": "author declined",
            "secret_scan": "secret scan hit",
            "session_changed": "session changed after sealing",
        }[reason]
        mid = self.t.post(self.cfg.shared, encode(f"Q{q} · leaf {i} withheld ({why})", obj))
        self.log(f"author-agent posted withheld {mid} for Q{q} leaf {i} ({reason})")


@dataclass
class ReviewerConfig:
    pr: PRData
    shared: str
    repo: Path
    head: str
    base: str
    author_agent: str
    author_agent_name: str
    pr_author: str
    reviewer_name: str
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class _Round:
    commit: str
    manifest: list[dict[str, Any]] | None
    manifest_bytes: bytes
    seal_note: str


@dataclass
class ReviewerAgent:
    """Gaps from public data, leaf requests, verdicts, coverage, and the brief."""

    t: Transport
    cfg: ReviewerConfig
    log: Log = print
    clock: Callable[[], float] = time.monotonic
    asked_at: float | None = None
    _round: _Round | None = None

    def roles(self) -> dict[str, str]:
        return {AUTHOR_AGENT: self.cfg.author_agent, REVIEWER_AGENT: self.t.me}

    def seal_commit(self) -> str | None:
        """The newest commit in base..head with exactly one valid Flipside-Seal trailer."""
        return find_seal(self.cfg.repo, self.cfg.base, self.cfg.head)

    def open_round(self, msgs: list[Msg]) -> _Round | None:
        """Wait for the seal message that matches the trailer; check the manifest hash."""
        commit = self.seal_commit()
        if commit is None:
            return _Round(self.cfg.head, None, b"", "no seal on this PR: questions only")
        trailer = parse_trailer(trailer_values(self.cfg.repo, commit)[0])
        assert trailer is not None
        for m in msgs:
            o = accept(m, self.roles())
            if not o or o["t"] != "seal" or o.get("commit") != commit:
                continue
            data = self.t.download(self.cfg.shared, str(o.get("mxc")))
            if hashlib.sha256(data).hexdigest() != trailer.manifest:
                return _Round(
                    commit,
                    None,
                    b"",
                    "MANIFEST_HASH: the attached manifest differs from the trailer",
                )
            try:
                manifest = load_manifest(data)
            except ManifestError as e:
                return _Round(commit, None, b"", f"MANIFEST_HASH: {e}")
            return _Round(
                commit,
                manifest,
                data,
                f"sealed: root {_short(trailer.root)}, {trailer.n} leaves, commit {_short(commit)}",
            )
        return None

    def step(self) -> int:
        msgs = self.t.read(self.cfg.shared)
        if self._round is None:
            self._round = self.open_round(msgs)
            if self._round is None:
                return 0
        rnd = self._round
        mine = [x for m in msgs if (x := accept(m, self.roles())) and m.sender == self.t.me]
        briefed = any(o["t"] == "brief" and o.get("commit") == rnd.commit for o in mine)
        acts = 0
        all_gaps = gaps(self.cfg.pr, rnd.manifest)
        qs, not_asked = asked(all_gaps)
        sel = {
            k: (select(g, rnd.manifest) if rnd.manifest else Selection())
            for k, g in enumerate(qs, 1)
        }
        if not briefed and not any(
            o["t"] == "questions" and o.get("commit") == rnd.commit for o in mine
        ):
            self.post_questions(rnd, qs)
            acts += 1
        if self.asked_at is None:
            self.asked_at = self.clock()
        requested = {o["q"] for o in mine if o["t"] == "request" and o.get("commit") == rnd.commit}
        for k, s in sel.items():
            if s.leaves and k not in requested and not briefed:
                self.post_request(rnd, k, s)
                acts += 1
        answers: dict[int, str] = {}
        for m in msgs:
            if m.sender == self.cfg.pr_author and (a := parse_answer(m.body)):
                answers.setdefault(a[0], a[1])
        verdicted = {o.get("ref") for o in mine if o["t"] == "verdict"}
        verdicts: list[dict[str, Any]] = [o for o in mine if o["t"] == "verdict"]
        withheld: list[dict[str, Any]] = []
        for m in msgs:
            o = accept(m, self.roles())
            if not o or m.sender != self.cfg.author_agent:
                continue
            if o["t"] == "withheld" and o.get("commit") == rnd.commit:
                withheld.append(o)
            if o["t"] == "disclosure" and m.id not in verdicted:
                verdicts.append(self.post_verdict(rnd, m.id, o))
                acts += 1
        if not briefed and self.ready(qs, sel, answers, verdicts, withheld):
            self.post_brief(rnd, qs, not_asked, sel, answers, verdicts, withheld)
            acts += 1
        return acts

    def post_questions(self, rnd: _Round, qs: list[Gap]) -> None:
        obj = {
            "t": "questions",
            "v": 1,
            "commit": rnd.commit,
            "qs": [
                {"q": k, "gap": g.kind, "file": g.file, "text": g.text} for k, g in enumerate(qs, 1)
            ],
        }
        line = (
            f"{len(qs)} question{'s' if len(qs) != 1 else ''} for PR #{self.cfg.pr.number} "
            f"({rnd.seal_note}); answer each as Q<k>: in your own words"
        )
        if not qs:
            line = f"No gaps on PR #{self.cfg.pr.number} ({rnd.seal_note})"
        mid = self.t.post(self.cfg.shared, encode(line, obj))
        self.log(
            f"reviewer-agent posted questions {mid}: "
            + "; ".join(
                f"Q{k} {g.kind} {g.file or g.check or ''}".rstrip() for k, g in enumerate(qs, 1)
            )
        )

    def post_request(self, rnd: _Round, q: int, s: Selection) -> None:
        obj = {"t": "request", "v": 1, "commit": rnd.commit, "q": q, "leaves": list(s.leaves)}
        line = (
            f"@{self.cfg.author_agent_name} Q{q} · requesting leaves "
            f"{', '.join(map(str, s.leaves))} · commit {_short(rnd.commit)}"
        )
        mid = self.t.post(self.cfg.shared, encode(line, obj))
        self.log(f"reviewer-agent posted request {mid} for Q{q}: leaves {list(s.leaves)}")

    def post_verdict(self, rnd: _Round, ref: str, d: dict[str, Any]) -> dict[str, Any]:
        v = verify(self.cfg.repo, d, rnd.manifest_bytes, commit=rnd.commit, head=self.cfg.head)
        i = d.get("i") if isinstance(d.get("i"), int) else -1
        q = d.get("q") if isinstance(d.get("q"), int) else 0
        obj: dict[str, Any] = {
            "t": "verdict",
            "v": 1,
            "commit": rnd.commit,
            "i": i,
            "q": q,
            "code": v.code,
            "ref": ref,
        }
        if v.ok and v.leaf is not None:
            obj["leaf"] = v.leaf
        mid = self.t.post(self.cfg.shared, encode(f"Q{q} · leaf {i} · {v.message()}", obj))
        self.log(f"reviewer-agent posted verdict {mid}: Q{q} leaf {i} {v.code}")
        return obj

    def ready(
        self,
        qs: list[Gap],
        sel: dict[int, Selection],
        answers: dict[int, str],
        verdicts: list[dict[str, Any]],
        withheld: list[dict[str, Any]],
    ) -> bool:
        """Page rule (7.5): every question answered and every requested leaf verified OK
        or withheld; or the timeout passed (then missing answers and leaves are listed)."""
        timed_out = self.asked_at is not None and self.clock() - self.asked_at >= self.cfg.timeout
        if timed_out:
            return True
        if any(k not in answers for k in range(1, len(qs) + 1)):
            return False
        settled = {(v["q"], v["i"]) for v in verdicts if v["code"] == "OK"} | {
            (w["q"], w["i"]) for w in withheld
        }
        return all((k, i) in settled for k, s in sel.items() for i in s.leaves)

    def post_brief(
        self,
        rnd: _Round,
        qs: list[Gap],
        not_asked: list[Gap],
        sel: dict[int, Selection],
        answers: dict[int, str],
        verdicts: list[dict[str, Any]],
        withheld: list[dict[str, Any]],
    ) -> None:
        found = []
        for k, g in enumerate(qs, 1):
            ok = [
                {"i": v["i"], "leaf": v["leaf"]}
                for v in verdicts
                if v["q"] == k and v["code"] == "OK" and "leaf" in v
            ]
            found.extend(contradictions(k, answers.get(k), g, ok, sel[k].anchored))
        line, obj = build_brief(
            self.cfg.pr,
            rnd.commit,
            rnd.seal_note,
            rnd.manifest,
            qs,
            not_asked,
            sel,
            answers,
            verdicts,
            withheld,
            found,
            self.cfg.reviewer_name,
        )
        mid = self.t.post(self.cfg.shared, encode(line, obj))
        self.log(f"reviewer-agent posted brief {mid}: {line}")
        for c in obj["coverage"]:
            self.log(f"  coverage {c['line']}")
