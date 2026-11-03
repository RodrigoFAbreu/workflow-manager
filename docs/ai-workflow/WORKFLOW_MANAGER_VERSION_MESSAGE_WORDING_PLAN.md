# Workflow Manager: A Version the Operator Did Not Type Is Named Correctly (Revision 2)

`work_item_id: version-message-wording` -- `governing_workflow_version: "2.2"`

**Deliverable:** a version the operator did not type -- the one the
installation record holds -- is named in words in the messages that quote it:
a null reads as `no workflow_version recorded`, an empty value as `''`, never
as a Python `None` or as nothing (roadmap row 26, issue #145 items 1 and 2;
item 3 is already fixed, section 1).

**Work item type:** `process`. **Base commit:** `10213e0`
(`10213e04d70a0da1129cbaa688b6660fbb6c79a4`, tip of `main`; Workflow 2.25.5
installed, automatic gates). **Branch:** `milestone/version-message-wording`.
**Scope source:** `docs/ROADMAP.md` row 26 (added by this item, Current now,
Done at acceptance). The pull request title is `fix: ...`, a **patch**
release (checked with `python3 tools/release/release.py check-title`). One
mechanism: *how a version taken from the record is named in a message*. Two
checkpoints, one review surface (three small `src/workflow_manager/` sites and
one test class). Sizing: far under 350 lines; no split needed.

## 1. Each item checked against main (`10213e0`)

| Item | Still present on main? | Evidence and decision |
| --- | --- | --- |
| #145 (1) `next:` line of `verify` / `status --release-version V` on a null record reads `a release directory holding None is needed ...` | Yes | `advice._directory_step`; probed with `advice.problem_step` and a null `installed_version`. **In scope.** |
| #145 (1) the `status` header reads `workflow None (full profile)` | Yes | `install.Status.__str__`, and the same line in `cli._print_record` (printed when the release cannot be resolved). **In scope**, both sites. |
| #145 (2) a record naming `""` prints `version: installed , release V` | Yes | `install.verify`. **In scope.** The same record also prints the header `workflow  (full profile)` (two spaces, no value) and `_directory_step` already quotes it; the header joins the item, one mechanism. |
| #145 (3) the `--release-dir` clause of `_not_a_version` interpolates the raw directory | **No, already fixed** | `advice._not_a_version` applies `shlex.quote` to the directory (commit `e5fa61f`, the code that rendered the command before it). The existing test `test_a_null_record_with_a_release_dir_names_one_step_without_it` builds its release directory as `root / "null release"` (a space) and asserts the quoted clause. **Dropped:** no change; one mutation at implementation confirms the existing test pins it (section 4). |
| #145 (4) `update` vs `update --dry-run` on a null record | Yes | A behaviour decision, **out of scope**; stays open on the issue. |
| Other messages that print a recorded version as-is | Yes | `AlreadyManagedError` (`install.py`, `workflow {v} is installed`) and the dry-run lines of `cli.cmd_update`. **Out of scope** (every other message, unchanged). |
| Workflow change | n/a | None. Exit codes unchanged. |

## 2. The wording (one rule)

A recorded version that is not text the operator typed is named by what it is:

| Site | Value | Before | After |
| --- | --- | --- | --- |
| `advice._directory_step` (the `next:` line) | null | `a release directory holding None is needed: run the command again with --release-dir DIR` | `a release directory is needed (no workflow_version recorded): run the command again with --release-dir DIR` |
| `Status.__str__`, `cli._print_record` (header) | null | `workflow None (full profile)` | `no workflow_version recorded (full profile)` |
| the same two | `""` | `workflow  (full profile)` | `workflow '' (full profile)` |
| `install.verify` (the `version:` line) | `""` | `version: installed , release V` | `version: installed '', release V` |

The suffix of the header (` — N problem(s):`, ` — clean`, ` — not verified ...`)
is unchanged. Every other value is untouched: `1.0.0`, a number such as `123`
(`holding 123`, `workflow 123`) and the existing null `version:` line
(`version: the installation record has no workflow_version, release V`) keep
their exact text, as does `_directory_step` for `""` (`holding ''`).

