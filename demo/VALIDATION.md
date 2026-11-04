# Codex Windows baseline

Recorded 4 Nov 2026 IST against PR #2 base `f14aead` in an isolated worktree.
This records the baseline before the lead's pending Windows fixes.
No production files, fixture expectations or generated reports were edited.

| Check | Result |
|---|---|
| Existing source: ruff check and format | Pass, 55 files formatted |
| Existing source: mypy | Fails at `flipside/room/solo.py:275`: Windows has no `signal.SIGKILL` |
| Existing pytest suite with a usable temp directory | 303 passed, 9 failed |
| `python -m demo.run --all` | All 9 existing synthetic cases and both G8 checks pass |
| `python -m demo.run` | CSV-export and both G8 checks pass |
| New demo source: ruff check, format and strict mypy | Pass |

Reproduction after `uv sync --frozen`:

```text
uv run --frozen ruff check flipside tests docs/seal/example.py examples fixtures
uv run --frozen ruff format --check flipside tests docs/seal/example.py examples fixtures
uv run --frozen mypy
uv run --frozen pytest --basetemp=.pytest-tmp/codex-run2 --tb=short
uv run --frozen python -m demo.run --all --log demo/evidence/offline.log
uv run --frozen ruff check demo
uv run --frozen ruff format --check demo
uv run --frozen mypy demo/run.py
```

Create `.pytest-tmp/` before invoking pytest with that nested `--basetemp`.
Use a fresh final directory for each run.
The default host pytest temp root was inaccessible; that is separate from the nine product/test failures below.
Git Bash was on PATH for the board-tool tests.

The nine failures group as follows:

- Windows POSIX mode assertions or permission-check precedence: two daemon tests, two setup tests and `test_seal_commit_trailer_state_and_key_mode`.
- CRLF versus LF: `test_fixtures_regenerate_byte_for_byte`, `test_examples_regenerate_byte_for_byte` and `test_g3_example_reproduces_vector_byte_for_byte`.
- Session-builder newline expansion changes the expected byte-prefix length: `test_seal_from_session_with_partial_last_line`.

Actual local logs are in `demo/evidence/windows-baseline.log` and `demo/evidence/offline.log`.
These are ignored local artifacts, not published evidence.
The failures and reproduction commands were posted to Message Board issue #1 for the Windows and seal owners.
The broad Windows baseline is not green and has not been certified by a second passing run.
All demo cases use FakeSwitch; this does not establish the live second-machine gate.

## Upstream follow-up

Aarav fixed the SIGKILL typing issue and second-clone user handling in `7cf7cb1` on PR #2.
This worktree was advanced to that commit after the baseline above.
`uv run --frozen mypy` now passes across all 56 source files.
The demo's ruff, formatting and strict mypy checks still pass after that update.
The nine Windows test failures above were measured on `f14aead`; the full suite was not rerun on `7cf7cb1`.

On `7045ee1`, the full Windows suite was rerun: 304 passed, 12 failed in 198.17 seconds.
UTF-8/LF generation and the partial-session-length failure are fixed.
Six failures involve Windows permission/mode checks, three involve CRLF checkout bytes, and three involve random binary keys written through the Windows CRT in text mode.
The binary-key diagnosis was reproduced independently: writing 32 synthetic LF bytes through `_write_private` stores 64 bytes and `load_key` refuses it.
No key bytes were printed.
The seal owner received the reproduction on Message Board issue #1.
The actual rerun output is retained locally at `demo/evidence/windows-7045ee1.log`.
This does not certify the broad Windows or M4 clean-clone gate.

Aarav fixed binary private-file writes in `3bd2927` after receiving the reproduction.
The demo branch was advanced to that base, where ruff, formatting and mypy (default and win32) pass.
The default CSV demo and exact G8 proof checks pass on that base as well.
The full nine-case demo passed again on `7045ee1` before that update.

## Fresh clone on 3bd2927

A new remote clone on this Windows machine passed `uv sync --frozen`, ruff check and format, strict mypy (default and win32), both G8 proof checks, offline replay and all nine existing fixtures.
The full test suite had 309 passing tests and nine failures in 191.97 seconds.
Five failures concern Windows mode/permission checks; three compare CRLF checkout bytes with LF output.
The ninth is in `test_private_write_is_binary_and_keeps_lf_bytes`: its spy removes `0x8000` before calling the real `os.open`, which removes the actual binary flag on Windows.
Outside that spy, the synthetic 32-byte reproduction stores and loads exactly 32 bytes with the fixed production writer.
The seal owner received this test-only diagnosis; the lead was tagged for the mode and checkout issues.
Actual local output is at `demo/evidence/m4-clean-3bd2927.log`.
The full Windows and M4 gates remain open.
