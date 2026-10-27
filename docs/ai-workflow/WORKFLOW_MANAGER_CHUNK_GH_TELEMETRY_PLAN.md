# Workflow Manager: Quiet gh Telemetry in the Test Chunks (Revision 2)

`work_item_id: chunk-gh-telemetry` -- `governing_workflow_version: "2.2"`

**Deliverable:** the per-chunk environment of the test runner turns the `gh`
CLI's background telemetry off (`GH_TELEMETRY=false`, `DO_NOT_TRACK=1`), so a
frozen Workflow suite that runs the real `gh` no longer leaves a detached
`gh send-telemetry` process behind for the orphan check to reject.

**Work item type:** `process`. **Base commit:** `184682b` (tip of `main`;
Workflow 2.22.0 installed, automatic gates). **Branch:**
`milestone/chunk-gh-telemetry`. **Scope source:** `docs/ROADMAP.md` row 18.
Tests and docs only (`tests/`, `docs/ARCHITECTURE.md`): the pull request title
is `test: ...`, which releases nothing (checked with `python3
tools/release/release.py check-title`). **Not in this milestone:** an orphan
exception (`orphan_sources` stays as it is), anything under `src/`, any other
change to the runner's behaviour, and any edit to a frozen Workflow suite (the
Workflow lane is told separately). One mechanism, two checkpoints (the sizing
rule's limits).

## 1. The problem

CI failed three times, and once on `main` (so the Release workflow was skipped
until a rerun), with `run_all: error[OrphanProcessError]:
frozen:<release>/<fixture>/workflow_state_completion_obligations_test.py#1: 1
orphaned process(es): 1 x /usr/bin/gh send-telemetry`. The frozen suites (the
retention tests of Workflow 2.20.0 to 2.22.0 and others) run the real `gh` on
the runner. `gh` 2.102.x starts a detached background `gh send-telemetry` that
outlives the chunk, and the orphan check (`orphan_sources` in
`tests/parallel/resources.json`) rejects it. It is intermittent (it passed on
rerun), and the local gate never shows it: the local `gh` has telemetry off or
never sends.

## 2. Decisions

**One mechanism: the chunk environment.** `isolation.chunk_env` builds the
environment every chunk process gets. It sets `GH_TELEMETRY=false` and
`DO_NOT_TRACK=1`. `gh` documents `GH_TELEMETRY` (`false` or `0`) as taking
precedence over `DO_NOT_TRACK`; both are set so a `gh` that reads only one is
quiet too. Nothing else about the environment changes.

**Where: with the other fixed settings, before the extras.** The two
assignments sit beside `PYTHONDONTWRITEBYTECODE`/`PYTHON_COLORS`/`TMPDIR`,
before `env.update(extra)`. Two consequences, both intended:

* An inherited value never wins. A parent shell or a CI runner that exports
  `GH_TELEMETRY=true` (or `DO_NOT_TRACK=0`) still gets a quiet chunk: the
  point is that no chunk sends telemetry, whatever the machine does.
* An explicit caller value may override. `extra` is the caller's deliberate
  per-call setting and already overrides the fixed variables above it. The extras
  the runner passes are phase B's `extra_env` (`phase_b_env()`: the records and
  context paths, `tests/parallel/executor.py`) through `run_one` ->
  `isolation.run_chunk` -> `chunk_env`; `prepare_merge` passes the Git template
  alone. None names either variable, so no run can turn telemetry back on by
  accident, and a test that wants the real behaviour can say so.

**Docs.** `docs/ARCHITECTURE.md`'s "Verification execution" describes the
chunk's Git discovery ceiling and the orphan check but does not list the
chunk environment. It gets one bullet next to the ceiling bullet: a chunk runs
with `gh` telemetry off, why (the orphan check), and that an orphan exception
is not the remedy. The page names no internal milestone id.

## 3. Tests

All hermetic: no network, no real `gh`, no process left behind. **No test's
outcome depends on whether the outer environment has telemetry off.** From CP1
on, every host test runs in a chunk whose `os.environ` already holds
`GH_TELEMETRY=false` and `DO_NOT_TRACK=1`, and a developer or CI machine may
export them too, so a test that reads its base from `os.environ` cannot tell
the change from the inheritance. The new class therefore builds its base with a
helper, `_telemetry_free_env()` (the `stripped_env()` result with `GH_TELEMETRY`
and `DO_NOT_TRACK` removed), and every test below starts from it or sets the
hostile values explicitly. The stub `gh`
is a small shell script in a scratch directory put first on `PATH`; it appends
`GH_TELEMETRY` and `DO_NOT_TRACK` to a log file and, as the real one does when
telemetry is not disabled (`GH_TELEMETRY` of `false` or `0`, or `DO_NOT_TRACK`
of `1` or `true` when `GH_TELEMETRY` is unset), writes a `sent` marker file
instead of starting a process, so nothing can be orphaned by the test itself.

