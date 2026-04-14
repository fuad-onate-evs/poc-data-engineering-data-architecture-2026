# Contributing

## Workflow

1. Branch from `develop`: `git checkout -b feat/<card-shortlink>-<slug>`.
2. Make your changes. Run `uv run pre-commit run --all-files` locally before pushing.
3. Commit with [Conventional Commits](https://www.conventionalcommits.org/) format — the `conventional-pre-commit` hook will reject non-conforming messages.
4. Push and open a PR to `develop`. CI (`ci-dev-qa.yml`, `no-ai-attribution.yml`, `trello-pr-sync.yml`) must pass.
5. Get at least one reviewer approval, then squash-merge.

## No coding-agent attribution

Commits, pull request descriptions, and any tracked file content in this repository must not include attribution to coding agents or LLMs. This keeps commit history, blame, and the public repo free of vendor markers.

A gatekeeper enforces the rule in two places:

- **Locally**, via `.pre-commit-config.yaml` → `no-ai-attribution-content` (scans staged files) and `no-ai-attribution-commit-msg` (scans `COMMIT_EDITMSG`).
- **On GitHub**, via `.github/workflows/no-ai-attribution.yml` → scans the PR's changed files, commit messages, title, and body.

The scanner matches attribution *phrasing*, not bare filenames. Blocked phrasing categories:

- Git trailers crediting a named coding agent or generic automation.
- Verb-of-creation phrasing (generated / authored / written / created / produced / built) paired with a named coding agent or generic automation.
- `-assisted` suffix phrasing paired with a named coding agent or generic automation.
- Robot-emoji markers commonly appended by coding agents.
- Promo taglines naming a specific coding-agent product.
- Links to vendor signature URLs (e.g. hosted-chat or agent-product pages).

Allowed usage includes:

- Mentioning gitignored fallback filenames (e.g. `AGENTS.md`, `CLAUDE.md`) in `.gitignore` or docs describing the symlink convention.
- Technical library or module names that happen to contain the substring `ai` or `llm` (e.g. a hypothetical `ai_helpers.py` import path).
- Describing the no-attribution policy itself at a meta level (this document).

See [`scripts/hooks/check_no_ai_attribution.py`](scripts/hooks/check_no_ai_attribution.py) for the full pattern list.

### If the gatekeeper flags something you believe is a false positive

1. Rephrase the content neutrally (describe what was done, not who/what did it).
2. If the phrasing is genuinely unavoidable and contextual, open a PR modifying the pattern list rather than adding an allowlist entry — the rule is about phrasing, not filenames.

## Definition of Done

Per [`docs/poc-agile-plan-energy.md`](docs/poc-agile-plan-energy.md#dod--definition-of-done):

- [ ] PR reviewed and approved (>= 1 reviewer)
- [ ] CI green: lint, format, tests, gatekeeper
- [ ] Docs updated where behavior or surface area changed
- [ ] Deployed to staging (`develop` → qa)
- [ ] Data-quality checks pass on the affected tables
