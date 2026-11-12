# Retention report

> For: someone who wants to know how many finished work items of a managed repository still have review folders on disk, and which of them are archived. Last checked with: Workflow Manager 1.13.2, Workflow 2.22.0.

Goal: see, without changing anything, which finished work items of a repository keep an untracked `.ai-review/` folder, which have an archive, and what to run next.

## Prerequisites

- The `workflow-manager` command ([Install](install.md)).
- A repository the Manager installed Workflow 2.20.0 or later into. The report comes from the repository's own `scripts/workflow_retention.py`; an older release has none.
- For a complete answer, `gh` signed in (`gh auth login`): the script asks GitHub once per finished work item whether its pull request is merged.

## Steps

1. Ask `status` for the section.

   ```bash
   workflow-manager status --retention /path/to/your/repo
   ```

2. Or ask `doctor`, which prints the section after its report.

   ```bash
   workflow-manager doctor --retention /path/to/your/repo
   ```

The option goes after the command. Without it, nothing changes: the same output, the same exit code, and the script is never started. It is opt-in because the script makes one GitHub query per finished work item (about 20 to 40 seconds for 25 items), and `status` and `doctor` stay fast without it. Nothing is cached: a stale answer about what can be archived is worse than none.

## What you should see

```text
retention (read-only; the Workflow script made one forge query per finished item):
  repository OWNER/NAME, archive directory DIR, time to live 30 days
  finished work items: 12 (review folders 3.2 MiB), kept as the most recent: 3
  with an archive: 4 of 12; archive store: 5 archives, 1 prunable (older than 30 days)
  interrupted removals: none
  next: in the repository, run `python3 -I scripts/workflow_retention.py archive ID --apply` (run it without `--apply` first for a dry run)
```

- **finished work items** are the finished work items with a review folder, beyond the most recent ones the script keeps. Their review folders are the untracked `.ai-review/<id>/` folders.
- **with an archive** counts finished work items only. A finished work item whose archive could not be read is shown as `(N unknown)`, never as archived and never as not archived.
- **archive store** is a separate count of every archive in the archive directory, including archives of work items that are not finished or no longer exist. It is never a share of the finished work items. Prunable archives are older than the time to live. From Workflow 2.24.0 the line `prunable archives: python3 -I scripts/workflow_retention.py prune ID --apply removes one (run `report` to list them)` names the command; before that it reads `prunable archives: this Workflow release has no prune command: workflow-manager update TARGET`. Neither is run by the Manager.
- **interrupted removals** lists work items whose removal was started and not finished: five ids, then a count (`a1, a2, a3, a4, a5 and 2 more`). A Workflow release before 2.22.0 does not report them, and the line says so.
- **next** is one command for you to run in the repository, the first that applies: `archive`, then `remove`, then resuming an interrupted `remove`. The Manager never runs them. A command the repository's Workflow release does not have is replaced by `workflow-manager update`. With nothing to do, the step reads `nothing to archive`; when finished work items have tracked review files it adds why: `nothing to archive: 2 finished work items have tracked review files; the script archives and removes only untracked folders`.

In a complete report with no finished work item, the first line reads `retention (read-only; the Workflow script found no finished work item):`, with `beyond the N most recent` added when the script keeps N recent ones; an incomplete report keeps the `retention: INCOMPLETE` first line whatever the count.

The Manager does not pass `--archive-root` or `--ttl-days`: the Workflow's defaults apply, and the section prints the archive directory and the time to live it used.

## If the report is incomplete

When some folder or archive could not be read, or some work items could not be checked against GitHub, the section opens with `retention: INCOMPLETE`, names what failed (at most five items, then a count), and its numbers are lower bounds. Fix what is named, then run the command again.

## If it is not available

The section then prints two lines and the exit status does not change:

```text
retention: not available: CAUSE
  next: STEP
```

