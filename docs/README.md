# Documentation map

> For: anyone looking for the right Workflow Manager page. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Start with the [project README](../README.md) for what the Manager is and a five-minute quick start. This page says where everything else is.

## I want to...

| I want to... | Go to |
|---|---|
| Install the Manager and put the Workflow into a repository | [Install](install.md) |
| Move a repository to a newer Workflow release | [Update](update.md) |
| Check that a repository's installation is intact | [Verify](verify.md) |
| Fix an error message or look up an exit code | [Troubleshooting](troubleshooting.md) |
| Look up a Manager word (pin, release cache, profile...) | [Glossary](glossary.md) |
| Look up a Workflow word (work item, approval gate...) | [Workflow glossary](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/glossary.md) |
| See what each Manager release changed | [Release history](releases/README.md) |
| Learn how the Workflow runs, step by step | [Workflow lifecycle](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/overview.md#lifecycle) |
| Understand who approves what | [Workflow gates](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/gates.md) |
| Run the Workflow's steps automatically | [Workflow Controller](https://github.com/RodrigoFAbreu/workflow-controller#readme) and its [compatibility page](https://github.com/RodrigoFAbreu/workflow-controller/blob/main/docs/compatibility.md) |
| Change the Manager's code or tests | [Development](development.md) |

## Maintainer reference

These pages are for people who maintain the Manager. They are not step-by-step guides.

| Page | What it holds |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The design: packages, pins, the release cache, what the installer owns, how the tests run. |
| [RELEASING.md](RELEASING.md) | How the Manager is released and how a new Workflow release gets pinned. |
| [MIGRATION.md](MIGRATION.md) | The history of how the first Workflow packages were made. |
| [ROADMAP.md](ROADMAP.md) | Where the work is heading. |
| [defects/](defects/) | Problems found in Workflow releases, written up rather than repaired. |
