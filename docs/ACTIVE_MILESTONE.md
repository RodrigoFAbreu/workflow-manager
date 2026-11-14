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
