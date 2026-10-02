# Agent Instructions

## Installation and Setup

```bash
cp .env.example .env
# edit .env
docker compose up -d
```

## Checks

Before finishing a task, run `make check` and make sure it passes. Never commit with `--no-verify`.

## Conventions

- Branches: `<type>/<short-description>` (feat, fix, refactor, docs, test, chore, exp)
- PR: Draft while work is in progress; Ready for review when done
- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- All changes go through PR; do not push directly to `main`
- One PR — one branch — one change
