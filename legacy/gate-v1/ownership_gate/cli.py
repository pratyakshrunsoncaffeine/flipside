"""`ogate`: check a PR, play a scenario, replay a room log, or run live in Switch."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from ownership_gate import github
from ownership_gate.entire import load_session, load_transcript_file
from ownership_gate.events import EventLog, print_event, read_events
from ownership_gate.gaps import DEFAULT_MAX_LINES, find_gaps
from ownership_gate.scenario import load_pr, load_scenario, run_scenario


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.func(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ogate", description=__doc__)
    sub = parser.add_subparsers(required=True)

    check = sub.add_parser("check", help="print the gaps for one PR")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--pr-json", type=Path, help="PR as JSON (see fixtures/*/pr.json)")
    source.add_argument("--github", metavar="OWNER/REPO#N", help="fetch the PR from GitHub")
    check.add_argument("--transcript", type=Path, help="session full.jsonl to use")
    check.add_argument("--repo-dir", type=Path, default=Path(), help="repo with Entire checkpoints")
    check.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    check.set_defaults(func=_check)

    demo = sub.add_parser("demo", help="play a scenario folder offline")
    demo.add_argument("scenario", type=Path)
    demo.add_argument("--record", type=Path, help="write the room log here as JSONL")
    demo.set_defaults(func=_demo)

    replay = sub.add_parser("replay", help="print a recorded room log, or post it into Switch")
    replay.add_argument("events", type=Path)
    replay.add_argument("--room-id", help="post into this Switch room instead of printing")
    replay.set_defaults(func=_replay)

    run = sub.add_parser("run", help="run the author's gate agent live in Switch")
    run.add_argument("--repo", required=True, help="OWNER/REPO on GitHub")
    run.add_argument("--author", required=True, help="the author's GitHub login")
    run.add_argument("--chat-user", help="the author's chat username (default: --author)")
    run.add_argument("--reviewer-chat", default="", help="chat username to page when cleared")
    run.add_argument("--reviewer-agent", default="", help="optional reviewer agent to invite")
    run.add_argument("--repo-dir", type=Path, default=Path())
    run.add_argument("--poll-seconds", type=float, default=30.0)
    run.set_defaults(func=_run)
    return parser


def _check(args: argparse.Namespace) -> int:
    if args.pr_json:
        pr = load_pr(args.pr_json)
    else:
        repo, _, number = args.github.partition("#")
        pr = github.fetch_pull_request(repo, int(number))
    if args.transcript:
        session = load_transcript_file(args.transcript)
    else:
        session = load_session(args.repo_dir, pr.checkpoint_ids)
    report = find_gaps(pr, session, args.max_lines)
    print(f"{pr.key}: {pr.title}")
    print("trail: linked session" if report.has_trail else "trail: none (No trail badge)")
    for i, gap in enumerate(report.questions(), 1):
        cite = f" [step {gap.step}]" if gap.step else ""
        print(f"{i}. ({gap.kind}){cite} {gap.question}")
    extra = len(report.gaps) - len(report.questions())
    if extra > 0:
        print(f"... and {extra} more gap(s) beyond the question limit")
    if not report.gaps:
        print("no gaps")
    return 1 if report.gaps else 0


def _demo(args: argparse.Namespace) -> int:
    for event in run_scenario(load_scenario(args.scenario), EventLog(args.record)):
        print_event(event)
    return 0


def _replay(args: argparse.Namespace) -> int:
    events = read_events(args.events)
    if not args.room_id:
        for event in events:
            print_event(event)
        return 0
    agent = _switch_agent()
    for event in events:
        agent.post(args.room_id, f"**[{event.kind}] {event.actor}:** {event.text}")
    return 0


def _run(args: argparse.Namespace) -> int:
    from ownership_gate.live import LiveConfig, LiveGate

    config = LiveConfig(
        repo=args.repo,
        author=args.author,
        chat_user=args.chat_user or args.author,
        repo_dir=args.repo_dir,
        agent_name=os.environ["SWITCH_AGENT_NAME"],
        reviewer_chat=args.reviewer_chat,
        reviewer_agent=args.reviewer_agent,
        poll_seconds=args.poll_seconds,
    )
    LiveGate(config=config, agent=_switch_agent()).run()
    return 0


def _switch_agent():
    from ownership_gate.switch_client import SwitchAgent

    missing = [
        k for k in ("SWITCH_URL", "SWITCH_AGENT_ID", "SWITCH_AGENT_KEY") if k not in os.environ
    ]
    if missing:
        sys.exit(f"set {', '.join(missing)} (run scripts/register_agent.py first)")
    return SwitchAgent(
        base_url=os.environ["SWITCH_URL"].rstrip("/"),
        agent_id=os.environ["SWITCH_AGENT_ID"],
        api_key=os.environ["SWITCH_AGENT_KEY"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
