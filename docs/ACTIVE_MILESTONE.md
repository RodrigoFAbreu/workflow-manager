# Active Milestone

## Milestone

`age-alert-next-step` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 4, implementation revision 1, base `61e5b51`, branch `milestone/age-alert-next-step`): roadmap row 44 (#218). A `fix:` pull request title (`fix: the age alert's next step names an old finished item`, Manager 1.19.1); the release-history row follows in a `docs:` pull request.

When the age threshold is reached, the retention alert's `next:` step names the finished item `retention-cleanup` would plan first for the age rule (the oldest old item, beyond the 3 most recent, that the script can act on), not the first archivable item in report order. The count and size steps and `retention.next_step` are unchanged.

### CP1: the age step, the shared id rule, the example and the tests -- complete (`91ef442`)

- `retention_alert._age_step` walks the old items oldest first, keeps the plannable ids, and returns the first one-entry `retention.next_step` that names a command (so tracked, unreadable-archive and interrupted-removal items are passed over); with none left it returns the accurate `nothing to archive` text, never a young item.
- `plannable_id` (with `_ID` and `RESERVED_IDS`) moved from `retention_cleanup` to `retention_alert`; `retention_cleanup._eligible` calls it.
- `docs/retention.md`: the alert example is a complete report (no `not known` line); the `next:` bullet says what the age step names.
- Tests: `TestAgeStep` (N1 to N5, N8), `TestAgeStepEndToEnd` (N7), the page test (N6), and the adjusted `test_the_age_line_and_its_variants`.
- Narrow check: `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py` -- 45/45 units, 262 tests, `verdict: exit 0`; `tools/check_docs.py` clean; the byte-identical `git diff --exit-code` against the base is empty.

### Self-review -- complete (no defect found)

- Every mutation of plan section 3 (M1, M2, M4, M5, M6, M8, M9) measured in a scratch clone outside the repository with `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py`; each failing set, read from the unit logs (the runner's summary drops subtests), equals the table: M1 fails N1, N2 (archived, tracked, kept-recent, unknown-age, `runtime`, `Bad_ID`), N4, N5, N7, N8 and `test_the_age_line_and_its_variants`; M2 fails N1, N2 (archived) and the adjusted test; M4 fails N4; M5 fails N5 and N8; M6 fails N6; M8 fails N2 (tracked), N3 and N8 ((b), (d)); M9 fails N2 (`runtime`, `Bad_ID`). The unmutated clone passes (45/45 units, 262 tests). No test or table row needed a change.
- Absent-key golden: `describe`, `block`, `render`, the `retention` section and `preview_lines` for three key-less policies over three reports (mixed, incomplete, empty) at releases 2.25.0 and 2.20.0 are byte-identical between `61e5b51` and the candidate (228 lines).
- Full gate at `91ef442`: `python3 tests/run_all.py`, 2413/2413 units, 16282 tests, `verdict: exit 0`.

## Functional review checklist

Source: plan section 6 (`docs/ai-workflow/WORKFLOW_MANAGER_AGE_ALERT_NEXT_STEP_PLAN.md`), with flow 5's driver written out below. The committed content under review is the checklist-evidence commit reported at the gate; read it with `git show <commit>:docs/ACTIVE_MILESTONE.md`.

### Setup

1. Checkout the branch `milestone/age-alert-next-step` at the evidence commit. Base: `61e5b51051864f3ce242f09ce1105b3b8365c273`.
2. Work in a scratch directory outside the clone (`D=$(mktemp -d)`). Every flow below only reads the clone.
3. Automated gate: the full run at `91ef442` (2413/2413 units, 16282 tests, `verdict: exit 0`) still stands. Nothing under `src/`, `tests/` or `tools/` has changed since (`git diff --stat 91ef442 HEAD -- src tests tools` is empty).
4. Nothing in this checklist needs the network, GitHub, `gh`, `claude`, `codex` or `ssh`.

### Test data

No repository state is seeded. Flow 5 builds its own fixed reports: a mixed report (a young item first, then old items: one not archived, one archived, one with a tracked review folder; then a fresh item), an incomplete report (one young and one old item, `complete` false) and an empty report. It runs five policies (three key-less; two with `finished_max_age_days: 30`) at releases 2.25.0 and 2.20.0.

### Flows

Sandbox column: "offline" runs in the sandbox with no network and writes nothing inside the clone; "full" needs the release cache and the test runner.

1. `git diff --stat 61e5b51 -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'`. Expect exactly five files: `docs/ROADMAP.md`, `docs/retention.md`, `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention_cleanup.py`, `tests/test_retention_alert.py`. (offline)
2. `git diff --exit-code 61e5b51 -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/retention.py src/workflow_manager/retention_run.py src/workflow_manager/retention_policy.py docs/exit-codes.md docs/verify.md README.md docs/README.md; echo $?`. Expect no output and `0`. (offline)
3. `grep -n 'Last checked with' docs/retention.md`. Expect the stamp `Last checked with: Workflow Manager 1.18.1, Workflow 2.29.3.`, unmoved by this item. (offline)
4. `grep -n -e 'not known (the report is incomplete)' -e 'finished items: 12' docs/retention.md`. Expect exactly one line, `  finished items: 12, limit 10: reached` (line 165), and no `not known` line. (offline)
5. Driver, below. Expect: the key-less policies print identical output in both trees; the `diff` exits 1 only because of `alert:   next:` lines in the two age-key policies (`age-only`, `age-and-count`). The age step names the cleanup's first item: at `age-only`, mixed report, release 2.25.0, the alert names `remove old-b --apply`, the same item as preview item 1 of that run. At `age-and-count` the count step (`archive young`) comes first and the age step after it, joined by `; `. The `section:` lines are identical in both trees: the retention section's own `next:` stays in report order by design. (offline)
6. `grep -n -E '^\| 44 ' docs/ROADMAP.md; grep -c -E '^\| 45 ' docs/ROADMAP.md`. Expect row 44 present with last cell `Current`, then `0`. (offline)
7. In a scratch extraction of the evidence commit (`git archive <commit> | tar -x -C "$D/full"`), run `python3 -I -B tools/check_docs.py; echo $?`. Expect no problem line and `0`. (offline)
8. In a scratch copy, apply mutations M1, M4, M5, M8 and M9 from plan section 3, one at a time, and run `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py` for each. Each must fail exactly the set the plan's table gives; the unmutated copy passes 45/45 units and 262 tests. Run `python3 tests/run_all.py --list` first; a version the cache lacks is a `PrimingError` (exit 2). (full)
9. `python3 tools/release/release.py check-title "fix: the age alert's next step names an old finished item"; echo $?`. Expect `valid title: fix, release impact patch` and `0`. (offline)

Flow 5 driver. Save as `$D/driver.py`, then:

```
BASE=61e5b51051864f3ce242f09ce1105b3b8365c273
mkdir "$D/base" "$D/cand"
git -C <checkout> archive "$BASE" src tests tools | tar -x -C "$D/base"
git -C <checkout> archive HEAD src tests tools | tar -x -C "$D/cand"
python3 -I -B "$D/driver.py" "$D/base" > "$D/base.out"
python3 -I -B "$D/driver.py" "$D/cand" > "$D/cand.out"
diff "$D/base.out" "$D/cand.out"; echo $?
```

```python
"""Flow 5 driver: prints what the retention alert, policy block, report section
and cleanup preview print for key-less and age-key policies over fixed reports.
Usage: python3 -I -B driver.py <tree>   (<tree> holds src/ and tests/ of one revision)."""
import copy
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "tests"))
import test_retention_status as rs  # noqa: E402  (the fixture helpers)
from workflow_manager import retention, retention_alert as ra, retention_cleanup as rc  # noqa: E402
from workflow_manager import retention_policy as rp  # noqa: E402

TARGET = Path("/scratch/repo")
VERSIONS = ("2.25.0", "2.20.0")
OLD, YOUNG = "2026-01-01T00:00:00Z", "2026-10-26T00:00:00Z"


def entry(item, when, **kw):
    e = rs.finished(item, **kw)
    e["last_transition"] = when
    return e


def report(*entries, complete=True):
    rep = rs.report(*entries)
    rep["complete"] = complete
    rep["generated_at"] = "2026-10-27T00:00:00Z"
    return rep


def state(policy):
    mode = "notify"
    return rp.PolicyState(rp.ADOPTED, mode=mode, policy={"schema_version": 1, "mode": mode,
                          "thresholds": policy}, digest="ab" * 32)


POLICIES = {
    "key-less-a": {"finished_items": 2, "finished_folder_mib": 1, "archives": 3, "prunable_archives": 2},
    "key-less-b": {"finished_items": 1},
    "key-less-c": {"finished_items": 3, "finished_folder_mib": 1},
    "age-only": {"finished_max_age_days": 30},
    "age-and-count": {"finished_max_age_days": 30, "finished_items": 1},
}
REPORTS = {
    "mixed": report(entry("young", YOUNG), entry("old-a", OLD), entry("old-b", OLD, archive=True),
                    entry("old-c", OLD, tracked=1), entry("fresh", "2026-10-20T00:00:00Z")),
    "incomplete": report(entry("young", YOUNG), entry("old-a", OLD), complete=False),
    "empty": report(),
}

for pname, thresholds in POLICIES.items():
    for rname, rep in REPORTS.items():
        for version in VERSIONS:
            st = state(thresholds)
            print(f"== policy {pname} report {rname} release {version}")
            print("describe:", rp.describe(st.policy))
            for line in rp.block(st, TARGET):
                print("block:", line)
            results = ra.evaluate(st, copy.deepcopy(rep))
            for line in ra.render(st, results, copy.deepcopy(rep), version, TARGET):
                print("alert:", line)
            for line in retention.render(copy.deepcopy(rep), version, TARGET):
                print("section:", line)
            for line in rc.preview_lines(rc.select(st, copy.deepcopy(rep)), TARGET):
                print("preview:", line)
```

### Known limitations and out of scope

- `retention --retention` and its section `next:` keep report order (for example `archive young`). This is unchanged by design; it is not the alert's step.
- The age step follows the cleanup's first item on a complete report with no `removing`. The one real divergence is an unreadable oldest archive: the step then names the next old item the script can act on (plan 2.1, N8 (b)). The preview is not a promise; the engine judges each item again.
- When the count or size rule is also reached, the `next:` line can carry two steps joined with `; `. Each is a user-only command with a dry run.
- Not in this item: the JSON alert output (#220), any engine-script change, `prune`, the "Last checked" stamp (flow 3), and the singular wording of `finished older than 30 days: 1 items` (LIR1-002).
- Optional findings from the plan and implementation reviews are dispositioned at acceptance; `/accept-milestone` requires each to have one.

### Findings and next steps

- Place findings at `.ai-review/age-alert-next-step/feedback/FUNCTIONAL_REVIEW.md` (confirm with `python3 scripts/workflow_fingerprint.py --resolve-feedback-path age-alert-next-step`).
- Once testing is clean, `/accept-milestone` is the only acceptance command. Findings go through `/apply-functional-review`: bounded fixes return to the implementation-review gate; new or wider scope becomes a remediation child.
