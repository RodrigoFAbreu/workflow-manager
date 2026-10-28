# Active Milestone

## Milestone

`http-read-deadline` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 7, base `0314658`, branch `milestone/http-read-deadline`): roadmap row 15 (#50). A `fix:` pull request title (releases a patch when it merges and `main` is green). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_HTTP_READ_DEADLINE_PLAN.md`.

`_http_read` (`src/workflow_manager/source.py`) no longer runs a worker thread: the connection itself is bounded, so every send and receive on it, a proxy's `CONNECT` exchange included, is clamped to the time left and the socket is closed at the deadline.

Not in this milestone: closing the DNS-resolution residual (a second mechanism, its own item if the review asks for it).

### CP1: the bounded connection, its proof and the architecture note -- complete

- `src/workflow_manager/source.py`: `_Bounded`, the connector, the two connection classes and handlers, the simplified `_http_read`/`_http_fetch`.
- `tests/test_discovery.py`: the new test class and the mutation-proof cases.
- `docs/ARCHITECTURE.md`: the two sentences; `docs/ROADMAP.md` row 15 Current.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 15 is marked Done at acceptance. No version is edited.

### Self-review -- complete

- `src/workflow_manager/source.py`: the owned `connect()` tolerates an `ENOPROTOOPT` from `TCP_NODELAY`, as the base `connect()` does; `tests/test_discovery.py`: a case for it, and the audit-hook case records only during itself.
- Evidence: the fail-first run at `0314658` and the eight mutations of the plan's section 3, each failing the cases the plan names; the full gate (`python3 tests/run_all.py`) exited 0 at head `95228d1` (2320 of 2320 units, 15347 tests, orphan check on).

## Next action

The implementation bundle and the local implementation review.