| Cause | Step |
|---|---|
| the repository is not managed by workflow-manager (`status` only) | `workflow-manager bootstrap TARGET` |
| the repository has no scripts/workflow_retention.py (the Workflow release that ships it is 2.20.0 or later) | `workflow-manager update TARGET` |
| the Python running workflow-manager cannot start: ERROR | reinstall workflow-manager (`pipx reinstall workflow-manager`) |
| the report did not finish within 300 seconds | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script refused (its own `error:` code and message, for example no GitHub `origin` remote or no state file) | the script's own `next step` |
| the script exited with status 2 without a refusal (FIRST LINE OF ITS ERROR OUTPUT, or `(no message)` when it wrote none), that is without its own `error:` and `next step:` lines | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script exited with status N (FIRST LINE OF ITS ERROR OUTPUT, or `(no message)` when it wrote none), N being neither 0 nor 2 | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's output is not UTF-8 text | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's output is not one JSON object | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's report has kind VALUE, not 'retention-report' | update workflow-manager to the newest release |
| the script's report has schema_version VALUE; this workflow-manager reads 1 | update workflow-manager to the newest release |
| the script's report is malformed: FIELD AND PROBLEM (see the limits below) | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the forge could not be queried (CODE, N items), every CODE `rate_limited` | wait for the forge's rate limit to reset, then run the command again |
| the forge could not be queried (CODE, N items), any other code | install gh and run `gh auth login`, then run the command again |

### Limits on the report

The Manager checks the whole report before it prints any of it. A string is valid text and has no control character. A number lies from 0 to 2**63 - 1. A work-item id or a reason has at most 256 characters (an id the script files as `invalid_id` is never printed and is only checked for valid text). `repository`, `archive_dir` and each `read_errors[].path` have at most 4096 characters, and each `read_errors[].error` at most 8192. A report that breaks a limit is shown as the two lines above with the `malformed` cause, and the exit status does not change.

The 4096 on `read_errors[].path` is Linux's `PATH_MAX`, but it is not a strict bound for that field: the script writes the path as a string, so a path can be longer. A valid report with such a path prints `retention: not available: the script's report is malformed: read_errors[].path is longer than 4096 characters`, never the path cut short, and its step is to run `python3 -I scripts/workflow_retention.py report`, which shows the whole report. The Manager does not raise the limit.

When the kind or schema_version is one the Manager does not read, the line shows the value as it prints, which puts a string between quotes and escapes each control character, so the printed form can be longer than the value. A value whose printed form is at most 40 characters is shown whole; a longer one shows its first 40 printed characters, then `... (N characters)`. N is the length of the value itself: a string counts its characters without the quotes the display adds, a number the characters it is written with, a sign included, and a list or object the characters of its printed form, never its elements.

## Retention policy

The owner of a repository can write down how much finished work it tolerates, and adopt that policy so the Manager knows it was meant. The Manager reads the policy and, for mode `notify` or `both`, evaluates its thresholds in `verify` and `doctor` (see [The retention alert](#the-retention-alert)). Reading the policy sends nothing, archives nothing, removes nothing and prunes nothing, and decides nothing for the owner. For mode `cleanup` or `both`, `workflow-manager retention-cleanup` previews what a cleanup would do and, only when its `--confirm` holds the sentence bound to the plan, archives and removes those items (see [Retention cleanup](#retention-cleanup)); prune is never run. A later release sends notifications.

The policy is the file `.workflow-manager/retention-policy.json`, committed by the owner. With no file nothing is printed and nothing changes.

```json
{"schema_version": 1, "mode": "off",
 "thresholds": {"finished_items": 10, "finished_folder_mib": 500,
                "archives": 20, "prunable_archives": 5}}
