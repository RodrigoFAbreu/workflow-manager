# Common problems

> For: someone who ran a Manager command and got an error. Last checked with: Workflow Manager 1.8.0, Workflow 2.9.1.

Every error the Manager prints has two parts: `error:` names the cause, and `next:` names one step to take (a command, a flag or a page). Run the `next:` step, then run your command again. This page lists the messages with the same fix in more words.

## Problems

| What you see | Fix |
|---|---|
| `workflow-manager: command not found` | Run `pipx ensurepath`, then open a new terminal. |
| `--version` prints `1.0.0` or "development build" | An editable install keeps old metadata. Run `pipx reinstall workflow-manager` once; if the saved wheel is gone, run `pipx uninstall workflow-manager`, then `pipx install <wheel>` with a fresh download. |
| `unrecognized arguments: --release-version ...` (or another global option) | Put the option before the command. The `next:` line prints the pattern, for example `workflow-manager [--release-version VERSION] update TARGET`. See [Exit codes](exit-codes.md#global-options). |
| `the following arguments are required: COMMAND` or `invalid choice` | The command line is incomplete or names a command that does not exist. `workflow-manager --help` lists the commands. |
| `no directory at ...` | The path is wrong. Create the repository with the `git init` command the `next:` line prints, or correct the path. |
| `is not a Git repository` | Run `git init` in the target (or give the repository's top directory, the one holding `.git`), then run the command again. |
| `is already managed (workflow X is installed)` | The repository already has the Workflow. Run `workflow-manager update TARGET` to move it to another release; `doctor` shows what that would do first. |
| `is not a managed repository` | The Manager has not installed the Workflow there. Run `workflow-manager bootstrap TARGET`. (`uninstall` prints that there is nothing to uninstall.) |
| `refusing to bootstrap: the repository already has its own file at these release paths` | Each `occupied:` line is a file of yours where a release file goes. Move your files away, or add `--force` to replace them with the release's. A line that says a directory is in the way, or a file where a directory goes, cannot be replaced even with `--force`: move or remove it. |
| `refusing to update: these release files were modified locally` | Keep a copy of every file a `modified:` line names, then re-run with `--force`. `update --dry-run` previews it. |
| `verify` prints `N problem(s)` | Run `update TARGET` to put the release's files back (add `--force` if a line says `modified:` for a release file: that replaces your edit), or undo the listed edits with `git checkout -- FILE`. |
| `cannot fetch ...` | The release is not in the cache and cannot be downloaded. Connect to the network once, or point `--release-source` at a mirror that holds `VERSION/`. |
| `does not match its pin` or `is damaged` | The download or the cache entry does not match its digest. Run the same command again, which downloads afresh. If the digests differ again, install nothing from it and report the message to the Manager's maintainer. |
| `release X is not published: this Manager has no pin for it` | This Manager does not know that Workflow release. [Update the Manager](update.md#update-the-manager) and run the command again. A release directory that is not published installs with `--release-dir DIR`. |
| An interrupted `bootstrap` or `update`, or `[Errno 13] Permission denied` and other file errors (exit 1) | Fix the cause the message names, then run the same command again. It finishes the job. See [An install stopped part way](#an-install-stopped-part-way). |
| `the installation record at ... is unreadable` | Delete `.workflow-manager/` in the repository and run `bootstrap` again with the release the repository was on (the `next:` line shows how to find it). State files are not stored there. |
| `was written by a newer Manager` | The repository was updated by a newer Manager than this one. [Update the Manager](update.md#update-the-manager). |
| A cache that seems stale or damaged | Delete the cache folder (default `~/.cache/workflow-manager/releases`). The next command downloads again. |
| `status` prints `work in flight:` | The block lists each active work item with its phase, type and governing version, so you do not read `WORKFLOW_STATE.json` by hand. `none` means the state was read and held no active item; `unknown (...)` or `could not be read (...)` means it was not, and names the command that says why. |
| `doctor` or `update --dry-run` reports a `blocked` finding | The real update would be refused, and the finding quotes the refusal and a `What to do:` step. Apply it (for a locally modified file: save the edit, then `update --force`), then run the check again. |
| `doctor` reports a `warning` finding | The update would proceed, but could disturb an in-flight work item, change gates or cross a downgrade boundary. Read the finding and its Recovery lines before you update; the finish-or-park advice is in [Update](update.md#check-before-you-update). |
| `doctor` reports `incomplete-inspection` | Part of the repository could not be read (state file, declarations, or a Git call). The report is not a clean bill of health; fix what it names, or review those parts by hand. An old legacy work item with no `docs/ai-workflow/registry/<id>-artifacts.json` declarations file always reports it, so `doctor` never reaches exit 0 until that item is retired; read the finding rather than chase it. |
| A repository went wrong after an update to 2.8.0 and gates behave differently | See "Approval gates" in [Update](update.md). |

## An install stopped part way

If `bootstrap` or `update` stopped before it finished (a full disk, a permission error, an interrupted terminal), fix the cause the message names and run the same command again. A resumed run finishes the job. If it then lists a file as modified or in the way that you did not edit, that file is a partial write from the interrupted run, and adding `--force` replaces it with the release's. Keep a copy of any file you did edit first.

## Repair workflow data by hand

The Manager prints no command that writes Workflow data: `WORKFLOW_STATE.json`, `WORKFLOW_CONFIG.json` and `docs/ACTIVE_MILESTONE.md` hold your work in flight, and `update` is not a repair for a missing or damaged one, because it recreates every missing state file from a blank template. Find a good copy in Git history instead: `git log --oneline -- docs/ai-workflow/WORKFLOW_STATE.json` lists the revisions, and `git show REVISION:docs/ai-workflow/WORKFLOW_STATE.json` prints one. Put the copy back yourself, then run the command again.

If no revision holds a good copy, each state file has a blank template in the release's `templates/` folder, which sits in the release cache (default `~/.cache/workflow-manager/releases/VERSION/tree/templates/`). Copy the one you need, review it, and commit it. The Manager never chooses between a template and your history for you: you decide which copy is the good one. `update` itself recreates every state file that is still missing from a blank template.

## Exit codes

Every command ends with a status: 0 for success, 1 when it found a problem or had no usable release (for `doctor`, a release it cannot resolve is 2), 2 when it refused to run or could not check. The full table, per command, is in [Exit codes](exit-codes.md).

Use them in scripts: `workflow-manager verify <repo> && echo ok`.

More help: [Install](install.md), [Verify](verify.md), [Exit codes](exit-codes.md), [Glossary](glossary.md).
