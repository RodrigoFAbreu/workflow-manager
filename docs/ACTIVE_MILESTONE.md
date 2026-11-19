# Active Milestone

## Milestone

**At functional review (round 2).** `unattended-retention-prune` (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `7e0ab69`, branch `milestone/unattended-retention-prune`): step A3 of issue #254. `workflow-manager retention-cleanup TARGET --unattended`, after its archive-and-remove phase, also prunes the archives the adopted unattended policy has aged out (`unattended.prune` true): class `finished` only, strictly older than `unattended.ttl_days`, only items whose review folder is already gone, never an id under an interrupted removal, at most `unattended.prune_max_per_run`, oldest first, and only after the engine's own dry run lists exactly the planned set.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_PRUNE_PLAN.md`.

Pull request title: `feat: prune old archives in the unattended retention run under the adopted unattended policy`.

### Checkpoints

- CP1 -- the prune selection, its plan digest and its two argv forms: **complete**. New pure module `retention_prune.py`: `select(report, unattended, policy_digest=)` returns a `PrunePlan` (ids oldest first by `(modified, id)`, cut at `prune_max_per_run`, `skipped` with `review-folder-present`, `removal-interrupted`, `unacceptable-id` or `age-not-known`, `capped`), reading `archives[]` defensively and selecting by `age_days > ttl_days` itself, never by the report's `prunable` flag; a missing `finished[]` entry fails closed as folder present; `prune_digest` is the sha256 of repository, policy digest, ttl and the ids in order; `argv_for` builds the dry-run form and the one-id apply form, each with `--ttl-days` and `--repo-root`, never `--archive-root`. Nothing calls it yet. Tests: `tests/test_retention_unattended_prune.py`.
- CP2 -- the prune phase: policy re-read, dry-run equivalence, per-id apply, audit lines: **complete**. `retention_prune.run_phase` re-reads the policy before the fresh report, the dry run and every apply (`retention_run.policy_holds`, extracted from `run`, with an `extra` predicate that `unattended.prune` is still true), selects, writes the `prune`/`started` line before any prune call, requires the engine's dry run to list exactly the planned ids (set comparison, `kind`, `mode`, `ttl_days`, empty `removed`), then applies one id per call and checks `result.removed` is exactly that id; the first failure stops it with one audit line (`prune` `failed`/`refused`/`interrupted`, or `policy` `stopped`/`interrupted`). `retention_run.run` gains a `closing` clause parameter (default: today's line); `retention_unattended.STEPS` gains `prune`. Nothing calls the phase yet.
- CP3 -- the unattended command runs the phase; the JSON document, text and exit codes: **complete**. `retention_unattended.run_command` runs the cleanup phase (with the `closing=""` clause when `unattended.prune` is true, so its closing line no longer says prune was not run) and then `retention_prune.run_phase` when prune is on and the cleanup did not stop, a nothing-to-do or nothing-eligible cleanup included (`_empty` is gone; the empty-run text is printed in the one flow). Exit code: the cleanup's own on its stop; a prune stop exits 1 when any cleanup call or a `prune --apply` was attempted, else 2. The document keeps `schema_version` 1 and gains `prune` (`enabled`, `outcome` `disabled`/`not-attempted`/`nothing-to-prune`/`done`/`stopped`, `ttl_days`, `max_per_run`, `plan_digest`, `ids`, `results`, `skipped`); `outcome` is `stopped` when either phase stopped and `stopped` names the first stop. Text: per-archive lines, the irreversibility and archive-store line when something was deleted, `nothing to prune` plus `skipped:` lines, the `audit:` line last. `cli.py`'s description and `--unattended` help carry the new wording and the exit-code clause; the help pin in `tests/test_retention_cleanup.py` moved with a needle that the old statements are gone.
- CP4 -- the status text, the docs and the ROADMAP row: **complete**. `retention_policy.enforcement_lines(unattended)` replaces the `NOT_ENFORCED` constant (one text for `status`, `doctor`, the adopt preview and the cleanup preview): with `prune` true two lines (what is enforced with `ttl_days`, `prune_max_per_run` and the limits; on its own line that deleting an archive cannot be undone and where the archive store is, `ARCHIVE_ROOT` now defined once in `retention_policy`), with `prune` false one line saying `unattended.prune` is false so no archive is pruned. The adopt help in `cli.py` says the unattended sentence prunes too only when `unattended.prune` is true. `docs/retention.md` replaces every statement that prune is not run unattended (items 1 to 3, 6 and 7 of plan section 2.6), adds "The unattended prune" (selection table, dry-run equivalence, safeguards, audit lines, text, `--json` `prune` section, exit status) and `docs/exit-codes.md` carries the exit-code extension. Row 52 of `docs/ROADMAP.md` is marked Done (the file stays uncommitted, as for earlier rows).

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended_prune.py`, 28 tests, `verdict: exit 0`. Mutations M1 to M9, M26, M27 and M28 of plan section 3 (on a scratch copy outside the repository, the module preloaded in place of the real one) each fail the named tests; the unmutated control passes. M8 (the report's `prunable` flag instead of `age_days`) fails the ttl test too.
- CP2: `python3 tests/run_all.py --select test_retention_unattended_prune.py` (61 tests, `verdict: exit 0`), and `--select` of `test_retention_run.py`, `test_retention_unattended_run.py`, `test_retention_unattended.py`, `test_retention_cleanup.py` and `test_retention_policy.py`, each `verdict: exit 0`. Mutations M10, M11, M12, M14, M15 and M16 (scratch copy, module preloaded) each fail the named tests.

- CP4: `--select` of `test_retention_unattended.py` (57 tests), `test_retention_policy.py` (87), `test_retention_cleanup.py` (69), `test_retention_run.py` (50), `test_retention_unattended_run.py` (86), `test_retention_unattended_prune.py` (86), `test_docs.py`, `test_operator_ux_docs.py`, `test_operator_ux.py`, `test_retention_status.py`, `test_retention_alert.py` and `test_retention_alert_json.py`, each `verdict: exit 0`. One mutation (the prune-false branch of `enforcement_lines` removed) fails `test_prune_false_says_so_in_every_state`; the unmutated control passes.
- CP3: `python3 tests/run_all.py --select test_retention_unattended_prune.py` (86 tests, `verdict: exit 0`), and `--select` of `test_retention_cleanup.py`, `test_retention_unattended_run.py`, `test_retention_run.py`, `test_retention_unattended.py` and `test_retention_policy.py`, each `verdict: exit 0`. Two mutations on the command (a prune stop always exiting 2; the cleanup closing line keeping "prune was not run") each fail the named tests; the unmutated control passes.

- Full gate, implementation revision 3 (`python3 tests/run_all.py` at `59b2c4e`, the last code commit): `verdict: exit 0`, 2491/2491 units, 16771 tests (`.ai-review/unattended-retention-prune/current/TEST_RESULTS.md`). Revision 1 (`862c8ec`) had 16769 tests. Since `59b2c4e` nothing under `src/`, `tests/` or `tools/` has changed; the commits after it change only `docs/ai-workflow/WORKFLOW_STATE.json`.

## Functional review checklist

Round 2: implementation revision 3, base `7e0ab69`, plan revision 5, head `59b2c4e`. The commit that carries this checklist changes only this file; the flows test the code at `59b2c4e`.

**What round 1 found, and what changed.** Round 1 (checklist tested at `1878aa5`) reported: flow 6 on `docs/retention.md:90` ("prune is never run"), fixed in `1b72add` with a regression test; flows 2 and 7, because the isolated checkout had no row 52 (the row is an uncommitted working-tree edit by design). The setup below copies that row into the scratch clone, which is the state those two flows expect. Implementation round 2 was REVISE (LIR2-001: `docs/retention.md` still said the unattended run adds "never new actions" although the prune phase is an added action; LIR2-002: its exit-status paragraph omitted the prune phase), fixed in `59b2c4e` with regression tests. Implementation round 3 is APPROVE from both reviewers (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`), and the technical approval is recorded by policy for `59b2c4e`.

