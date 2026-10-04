# Install

> For: someone setting up the Workflow Manager and putting the Workflow into a repository for the first time. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Goal: have the `workflow-manager` command on your machine and a repository that runs the Workflow.

## Prerequisites

- Python 3.11 or newer and Git.
- [pipx](https://pipx.pypa.io/).
- The [GitHub CLI](https://cli.github.com/) (`gh`), signed in.
- A network connection for the first install. The Manager downloads each Workflow release once, then works offline.
- A Git repository to install into. It must already exist (`git init` is enough).

## Steps

1. Download the latest Manager release and check it.

   ```bash
   gh release download --repo RodrigoFAbreu/workflow-manager --dir wm-latest \
     --pattern SHA256SUMS --pattern '*.whl'
   (cd wm-latest && sha256sum --ignore-missing -c SHA256SUMS)
   ```

2. Install it.

   ```bash
   pipx install ./wm-latest/workflow_manager-*-py3-none-any.whl
   workflow-manager --version
   ```

3. See which Workflow releases this Manager knows about.

   ```bash
   workflow-manager releases
   ```

4. Install the newest of them into your repository.

   ```bash
   workflow-manager bootstrap /path/to/your/repo
   ```

5. Check the installation.

   ```bash
   workflow-manager verify /path/to/your/repo
   ```

6. Look at what was added (`git status`) and commit it.

Optional choices for step 4:

- A different Workflow release: put the option before the command, for example `workflow-manager --release-version 2.7.0 bootstrap /path/to/your/repo`.
- A smaller install: add `--profile runtime`. The default `full` profile also installs the Workflow's own conformance checks. See [Glossary](glossary.md#profile).

## What you should see

- Step 2 prints `workflow-manager 1.4.0` (or a newer number).
- Step 3 lists one line per Workflow release, from 2.3.1 to 2.8.0, each ending in `[cached]` or `[not cached]`.
- Step 4 prints `bootstrapped workflow 2.8.0 (full) into /path/to/your/repo` and a count of managed, state and merged files. The first run of a release downloads it, so it takes a moment.
- Step 5 prints `installation matches workflow 2.8.0` and exits with status 0.
- The repository now has `.claude/commands/`, `scripts/`, `docs/ai-workflow/` and `.workflow-manager/installation.json` (the [installation record](glossary.md#installation-record)).

## Approval gates after a fresh install

A new Workflow 2.8.0 installation has no `docs/ai-workflow/GATE_POLICY.json`. Without it, the Workflow satisfies its approval gates automatically from evidence. If you want a person to approve every gate, create that file with this content and commit it:

```json
{"schema_version": 1, "human_approval": true}
```

`human_approval` is the master switch for every gate. To make only some gates a person's, the policy file also accepts a per-gate switch, `gates.<gate>.human`; see the Workflow's `docs/ai-workflow/GATE_POLICY.md`, installed with the release.

[Update](update.md) explains this in more detail, and the Workflow's [gates page](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/gates.md) describes each gate.

## If it fails

- `is not a Git repository`: run `git init` in the target first.
- `already managed`: the repository already has the Workflow. Use [Update](update.md) to change its release.
- A list of files that collide: your repository already keeps its own file where a release file goes (`scripts/` and `.claude/commands/` are ordinary names). Move your files, or re-run with `--force` to replace them with the release's.
- A download error with no network: the release is not in the cache yet. Connect once, or see [Troubleshooting](troubleshooting.md).
- `workflow-manager: command not found`: run `pipx ensurepath` and open a new terminal.
- `--version` shows `1.0.0` after an editable install: run `pipx reinstall workflow-manager` once.

More: [Troubleshooting](troubleshooting.md), [Verify](verify.md).
