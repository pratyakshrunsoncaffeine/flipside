@AGENTS.md

## Claude Code notes

- Pytest uses `--basetemp=.pytest-tmp` because the system temp folder is not writable on some Windows machines.
- Write Python edits with the Edit tool, not shell heredocs: Git Bash heredocs turned `\b` in regexes into backspace characters.
