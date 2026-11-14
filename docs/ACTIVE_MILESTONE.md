# Active Milestone

## Milestone

`retention-alert-json` -- complete (accepted by policy) (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `84e6e3f`, branch `milestone/retention-alert-json`): roadmap row 45 (#220). A `feat:` pull request title (`feat: a machine-readable retention alert, doctor --retention --json`, Manager 1.20.0); the release-history row follows in a `docs:` pull request.

`workflow-manager doctor --retention TARGET --json` prints the retention alert as one byte-stable JSON document: per threshold the rule, threshold, current value, `reached`, a `state` of `reached`, `clear` or `unknown`, and an opaque `alert_key`; an explicit `evaluation` (`evaluated`, `not_evaluated`, `not_applicable`) that is never a false all-clear; and a `snapshot` of current facts a Controller compares between two complete documents, reading each difference as an observed change of uncertain cause (the Manager emits no `archived` or `deleted` state). It writes nothing, starts the script only after the policy gate, refuses the release options, skips the compatibility report and exits 0 whenever the document is printed.

### CP1: the assessment, the JSON document, the flag, and the tests -- complete (`7b6a5c1`)

- `retention_alert.assess` returns one `Assessment` (policy state, not-evaluated cause and step, results, report); `alert_lines` renders it, byte-identical to the base.
- `retention_alert_json.document`/`render`: the second renderer of the same assessment, with its own exception boundary.
- `cli.py`: `doctor --json` (only with `--retention`), `_doctor_json` (release options refused first, then not managed, the unparseable record, the cache or temporary directory check; destinations planned for the installed release only).
- Tests J1 to J8, D0, K1, E1, X1, W1, S1, P1, T1 in `tests/test_retention_alert_json.py`.

### CP2: the pages, the roadmap pin and the page tests -- complete (`6339962`)

- `docs/retention.md`: "The retention alert as JSON" (the document, the key and `evaluation` tables, `state`, the `alert_key` rule, why `archived` and `deleted` are not emitted and how to compare two snapshots, the exit rule); the "Exit status" sentence.
- `docs/exit-codes.md`: the two `doctor --retention --json` rows (0 and 2).
- Page tests D1.

### Self-review -- complete (three findings fixed)

- **Fixed (important):** the page documented the order of `alerts` as `finished_items`, `finished_folder_mib`, `archives`, `prunable_archives`, `finished_max_age_days`; the document follows `retention_policy.THRESHOLDS`, which puts `finished_max_age_days` third. The page now states the code's order, and a new page test (`test_D1_the_order_of_the_alerts_is_the_codes`) ties the sentence to `THRESHOLDS`.
- **Fixed:** plan section 7 says the page tells a consumer to ignore an unknown `state` value; it did not. One sentence added under `state`, pinned by D1.
- **Fixed:** plan section 3 makes J7 a whole-document golden, so M1 must fail it; the J7 tests asserted only snapshot fields and M1 did not fail them. `TestObservedChanges` now adopts a one-rule policy and its first pair compares the complete documents (`J7-before`, `J7-after`).
- Mutations M1 to M10 measured in a scratch copy outside the repository (`python3 -B -m unittest test_retention_alert_json test_retention_alert test_doctor_cli`): every claimed failing set of the plan's table fails; the measured sets and their extra failures are in the implementation summary. The unmutated copy passes.
- Flow 5 text golden: `verify`, `doctor` and `doctor --retention` text in 20 scenarios (J1 to J8) is byte-identical between `84e6e3f` and the candidate (60 runs, adoption times normalized).
- Narrow check: `python3 tests/run_all.py --select test_retention_alert_json.py --select test_retention_alert.py --select test_retention_status.py --select test_retention_cleanup.py --select test_doctor_cli.py --select test_docs.py --select test_operator_ux_docs.py`, `verdict: exit 0`; `python3 tools/check_docs.py` clean.

## Functional review checklist

`retention-alert-json`, implementation revision 1, base `84e6e3f`, branch `milestone/retention-alert-json`. This section is committed by the checklist-evidence commit; that commit's SHA and blob are reported with the checklist, since a file cannot name its own commit. It replaces the checklist committed at `9f51064` (blob `5a67b19`): a sandbox run of that one could not run flows 1, 5, 6, 8 and 10 as written.

**Automated verification is current.** The full gate `python3 tests/run_all.py` ran at `ab4eb07` (the code head): full selection, 2421/2421 units, 16315 tests, `verdict: exit 0` (`.ai-review/retention-alert-json/current/TEST_RESULTS.md`). Since `ab4eb07` only documentation and `docs/ai-workflow/WORKFLOW_STATE.json` have changed, so nothing needs a rerun.

### Setup

- **Sandbox checkout:** a clone of `milestone/retention-alert-json` at its committed HEAD, with a clean working tree. Flows marked *sandbox* run here, offline. No flow uses `gh`, `claude`, `codex` or `ssh`.
- **Working tree:** the clone you work in, with the uncommitted `docs/ROADMAP.md` row 45. That row is deliberate (a planning row, not a deliverable). Flows marked *manual* run here or in a full environment.
- Python 3 (standard library) and `git`. `S` is a scratch directory outside the clone, and a flow writes only there. Run Python with `-B`, so nothing is written into the clone.
- Flows 5 and 8 import `tests/support.py`, which reads the release cache for every tested Workflow release. A sandbox needs `WORKFLOW_MANAGER_RELEASE_CACHE` set to a primed cache (read only is enough; a full `python3 tests/run_all.py` primes it). Without it the import stops with a named error: an environment result, not a defect.
- `BASE` is `84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74`. Read exit codes with `; echo $?`, not through a pipe.

### Test data

- Sandbox flows: nothing to seed. Flow 5 builds its own 20 scenarios in the driver.
- Manual flows: flows 10a to 10c and 10f need one managed scratch repository with an adopted retention policy.

### Flows

Each flow is labelled **sandbox** (runs offline in the sandbox checkout) or **manual**. A sandbox run records a manual flow as not run; that is not a defect.

**Flow 1: scope of the committed change.** Sandbox: yes.
- Do (sandbox checkout): `git diff --name-status BASE HEAD -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'; echo $?`
- Expect: six paths: `M docs/exit-codes.md`, `M docs/retention.md`, `M src/workflow_manager/cli.py`, `M src/workflow_manager/retention_alert.py`, `A src/workflow_manager/retention_alert_json.py`, `A tests/test_retention_alert_json.py`; then `0`.
- Manual, working tree: the same with `HEAD` left out (`git diff --name-status BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'`). Expect the six paths and one more, `M docs/ROADMAP.md`, one line (row 45).

**Flow 2: frozen paths unchanged.** Sandbox: yes.
- Do: `git diff --exit-code BASE HEAD -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/retention.py src/workflow_manager/retention_policy.py src/workflow_manager/retention_cleanup.py src/workflow_manager/retention_run.py README.md docs/README.md docs/verify.md; echo $?`
- Expect: no output, `0`.

**Flow 3: the stamps not moved.** Sandbox: yes.
- Do: `grep -n 'Last checked with' docs/retention.md docs/exit-codes.md`
- Expect: both read `Workflow Manager 1.18.1, Workflow 2.29.3`.

**Flow 4: the page names the document.** Sandbox: yes.
- Do: `grep -n -e retention_alert -e schema_version -e alert_key docs/retention.md`
- Expect: the section "The retention alert as JSON" (line 179) names the `kind` value `retention_alert`, `schema_version`, `alert_key`, and the three `evaluation` values `evaluated`, `not_evaluated` and `not_applicable`.

**Flow 5: the text is unchanged.** Sandbox: yes, with `WORKFLOW_MANAGER_RELEASE_CACHE` set (see Setup).
- Do: save the driver below as `$S/driver.py`, outside the clone. With `C` the sandbox checkout and `BASE` as above:
  ```
  mkdir -p "$S/base" "$S/cand"
  git -C "$C" archive "$BASE" src tests tools | tar -x -C "$S/base"
  git -C "$C" archive HEAD src tests tools | tar -x -C "$S/cand"
  TMPDIR="$S" python3 -I -B "$S/driver.py" "$S/base" > "$S/base.out"; echo $?
  TMPDIR="$S" python3 -I -B "$S/driver.py" "$S/cand" > "$S/cand.out"; echo $?
  diff "$S/base.out" "$S/cand.out"; echo $?
  ```
- Expect: both runs exit `0` with 1842 lines each; `diff` empty, `0`.

Driver (`$S/driver.py`):

```python
"""Flow 5 driver: the text of `verify`, `doctor` and `doctor --retention` in every
J scenario of the plan, on the stub script, for one tree's `src`.
Usage: python3 -I -B driver.py <tree>   (<tree> holds src/ and tests/ of one revision)."""
import json
import re
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "tests"))
import support  # noqa: E402,F401
import test_retention_alert as tra  # noqa: E402
import test_retention_status as rs  # noqa: E402
from workflow_manager import retention_alert as ra, retention_policy as rp  # noqa: E402

assert Path(ra.__file__).resolve().is_relative_to(root), ra.__file__
MIB = 2**20
ALL_FIVE = {"schema_version": 1, "mode": "notify",
            "thresholds": {"finished_items": 2, "finished_folder_mib": 1, "archives": 3,
                           "prunable_archives": 2, "finished_max_age_days": 30}}
TWO = {"schema_version": 1, "mode": "notify", "thresholds": {"finished_items": 2, "archives": 3}}
FIVE = {"schema_version": 1, "mode": "notify", "thresholds": {"finished_items": 5, "archives": 3}}


def aged(*entries):
    return rs.report(*entries, generated_at=tra.GENERATED, kept_recent=[])


def reached():
    rep = aged(tra.old_entry("old-a"), tra.old_entry("old-b", when="2026-02-01T00:00:00Z"),
               tra.aged_entry("no-age", tra.MISSING), tra.aged_entry("young", tra.at(86400)))
    rep["totals"]["finished_folder_bytes"] = 3 * MIB + 5
    return rep


def j8(removing):
    rep = rs.report(rs.finished("x" * 64, folder=False, archive=True), *tra.entries(2))
    if removing is None:
        del rep["removing"]
    else:
        rep["removing"] = removing
    return rep


class Driver(tra.Base):
    def runTest(self):
        pass

    def shown(self, text):
        for path in sorted({str(self.repo.resolve()), str(self.repo), str(self.outside)}, key=len,
                           reverse=True):
            text = text.replace(path, "<REPO>" if "repo" in path or path.startswith(str(self.repo)) else "<OUT>")
        return re.sub(r"adopted [0-9]{4}-[0-9-]+T[0-9:]+Z", "adopted <TIME>", text)

    def scenario(self, name, rep, *, policy=ALL_FIVE, prepare=None, seam=ra.SCRIPT_OK, **env):
        for command, flag in (("verify", False), ("doctor", False), ("doctor", True)):
            self.install_stub()
            self.drop_policy()
            if policy is not None:
                self.adopt(policy)
            if prepare:
                prepare()
            got = self.call(command, rep, flag=flag, seam=seam, **env)
            print(f"=== {name} | {command}{' --retention' if flag else ''} | exit {got.code}")
            print(self.shown(got.out), end="")
            print("--- stderr")
            print(self.shown(got.err), end="")


d = Driver()
d.setUp()
try:
    d.scenario("J1 reached", reached())
    d.scenario("J2 clear", aged(tra.aged_entry("young", tra.at(86400))))
    d.scenario("J3 incomplete, one reached", rs.report(*tra.entries(3), complete=False), policy=TWO)
    d.scenario("J4 incomplete, nothing reached", rs.report(*tra.entries(1), complete=False), policy=FIVE)
    d.scenario("J5 absent", reached(), policy=None)
    d.scenario("J5 off", reached(), policy=dict(ALL_FIVE, mode="off"))
    d.scenario("J5 cleanup", reached(), policy=dict(ALL_FIVE, mode="cleanup"))
    d.scenario("J5 changed", reached(), prepare=lambda: rp.policy_path(d.repo).write_text(
        json.dumps(dict(ALL_FIVE, mode="both"))))
    d.scenario("J6 no script", reached(), prepare=lambda: (d.repo / rs.SCRIPT).unlink())
    d.scenario("J6 refusing", reached(), STUB_MODE="exit", STUB_EXIT="2",
               STUB_STDERR="error: no_origin: no origin\\nnext step: x")
    d.scenario("J6 malformed", "[1]", STUB_MODE="raw")
    d.scenario("J6 modified", reached(), seam=ra.SCRIPT_MODIFIED)
    d.scenario("J6 unchecked", reached(), seam=ra.SCRIPT_UNCHECKED)
    with mock.patch.object(ra, "evaluate", side_effect=ValueError("x")):
        d.scenario("J6 evaluate raises", reached())
    kept = tra.entries(3)
    d.scenario("J7 before", rs.report(rs.finished("gone", folder=True, archive=True), *kept))
    d.scenario("J7 after", rs.report(rs.finished("gone", folder=False, archive=True), *kept))
    d.scenario("J7 incomplete", rs.report(*tra.entries(3), complete=False))
    for label, removing in (("present", ["half-done", "x" * 64]), ("empty", []), ("null", None)):
        d.scenario(f"J8 {label}", j8(removing))
finally:
    d.tearDown()
```

**Flow 6: the roadmap row.** Sandbox: no (manual). Row 45 is an uncommitted edit in the working tree, so a sandbox checkout has no row 45. Not a defect there.
- Do (working tree): `grep -n -E '^\| 45 ' docs/ROADMAP.md; grep -c -E '^\| 46 ' docs/ROADMAP.md`
- Expect: row 45 present, its last cell `Current`; then the count `0`.

**Flow 7: the docs check.** Sandbox: yes.
- Do (sandbox checkout): `python3 -B tools/check_docs.py; echo $?`
- Expect: no problem line; `0`.

**Flow 8: the mutations are caught.** Sandbox: no (manual, full environment). It needs the measured sets in `.ai-review/retention-alert-json/current/IMPLEMENTATION_SUMMARY.md`, which is not in git, and it runs the test modules once per mutation, which is slow.
- Do: in a scratch copy of the candidate, never the clone, apply one mutation at a time from plan section 3 (M1, M2, M4, M6, M9, M10) and run `python3 -B -m unittest test_retention_alert_json test_retention_alert test_doctor_cli` in its `tests/` with `src` on the path, as the implementation summary did. Run the unmutated copy too.
- Expect: each mutation fails the set recorded in "Mutations (plan section 3), measured" in that summary; the unmutated copy passes all three modules.

**Flow 9: the release title.** Sandbox: yes.
- Do (sandbox checkout): `python3 -B tools/release/release.py check-title "feat: a machine-readable retention alert, doctor --retention --json"; echo $?`
- Expect: `valid title: feat, release impact minor`; `0`.

**Flow 10: the command on a managed repository.** Run the candidate's CLI, `PYTHONPATH=<checkout>/src python3 -B -m workflow_manager`, in place of `workflow-manager`: the installed release has no `--json`. Global options such as `--release-version` go before the command.

- **10d, refused release option (sandbox: yes; no target is read).** `PYTHONPATH=<sandbox checkout>/src python3 -B -m workflow_manager --release-version 2.29.3 doctor "$S/none" --retention --json; echo $?`. Expect exit `2`, empty stdout, one `error:` line on stderr naming `--release-version` and `--json`. (Placed after `doctor`, argparse rejects the option with `unrecognized arguments` instead; that is a usage error, not this refusal.)
- **10e, `--json` alone (sandbox: yes).** `PYTHONPATH=<sandbox checkout>/src python3 -B -m workflow_manager doctor "$S/none" --json; echo $?`. Expect exit `2` and empty stdout; stderr `--json is only valid with --retention`.
- **10a, absent policy (manual).** A managed target with no `.workflow-manager/retention-policy.json`. Run `... doctor <target> --retention --json; echo $?`. Expect exit `0` and stdout equal to the golden `J5-absent` in `tests/test_retention_alert_json.py`, with `repo` set to the target's absolute path: `kind` `retention_alert`, `schema_version` `1`, `policy` `{"state": "absent", "mode": "off", "digest": null}`, `evaluation` `not_applicable`, `alerts` `[]`, `snapshot` `null`.
- **10b, adopted policy (manual).** Adopt the policy as `docs/retention.md`'s "Adopting it" says (the adoption writes `.workflow-manager/retention-adoption.json` and commits nothing), then run the same command. Expect exit `0`; `policy.state` `adopted`, `mode` `notify`, `digest` 64 hex characters; `evaluation` `evaluated` with `report_complete` `true` when the report is complete; one `alerts` entry per threshold the policy sets, in the order `finished_items`, `finished_folder_mib`, `finished_max_age_days`, `archives`, `prunable_archives`; each `alert_key` begins `retention:` and the target's absolute path.
- **10c, byte-stable (manual).** Run 10b's command twice, saving stdout to two files; `cmp` them. Expect no difference.
- **10f, nothing written (manual).** `git -C <target> status --porcelain` and `git -C <target> rev-parse HEAD` before 10a and after 10e. Expect the same output both times.

### Known limitations (by design)

- There is no `archived` or `deleted` state. The `snapshot` values are observed facts: an id entering or leaving `archived_and_removed`, or a fall in `archive_store`, is an observed change of uncertain cause (plan section 2.3). A Controller compares only two complete documents (`report_complete` true on both).
- `--json` skips the compatibility report. A Controller that also needs findings runs `doctor` without the flag.
- `alert_key` embeds the resolved repository path, so a moved repository is a new identity.
- `--release-version`, `--release-dir` and `--manager-root` are refused under `--json` (exit 2).
- Out of scope: the notification sender and scheduling (Controller lane), `prune`, the cleanup, any Workflow engine change, and the release-history row (a later `docs:` pull request).
- Optional findings from plan review and self-review get their recorded disposition at acceptance.

**Next action:** `/milestone-plan` for the next incomplete milestone in `docs/ROADMAP.md`; none is listed after row 45 today. `retention-alert-json` is accepted by policy; its pull request #226 merges as `feat:` and Manager 1.20.0 follows the merge. The release-history row for 1.20.0 is a separate `docs:` pull request after the release.
