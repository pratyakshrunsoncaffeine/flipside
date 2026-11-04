# Gate+ design

Gate+ is Ownership Gate with sealed evidence, run by two owners' agents in one Switch room.
Owner: the team lead. Propose changes on the board before editing the contracts in sections 4 and 5.

## 1. Trust split

The side that benefits from a check runs it.

- **gate-reviewer agent** (owned by the reviewer): polls GitHub, opens the room, computes gaps from public data (PR body, diff, CI, manifest), asks numbered questions, requests leaves by index, verifies proofs, computes coverage, posts the brief, pages the reviewer.
- **gate-author agent** (owned by the PR author): uploads the manifest, and after the author approves, posts disclosures made by `flip prove`.
- The session file and the seal key never leave the author's machine.

## 2. One PR, end to end

1. **Seal.** Before opening the PR the author runs `flip seal`: session to leaves to root; key saved under `.git/flipside/`; an empty commit carries the `Flipside-Seal:` trailer.
2. **Room.** The reviewer's agent sees the PR and the trailer, creates `#pr-<n>` from `templates/pr-room.yaml`, and invites the author and the gate-author agent.
3. **Manifest.** The gate-author agent uploads `manifest.json` as a room attachment (`POST /{agent_id}/rooms/{room_id}/media`). The reviewer's agent downloads it and checks its SHA-256 against the trailer.
4. **Gaps.** The reviewer's agent compares PR body, diff and CI with the manifest and posts numbered questions.
5. **Answers.** The author answers in their own words (`1: ...`). Only the author's answers count.
6. **Requests.** For each answer that leans on the session, the reviewer's agent names leaf indexes chosen from the manifest.
7. **Approve.** The author posts `approve 41 57` or `withhold 41`. A withheld leaf counts as withheld in coverage.
8. **Disclose.** The gate-author agent posts one disclosure per approved leaf.
9. **Verify.** The reviewer's agent runs the checks in section 5, then checks the claim against the disclosed bytes with `commands.py` and `contradictions.py`.
10. **Brief.** When every gap is answered and no contradiction stands, it posts the brief and pages the reviewer. A new head SHA starts a new round with a new seal.

The author can clear a scope gap by disclosing the prompt leaf that asked for the file. The reviewer's agent runs the `_mentioned` check on the disclosed text itself.

## 3. Seal construction

From the Flip Seal M1 spec, with fixes F1 to F6 below.

- **Read:** Claude Code session JSONL. Main-thread user and assistant lines, plus each sidechain (subagent) transcript as its own `session` index (F3).
- **Steps:** one per message. Assistant lines sharing `message.id` merge. Each tool result is its own step and inherits its call's tool names and files through `tool_use_id`.
- **Step text:** text blocks verbatim, then each tool call as `[tool Edit]` plus the canonical JSON of its input. A tool result's text is its text content; an image becomes `[image sha256:...]`. Thinking blocks are not sealed.
- **Files:** only from structured tool input (`file_path`, `notebook_path`, `path`), repo-relative POSIX; outside the repo becomes `<external>`.
- **Chunks:** NFC, CRLF to LF, at most 300 characters, cut at the last space or newline.
- **Leaf:** `{v, session, step, chunk, role, tools, files, text}` plus F2 and F6 fields.
- **Canonical JSON:** sorted keys, no spaces, UTF-8, integers and strings only.
- **Key:** `K` = 32 random bytes in `.git/flipside/<root>.key`, mode 0600, never sent.
- **Salt:** `HMAC-SHA256(K, b"flipside/salt/v1" + canonical_json([session, step, chunk]))`. Plain concatenation.
- **Leaf hash:** `SHA-256(0x00 + salt + canonical_json(leaf))`. **Node:** `SHA-256(0x01 + left + right)`.
- **Tree:** RFC 9162 §2.1.1: split at the largest power of two smaller than n; never duplicate the last leaf.
- **Manifest:** `canonical_json([leaf without text, plus i, for each leaf])`.
- **Trailer:** `Flipside-Seal: v1 root=<hex> n=<count> manifest=<sha256 hex>` on an empty commit (`git commit --allow-empty --trailer`, git 2.32+).

### Fixes to the M1 spec

