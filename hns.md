# HNS

## Branch Sync Rule

- Before starting any task, sync with upstream: `git fetch origin` and rebase/pull from your tracking branch.
- Do not start implementation when local and remote histories are diverged.
- Verify sync explicitly: `git rev-list --left-right --count HEAD...@{u}` should be `0\t0` before edits.
