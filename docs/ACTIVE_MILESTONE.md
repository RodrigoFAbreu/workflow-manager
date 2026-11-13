# Active Milestone

## Milestone

`docs-restamp` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `bfd255f`, branch `milestone/docs-restamp`): roadmap row 41 (#156). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_DOCS_RESTAMP_PLAN.md`.

Every stamped user page the first re-check left alone says only what is true of Workflow Manager 1.18.1 and Workflow 2.29.3, and its stamp says so; `docs/release-history.md` row 1.14.6 describes a null and an empty recorded version separately. A `docs:` change that releases nothing.

**Next action:** CP2 (the map, the metadata page, the project README, the history row, the roadmap).

## Per-page record

How each page was checked: the sandbox is a scratch Git repository bootstrapped from the cached release 2.29.3, every command run offline under `unshare -rn` with `PYTHONPATH=src`; the source is `src/workflow_manager/`.

| Page | Checked how | Text changed | Stamp |
| --- | --- | --- | --- |
| `docs/exit-codes.md` | every row against the exit paths of `cli.py` (`main`'s error mapping, `cmd_status`, `cmd_verify`, `cmd_adopt_retention_policy`, `cmd_retention_cleanup`, `cmd_package`) and the sandbox: global option after the command (2), unmanaged `status` (0), `verify` and `uninstall` of an unmanaged repository (2), not a Git repository (2), already managed (2), `v2.12.0` for `verify` (1) and `doctor` (2), `update --dry-run` below the installed release, `package verify` with a bad file and a bad `--sha256` (1), `package build` of a directory with no manifest (1), `package` with no action (2), `adopt-retention-policy` with no file and with a wrong sentence (2), `retention-cleanup` refusals and "nothing to do" (2 and 0), `--help` listing both retention commands | none: every row already matches | moved to 1.18.1 / 2.29.3 |
| `docs/retention.md` | the policy file, the adoption preview and the confirmed adoption, the `status --retention` policy block and the "not available" section, `verify` for a not-adopted policy, `retention-cleanup` preview, "nothing to do" and a wrong `--confirm`, run in the sandbox; the cleanup preflight order, the 2.25.5 floor, the plan and run text against `retention_cleanup.py` and `retention_run.py` (the same pages 1.18.1 reworded) | none: the text matches the code and the sandbox output (the report and the confirmed run's per-item output need GitHub and a Workflow with finished items; the pinned tests `test_retention_run.py` and `test_retention_cleanup.py` carry them) | moved |
| `docs/common-problems.md` | every quoted message looked up in the source (all 25 found: `install.py`, `installation.py`, `source.py`, `release.py`, `compatibility.py`, `cli.py`, `advice.py`); the sandbox outputs of the rows for a missing directory, a non-repository, an already managed repository, an unmanaged one, a global option after the command and a name that is not a version | none | moved |
| `docs/glossary.md` | each term against the current behaviour: the installation record's fields (`installation.py`), the merged files (`install.py`), the cache default (`source.py`), `uninstall` (`install.uninstall`: it also removes the `.workflow-manager/` folder, so an adopted retention policy goes with it, as `docs/retention.md` says) | the example versions of the Manager and Workflow release (1.5.0, 2.9.0) read 1.18.1 and 2.29.3; the Uninstall entry now says the `.workflow-manager/` folder is removed too, and what that holds. No retention term added: `docs/retention.md` defines each word it uses | moved |