`tests/test_orphan_processes.py`, new class `TestChunkEnvGhTelemetry` (the
pattern of `TestChunkEnvGitConfig`, its `stripped_env`/`_Tmp` helpers). Each
test below fails at `184682b`:

* `test_both_variables_are_set`: from `_telemetry_free_env()` (a base without
  either), the chunk environment has `GH_TELEMETRY == "false"` and `DO_NOT_TRACK == "1"`.
* `test_an_inherited_value_is_overridden`: a base with `GH_TELEMETRY=true`
  and `DO_NOT_TRACK=0` still yields the quiet values.
* `test_an_explicit_extra_overrides`: `extra={"GH_TELEMETRY": "true"}` wins
  (the documented order), and the other variable stays quiet.
* `test_nothing_else_changes`: over a `_telemetry_free_env()` base, the keys
  the chunk environment adds, and every changed value, are exactly the set that
  exists today plus the two new variables; every other entry of the base is
  byte-identical.
* `test_the_stub_gh_stays_quiet_under_the_chunk_environment`: the stub run
  under `chunk_env(...)` (over `_telemetry_free_env()`) records the two values
  and writes no `sent` marker.
* `test_the_stub_gh_sends_without_it`: the same stub under
  `_telemetry_free_env()` itself, not `stripped_env()`, writes the marker. This
  control proves the stub detects the difference, so the previous test is not
  vacuous, and it stays green inside a chunk that already has telemetry off.

`tests/test_parallel_runner.py`, `test_the_chunk_environment_and_session`: the
chunk's recorded environment gains `GH_TELEMETRY` and `DO_NOT_TRACK`, asserted
`false` and `1`, so the executor's real chunk process (not only the function)
is covered, with the existing `PYTHON_COLORS` and Git assertions unchanged. Its
`mock.patch.dict(os.environ, ...)` gains the hostile `GH_TELEMETRY: "true"` and
`DO_NOT_TRACK: "0"` beside the existing `PYTHONPATH`/`FORCE_COLOR`/
`GIT_TEMPLATE_DIR`, so the assertions prove the override in the spawned chunk
whatever the outer environment holds: they fail when the two assignments are
removed from `chunk_env`, even with `GH_TELEMETRY=false` exported in the outer
shell.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Quiet gh telemetry in the chunk environment, with tests | - | 1 | 1 |
| CP2 | Architecture note and bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the chunk environment and its tests

**Files:** `tests/parallel/isolation.py`, `tests/test_orphan_processes.py`, `tests/test_parallel_runner.py`.

Section 2 ("One mechanism", "Where") and section 3. `isolation.chunk_env`:
the two assignments and the docstring sentence naming them; nothing else in
the function moves. The new test class and the extended executor test as in
section 3.

Evidence: the new tests fail first at `184682b` and are green after;
`python3 tests/run_all.py --select test_orphan_processes.py` and `--select
test_parallel_runner.py` green; a scratch run of the chunk environment with
the stub `gh` on `PATH` (no network) shows the quiet values and no marker,
and the plain environment shows the marker; the full gate `python3
tests/run_all.py` green, with the stub control green inside a chunk that
already has telemetry off; the executor test, with the two assignments removed
from `chunk_env`, fails even with `GH_TELEMETRY=false` exported in the outer
shell.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- architecture note and bookkeeping

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

`docs/ARCHITECTURE.md`: the bullet of section 2 ("Docs"). Row 18 of
`docs/ROADMAP.md` is Current when the plan starts and Done at acceptance, and
`docs/ACTIVE_MILESTONE.md` records the milestone. No version is edited: a
`test:` title releases nothing.

`docs/ROADMAP.md` and `docs/ACTIVE_MILESTONE.md` stay excluded at both stages,
as in every item: the acceptance step writes them, so they are bookkeeping, not
a reviewed deliverable. `docs/ARCHITECTURE.md` and the three test files are
implementation-protected.

Evidence: `python3 tests/run_all.py --select test_docs.py` green (the
documentation checks); the full gate green.
<!-- /CP2 -->

## 5. Risks

* A `gh` that ignores both variables would still send. `GH_TELEMETRY` is the
  documented switch; `DO_NOT_TRACK` is the console-standard fallback. If a
  future `gh` still leaves a process, the orphan check will report it as it
  does today, and the response is a new item, not an exception here.
* The guarantee ends where the environment does. It reaches a `gh` that
  inherits `os.environ` (the 2.22.0 frozen suites build their children's
  environment as `os.environ` minus three Python keys). A child started with
  an allowlisted environment (`support.pinned_env`/`cli_env`,
  `tests/retention_recipe.py`) would drop the variables; none of those reaches
  the real `gh` today, and one that did would be a new item.
* The chunk is quiet for every program it starts, not only `gh`; nothing else
  in the suites reads either variable.
* The change is invisible to a machine whose `gh` never sent telemetry; the
  stub tests are what prove it, since the local gate cannot.

## 6. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
