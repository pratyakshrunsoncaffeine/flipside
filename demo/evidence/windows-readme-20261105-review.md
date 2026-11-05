# Windows README judge walkthrough

Date: 5 Nov 2026 IST.
Tested source: main `05fa751d7e06ea8f2c45439ac173d67e7a27bfc7` in a fresh remote clone.
README SHA-256: `d2302698fa3697a178fbaa31ce90e29927f9f546ff039b20998bd2ec532e62e6`.
The README is unchanged from `04db28d`; the later source includes the merged UTF-8 stdio fix.
No README, product code or fixture expectations were edited for this walkthrough.

## Results

| README command | Result |
|---|---|
| `uv sync --frozen` | Exit 0 |
| `uv run --frozen ruff check flipside tests docs/seal/example.py examples fixtures` | Exit 0 |
| `uv run --frozen ruff format --check flipside tests docs/seal/example.py examples fixtures` | Exit 0 |
| `uv run --frozen mypy` | Exit 0 |
| `uv run --frozen pytest` | Exit 1: 87 passed, 2 skipped, 265 setup errors from the existing host temporary-directory ACL |
| Documented fallback: `uv run --frozen pytest --basetemp=C:/t/codexREADME27-2` | Exit 0: 352 passed, 2 skipped in 172.09 seconds |
| Original G8 verify command | `OK`, exit 0 |
| Forged G8 verify command followed by `$LASTEXITCODE` | `PROOF_FAIL`, printed exit 2 |
| `uv run --frozen python -m flipside.cli replay --offline` | Exit 0, four modeled refusals, zero duplicate posts |
| `uv run --frozen python -m flipside.cli replay --fixtures` | Exit 0, 9/9 fixtures match |

The failed default pytest command reports `PermissionError: [WinError 5] Access is denied` for the host's existing `%TEMP%/pytest-of-surya` directory.
The successful fallback uses the README's documented short temporary-directory option with a fresh directory, rather than overwriting another run's folder.
This is a host prerequisite finding, not a claim that the default command passed.
The walkthrough stopped before the live Switch block as requested.
No Switch credentials, env-file contents or live endpoint were used.

The final transcript is [windows-readme-20261105T104155-published.log](windows-readme-20261105T104155-published.log).
It contains native output and exit codes, with four credential-shaped synthetic secret-scan test labels redacted and line endings normalized to LF.
The raw capture remains local and unmodified.
The earlier capture that missed native output remains local and is not published as gate evidence.

## Backing files and written-material judge

[The path audit](backing-paths-05fa751.json) resolves all 64 concrete quoted repository paths and relative links found in README and VERIFICATION; no referenced file was missing.
File existence does not by itself prove every semantic claim.
Historical make/macOS/live commands in VERIFICATION were reviewed as scoped historical records, not re-executed as Windows offline commands.

A fresh-context Codex judge read only `head.txt`, this source's README and `single-tail.txt` before seeing any implementation.
The result is [codex-final-20261105T1035.out](https://github.com/pratyakshrunsoncaffeine/gateplus/blob/team-notes/docs/judging/blind/codex-final-20261105T1035.out): Switch 9, Technical 8, Creativity 9, Presentation 8; weighted TOTAL 8.6; shortlist yes.
Top deductions: no author/reviewer split across machines, awkward human participation through the gateway, and narrow session/rule coverage with the acknowledged proof limits.
This is one written-material assessment, not a code or video review.
