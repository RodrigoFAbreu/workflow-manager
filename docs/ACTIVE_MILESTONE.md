# Active Milestone

## Milestone

`retention-pins-and-title` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `72b8e56`, branch `milestone/retention-pins-and-title`): roadmap row 42 (#208, #211). A `test:` pull request title; no release follows.

Three tests pin wording that could drift (the `UNDO_WARNING` literal, the first per-item call of the cannot-start case, the help's exit-1 qualifier), and `docs/retention.md` has a title and `For:` line that cover the report, the policy, the alert and the cleanup. The #208.4 decision: `retention-run-mapping.json` stays as it is, a historical requirement record (KEEP).

### CP1: the three pins, the page header and roadmap row 42 -- complete

- Evidence: M1 to M3 each fail only their own test in a scratch copy; `tools/check_docs.py` exits 0; `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the base; the full gate on `f357c7a` ran 2406/2406 units, `verdict: exit 0`.
- Functional review: flows 1 to 8 passed at the approved content; the recorded Optional findings are dispositioned in `docs/ai-workflow/registry/retention-pins-and-title-dispositions.json` and listed in `docs/milestones/completed/retention-pins-and-title-findings.md`.

**Next action:** no incomplete milestone remains in `docs/ROADMAP.md` (row 42 is the last); run `/milestone-plan` once the owner names the next item. Follow-ups of this milestone: RodrigoFAbreu/workflow-manager#216.