Implementation: one function in `src/workflow_manager/install.py`,
`record_head(version, profile) -> str`, builds the header for the three cases
and is used by `Status.__str__` and `cli._print_record` (no second copy of the
rule); `_directory_step` gets its null branch beside its existing empty one;
`verify` quotes the empty value as `_directory_step` does (`repr`).

`_directory_step` is also reached from `advice._repair_step` (a local-source
record whose version differs from `--release-dir`'s), so the null branch
changes that `next:` line too for a local record with a null version. That is
the same rule, not an extra change; the `_repair_step` case is covered by
the null-step unit case below.

## 3. Tests (`tests/test_operator_ux.py`, in the class holding the null-record cases)

Exact strings, before and after; no network, no release cache needed for the
unit cases.

* **A null record, in words** -- `advice.problem_step` with a null
  `installed_version` (recorded) returns exactly the null `next:` text of
  section 2; `str(install.Status(True, None, "full", ["p"], True))` and the
  line `cli._print_record` prints (captured, against a scratch record built by
  the class's `damaged(None)`) start with `no workflow_version recorded (full
  profile)`; `Python None` appears in none of them. End to end, `verify` and
  `status --release-version V` on `damaged(None)` print the `version:` line
  already pinned, then a `next:` line, and leave the tree digest unchanged.
  The two commands build the line differently, so each is asserted exactly:
  `verify` prints `next: ` and the step alone (`cli.cmd_verify`), i.e. `next: a
  release directory is needed (no workflow_version recorded): run the command
  again with --release-dir DIR`; `status` prints `next: ` and the step, `; `,
  then `advice.doctor_step(context)` (`cli.cmd_status`), i.e. `next: a release
  directory is needed (no workflow_version recorded): run the command again
  with --release-dir DIR; `workflow-manager doctor <repo>` reports what an
  update would meet`, with `<repo>` the target as the command renders it
  (the test builds the expected suffix from `advice.doctor_step` on the same
  context rather than retyping the path).
* **An empty value, quoted** -- the same three entry points for `damaged("")`, and the same two end-to-end
  commands (`verify`: the step alone; `status`: the step, `; `, the doctor
  step, with the step unchanged `holding ''`):
  `version: installed '', release V`, the header `workflow '' (full profile)`
  and `_directory_step`'s unchanged `holding ''`; the tree digest is unchanged.
* **Everything else byte-identical** -- `1.0.0` and `123` produce today's
  header and step (`workflow 1.0.0 (full profile)`, `workflow 123 (full
  profile)`, `holding 123`), pinned by exact strings.
* **Failure-only mutations** (restore the old text; each exits non-zero and
  fails the named case, and nothing else changes): (a) `_directory_step`'s null
  branch removed -- the null step case; (b) `record_head`'s null branch
  removed -- the null header case, in both `Status` and `_print_record`;
  (c) `record_head`'s empty branch removed -- the empty header case;
  (d) `verify` without the quoting -- the empty `version:` line case; (e)
  `_print_record` back to its own f-string -- the `_print_record` case only
  (proves the two sites share the rule); (f) the `shlex.quote` of
  `_not_a_version`'s directory removed -- the existing
  `test_a_null_record_with_a_release_dir_names_one_step_without_it` fails
  (item 3's pin, no new test).

No existing test pins the changed text (searched `tests/` and `docs/` for
`holding None`, `installed ,`, `workflow None`, `workflow  (`): no current test
or usage documentation shows the changed text (the only other hits are historical
records, `docs/ai-workflow/WORKFLOW_MANAGER_NULL_RECORD_WORDING_PLAN.md` and
`docs/milestones/completed/null-record-wording-findings.md`, which stay
unchanged); the unchanged `holding 123` and `has no workflow_version` assertions of
`tests/test_operator_ux_readonly.py` and `tests/test_discovery.py` stay green
and are not edited. No current docs page shows the changed text, so none changes.

Evidence at implementation (implementation validation, not a functional-review
flow: it needs the Workflow release cache or network, because `run_all.py`
primes every tested release and the selected suite builds fixtures from the
newest pinned one): `python3 tests/run_all.py --select test_operator_ux.py`
green, each mutation failing the case named, then `python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The wording, its function and its tests | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the wording, its function and its tests

**Files:** `src/workflow_manager/install.py`, `src/workflow_manager/cli.py`,
`src/workflow_manager/advice.py`, `tests/test_operator_ux.py`.

Sections 2 and 3. `install.py` gets `record_head`, used by `Status.__str__`,
and quotes the empty value in `verify`; `cli.py`'s `_print_record` calls
`record_head`; `advice.py`'s `_directory_step` gets the null branch. No exit
code, option or other message changes.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 26 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: the `fix:` title releases a patch. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 5. Functional review

Every flow runs offline in a sandbox: no network, no `gh`, no installs, no
sockets, no zlib-ng, a small tmpfs, and **no Workflow release cache**. Every flow
below holds under those conditions; the test suite is not a flow (it needs the
release cache, section 3's implementation validation). No flow
bootstraps a release; flows 1 to 6 call the changed functions through
`python3 -I` with injected inputs, once against the base and once against the
candidate. Setup: `S=$(mktemp -d "$HOME/.cache/vmw-fr.XXXXXX"); mkdir -p $S/base $S/cand` (a named
scratch directory on disk, never `/tmp`, deleted with `rm -rf $S` when the
flows finish); `git archive
10213e0 src | tar -x -C $S/base`; `git archive <candidate head> src | tar -x -C
$S/cand`. The harness `$S/h.py`: `import sys,argparse;from pathlib import
Path;sys.path.insert(0,sys.argv[1]+"/src");from workflow_manager import
advice,install;exec(sys.argv[2])`, run as `python3 -I $S/h.py $S/<base|cand>
"<code>"`. Each flow is its own process, so the definition of `step` below is
written into `h.py` itself, after the `import` line and before the `exec`
(flows 1, 4 and 5 call it): `def step(v): return
advice.problem_step(advice.Context(args=argparse.Namespace(command="verify",
target=Path("/t"),release_version="2.12.0",release_source=None,release_cache=None,release_dir=None,profile=None),installed_version=v,installed_recorded=True),["version: x"])`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | code `print(step(None))` | candidate: `a release directory is needed (no workflow_version recorded): run the command again with --release-dir DIR`; base: `a release directory holding None is needed: ...` |
| 2 | code `print(install.Status(True,None,"full",["p"],True))` | candidate: first line `no workflow_version recorded (full profile) — 1 problem(s):`; base: `workflow None (full profile) — 1 problem(s):` |
| 3 | code `print(install.Status(True,"","full",[],True))` | candidate: `workflow '' (full profile) — clean`; base: `workflow  (full profile) — clean` |
| 4 | code `print(step(""))` | both: `a release directory holding '' is needed: run the command again with --release-dir DIR` (unchanged) |
| 5 | code `print(step(123));print(install.Status(True,123,"full",[],True));print(install.Status(True,"1.0.0","full",["p"],False))` | both: `a release directory holding 123 is needed: ...`, `workflow 123 (full profile) — clean`, `workflow 1.0.0 (full profile) — 1 problem(s):` (byte-identical) |
| 6 | (candidate only) code `print(install.record_head(None,"full"));print(install.record_head("","runtime"));print(install.record_head("2.12.0","full"))` | `no workflow_version recorded (full profile)`, `workflow '' (runtime profile)`, `workflow 2.12.0 (full profile)` |

## 6. Risks

* `record_head` is public in `install.py`; `Status.__str__` and
  `_print_record` are the only callers, and a test (mutation (e)) proves the
  second one uses it.
* A Workflow release whose manifest carries a null or empty version still
  installs a record that the `update` path rejects; this item changes only
  how the messages name it.
* `workflow_version` of a type other than text, null or empty (a number)
  keeps its present text on purpose: widening is a later item if wanted.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