**Already checked.** A scratch clone of `d9ade3f` (the same code as `59b2c4e`), built with the setup below and run with the sandbox limits (stand-ins, no network, scratch origin): flows 1 to 9 gave the expected result; flow 8 exited 2 with the named message and created no state directory. Flow 10: see the note under the table. The owner flows 11 to 13 are not run here.

### Setup (sandbox flows 1 to 10)

Never work in the product clone `P`. Build a scratch clone under `$HOME/.cache`:

```
S=$(mktemp -d "$HOME/.cache/up-fr.XXXXXX")
git clone -q --bare --no-hardlinks "$P" "$S/origin.git"        # scratch origin
git clone -q "$S/origin.git" "$S/cand"                          # the branch, at its head
command cp -f "$P/docs/ROADMAP.md" "$S/cand/docs/ROADMAP.md"   # row 52 is an uncommitted working-tree edit
mkdir -p "$S/bin" "$S/home" "$S/tmp" "$S/cache/workflow-manager"
for t in gh claude codex ssh; do   # refusing, logging stand-ins
  printf '#!/bin/sh\necho "%s $*" >> "%s/stand-in.log"\necho "stand-in: %s refused (sandbox)" >&2\nexit 1\n' "$t" "$S" "$t" > "$S/bin/$t"; chmod +x "$S/bin/$t"; done
command cp -a "$HOME/.cache/workflow-manager/releases" "$S/cache/workflow-manager/"   # primed release cache, about 770 MB
(cd "$S/cand" && python3 -m compileall -q src)                  # before any test runs
```