```

| Key | Value | Meaning, for the release that evaluates it |
|---|---|---|
| `schema_version` | the integer 1 | a newer file is refused, so an older Manager falls back to `off` |
| `mode` | `off`, `notify`, `cleanup` or `both` (lower case) | `off`: nothing; `notify`: tell the owner; `cleanup`: clean up silently; `both`: both |
| `thresholds.finished_items` | integer, 1 to 100000 | finished work items with a review folder, beyond the most recent ones, at or above it |
| `thresholds.finished_folder_mib` | integer, 1 to 1048576 | MiB in the review folders of those items, at or above it |
| `thresholds.archives` | integer, 1 to 100000 | archives in the store, at or above it |
| `thresholds.prunable_archives` | integer, 1 to 100000 | archives older than the script's time to live, at or above it |

`thresholds` and each key in it are optional, and a missing one is not checked. A mode other than `off` needs at least one threshold. The file is closed and strict: an unknown key, a wrong type (a boolean or a decimal where an integer goes), a number out of range, a duplicate key, a link, a file that is not regular or one larger than 4096 bytes is refused.

### Adopting it

The file is only a proposal. Adopting it records its digest, so a later edit is never taken for the owner's decision.

1. Preview. This writes nothing.

   ```
   workflow-manager adopt-retention-policy /path/to/your/repo
   ```

   It prints the file's digest, its mode and thresholds, the state, and the sentence that adopts it: `Adopt the retention policy`, then the first 12 characters of the digest and a full stop.

2. Adopt. Only the repository's owner runs this, with that sentence in `--confirm` (an agent must not: the sentence is the owner's decision, bound to this digest). Other words around it are allowed; the sentence for another digest, or without the full stop, is refused and nothing is written.

   ```
   workflow-manager adopt-retention-policy /path/to/your/repo --confirm "Adopt the retention policy 1a2b3c4d5e6f."
   ```

   It writes `.workflow-manager/retention-adoption.json`. Commit it with the policy file. The command commits nothing.

The mode in force is `off` unless the file is valid and the record names exactly the file's digest. Editing the file after adopting it returns the mode to `off` (state `changed`) until you adopt it again.

### What `status --retention` and `doctor --retention` print

Before the report, one block, only when there is a policy file or a record:

```
retention policy: adopted, mode both (digest 1a2b3c4d5e6f, adopted 2026-11-10T12:00:00Z)
  thresholds: finished items 10, finished folders 500 MiB, archives 20, prunable archives 5
  this Manager release reads the policy and, for notify and both, evaluates its thresholds in verify and doctor; it sends nothing, and cleans up only when retention-cleanup runs with --confirm
```

Any other state reads `retention policy: STATE (WHY); mode off is in force`, then up to five problems, and an indented `next:` step.

| State | When | Mode in force |
|---|---|---|
| `not-adopted` | a valid file and no record | `off` |
| `adopted` | a valid file and a valid record with the same digest | the file's mode |
| `changed` | a valid file and a valid record with another digest | `off` |
| `invalid` | the file is refused (or `.workflow-manager` is a link) | `off` |
| `record-invalid` | a valid file and a refused record | `off` |
| `file-missing` | a record and no file | `off` |

`workflow-manager uninstall` removes `.workflow-manager/` and with it an adopted policy, so the mode returns to `off`. The block never changes an exit code.

## The retention alert

For a policy that is adopted with mode `notify` or `both`, `workflow-manager verify` and `workflow-manager doctor` compare the four thresholds with the retention report and print a block after their own output when one is reached:

```text
retention alert: 2 of 4 thresholds reached (mode notify, policy 1a2b3c4d5e6f)
  finished items: 12, limit 10: reached
  finished folders: 612 MiB, limit 500 MiB: reached
  archives: at least 5, limit 20: not known (the report is incomplete)
  next: in the repository, run `python3 -I scripts/workflow_retention.py archive ID --apply` (run it without `--apply` first for a dry run); ...
