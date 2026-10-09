# Exit codes

> For: anyone who runs `workflow-manager` from a script or wants to know what a status means. Last checked with: Workflow Manager 1.6.0, Workflow 2.9.0.

Every command ends with a status. This is the one table of them. The quick fix for each error message is in [common problems](common-problems.md).

| Code | Command | Meaning | What to do |
|---|---|---|---|
| 0 | every command | It succeeded. `verify` found no problems. `status` found the repository intact, or not managed. `doctor` found nothing to warn about. `update --dry-run` printed its report and the real update would not be refused. `package verify` accepted the archive. | Nothing. |
| 1 | `verify`, `status` | The installed files differ from the release (`N problem(s)`). | Undo the listed edits with `git checkout -- <file>`, or run `update --force` to restore the release's files. |
| 1 | `doctor` | At least one finding is `blocked` or a `warning`. An incomplete inspection counts as a warning. | Read the report and its recovery lines before you update. |
| 1 | any command that needs a Workflow release (`bootstrap`, `update`, `update --dry-run`, `verify`, `status`) | No usable release: the version is not pinned, it is not cached and cannot be downloaded, or a download fails its digest, size or manifest check. | Connect to the network once, point `--release-source` at a mirror, or install a newer Manager. If a digest does not match after a retry, do not install, and report it. |
| 2 | every command | The command line did not parse: an unknown command or option, or a missing argument. | Put global options such as `--release-version` before the command: `workflow-manager --release-version 2.9.0 update <repo>`. |
| 2 | `bootstrap` | The target is not a directory or not a Git repository, it is already managed (or its record is unreadable), or it has files in the way of the release's files. | Use `update` for a managed repository, run `git init`, or move your files away or re-run with `--force`. For an unreadable record, delete `.workflow-manager/` and bootstrap again. |
| 2 | `update`, `update --dry-run` | The repository is not managed, its record is unreadable, managed files were edited locally, or the release needs paths the repository uses for something else. The dry run refuses in the same cases as the real update. The dry run also refuses when the release cache or a temporary directory named in the environment is inside the repository. | Run `bootstrap` first; save your edits and re-run with `--force`; or move the files in the way. For an unreadable record, delete `.workflow-manager/` and bootstrap again. For the cache or temporary directory, choose another cache with `--release-cache`, or unset `TMPDIR`. |
| 2 | `doctor` | It could not check: the repository is not managed, its record is unreadable, or the target release could not be resolved. It also refuses when the release cache or a temporary directory named in the environment is inside the repository. | Fix what the message names, then run it again. Choose another cache with `--release-cache`, or unset `TMPDIR`. |
| 2 | `verify` | The repository is not managed, or its record is unreadable. | Run `bootstrap`, or delete `.workflow-manager/` and bootstrap again. |
| 2 | `status` | Its record is unreadable. (A repository that is not managed is exit 0.) | Delete `.workflow-manager/` and run `bootstrap` again. |
| 2 | `uninstall` | The repository is not managed, or its record is unreadable. | Delete `.workflow-manager/` by hand if the record is damaged. |
| 1 | `package verify` | The archive does not match `--sha256`, cannot be read, or is not a valid package. | Download the archive again and check it against `SHA256SUMS`. |

`releases` exits 0. `package build` exits 0 when it finishes, and 1 when the directory is not a valid release. Any other error in the Manager's own code ends as a Python traceback with exit 1; report it.

Use them in scripts: `workflow-manager verify <repo> && echo ok`.
