# flip seal v1.1

This is the normative spec for `flip seal`, `flip prove` and `flip verify`.
It supersedes the v1 page (`flip-seal-spec.pdf`, `flip-seal-spec.html`), which stays as the visual explainer.
v1.1 adds the six fixes from the Gate-plus-Seal review (F1 to F6 below).
The v1 example hashes (root `50ab222b…`) are superseded, because the v1.1 leaf has more fields.
The v1.1 vectors are pinned in `tests/vectors/seal_v1_1.json` (root `05e8bcaa…`, manifest `3df385b6…`), reproduced by `docs/seal/example.py --json`.
The Clarifications section at the end is normative and settles cases the sections above leave open.

## Promise

A verified disclosure proves three things.
1. These exact bytes were in the author's agent session when it was sealed.
2. They belong to the step and chunk named, with the tools, files and test outcome the public manifest lists.
3. The seal sits in the commit the question named, so later edits and re-seals cannot change the answer.

It does not prove the session is genuine (a session forged before sealing is out of scope), that a quote fully answers a question, or that this session wrote the code.

## Inputs

- One Claude Code session: `~/.claude/projects/<project-dir>/<session-id>.jsonl`.
- Its subagent transcripts: `~/.claude/projects/<project-dir>/<session-id>/subagents/agent-*.jsonl` (F3).
- Large tool outputs that Claude Code stored beside the session: `<session-id>/tool-results/` (read when a tool result points to one).
- The repo, its PR base ref (`--base`, default `origin/main`), and the changed-file list `git diff --name-only <base>...HEAD`.

Codex sessions are out of scope for M1.

## Sessions

Session index 0 is the main JSONL.
Indexes 1..k are the subagent transcripts, sorted by the timestamp of their first line, then by file name.
Every leaf carries its `session` index.

## Steps

Read lines in file order.
Keep lines whose `type` is `user` or `assistant`.
Skip lines with `isMeta: true` and every other type (`api-request-blob`, summaries, attachments, snapshots).
In the main session, skip lines with `isSidechain: true`; their content is sealed from the subagent file instead.

A step is one message:
- assistant lines that share `message.id` merge into one step, in line order;
- a user line with string content, or with text blocks, is one `user` step;
- each `tool_result` block is its own `tool_result` step.

Step text:
- text blocks verbatim, joined with `\n`;
- each `tool_use` block as `[tool <name>] ` followed by the canonical JSON of its `input`;
- each `tool_result` as its text content, list items joined with `\n`; an image becomes `[image sha256:<hex>]`; a pointer to a stored tool-results file is replaced by that file's text.

`thinking` and `redacted_thinking` blocks are not sealed.

## Step metadata

| Field | Rule |
|---|---|
| `role` | `user`, `assistant` or `tool_result` |
| `tools` | Tool names called in the step, in order; a `tool_result` step names the tool of its `tool_use_id` |
| `files` | Paths from structured tool input only: `file_path`, `notebook_path`, `path`; repo-relative POSIX; outside the repo becomes `<external>`; a `tool_result` inherits the files of its call |
| `mentions` | F2. For Bash steps: every PR-changed path that appears as a substring of the command text; sorted; empty otherwise |
| `cmd` | F6. For Bash steps: `test`, `lint`, `build` or `other`, from the fixed table below; `null` otherwise |
| `ok` | F6. For a Bash `tool_result`: `true` unless the result has `is_error: true`; `null` when the call never ran (C14); `null` for every other step |

The `cmd` table is matched on the first command word of each shell segment after stripping env assignments, wrappers and `uv run`/`npx`/`python -m` (C15); the command's class is the highest of its segments:

| cmd | Commands |
|---|---|
| test | `pytest`, `unittest`, `go test`, `cargo test`, `make test`, `vitest`, `jest`; package scripts `test` or `test:*` (C15) |
| lint | `ruff`, `mypy`, `eslint`, `tsc --noEmit`, `flake8`, `black --check`, `make lint`; package scripts `lint` or `lint:*` (C15) |
| build | `cargo build`, `go build`, `make`, `docker build`; package scripts `build` or `build:*` (C15) |
| other | everything else |