```

- A number **at or above** its limit is reached. Only thresholds the policy sets are checked. A threshold that is within its limit is not listed; when every threshold is within, nothing is printed.
- **finished items** counts the finished work items that still have a review folder, the number archiving and removing lowers. The folders limit is in MiB; the printed size is rounded down.
- An incomplete report gives lower bounds: a number at or above its limit is still reached (printed `at least N`), and one below it is `not known`, never within. The `next:` step then ends with the incomplete-report step.
- The `next:` step names the user-only command for the cause: `archive` or `remove` for the finished items and their folders, `prune` for prunable archives (and for the archive count when some archive is past the time to live; otherwise the line says none can be pruned yet, or, for an incomplete report, that no prunable archive was observed, and that the policy's `thresholds.archives` is yours to raise). A Workflow release without the command gets `workflow-manager update`. The Manager never runs any of them.
- When the report cannot be had, one line reads `retention alert: not evaluated: CAUSE` with an indented `next:`: the script is missing or refuses, its report is malformed or times out, the report is incomplete with nothing reached, the installed `scripts/workflow_retention.py` does not match the release (the alert never starts a script `verify` reports as modified; run `workflow-manager update TARGET --force`), the installation record names no release, or the installed release cannot be checked. It is never an all-clear.
- The alert is not a `[warning]` finding and **never changes an exit code**: `verify` and `doctor` exit as they would without the policy.
- It costs a run of the report: one forge query per finished work item (about 20 to 40 seconds for 25 items, 300 seconds at most), and `gh` signed in for a complete answer. A repository without an adopted `notify` or `both` policy pays nothing and sees no change. With `doctor --retention` the script runs once for both the section and the alert; `doctor` judges the script against the installed release, not the one `--release-version` names.

## Retention cleanup

For a policy adopted with mode `cleanup` or `both`, `workflow-manager retention-cleanup TARGET` shows which finished work items an unattended cleanup would archive and then remove. It is its own command: `verify`, `doctor`, `update` and `status` never run it. **Without `--confirm` it is a preview: it writes nothing, archives nothing and removes nothing, and it runs no script verb but `report`.** With `--confirm` holding the plan's sentence it runs the plan (see [The confirmed run](#the-confirmed-run)). Prune is never part of cleanup: it stays user-only and is never run.

It checks these, in order, and the first that fails refuses with `error:` and `next:` on stderr (exit 2) before anything else runs:

1. the repository is managed;
2. the policy is adopted unchanged and its mode is `cleanup` or `both` (`off` and `notify` are refused);
3. `.workflow-manager/retention-policy.json` and `.workflow-manager/retention-adoption.json` are committed at HEAD with the bytes that were adopted;
4. no tracked file is changed (untracked review folders are expected);
5. the installed Workflow release is **2.25.5 or later** (an older engine can end in a traceback in the middle of a removal; `workflow-manager update TARGET`);
6. the installed `scripts/workflow_retention.py` is the release's own;
7. the retention report can be had (this is the one run of the script: one forge query per finished item, `gh` signed in, 300 seconds at most);
8. the report is complete and no removal was interrupted (finish an interrupted removal yourself, with the user-only `remove ID --apply`).

Only the two thresholds that archiving and removing can lower take part, `finished_items` and `finished_folder_mib`; `archives` and `prunable_archives` never plan anything. The oldest finished items that still have a review folder are taken first, until every threshold the policy sets is below its limit, at most 5 per run. An item with an archive and a folder is planned as `remove only`; an item whose folder holds files Git tracks, or whose id the engine would not accept, is skipped and named. The preview ends with one of three outcomes: below every limit, stopped at the cap (run it again to plan more), or no further item is eligible (running it again will not help).

```text
retention cleanup: preview (nothing was written; mode both, policy 1a2b3c4d5e6f, plan 9f8e7d6c5b4a)
  thresholds reached: finished items 12 (limit 10), finished folders 612 MiB (limit 500 MiB)
  would clean 3 of 12 finished items with a review folder, oldest first, at most 5 per run:
    1. item-a: 210 MiB, archive then remove
    2. item-b: 3 MiB, remove only (already archived)
    3. item-c: 40 MiB, archive then remove
  skipped: item-x: Git tracks files under its review folder (the engine archives untracked folders only)
  after this run: finished items 9, finished folders 359 MiB: below every limit
  next: workflow-manager retention-cleanup TARGET --confirm "Run the retention cleanup 9f8e7d6c5b4a."
  by hand, one item at a time: the Workflow's user-only `/archive-finished-item ID`; for an item that is already archived, `python3 -I scripts/workflow_retention.py remove ID --apply` alone
