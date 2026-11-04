"""Register the author's gate agent with Switch and print the env vars `ogate run` needs.

Usage: python scripts/register_agent.py --url http://localhost:8000 --name dana-gate

Reads the token from SWITCH_TOKEN: the author's personal API key (so the agent is owned
by the author) or, for a local test, AGENT_REGISTRATION_TOKEN from Switch's .env.
"""

from __future__ import annotations

import argparse
import os
import sys

from ownership_gate.switch_client import register

DESCRIPTION = (
    "Holds the owner's AI-written PRs until the owner answers gap questions; "
    "checks answers against the owner's local agent session."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--name", required=True, help="agent name, e.g. dana-gate")
    args = parser.parse_args()
    token = os.environ.get("SWITCH_TOKEN")
    if not token:
        sys.exit("set SWITCH_TOKEN to a personal API key or the registration token")
    created = register(args.url.rstrip("/"), token, args.name, DESCRIPTION)
    print(f"export SWITCH_URL={args.url}")
    print(f"export SWITCH_AGENT_NAME={args.name}")
    print(f"export SWITCH_AGENT_ID={created['id']}")
    print(f"export SWITCH_AGENT_KEY={created['api_key']}")
    print("# then set its addressing policy to owner in the Switch dashboard", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