A `tool_result` step copies `cmd` from its call.

## Chunks

Normalise the step text: CRLF to LF, then Unicode NFC.
Split it into chunks of at most 300 code points.
Cut after the last space or newline inside the window; if there is none, cut at 300.
An empty step text gives one empty chunk, so every step has a leaf.

## Leaves

```
leaf  = canonical_json({v:1, session, step, chunk, role, tools, files, mentions, cmd, ok, text})
salt  = HMAC-SHA256(K, "flipside/salt/v1" || canonical_json([session, step, chunk]))
L(i)  = SHA-256(0x00 || salt || leaf)
```

Canonical JSON: keys sorted, separators `,` and `:` with no spaces, UTF-8, `ensure_ascii` off.
Allowed values: strings, integers, booleans, null, lists, objects.
Floats are forbidden; the encoder raises on one.

`K` is 32 bytes from `os.urandom`, stored at `.git/flipside/<root>.key` with mode 0600.
It never leaves the author's machine.
Leaves are numbered `i = 0..n-1` in (session, step, chunk) order.

## Tree

RFC 9162 section 2.1.1, SHA-256.
`MTH` of one leaf is `L(0)`.
For `n > 1`, let `k` be the largest power of two below `n`; `MTH = SHA-256(0x01 || MTH(L[0:k]) || MTH(L[k:n]))`.
`n = 0` is an error (`EMPTY_SESSION`).
Inclusion proofs follow section 2.1.3.1; verification follows section 2.1.3.2.

## Manifest

The manifest is public and holds no text and no salts.

```
manifest = canonical_json([{i, v, session, step, chunk, role, tools, files, mentions, cmd, ok} for each leaf])
manifest_sha256 = SHA-256(manifest)
```

It reveals the step count, roles, tool names, repo-relative paths, chunk counts (length to the nearest 300 characters), command classes and test outcomes.

## Seal record

Two public records, made by different parties.

1. **git.** An empty commit on the PR branch:
   ```
   flipside: seal session

   Flipside-Seal: v1 root=<64 hex> n=<int> manifest=<64 hex>
   ```
   Made with `git commit --allow-empty --trailer` (git 2.32 or later).
   `--amend` adds the trailer to HEAD instead, only for an unpushed branch.
2. **Switch.** When the PR room opens, author-agent posts the seal line and uploads `manifest.json` as a room attachment (`POST /agents/{agent_id}/rooms/{room_id}/media`, multipart field `file`) (F4).
   Switch's message timestamp is the second, independent record.

Local state, never sent: `.git/flipside/<root>.json` with the session paths, and for each session file its sealed byte length and the SHA-256 of that prefix (F1).
Sealing cuts each file at the last complete line.

## Prove (author side)

`flip prove --root <hex> --leaf <i>` returns a disclosure:

```
{"v":1, "commit":"<sha>", "i":<int>, "n":<int>, "salt":"<hex>", "leaf":{…}, "proof":["<hex>", …]}
```

Before proving, it re-reads each session file's first `length` bytes and checks their SHA-256 (F1).
A mismatch refuses with `SESSION_CHANGED`.
Bytes appended after the seal are expected and ignored.

## Verify (reviewer side)

`flip verify --commit <sha> --head <sha> --manifest manifest.json disclosure.json` runs these checks in order and stops at the first failure.

| # | Code | Fails when |
|---|---|---|
| 0 | `BAD_DISCLOSURE` | The disclosure is not well formed (C4) |
| 1 | `NO_SEAL` | The named commit has no `Flipside-Seal:` trailer, or more than one (`git interpret-trailers --parse`) |
| 2 | `WRONG_COMMIT` | The disclosure names a commit other than the one the question named |
| 3 | `NOT_IN_PR` | The commit is not an ancestor of, or equal to, the PR head (`git merge-base --is-ancestor`) |
| 4 | `MANIFEST_HASH` | SHA-256 of the manifest bytes differs from the trailer |
| 5 | `MANIFEST_MISMATCH` | The leaf's fields, minus `text`, differ from manifest entry `i` |
| 6 | `BAD_SIZE` | `i >= n`, `n` differs from the trailer, or the proof length is wrong for `i` and `n` |
| 7 | `PROOF_FAIL` | Hashing up from `L(i)` does not reach the trailer root |

