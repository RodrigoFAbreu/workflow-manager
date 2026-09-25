# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## Project summary

RepFlow is an offline-first Android workout tracker (Kotlin, Compose, Room,
Hilt) built as a layered architecture inside a single `:app` module. Preserve
that architecture and offline-first behavior; avoid unnecessary abstractions.

## Mandatory startup reading

Before any non-trivial work, per `AGENTS.md`, always read:

- `docs/ACTIVE_MILESTONE.md` — current state/checkpoint (ground truth, not
  inferred from plan text);
- `docs/ROADMAP.md` — milestone order and completion.

`AGENTS.md` and `.github/copilot-instructions.md` are the canonical rule
sources — follow them, don't re-derive them here.

## Conditional routing

Load only what the task actually needs:

- architecture/layer boundaries → `docs/adr/0003-layered-modular-architecture.md`
- Room/persistence/migrations/backup → `docs/adr/0002-offline-first-local-database-source-of-truth.md`
- domain terminology/business rules → `docs/DOMAIN_GLOSSARY.md`
- navigation/UI/interaction → `docs/UX_FLOWS.md`
- toolchain/dependency decisions, incl. "Open decisions" (do not silently
  finalize these) → `docs/TECHNICAL_DECISIONS.md`
- historical context on a completed feature → `docs/milestones/completed/`
- build/test/lint commands → `AGENTS.md`

Do not load `docs/agent-context/` or completed-milestone docs by default —
see `docs/ai-workflow/REVIEW_PROTOCOL.md` for the full context-efficiency
rules.

## Universal safety rules

- Preserve dependency direction: Domain → Application → Data/Infrastructure →
  Presentation. Domain stays pure Kotlin — no Android/AndroidX/Room/Hilt/
  coroutines imports.
- Never expose Room entities or DAOs outside `infrastructure`/`data`.
- Never use destructive Room migrations. Any schema change past version 1
  needs a version bump, an explicit `MIGRATION_x_y`, and a migration test.
- Persist enum values by stable string, never ordinal.
- Don't swallow `CancellationException`; no broad `catch` around suspend work.
- Backup/restore uses the versioned transfer schema
  (`BackupSnapshot`/`BackupJsonMapper`) — never serialize Room entities
  directly as the backup format.
- No network dependency during a workout — Room is the offline source of
  truth.
- No speculative abstractions, unused dependencies, or new Gradle modules
  without a concrete need.

## Semi-autonomous workflow gates

Milestone work follows the state machine in
`docs/ai-workflow/MILESTONE_WORKFLOW.md`. Claude works autonomously between
gates but must stop and wait at every hard gate that document names — see
its "Hard gates summary" for the current count and list, which changes as
the workflow evolves; do not hardcode a count here. Use the commands in
`.claude/commands/` to drive each state — do not skip a gate because the
diff looks small.

## Git restrictions

- Commits are normally prohibited. Only commit when a milestone command or
  prompt explicitly authorizes it after verification gates pass.
- Never push, merge, rebase, force-push, or open a pull request.
- Don't touch unrelated working-tree changes.

## Commands and detailed workflow docs

- Build/test/lint commands: `AGENTS.md`.
- Milestone state machine: `docs/ai-workflow/MILESTONE_WORKFLOW.md`.
- Review bundle mechanics and feedback format:
  `docs/ai-workflow/REVIEW_PROTOCOL.md`.
- Slash commands: `.claude/commands/` (`milestone-plan`, `apply-plan-review`,
  `milestone-implement`, `apply-implementation-review`, `approve-review`,
  `prepare-functional-review`, `apply-functional-review`,
  `accept-milestone`, `prepare-review`, `bootstrap-workflow-v2`,
  `record-manual-plan-review`, `review-plan`,
  `recover-implementation-provenance`, `review-implementation`,
  `review-functional`).
