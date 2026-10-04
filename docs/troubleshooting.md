# Troubleshooting

> For: someone who ran a Manager command and got an error. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

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
| A repository went wrong after an update to 2.8.0 and gates behave differently | See "Approval gates" in [Update](update.md). |

## Exit codes

Every command ends with one of these statuses.

| Exit code | Meaning |
|---|---|
| 0 | The command succeeded. `verify` found no problems, or `status` found the repository clean (or not managed). |
| 1 | The command ran and found a problem: `verify` or `status` found differences, or no usable release was available (not pinned, not downloadable, or failing its digest check). |
| 2 | The command refused to run: unknown or missing arguments, a repository that is not managed (or already is), not a Git repository, a collision or local edit that needs `--force`, or an unreadable record. |

Use these in scripts: `workflow-manager verify <repo> && echo ok`.

More help: [Install](install.md), [Verify](verify.md), [Glossary](glossary.md).