Success prints `OK leaf <i> (session <s>, step <t>, chunk <c>) against seal <root7> in commit <sha7>`.
Exit code 0 on OK, 2 on any refusal, 1 on usage or I/O errors.

## Coverage (reviewer side)

Computed from the manifest alone, by the side that benefits from it.
For a file F, the touching steps are those with F in `files` or `mentions`.
A step counts as disclosed when at least one of its leaves verified OK.
Every other touching step is not disclosed, whether nobody asked for it or the author declined it.
"Withheld" is used only for an author's decision (`withheld` message), never for coverage.
The line reads:

```
auth/session.py: 4 sealed steps, 1 disclosed, 3 not disclosed (steps 19, 23, 31); 2 by Bash mention
```

## Leaf selection (F5)

The reviewer's agent names the leaves it wants, from the manifest.
The author can approve or withhold each one.
A withheld leaf is posted as withheld; coverage counts its step as not disclosed.
The author may also offer extra leaves; they verify the same way.

## Threats

| Attack | Stopped by | Result |
|---|---|---|
| Edit a quote after sealing | Leaf hash and inclusion proof | `PROOF_FAIL` |
| Edit the session, re-seal, answer again | Question pins the seal commit | `WRONG_COMMIT` |
| Guess a short hidden chunk from sibling hashes | 256-bit HMAC salt per leaf | Needs the salt |
| Pass an inner node off as a leaf | `0x00` / `0x01` prefixes | `PROOF_FAIL` |
| Duplicate-last-leaf tricks | RFC 9162 split, `n` in the trailer | `BAD_SIZE` or `PROOF_FAIL` |
| Hide other steps on the same file | Public manifest, reviewer-side coverage, `mentions` | Undisclosed steps listed |
| Pick only flattering quotes | Reviewer names the leaves (F5) | Refusals counted |
| Hide subagent edits | Subagent transcripts sealed (F3) | Steps appear in the manifest |
| Backdate the seal | Switch room timestamp plus git push | Two records |
| Forge the session before sealing | Not stopped | Stated in Limits |

## Decisions

| ID | Chosen | Rejected, and why |
|---|---|---|
| D1 | One step per message; assistant blocks merge by `message.id` | One step per block splits reasoning from the edit it explains |
| D2 | Thinking not sealed | Often redacted or signed, and the most private part |
| D3 | 300 code points, cut at whitespace | Fixed windows cut words; sentence splitting is language-dependent |
| D4 | Metadata inside the leaf | Text-only leaves cannot back the file check |
| D5 | Salts from one key by HMAC | Per-leaf random salts mean thousands of secrets; no salt is guessable |
| D6 | RFC 9162 tree, SHA-256 | Duplicate-last-leaf trees have a known mutation bug (CVE-2012-2459) |
| D7 | Empty seal commit with a trailer | git notes are not pushed by default; amending rewrites pushed history |
| D8 | Manifest as a Switch attachment, hash in the trailer | Committing it adds a file to the PR the owning team merges |
| D9 | Verify against the question's commit | Verifying against HEAD lets a re-seal win |
| D10 | Python standard library only | A dependency in the verification path |
| D11 | Claude Code sessions only in M1 | Two parsers before one works end to end |
| D12 | Prefix check for `SESSION_CHANGED` (F1) | Whole-file hash fires on normal use, because Claude Code keeps appending |
| D13 | Reviewer names the leaves (F5) | Author-picked chunks invite cherry-picking |

## Clarifications (v1.1, settled 4 Nov 2026)

C1 to C4 were decided by the lead; C5 to C11 follow the most direct reading of the text above.
C14 and C15 (5 Nov 2026) fix false flags on honest PRs: a rejected test call was sealed as a failed run, and common test commands such as `npm run test` or `source .venv/bin/activate && pytest` were sealed as `other`.
All are implemented and tested in `flipside/seal/` and `tests/seal/`.

