# Sessions

> Cross-session handoff archive. Each file captures **what was done in one working session**, the resulting state of the project, and the next-up priorities. The most recent session is at the top of the index — read it first when picking up the project.

## Index (newest first)

| Date | Session | Headline |
|---|---|---|
| 2026-04-11 | [LLM rename + write rename + Trello](2026-04-11-llm-write-trello.md) | Rewrote README, renamed `CLAUDE.md`→`LLM.md`, restructured `SESSION_UPDATE.md` into `sessions/`, renamed `ingestion/`→`write/`, built first-class Trello integration (4 use cases, 22 tests, GHA workflow, docs) |
| 2026-04-10 | [Bootstrap](2026-04-10-bootstrap.md) | Materialized scaffold from chat artifacts, set up uv project, wrote README + ONBOARDING + LLM.md, initialized git |

---

## Conventions

### Naming

```text
sessions/
├── README.md                           ← this index
└── YYYY-MM-DD-<slug>.md                ← one file per session
```

- **Date** is the session date in `YYYY-MM-DD` (lexicographic = chronological).
- **Slug** is a 1–3 word topic in kebab-case (`bootstrap`, `silver-models`, `dab-deploy`, `dq-checks`).
- If two sessions land on the same day, suffix with `-1`, `-2` (`2026-04-15-dq-checks-2.md`).

### Session file structure

Every session file should have these sections:

1. **Header** — date, session type, owner, repo link, link back to this index
2. **What this session did** — numbered list of concrete changes
3. **State at end of session** — what works now, what's installed, what's committed
4. **Next-up priorities** — what the next session should pick up first
5. **Open questions** — decisions deferred to the user / team
6. **Files to read first when resuming** — ordered list with one-line "why" each
7. **Resume command** — copy-paste shell snippet to get back into the dev loop

Keep sessions focused on **state changes and decisions**, not narration. Future readers (team members, LLMs, future-you) need to know what changed and why — not the play-by-play.

### Lifecycle

- **Create** a new session file at the start of any non-trivial working session
- **Update** it incrementally during the session (it's not a post-mortem)
- **Append** an entry to the index at the top when the session ends
- **Never delete** old sessions — they're the project's working memory
- **Cross-link** between sessions when one builds on another (`see [2026-04-10-bootstrap.md](2026-04-10-bootstrap.md) §3`)

### What belongs here vs other docs

| Location | Purpose | Lifetime |
|---|---|---|
| `sessions/` | Chronological log of *what was done when* | Permanent, append-only |
| [../LLM.md](../LLM.md) | Current architecture, conventions, Done/TODO | Mutable, always reflects HEAD |
| [../docs/ONBOARDING.md](../docs/ONBOARDING.md) | First-day team walkthrough | Stable, rarely changes |
| [../docs/poc-agile-plan-energy.md](../docs/poc-agile-plan-energy.md) | Sprint plan, ownership, SP | Stable through the sprint |
| [../README.md](../README.md) | Public-facing project overview | Stable, marketing-grade |

If you're tempted to put information in `sessions/` that's actually about the project's *current* state (not what changed), put it in `LLM.md` instead.

---

## Why this directory exists

LLM coding tools and human team members both need to ramp into a project quickly. A single `SESSION_UPDATE.md` overwritten each session loses history. A `sessions/` directory keeps every handoff readable in chronological order, so anyone resuming the project can:

1. Read the latest session file → know where things stand and what's next
2. Skim earlier sessions backward → understand *how* the project got here when something is unclear
3. Diff a file across two session timestamps → see how a decision evolved
