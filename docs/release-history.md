# Release history

> For: someone choosing a Manager version or wondering what changed. Last checked with: Workflow Manager 1.14.8, Workflow 2.29.1.

One line per Workflow Manager release, newest first. The Manager's version is the Git tag. Each release links to its GitHub page, which lists the changes and carries the files. A Manager release carries no Workflow release of its own. The last column says which Workflow releases it can install.

| Manager | Date | What changed, in plain words | Workflow releases it installs | Release page |
|---|---|---|---|---|
| 1.14.8 | 2026-11-04 | The retention view counts what it echoes by one rule, states its limits in words, and tests every cause exactly; nothing else changes for someone installing. | 2.3.1 and every later published release | [v1.14.8](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.8) |
| 1.14.7 | 2026-11-03 | `update --dry-run` now decides the same way as `update` for a record that has no recorded Workflow version, so a dry run no longer promises something the real update would not do. | 2.3.1 and every later published release | [v1.14.7](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.7) |
| 1.14.6 | 2026-11-03 | Names a missing or empty recorded Workflow version in words in the messages that quote it, instead of `None` or a blank. | 2.3.1 and every later published release | [v1.14.6](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.6) |
| 1.14.5 | 2026-11-03 | A fix to the Manager's own test runner: a run that cannot succeed (a release the cache cannot serve, or too little free disk space) now stops at its start and says why; nothing changes for someone installing. | 2.3.1 and every later published release | [v1.14.5](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.5) |
| 1.14.4 | 2026-11-01 | The retention view gives the right next step when GitHub rate-limits it, refuses a linked scripts directory, and shortens its lists and counts. | 2.3.1 and every later published release | [v1.14.4](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.4) |
| 1.14.3 | 2026-11-01 | The retention report refuses control characters and out-of-range values before printing them. | 2.3.1 and every later published release | [v1.14.3](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.3) |
| 1.14.2 | 2026-11-01 | A message about an installation record with no `workflow_version` says so, and each error ends in one next step. | 2.3.1 and every later published release | [v1.14.2](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.2) |
| 1.14.1 | 2026-10-28 | Discovering Workflow releases no longer hangs on a slow connection: the read gives up after a bounded wait. | 2.3.1 and every later published release | [v1.14.1](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.1) |
| 1.14.0 | 2026-10-27 | Adds `--retention`, which reports the state of the archive of finished work. | 2.3.1 and every later published release | [v1.14.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.14.0) |
| 1.13.4 | 2026-10-25 | Clearer wording and exit paths in the messages the Manager prints. | 2.3.1 and every later published release | [v1.13.4](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.13.4) |
| 1.13.3 | 2026-10-25 | An explicit run's "Latest available" lists only releases this Manager can install. | 2.3.1 and every later published release | [v1.13.3](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.13.3) |
| 1.13.2 | 2026-10-22 | Clearer refusals for a version below the floor or not a version, and `doctor`'s "Latest available" says what the release listing left out. | 2.3.1 and every later published release | [v1.13.2](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.13.2) |
| 1.13.1 | 2026-10-17 | A fix to the Manager's own release process; nothing changes for someone installing. | 2.3.1 and every later published release | [v1.13.1](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.13.1) |
| 1.13.0 | 2026-10-17 | Installs new Workflow releases without a new Manager release: it discovers published releases, verifies them by their checksums and reads their metadata. | 2.3.1 and every later published release | [v1.13.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.13.0) |
| 1.12.0 | 2026-10-16 | Adds Workflow 2.12.0, which gives review rounds from round 2 the changes since the last review and refuses a malformed verdict. | 2.3.1 to 2.12.0 | [v1.12.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.12.0) |
| 1.11.0 | 2026-10-13 | Adds Workflow 2.11.0, which checks a plan's checkpoint anchors before any plan review instead of first at plan approval. | 2.3.1 to 2.11.0 | [v1.11.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.11.0) |
| 1.10.0 | 2026-10-12 | Adds Workflow 2.10.0, which refuses to create a new work item while a repository still defaults to governing version 2.1; `doctor` and `update --dry-run` warn about that default before you update. | 2.3.1 to 2.10.0 | [v1.10.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.10.0) |
| 1.9.0 | 2026-10-11 | Adds Workflow 2.9.2, a fix release: the generation record is the last commit of a functional-review fix round, and its trailers are the final paragraph alone. | 2.3.1 to 2.9.2 | [v1.9.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.9.0) |
| 1.8.0 | 2026-10-10 | Every message names its cause and a concrete next step, and `status` shows work in flight. | 2.3.1 to 2.9.1 | [v1.8.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.8.0) |
| 1.7.0 | 2026-10-10 | Adds Workflow 2.9.1, a fix release: a review that asks for changes no longer blocks the fix round that follows it. | 2.3.1 to 2.9.1 | [v1.7.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.7.0) |
| 1.6.0 | 2026-10-09 | Adds `workflow-manager doctor` and `update --dry-run`, which report what an update would do, and which Workflow guarantees it would cross, without changing anything. | 2.3.1 to 2.9.0 | [v1.6.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.6.0) |
| 1.5.0 | 2026-10-08 | Adds Workflow 2.9.0, which can close a long-finished legacy work item and starts new installations on governing version 2.2. | 2.3.1 to 2.9.0 | [v1.5.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.5.0) |
| 1.4.0 | 2026-10-04 | Adds Workflow 2.8.0, which makes approval gates automatic unless a repository asks for human approval. | 2.3.1 to 2.8.0 | [v1.4.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.4.0) |
| 1.3.0 | 2026-10-02 | Adds Workflow 2.7.0 (the protocol that lets a program drive the Workflow). | 2.3.1 to 2.7.0 | [v1.3.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.3.0) |
| 1.2.0 | 2026-10-01 | Workflow releases are downloaded, checked against their pins and cached, instead of being stored inside the Manager. | 2.3.1 to 2.6.0 | [v1.2.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.2.0) |
| 1.1.0 | 2026-09-29 | First Manager release published on GitHub, with a release process driven by Git tags. | 2.3.1 to 2.6.0 (stored inside the Manager) | [v1.1.0](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.1.0) |
| 1.0.0 | 2026-09-05 | First packaged Manager: an unpublished local build, never released on GitHub. | 2.3.1 (stored inside the Manager) | none |

## Workflow releases and the Manager that first installs them

| Workflow | First available in Manager |
|---|---|
| 2.3.1 | 1.0.0 |
| 2.4.0, 2.5.0, 2.5.1, 2.6.0 | 1.1.0 |
| 2.7.0 | 1.3.0 |
| 2.8.0 | 1.4.0 |
| 2.9.0 | 1.5.0 |
| 2.9.1 | 1.7.0 |
| 2.9.2 | 1.9.0 |
| 2.10.0 | 1.10.0 |
| 2.11.0 | 1.11.0 |
| 2.12.0 | 1.12.0 |
| 2.13.0 and every later release | 1.13.0 (any Manager from 1.13.0 on installs it; the release's own `min_manager_version` decides) |

To see exactly what your installed Manager can install, run `workflow-manager releases`. To move to a newer Manager, see [Update](update.md). For what each Workflow release changed, read the [Workflow repository](https://github.com/RodrigoFAbreu/workflow#readme).
