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

- **finished work items** are the work items the script counts as finished and no longer among the most recent ones it keeps. Their review folders are the untracked `.ai-review/<id>/` folders.
- **with an archive** counts finished work items only. A finished work item whose archive could not be read is shown as `(N unknown)`, never as archived and never as not archived.
- **archive store** is a separate count of every archive in the archive directory, including archives of work items that are not finished or no longer exist. It is never a share of the finished work items. Prunable archives are older than the time to live; the Workflow has no command to prune them yet, so none is printed.
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
| the script exited with status 2 without a refusal (FIRST LINE OF ITS ERROR OUTPUT), that is without its own `error:` and `next step:` lines | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script exited with status N (FIRST LINE OF ITS ERROR OUTPUT), N being neither 0 nor 2 | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's output is not UTF-8 text | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's output is not one JSON object | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the script's report has kind VALUE, not 'retention-report' | update workflow-manager to the newest release |
| the script's report has schema_version VALUE; this workflow-manager reads 1 | update workflow-manager to the newest release |
| the script's report is malformed: FIELD AND PROBLEM (see the limits below) | run `python3 -I scripts/workflow_retention.py report` in the repository |
| the forge could not be queried (CODE, N items), every CODE `rate_limited` | wait for the forge's rate limit to reset, then run the command again |
| the forge could not be queried (CODE, N items), any other code | install gh and run `gh auth login`, then run the command again |

### Limits on the report

The Manager checks the whole report before it prints any of it. A string has no control character. A number lies from 0 to 2**63 - 1. A work-item id or a reason has at most 256 characters (an id the script files as `invalid_id` is never printed and is only checked for valid text). `repository`, `archive_dir` and each `read_errors[].path` have at most 4096 characters, and each `read_errors[].error` at most 8192. A report that breaks a limit is shown as the two lines above with the `malformed` cause, and the exit status does not change.

The 4096 on `read_errors[].path` is Linux's `PATH_MAX`, but it is not a strict bound for that field: the script writes the path as a string, so a path can be longer. A valid report with such a path prints `retention: not available: the script's report is malformed: read_errors[].path is longer than 4096 characters`, never the path cut short, and its step is to run `python3 -I scripts/workflow_retention.py report`, which shows the whole report. The Manager does not raise the limit.

When the kind or schema_version is one the Manager does not read, the line shows the value cut at 40 characters, then `... (N characters)`. N is the length of the value itself: a string counts its characters without the quotes the display adds, a number the characters it is written with, a sign included, and a list or object the characters of its printed form, never its elements.

## Exit status

`--retention` never changes an exit code. See [Exit codes](exit-codes.md).
