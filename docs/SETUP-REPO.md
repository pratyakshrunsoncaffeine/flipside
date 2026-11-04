# Repo setup (teammate)

This folder is ready to become the team repo.
It is not a git repository yet and has no GitHub remote.
The teammate creates both, so the lead's machine does not push anything first.

## 1. Get the folder

The lead sends this folder as a zip (or shares it any other way).
Before the first commit, delete local-only files if they came along:

```
rm -f killtests/.local-users.json
rm -rf .board __pycache__ killtests/__pycache__
```

`.gitignore` already excludes them, so a later `git add` will not pick them up.

## 2. Create the repo

```
git init -b main
git add .
git commit -m "Flipside: spec, build plan, kill tests, agent board"
gh repo create <owner>/flipside --private --source . --push
gh repo edit --add-topic flip-the-switch
```

Keep it private until submission; the hackathon needs it public by 7 Nov 23:59 IST (`gh repo edit --visibility public`).
Add the lead as a collaborator: `gh api -X PUT repos/<owner>/flipside/collaborators/kadoo69 -f permission=maintain`.

## 3. Pin the board

1. On GitHub: Issues, New issue, "Message board" template, submit, then Pin issue.
2. If it is not issue #1, every teammate runs `export BOARD_ISSUE=<number>` (add it to the shell profile).
3. Every teammate runs `gh auth login` once, then `tools/board whoami`.
4. First post: `tools/board post "[<Name>'s Claude] board is up, @all please run tools/board whoami"`.

## 4. Fill the team in

In `AGENTS.md`, replace `@<teammate-login>` and `<Teammate>` with the real login and name, in section 1 and in the owner table.
Commit that as the first PR, so the board hooks and owner table are live for every agent.

## 5. Check M0

- `tools/board whoami` works on both machines and one post round-trips.
- `make killtests` passes 9/9 on the lead's Mac (needs Switch Console running its local server).
- On Windows, Switch Console's local server may need WSL or Docker; the M3 and M4 gates can run on the lead's Mac, and the teammate's machine is the clean-clone check in M4.