| ID | Case | Rule |
|---|---|---|
| C1 | A `tool_use` input holds a float (real sessions do, e.g. `scale: 0.6`) | Step text renders input as canonical JSON that also allows finite floats, in Python's shortest round-trip form. Leaves and the manifest still forbid floats |
| C2 | `mentions` on a Bash `tool_result` step | Copied from its call, like `files` and `cmd` |
| C3 | Several Bash calls in one assistant step | The step's `cmd` is the highest of test, lint, build, other. Each `tool_result` copies its own call's `cmd`. `python3 -m` and `python3.N -m` strip like `python -m` |
| C4 | A malformed disclosure | Check 0, `BAD_DISCLOSURE`, exit 2. Well formed: keys `v` (1), `commit` (40 lowercase hex), `i` and `n` (non-negative integers), `salt` (64 lowercase hex), `proof` (list of 64 lowercase hex), `leaf` (exactly the leaf keys, valid types, no floats). Other top-level keys, such as the room's `t` and `q`, are ignored |
| C5 | `cmd` launcher stripping | After `uv run` and `npx`, leading flags are skipped, with the value of a flag that takes one (`--project x`, `--with x`, `-p x`). `python` flags before `-m` are skipped the same way (`-X dev`, `-u`). The first word is compared by its basename, so `.venv/bin/pytest` is `pytest` |
| C6 | `files` order and relative paths | Order of first appearance in the step, without duplicates. A relative path resolves against the line's `cwd`; a relative or missing `cwd` resolves against the repo root. The repo root itself is `.` |
| C7 | Image blocks in user messages | Rendered like tool-result images: `[image sha256:<hex>]`, the hash of the base64-decoded bytes |
| C8 | A user line with text blocks and `tool_result` blocks | Block order: each `tool_result` is its own step; the text and image blocks form one `user` step placed at its first block |
| C9 | A `tool_result` with no matching `tool_use` | `tools`, `files` and `mentions` are empty; `cmd` and `ok` are null |
| C10 | Stored tool-results pointer | A tool-result text that starts with `<persisted-output>` and names `Full output saved to: <path>` is replaced by that file's text, only when the file is directly inside `<session-id>/tool-results/`. Prove re-checks those files' SHA-256 and refuses with `SESSION_CHANGED` on a change |
| C11 | Other block types; thinking-only messages | Block types other than text, tool_use, tool_result and image are not sealed. An assistant message with only thinking is still a step, with empty text and one empty chunk |
| C12 | Chunk window | The cut point is searched in the first 300 code points only, so no chunk exceeds 300. The v1 `example.py` searched 301 and could emit a 301-code-point chunk |
| C13 | Seal commit hygiene | `flip seal` refuses when the index has staged changes, so the seal commit stays empty |
| C14 | A Bash call that never ran: the user rejected or interrupted it, a permission rule or hook denied it, or its input was invalid | When `is_error` is true and the result's first text starts with `The user doesn't want to proceed`, `Permission to use`, `Permission for this`, `[Request interrupted`, `<tool_use_error>` or `PreToolUse:` (after leading whitespace), `ok` is `null`, not `false`. The leaf text is unchanged |
| C15 | Which command a Bash call runs | Segments: split at unquoted `&&`, `\|\|`, `;`, `\|`, `&`, `(`, `)` and newlines; heredoc bodies (`<<WORD` to a line `WORD`) are dropped; an unbalanced quote makes the whole command one segment. Wrappers stripped with their flags: `env`, `timeout` (and its duration), `time`, `nice`, `exec`, `command` (`command -v` is `other`). Package scripts: for `npm`, `pnpm`, `yarn` and `bun`, the script is the word after `run` or `run-script`; without `run`, it is the first word, except that `npm` runs only `test` and `t`. A script named `test`, `lint` or `build`, or starting with that name and `:`, has that class. Example: `ruff check . && npm run test:unit` is `test` |
