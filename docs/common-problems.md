# Common problems

> For: someone who ran a Manager command and got an error. Last checked with: Workflow Manager 1.6.0, Workflow 2.9.0.

Each problem has a one-line fix. Find the message, apply the fix, run the command again.

## Problems

| What you see | Fix |
|---|---|
| `workflow-manager: command not found` | Run `pipx ensurepath`, then open a new terminal. |
| `--version` prints `1.0.0` or "development build" | An editable install keeps old metadata. Run `pipx reinstall workflow-manager` once; if the saved wheel is gone, run `pipx uninstall workflow-manager`, then `pipx install <wheel>` with a fresh download. |
| `unrecognized arguments: --release-version ...` | Put the option before the command: `workflow-manager --release-version 2.8.0 update <repo>`. |
| `is not a Git repository` | Run `git init` in the target, then retry. |
| `is already managed; use update() to move it to another release` | The repository already has the Workflow. Use `workflow-manager update <repo>`. |
| `is not a managed repository` | The Manager has not installed the Workflow there. Run `workflow-manager bootstrap <repo>`. |
| A list of colliding files from `bootstrap` | Move your own files away, or re-run with `--force` to replace them with the release's. |
| `refusing to update: these release files were modified locally` | Save your edits elsewhere, then re-run with `--force`. |
| `verify` prints `N problem(s)` | Undo the listed edits with `git checkout -- <file>`, or run `update --force` to restore the release's files. |
| An error naming a version, a URL and a cache directory | The release is not cached and cannot be downloaded. Connect to the network once, or point `--release-source` at a mirror. |
| An error about a digest, size or manifest that does not match | The download does not match its pin. Retry once. If it persists, do not install, and report it in the Manager repository. |
| An error about an unpinned version | This Manager does not know that Workflow release. Install the newest Manager ([Update](update.md)). |
| An interrupted `bootstrap` or `update` | Run the same command again. It finishes the job. |
| The installation record is unreadable | Delete `.workflow-manager/` in the repository and run `bootstrap` again. State files are not stored there. |
| A cache that seems stale or damaged | Delete the cache folder (default `~/.cache/workflow-manager/releases`). The next command downloads again. |
| `doctor` or `update --dry-run` reports a `blocked` finding | The real update would be refused, and the finding quotes the refusal. Apply its fix (for a locally modified file: save the edit, then `update --force`), then run the check again. |
| `doctor` reports a `warning` finding | The update would proceed, but could disturb an in-flight work item, change gates or cross a downgrade boundary. Read the finding and its Recovery lines before you update; the finish-or-park advice is in [Update](update.md#check-before-you-update). |
| `doctor` reports `incomplete-inspection` | Part of the repository could not be read (state file, declarations, or a Git call). The report is not a clean bill of health; fix what it names, or review those parts by hand. An old legacy work item with no `docs/ai-workflow/registry/<id>-artifacts.json` declarations file always reports it, so `doctor` never reaches exit 0 until that item is retired; read the finding rather than chase it. |
| A repository went wrong after an update to 2.8.0 and gates behave differently | See "Approval gates" in [Update](update.md). |

## An install stopped part way

If `bootstrap` or `update` stopped before it finished (a full disk, a permission error, an interrupted terminal), fix the cause the message names and run the same command again. A resumed run finishes the job. If it then lists a file as modified or in the way that you did not edit, that file is a partial write from the interrupted run, and adding `--force` replaces it with the release's. Keep a copy of any file you did edit first.

## Repair workflow data by hand

The Manager prints no command that writes Workflow data: `WORKFLOW_STATE.json`, `WORKFLOW_CONFIG.json` and `docs/ACTIVE_MILESTONE.md` hold your work in flight, and `update` is not a repair for a missing or damaged one, because it recreates every missing state file from a blank template. Find a good copy in Git history instead: `git log --oneline -- docs/ai-workflow/WORKFLOW_STATE.json` lists the revisions, and `git show REVISION:docs/ai-workflow/WORKFLOW_STATE.json` prints one. Put the copy back yourself, then run the command again.

## Exit codes

Every command ends with a status: 0 for success, 1 when it found a problem or had no usable release (for `doctor`, a release it cannot resolve is 2), 2 when it refused to run or could not check. The full table, per command, is in [Exit codes](exit-codes.md).

Use them in scripts: `workflow-manager verify <repo> && echo ok`.

More help: [Install](install.md), [Verify](verify.md), [Exit codes](exit-codes.md), [Glossary](glossary.md).
