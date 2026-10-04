# Workflow Manager

> For: anyone who wants to put the Workflow into a repository. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

[![Verification](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml/badge.svg?branch=main&event=push)](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml?query=branch%3Amain+event%3Apush)
[![Nightly](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml/badge.svg?event=schedule)](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml?query=event%3Aschedule)
[![Release](https://img.shields.io/github/v/release/RodrigoFAbreu/workflow-manager?sort=semver)](https://github.com/RodrigoFAbreu/workflow-manager/releases)

Workflow Manager is a small command-line tool. It installs a published
Workflow release into a Git repository, moves the repository to a newer
release, and checks that the installed files are still the release's files.
It never overwrites the work-item state the repository builds up.

## How the pieces fit

[Workflow](https://github.com/RodrigoFAbreu/workflow#readme) is the development process and its commands, installed into a repository. [Workflow Manager](https://github.com/RodrigoFAbreu/workflow-manager#readme) installs, updates and verifies the Workflow from published, digest-pinned releases. [Workflow Controller](https://github.com/RodrigoFAbreu/workflow-controller#readme) runs the Workflow's lifecycle steps automatically and stops wherever a person is needed.

## Quick start

About five minutes. You need Python 3.11 or newer, Git, [pipx](https://pipx.pypa.io/) and the
[GitHub CLI](https://cli.github.com/) (`gh`), signed in.

```bash
# 1. Install the latest Manager release (downloaded into a temporary folder,
#    which is deleted afterwards; pipx keeps the installed Manager).
dl=$(mktemp -d)
gh release download --repo RodrigoFAbreu/workflow-manager --dir "$dl" \
  --pattern SHA256SUMS --pattern '*.whl'
(cd "$dl" && sha256sum --ignore-missing -c SHA256SUMS)
pipx install "$dl"/workflow_manager-*-py3-none-any.whl
rm -rf "$dl"
workflow-manager --version

# 2. Put the newest pinned Workflow release into a Git repository.
workflow-manager bootstrap /path/to/your/repo

# 3. Check the result.
workflow-manager verify /path/to/your/repo
```

Step 3 should print `installation matches workflow 2.8.0` and exit with
status 0. If something goes differently, see
[Troubleshooting](docs/troubleshooting.md).

## Where to go next

| I want to... | Page |
|---|---|
| Install the Manager, or put the Workflow into a repository | [Install](docs/install.md) |
| Move a repository to a newer Workflow release | [Update](docs/update.md) |
| Check that an installation is intact | [Verify](docs/verify.md) |
| Fix an error message | [Troubleshooting](docs/troubleshooting.md) |
| Look up a word (pin, release cache, profile...) | [Glossary](docs/glossary.md) |
| See what each Manager release changed | [Release history](docs/releases/README.md) |
| Understand the Workflow itself | [Workflow lifecycle](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/overview.md#lifecycle) |
| Work on the Manager's code | [Development](docs/development.md) |
| Find every page | [Documentation map](docs/README.md) |

The commands, in one place:

```bash
workflow-manager releases                  # the pinned Workflow releases, and which are cached
workflow-manager status    /path/to/repo   # is it managed, is it clean
workflow-manager bootstrap /path/to/repo   # install into a repository
workflow-manager verify    /path/to/repo   # is every installed file as released
workflow-manager update    /path/to/repo   # move to the newest pinned release
workflow-manager uninstall /path/to/repo   # remove the managed files
workflow-manager --version                 # the Manager's own version
```

## Good to know

- Nothing is installed unchecked. A downloaded Workflow release must match
  its pin (a digest recorded inside the Manager) and its published
  `SHA256SUMS`, and every file is checked as it is copied.
- The first use of a Workflow release downloads it into a local cache.
  After that, every command works offline.
- `update` never touches `WORKFLOW_STATE.json`, `docs/ACTIVE_MILESTONE.md`
  or `.ai-review/`. It refuses to overwrite a release file you edited,
  unless you pass `--force`.
- Both `bootstrap` and `update` can be re-run after an interruption.
- Updating can change a repository's approval gates (with no `GATE_POLICY.json`, plan approval and acceptance become automatic for new work items). Read
  [Update](docs/update.md) before you update to Workflow 2.8.0.