| # | Problem | Fix |
|---|---|---|
| F1 | Claude Code keeps appending to the session after the seal, so a whole-file hash check fails on normal use. | Record the sealed byte length and the SHA-256 of that prefix. `flip prove` checks the prefix only. Confirm on a real session that earlier lines are never rewritten. |
| F2 | Bash edits tag no files, so coverage can falsely say "0 withheld". | Leaf field `mentions`: PR-changed paths that appear in the Bash command text. Coverage counts them. |
| F3 | Subagent edits are unsealed. | Seal each sidechain as another `session` index. |
| F4 | A large manifest does not fit in one chat message. | Upload it as a room attachment. |
| F5 | The author picks which leaf to show. | The reviewer's agent names leaf indexes. Refusals count as withheld. |
| F6 | The reviewer cannot see from the manifest which steps ran tests or whether they passed. | Leaf fields `cmd` (test, lint, build, other) and `ok` (true, false, null) on Bash steps. |

### Test vectors (key = 32 zero bytes, from the M1 spec, reproduced)

| Leaf | session, step, chunk | role | tools | files | text | L(i) prefix |
|---|---|---|---|---|---|---|
| 0 | 0, 0, 0 | user | [] | [] | `Add CSV export to the reports page.` | `07b90a6b3a1b` |
| 2 | 0, 2, 0 | tool_result | ["Bash"] | [] | `FAILED tests/test_export.py::test_export_csv - SessionExpired` | `2323720cacf6` |
| 4 | 0, 4, 0 | assistant | [] | [] | `CSV export works and the tests pass.` | `a12cd9883008` |

Salt for (0, 3, 0): `29c3111716183cdc4bf6fca921591cdf5a38bd767d8cab569875c964483aef2a`.
These vectors predate F2 and F6; leaves without those fields must still reproduce them, so add the new fields only where they apply.

## 4. Room messages

```text
seal        Flipside-Seal: v1 root=<hex> n=<n> manifest=<hex>   (+ manifest.json attachment)
request     **Show leaves** 41, 57  (commit <sha>)
approve     approve 41 57      |  withhold 41
disclosure  {"v":1,"commit":"<sha>","i":41,"n":212,"salt":"<hex>","leaf":{...},"proof":["<hex>", ...]}
verdict     OK leaf 41 (step 19, chunk 0) against seal <root7> in commit <sha7>
coverage    auth/session.py: 1 sealed step, 1 disclosed, 0 withheld; 2 Bash steps mention it
```

Requests and verdicts count only from the gate-reviewer agent. Answers and approvals count only from the PR author. Disclosures count only from the gate-author agent.

## 5. Verify, in order

| Code | Fails when |
|---|---|
| NO_SEAL | The named commit has no `Flipside-Seal:` trailer, or more than one. |
| WRONG_COMMIT | The disclosure names a different commit from the request. |
| NOT_IN_PR | The commit is not an ancestor of, or equal to, the PR head. |
| MANIFEST_HASH | SHA-256 of the manifest does not match the trailer. |
| MANIFEST_MISMATCH | The leaf's metadata differs from manifest entry i. |
| BAD_SIZE | i >= n, or the proof length is wrong for that index and size. |
| PROOF_FAIL | Hashing up from the leaf (RFC 9162 §2.1.3.2) does not reach the root. |

Author side: `flip prove` refuses with SESSION_CHANGED when the sealed prefix differs (F1).

## 6. Build plan and kill rules

| When (IST) | Work | Done when |
|---|---|---|
| Nov 4 evening | Docker and Switch up; two Switch users, one agent each | Each owner's agent posts one message in one room |
| Nov 5 morning | `ownership_gate/seal/` | Proofs verify for all sizes 1 to 256; single-bit flips give the right codes; test vectors reproduce; F1 to F3 tested |
| Nov 5 afternoon | Reviewer-side gaps from the manifest; request, approve, disclose flow; offline two-agent replay | `fixtures/honest` gives zero gaps; the CSV-export scenario gives one scope gap, cleared by one verified disclosure |
| Nov 6 | Live two-owner run; blind fixture set B; restart test on both sides | One real PR goes from seal to brief live |
| Nov 7 | Demo video, README, judge reproduction script | Submitted by 18:00 |

- Seal checks not green by Nov 5 18:00: ship Gate two-owner without Seal.
- No live Switch by Nov 5 18:00: ship the replay demo.

## 7. Limits

- A session forged before sealing is not caught.
- Work done outside the agent has no session evidence; the gate asks about it instead.
- The manifest reveals step count, roles, tool names, repo paths, chunk counts, and test pass or fail. Never text.
- Nobody can prove a human typed an answer.
