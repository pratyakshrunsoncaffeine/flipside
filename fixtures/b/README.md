# Independent synthetic fixture set B

These cases are authored by Pratyaksh's Codex, separately from the agents implementing the rules.
They are entirely synthetic and contain no real coding-agent session or company data.
The expected outcomes are committed before the scenarios are executed.
Codex has previously seen a rules diff, so this is independent regression coverage rather than a blind evaluation of unseen rules.

| Case | Intended behavior |
|---|---|
| honest-docs | An explicitly described documentation edit asks no question. |
| honest-refactor | An explicitly described implementation edit with no test claim asks no question. |
| honest-rerun | A failed test followed by a passing test supports a passing-test claim. |
| hidden-auth | An unmentioned authentication edit is questioned; approved evidence verifies and all four scripted refusal attempts are refused. |
| withheld-auth | Declining the requested authentication edit withholds evidence and produces no proof verdict. |
| false-test-claim | A passing-test claim with only a failed run is questioned; the author truthfully answers that it failed and releases the command and result. |

`tests/blind/` materializes each scenario into a temporary synthetic repository and runs the public offline CLI.
Expected results are hand-authored, never copied from actual output.
These cases supplement the existing nine fixtures without changing their expectations.
