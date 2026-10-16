# Moving this project into its own repository

This project was authored inside `agx01/agx01` (branch `claude/happy-mendel-sswq5r`, directory
`market-brain/`) because this session's GitHub App is scoped to that one repository and **cannot create
repositories** (`POST /user/repos` → `403 Resource not accessible by integration` — see
[docs/12](docs/12-environment-notes.md)). The target is a standalone `agx01/market-brain`.

Two ways to get there. Both keep the work; the first keeps its history.

## Option A — keep history (`git subtree split`)

```bash
# 1. On github.com, create an EMPTY private repo: agx01/market-brain
#    (no README, no .gitignore, no license — an empty repo)

# 2. In a clone of agx01/agx01
git fetch origin claude/happy-mendel-sswq5r
git checkout claude/happy-mendel-sswq5r

# 3. Split the subdirectory into its own branch, rewriting paths to the repo root
git subtree split --prefix=market-brain -b market-brain-root

# 4. Push that branch as the new repo's main
git push https://github.com/agx01/market-brain.git market-brain-root:main

# 5. Clone the new repo and work there from now on
cd ..
git clone https://github.com/agx01/market-brain.git
```

Commits that touched `market-brain/` keep their messages and dates, with paths rewritten so `docs/`
sits at the repository root.

## Option B — clean slate

```bash
# After creating the empty repo
mkdir market-brain && cd market-brain
git init -b main
cp -r /path/to/agx01/market-brain/. .
git add .
git commit -m "Initial import: design documentation for a Flowsint-based market research brain"
git remote add origin https://github.com/agx01/market-brain.git
git push -u origin main
```

## After the move

1. **Keep it private.** The vault will hold positions and reasoning
   ([docs/09](docs/09-security-and-secrets.md)).
2. **Add a `LICENSE`.** Our own code can be whatever you like; it is a separate work from Flowsint
   (Apache-2.0). If any upstream code is ever vendored, carry upstream's `LICENSE` and `NOTICE` with it
   ([docs/10](docs/10-compliance-and-ethics.md)).
3. **Add `.gitignore`** before any code lands: `.env`, `*.key`, `vault/private/`, `tools/cache/`,
   `tools/archive/`, `*.dump`, `__pycache__/`, `.venv/`.
4. **Remove `market-brain/` from `agx01/agx01`** so there is one copy:
   ```bash
   git rm -r market-brain && git commit -m "Move market-brain into its own repository"
   git push origin claude/happy-mendel-sswq5r
   ```
   (Or simply leave the branch unmerged — the profile repo's `main` was never touched.)
5. **Grant session access** to the new repo if a future Claude session should push to it: attach it to
   the session and confirm the Claude GitHub App has access to `agx01/market-brain`.
6. **Clone it where the notes should live.** On your Windows workstation, cloning into
   `...\Google Drive\My Drive\myclaudeproject\market-brain` gives version control plus device sync
   ([docs/12](docs/12-environment-notes.md)).

## Then start phase 1

Open questions Q1–Q6 in [docs/02 §6](docs/02-flowsint-primer.md#6-open-questions-to-resolve-in-phase-1)
are the first work, and [ADR-0003](docs/adr/0003-type-registration-strategy.md) is the one that gates
everything else: get a market type registered inside a running Flowsint, confirm it appears in the API
and the UI, and write one node with the expected label.
