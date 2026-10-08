# Release history

> For: someone choosing a Manager version or wondering what changed. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

One line per Workflow Manager release, newest first. The Manager's version is the Git tag, and every release is listed on the [releases page](https://github.com/RodrigoFAbreu/workflow-manager/releases). A Manager release carries no Workflow release of its own. The last column says which Workflow releases it can install.

| Manager | Date | What changed, in plain words | Workflow releases it installs |
|---|---|---|---|
| 1.5.0 | 2026-10-08 | Adds Workflow 2.9.0, which can close a long-finished legacy work item and starts new installations on governing version 2.2. | 2.3.1 to 2.9.0 |
| 1.4.0 | 2026-10-04 | Adds Workflow 2.8.0, which makes approval gates automatic unless a repository asks for human approval. | 2.3.1 to 2.8.0 |
| 1.3.0 | 2026-10-02 | Adds Workflow 2.7.0 (the protocol that lets a program drive the Workflow). | 2.3.1 to 2.7.0 |
| 1.2.0 | 2026-10-01 | Workflow releases are downloaded, checked against their pins and cached, instead of being stored inside the Manager. | 2.3.1 to 2.6.0 |
| 1.1.0 | 2026-09-29 | First Manager release published on GitHub, with a release process driven by Git tags. | 2.3.1 to 2.6.0 (stored inside the Manager) |
| 1.0.0 | 2026-09-05 | First packaged Manager: an unpublished local build, never released on GitHub. | 2.3.1 (stored inside the Manager) |

## Workflow releases and the Manager that first installs them

| Workflow | First available in Manager |
|---|---|
| 2.3.1 | 1.0.0 |
| 2.4.0, 2.5.0, 2.5.1, 2.6.0 | 1.1.0 |
| 2.7.0 | 1.3.0 |
| 2.8.0 | 1.4.0 |
| 2.9.0 | 1.5.0 |

To see exactly what your installed Manager can install, run `workflow-manager releases`. To move to a newer Manager, see [Update](../update.md). For what each Workflow release changed, read the [Workflow repository](https://github.com/RodrigoFAbreu/workflow#readme).