Run every flow from `$S/cand` with `env -i PATH=$S/bin:/usr/bin:/bin HOME=$S/home XDG_CACHE_HOME=$S/cache XDG_STATE_HOME=$S/state TMPDIR=$S/tmp PYTHONDONTWRITEBYTECODE=1`. Flow 10 also runs under `unshare -rn` (no network) with `--allow-root`, because `unshare` maps the caller to root. Afterwards `test ! -s "$S/stand-in.log"`: no flow reached a forge or an agent.

**Test data:** none. Each unit test builds its own scratch repository and a fake engine.

### Sandbox flows

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --name-status 7e0ab69 HEAD -- src tests tools .github .claude scripts .workflow-manager` | `A` `src/workflow_manager/retention_prune.py` and `tests/test_retention_unattended_prune.py`; `M` `src/workflow_manager/cli.py`, `retention_policy.py`, `retention_run.py`, `retention_unattended.py`, and `tests/test_retention_cleanup.py`, `test_retention_unattended.py`, `test_retention_unattended_run.py`; nothing under `tools`, `.github`, `.claude`, `scripts` or `.workflow-manager`; `tests/test_retention_run.py` and `tests/test_retention_policy.py` not listed |
| 2 | `git diff --name-status 7e0ab69 HEAD -- docs`, then `git diff --name-status 7e0ab69 -- docs/ROADMAP.md` | committed: `M` `docs/exit-codes.md`, `docs/retention.md`, `docs/ACTIVE_MILESTONE.md`, `docs/ai-workflow/WORKFLOW_STATE.json`, and `A` the item's plan, registry, artifacts and mapping files, no other page; working tree: `M` `docs/ROADMAP.md` |
| 3 | `git diff --exit-code 7e0ab69 HEAD -- docs/verify.md docs/update.md docs/release-history.md README.md tests/parallel/resources.json src/workflow_manager/retention.py src/workflow_manager/retention_cleanup.py src/workflow_manager/retention_alert.py src/workflow_manager/retention_alert_json.py` | exit 0 |
| 4 | `grep -n "older than .ttl_days\|prune_max_per_run\|cannot be undone\|workflow-archive" docs/retention.md`; `grep -n "prune" docs/exit-codes.md` | the page names the ttl rule, the cap, that a deleted archive cannot be undone, and the archive store; exit codes 0, 1 and 2 each mention prune |
| 5 | `grep -rn "unattended-retention\|#254\|#259" docs/retention.md docs/exit-codes.md` | no match (exit 1) |
| 6 | `grep -rni --include='*.py' --include='*.md' "prune is not run unattended yet\|Prune is not yet unattended\|not prune,\|Prune is never run\.\|never part of cleanup\|does not run it either\|Neither is run by the Manager\|The Manager never runs any of them\|prune was not run\|it adds authority and evidence, never new actions" src docs/retention.md` | exactly two matches, both `prune was not run`: `src/workflow_manager/retention_run.py:359` (the confirmed run's closing line, and the unattended run's with prune off) and `docs/retention.md:362` (the page's description of it). No match for `never new actions` (`docs/retention.md:371` names the prune phase as the run's added action) |
| 7 | `grep -n "^\| 5[0-2] " docs/ROADMAP.md`; `git diff --numstat 7e0ab69 -- docs/ROADMAP.md` | row 52 names #254 and A3 with status Done; numstat `1 0` (rows 50 and 51 unchanged) |
| 8 | `XDG_STATE_HOME=$S/state PYTHONPATH=src python3 -m workflow_manager retention-cleanup "$S" --unattended --confirm x; echo $?; test ! -e "$S/state" && echo absent` | stderr `error: retention cleanup: --confirm and --unattended cannot be combined`; exit 2; `absent` |
| 9 | `python3 tools/release/release.py check-title "feat: prune old archives in the unattended retention run under the adopted unattended policy"` | `valid title: feat, release impact minor`, exit 0 |
| 10 | `unshare -rn python3 tests/run_all.py --allow-root --select test_retention_unattended_prune.py --select test_retention_unattended_run.py --select test_retention_unattended.py --select test_retention_run.py --select test_retention_cleanup.py --select test_retention_policy.py` | `verdict: exit 0` (71 of 71 units, 437 tests). Then mutation M3 in a second copy `$S/m3` (`command cp -a "$S/cand" "$S/m3"`): in `src/workflow_manager/retention_prune.py` change `elif _folder_present(report, item_id):` to `elif False and _folder_present(report, item_id):`, run `python3 -m compileall -q src` in that copy, then `unshare -rn python3 tests/run_all.py --allow-root --select test_retention_unattended_prune.py`: `verdict: exit 1`, with failures including `test_an_old_archive_whose_folder_is_present_is_never_named` and `test_a_present_review_folder_is_excluded_with_its_reason` |

Flow 10 is the one flow that runs the test suite. It must run with the release cache copied in (the setup does this): without it, `run_all` stops with `PrimingError` (exit 2) before any test runs. The round-2 result at `d9ade3f` (the code of `59b2c4e`): the unmutated selection `verdict: exit 0` (71 of 71 units, 437 tests); M3 `verdict: exit 1` with eight failing test methods (`test_retention_unattended_prune.py` only), including the two named above and `test_the_cap_counts_only_selectable_archives`, `test_the_skipped_ids_do_not_move_it`, `test_a_missing_finished_entry_fails_closed`, `test_a_nothing_to_prune_document_lists_the_skips`, `test_nothing_to_prune_prints_one_line_and_its_skips_and_no_audit_line` and `test_a_folder_fact_that_is_not_exactly_false_fails_closed` (five values). The run made no stand-in call.

### Owner flows (need the real `gh`; the sandbox cannot run these)

The cleanup report makes one forge query per finished item, so the sandbox's refusing `gh` stops it before any action. Run these in your own shell on a scratch managed repository whose name no real repository uses: the archive store is keyed by repository name (`~/.local/share/workflow-archive/<repository>`). For flow 12, run with `HOME=$S/home` and `GH_CONFIG_DIR=$HOME/.config/gh` so the real store is untouched (`docs/retention.md`, "The archive store"), and keep `$S` on the repository's file system.

**Test data:** a managed repository with an adopted policy in the unattended form (`cleanup` true, `prune` true, `keep_recent` 5, `ttl_days` 14, `prune_max_per_run` 3), adopted with `workflow-manager adopt-retention-policy TARGET --confirm "Adopt the unattended retention policy DIGEST12."`; at least four archives older than 14 days whose review folders are already gone, and one archive younger than 14 days (set the older mtimes with `touch -d` in the scratch store only).

| Flow | Do | Expect |
| --- | --- | --- |
| 11 | `workflow-manager retention-cleanup TARGET` (preview) and `workflow-manager status --retention TARGET` | exit 0; the lines say the run archives and removes, then prunes archives of finished items whose review folder is gone, older than 14 days, at most 3 per run, and that a deleted archive cannot be undone, with the archive store path; no line says prune is not run |
| 12 | `XDG_STATE_HOME=$S/state HOME=$S/home GH_CONFIG_DIR=$HOME/.config/gh workflow-manager retention-cleanup TARGET --unattended --json` | exit 0; stdout is one JSON document with `prune.enabled` true and `prune.outcome` `done`; `prune.ids` has the at most three oldest old archives, oldest first; the young archive is not named; the deleted archives are gone from `$S/home/.local/share/workflow-archive/<repository>` and the rest remain; `$S/state/workflow-manager/retention-audit.jsonl` has a `prune` `started` line before the first delete and one `ok` line per deleted archive; the real `~/.local/share/workflow-archive` has nothing of this repository |
| 13 | Change `prune` to `false`, re-adopt with the new digest's sentence, run flow 12's command again | the preview says `unattended.prune` is false, so no archive is pruned; the closing line ends `prune was not run`; the JSON `prune.enabled` is false and `prune.outcome` is `disabled`; no `prune` line in the audit file; no archive is deleted |

### Known limitations (out of scope)

- Deleting an archive cannot be undone, and the archive store is not backed up by the Manager. Moving it to a backed-up disk is the owner's decision and is not part of this item.
- The confirmed run never prunes; `scripts/workflow_retention.py prune` stays user-only. No scheduler and no notification (the lane heartbeat step comes later). No Workflow release and no pin change.
- `keep_recent` does not protect archives; only `ttl_days` and the cap do.
- A review folder that reappears between the report and an apply is not seen by the engine. Named risk, bounded by the cap, not closed.
- Plan section 5 expects `tests/test_retention_policy.py` to be modified. It is not: `enforcement_lines` lives in `retention_policy.py`, and that test file passes unchanged.

### Known findings at preparation

- None open. The round-1 findings are fixed (see "What round 1 found" above), and the implementation review's LIR2-001 and LIR2-002 are fixed in `59b2c4e`.
- **Flows 2 and 7**: they expect `docs/ROADMAP.md` row 52 as an uncommitted working-tree change. The setup copies that row into the scratch clone, so they pass in a clean sandbox checkout; in the product clone the row is present (`1 0` numstat) and stays uncommitted by design.

### Feedback and next steps

- Findings go to `.ai-review/unattended-retention-prune/feedback/FUNCTIONAL_REVIEW.md`. Do not create a flat path.
- Once testing is clean, `/accept-milestone` is the only acceptance command. It needs every checkpoint `COMPLETE`; CP1 to CP4 are, so acceptance is possible after a clean round. If a checkpoint were outstanding, the way forward would be `/milestone-implement`.
- `docs/ROADMAP.md` row 52 stays uncommitted. Never stage it with this item's commits.
