# Browser verifier gate

Open `site/verify.html` directly as a local file, or serve `site/` on localhost.
The page is self-contained and uses browser WebCrypto SHA-256 without packages, uploads, persistence or remote assets.
Use the synthetic sample to check `OK`, then the edited sample to check `PROOF_FAIL`.
For your own proof, provide the disclosure, the original public manifest bytes and an independently obtained `Flipside-Seal:` record.
Choosing a manifest file preserves its exact bytes; pasting is useful only if it preserves those same bytes.

The page checks disclosure shape, then manifest hash and canonical metadata, metadata equality, tree size and Merkle inclusion, in CLI order.
An `OK` is conditional on the seal record the user supplied.
It does not authenticate that record or run `NO_SEAL`, `WRONG_COMMIT` or `NOT_IN_PR`.
Run `flip verify --commit <question-commit> --head <pr-head> --manifest manifest.json disclosure.json` in the PR clone for all checks.
For a local bundle, add `--bundle seal.bundle`.
Earlier Git failures take precedence over the browser's checks in the full CLI.

Run `uv run --frozen pytest tests/blind/test_browser_verify.py` with Node 22+ on PATH.
This mandatory test extracts the actual `verify-core` script from the shipped HTML and executes it with Node WebCrypto; it never skips when Node is missing.
No npm dependencies or browser download is required.
The gate compares the real `flip verify` subprocess with every pinned `tests/vectors/*.json` case, both G8 examples, and ordered malformed, metadata, size and tamper cases.
Synthetic vector seals are put in a temporary Git commit so the CLI's Git checks pass before comparing browser-checkable verdict codes.
Additional coverage checks all leaves of balanced and uneven trees, exact manifest bytes, Unicode, arbitrary-size integer metadata, JSON floats and the embedded sample.
Node execution verifies page logic; it does not test browser rendering or a browser's file picker.