```

The plan digest identifies the repository, the policy and the ordered items; sizes are rounded down to whole MiB. When no threshold is reached the output is one line, `retention cleanup: nothing to do (...)`, and the exit status is 0. A preview is not a promise: the engine judges each item again when it archives and removes it.

### The confirmed run

`workflow-manager retention-cleanup TARGET --confirm "Run the retention cleanup DIGEST12."` runs the plan. `DIGEST12` is the first 12 characters of the plan digest the preview prints. The command does the same checks as the preview, plans again from a fresh report, and acts only if the sentence names that plan. Whitespace is collapsed and case is ignored, other words may surround it, and at least one match is needed, with every match naming the same 12 characters. A sentence for another plan (a changed plan, repository or policy all change the digest), an empty one or none of the sentence is refused with exit 2 before any `archive` or `remove` runs, and `next:` names the command that shows the current plan. A plan with no items runs nothing and the sentence is not consulted.

Per item, in the preview's order and at most 5 per run, each step is a call of the target's own `scripts/workflow_retention.py` (600 seconds at most per call):

1. `archive ID --apply`, unless the item is `remove only`;
2. the engine's own verification, the dry run of `remove ID`, which writes nothing;
3. `remove ID --apply`.

The Manager reimplements none of them: no archive format, no hashing and no deletion of its own, only the three calls above, each ending in `--repo-root` for the target. The adopted policy is read again before each item; a policy that changed stops the run. **The first failure of any step stops the run**: no further call and no further item, and the report says what was done and what was not. The run prints as it goes:

```text
retention cleanup: running plan 9f8e7d6c5b4a (mode both, policy 1a2b3c4d5e6f), 3 items
  1. item-a: archived 41 MiB, verified, removed
  2. item-b: remove only, verified, removed
  3. item-c: stopped at verify (archive_mismatch): the review folder differs from its archive in 1 entry: REVIEW.md (differs)
     next step (the engine's): ...
retention cleanup: stopped after 2 of 3 items; item-c's folder is untouched; nothing was committed or needs committing
```

A stop at `archive` or `verify` leaves the review folder where it was, and the report says so. At `archive` the report says exactly what is known: after an engine refusal it says the item was not archived, except that after `already_archived` it says this run did not create an archive (one already exists), and after a refusal where the engine printed `warning: the undo could not remove` (its undo of the failed archive left something behind) it says the item may or may not be archived; after a timeout, an interrupt or output the Manager cannot read it also says the item may or may not be archived, and the next preview shows which. A stop at `archive` never reaches `remove`. A stop at `remove` quotes the engine's message and next step and says where its folder is only as far as the engine does; after a timeout, an interrupt or output the Manager cannot read, the report says the folder's state is unknown and may be partly removed and names the user-only `python3 -I scripts/workflow_retention.py remove ID --apply`, which finishes it (the next preflight refuses until then, when the folder is in `.removing`). A clean run ends `retention cleanup: done, N of N items archived and removed; Git is unchanged (the review folders were untracked); prune was not run`. **Nothing is committed**: the review folders are untracked, so HEAD and the tracked files are identical before and after.

- **Exit status.** 0: the preview, nothing to do, or every item done. 1: the run stopped after an engine call started (the closing `retention cleanup: stopped` line says where; stderr has `error:` and `next:`). 2: refused with nothing written.
- **Re-runs.** An item archived by an earlier run whose removal did not happen is planned `remove only`: no second `archive` (the engine refuses `already_archived`). A removal left half done in `.removing/ID` is refused by the preflight and finished by hand. After a killed archiver the next `archive` refuses `partial_present`, and the run stops at that item. Two runs at once: the engine's lock makes the second stop with `archive_busy`.
- **The archive store.** It is the engine's default, under `HOME` (`~/.local/share/workflow-archive/<repository>`). A job that runs with another `HOME` archives elsewhere. If the store is on another file system than the repository's `.ai-review`, the engine archives, then refuses the removal as `cross_device`, on every run: the report quotes its message and no item progresses. Remove by hand with `--archive-root`, or run with a `HOME` on the repository's file system; a user who changes `HOME` keeps `gh` signed in by setting `GH_CONFIG_DIR` to the real configuration directory first, and needs a Git identity if the run's repository setup commits.
- **The sentence is a formality for a job that scrapes it.** The sentence proves the plan was shown, not who asked. A scheduled job that reads the sentence from the preview's `next:` line and passes it back makes the confirmation a formality: the owner's control is the adopted policy and the schedule.

## Exit status

`--retention` and the retention alert never change an exit code; `adopt-retention-policy` exits 0 when it previews or adopts and 2 when it refuses; `retention-cleanup` exits 0 when it previews, has nothing to do or finishes the run, 1 when a confirmed run stopped after it started, and 2 when it refuses. See [Exit codes](exit-codes.md).
