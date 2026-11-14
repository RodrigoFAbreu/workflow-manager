# Active Milestone

## Milestone

`retention-alert-json` -- implementing, self-review complete (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `84e6e3f`, branch `milestone/retention-alert-json`): roadmap row 45 (#220). A `feat:` pull request title (`feat: a machine-readable retention alert, doctor --retention --json`, Manager 1.20.0); the release-history row follows in a `docs:` pull request.

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

`retention-alert-json`, implementation revision 1, base `84e6e3f`, branch `milestone/retention-alert-json`. This section is committed by the checklist-evidence commit; that commit's SHA and blob are reported with the checklist, since a file cannot name its own commit.

**Automated verification is current.** The full gate `python3 tests/run_all.py` ran at `ab4eb07` (the code head): full selection, 2421/2421 units, 16315 tests, `verdict: exit 0` (`.ai-review/retention-alert-json/current/TEST_RESULTS.md`). Since `ab4eb07` only `docs/ai-workflow/WORKFLOW_STATE.json` has changed (`27dfc40`, `cf8fee9`), so nothing needs a rerun.

### Setup

- A checkout of `milestone/retention-alert-json` at its HEAD, with Python 3 (standard library) and `git`.
- Flows 1 to 9 need no network, no GitHub and no `claude`, `codex` or `ssh`. They read the clone and write nothing inside it; any copy goes to a scratch directory outside the clone.
- `docs/ROADMAP.md` row 45 is uncommitted in the working tree on purpose (the planning row, not a deliverable). Flows 1 and 6 are not sandbox flows: run them in that working tree only. A checkout of the committed head has six changed files in flow 1 and no row 45 in flow 6, which is expected, not a defect.
- `BASE` is `84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74`. Read exit codes with `; echo $?`, not through a pipe.

### Test data

- Flows 1 to 9: nothing to seed. Flow 5 builds its own 20 scenarios on a stub script.
- Flow 10: one managed scratch repository, with an adopted retention policy for 10b.

### Flows

Each flow says whether the automated tester can run it in the sandbox (offline, against the clone, with no forge or agent stand-ins).

**Flow 1: scope of the change.** Sandbox: no. It needs the working tree of the clone with the uncommitted `docs/ROADMAP.md` row 45; a committed-head sandbox shows six files, not seven (round 1: automated tester, no product defect).
- Do: `git diff --stat 84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74 -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'`
- Expect: seven files: `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention_alert_json.py` (new), `src/workflow_manager/cli.py`, `tests/test_retention_alert_json.py` (new), `docs/retention.md`, `docs/exit-codes.md`, `docs/ROADMAP.md` (one line, row 45).

**Flow 2: frozen paths unchanged.** Sandbox: yes.
- Do: `git diff --exit-code 84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74 -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/retention.py src/workflow_manager/retention_policy.py src/workflow_manager/retention_cleanup.py src/workflow_manager/retention_run.py README.md docs/README.md docs/verify.md; echo $?`
- Expect: no output, `0`.

**Flow 3: the stamps not moved.** Sandbox: yes.
- Do: `grep -n 'Last checked with' docs/retention.md docs/exit-codes.md`
- Expect: both read `Workflow Manager 1.18.1, Workflow 2.29.3`.

**Flow 4: the page names the document.** Sandbox: yes.
- Do: `grep -n -e retention_alert -e schema_version -e alert_key docs/retention.md`
- Expect: the section "The retention alert as JSON" (from line 179) names the `kind` value `retention_alert`, `schema_version`, `alert_key`, and the three `evaluation` values `evaluated`, `not_evaluated` and `not_applicable`.

**Flow 5: the text is unchanged.** Sandbox: yes, if the release it resolves is already cached. The preparer ran it outside the sandbox; the offline run is not checked.
- Do: extract the Python block under "Flow 5 driver" in `.ai-review/retention-alert-json/current/IMPLEMENTATION_SUMMARY.md` to `$D/driver.py`, with `D` a new scratch directory outside the clone, then:
  ```
  mkdir -p "$D/base" "$D/cand"
  git -C <checkout> archive 84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74 src tests tools | tar -x -C "$D/base"
  git -C <checkout> archive HEAD src tests tools | tar -x -C "$D/cand"
  TMPDIR="$D" python3 -I -B "$D/driver.py" "$D/base" > "$D/base.out"
  TMPDIR="$D" python3 -I -B "$D/driver.py" "$D/cand" > "$D/cand.out"
  diff "$D/base.out" "$D/cand.out"; echo $?
  ```
- Expect: both runs exit 0 with 1842 lines each; `diff` empty, `0`.

**Flow 6: the roadmap row.** Sandbox: no. Row 45 exists only as an uncommitted edit in the clone's working tree; a committed-head sandbox has no row 45 (round 1: automated tester, no product defect).
- Do: `grep -n -E '^\| 45 ' docs/ROADMAP.md; grep -c -E '^\| 46 ' docs/ROADMAP.md`
- Expect: row 45 present, its last cell `Current`; then `0`.

**Flow 7: the docs check.** Sandbox: yes.
- Do: `python3 tools/check_docs.py; echo $?`
- Expect: no problem line; `0`.

**Flow 8: the mutations are caught.** Sandbox: not checked. It runs the test modules once per mutation in a scratch copy, which is slow, so run it in the full environment.
- Do: in a scratch copy of the candidate, never the clone, apply one mutation at a time from plan section 3 (M1, M2, M4, M6, M9, M10) and run `python3 -B -m unittest test_retention_alert_json test_retention_alert test_doctor_cli` with `src` on the path, as the implementation summary did. Run the unmutated copy too.
- Expect: each mutation fails the set recorded in "Mutations (plan section 3), measured" in `.ai-review/retention-alert-json/current/IMPLEMENTATION_SUMMARY.md`; the unmutated copy passes all three modules.

**Flow 9: the release title.** Sandbox: yes.
- Do: `python3 tools/release/release.py check-title "feat: a machine-readable retention alert, doctor --retention --json"; echo $?`
- Expect: `valid title: feat, release impact minor`; `0`.

**Flow 10: the command on a managed repository.** Sandbox: no. It needs a managed target with the Workflow release installed and a policy adoption (10b); the sandbox has no such target. Use the candidate's CLI, `PYTHONPATH=<checkout>/src python3 -m workflow_manager`, in place of `workflow-manager`: the installed release has no `--json`.
- 10a, absent policy: a managed target with no `.workflow-manager/retention-policy.json`. Run `doctor <target> --retention --json; echo $?`. Expect exit `0` and stdout equal to the golden `J5-absent` in `tests/test_retention_alert_json.py`, with `repo` set to the target's absolute path: `kind` `retention_alert`, `schema_version` `1`, `policy` `{"state": "absent", "mode": "off", "digest": null}`, `evaluation` `not_applicable`, `alerts` `[]`, `snapshot` `null`.
- 10b, adopted policy: adopt the policy as `docs/retention.md`'s "Adopting it" says (the adoption writes `.workflow-manager/retention-adoption.json` and commits nothing), then run the same command. Expect exit `0`; `policy.state` `adopted`, `mode` `notify`, `digest` 64 hex characters; `evaluation` `evaluated` with `report_complete` `true` when the report is complete; one `alerts` entry per threshold the policy sets, in the order `finished_items`, `finished_folder_mib`, `finished_max_age_days`, `archives`, `prunable_archives`; each `alert_key` begins `retention:` and the target's absolute path.
- 10c, byte-stable: run 10b's command twice, saving stdout to two files; `cmp` them. Expect no difference.
- 10d, refused release option: `doctor <target> --retention --json --release-version 2.29.3; echo $?`. Expect exit `2`, empty stdout, one `error:` line on stderr naming `--release-version` and `--json`.
- 10e, `--json` alone: `doctor <target> --json; echo $?`. Expect exit `2` and empty stdout.
- 10f, nothing written: `git -C <target> status --porcelain` and `git -C <target> rev-parse HEAD` before 10a and after 10e. Expect the same output both times.

### Known limitations (by design)

- There is no `archived` or `deleted` state. The `snapshot` values are observed facts: an id entering or leaving `archived_and_removed`, or a fall in `archive_store`, is an observed change of uncertain cause (plan section 2.3). A Controller compares only two complete documents (`report_complete` true on both).
- `--json` skips the compatibility report. A Controller that also needs findings runs `doctor` without the flag.
- `alert_key` embeds the resolved repository path, so a moved repository is a new identity.
- `--release-version`, `--release-dir` and `--manager-root` are refused under `--json` (exit 2).
- Out of scope: the notification sender and scheduling (Controller lane), `prune`, the cleanup, any Workflow engine change, and the release-history row (a later `docs:` pull request).
- Optional findings from plan review and self-review get their recorded disposition at acceptance.

### Findings and next steps

- Write findings to `.ai-review/retention-alert-json/feedback/FUNCTIONAL_REVIEW.md` (`python3 scripts/workflow_fingerprint.py --resolve-feedback-path retention-alert-json` prints the path).
- Once testing is clean, `/accept-milestone` is the only acceptance command; both checkpoints (CP1, CP2) are COMPLETE. Findings go through `/apply-functional-review`.
