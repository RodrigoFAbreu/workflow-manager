# Update

> For: someone moving a repository to a newer Workflow release, or moving the Manager itself to a newer version. Last checked with: Workflow Manager 1.6.0, Workflow 2.9.0.

Goal: bring a repository to the newest pinned Workflow release without losing its work-item state.

## Before you start: two things to know

**Workflow 2.8.0 changes a repository's approval gates.** With no committed `docs/ai-workflow/GATE_POLICY.json`, plan approval and milestone acceptance are satisfied automatically, from evidence, for new work items. Implementation (technical) approval becomes automatic only for work items on governing version "2.2"; items on version "2.1" keep a person for it, and items on version "1" keep a person for plan and implementation approval. Earlier releases always asked a person. If your repository wants a person at every gate, commit this file **before** you update:

```json
{"schema_version": 1, "human_approval": true}
```

`human_approval` is the master switch for every gate. To make only some gates a person's, the policy file also accepts a per-gate switch, `gates.<gate>.human`; see the Workflow's `docs/ai-workflow/GATE_POLICY.md`, installed with the release.

The update changes no state file by itself. The Workflow's [gates page](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/gates.md) explains each gate, and the [lifecycle](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/overview.md#lifecycle) shows where they sit.

**Going back to an older release is unsupported.** Once a repository has used a release, do not run `update` with an older `--release-version`. Newer releases add values to the repository's state files that older releases ignore or cannot read. The result can be silent loss of guarantees or a stuck work item. In short: once a repository has run on a release, never move it back to an older one. To undo a bad update, restore the repository from Git instead.

Two Workflow 2.9.0 points. An update never changes the default version in your existing `docs/ai-workflow/WORKFLOW_CONFIG.json`; only a new installation starts on version 2.2. And once you have closed a legacy work item with `/retire-legacy-work-item`, staying on 2.9.0 or later matters even more: older releases have no guard that keeps a retired item closed, so a failing pull-request report could reopen it.

## Prerequisites

- A repository the Manager installed the Workflow into ([Install](install.md)).
- No unfinished edits to release files. Run `workflow-manager verify` first.
- A Manager that knows the release you want. Each Manager release pins a fixed set of Workflow releases; `workflow-manager releases` lists them.

## Check before you update

`doctor` and `update --dry-run` read the repository and tell you what an update would do and which Workflow guarantees it would cross. Neither writes the repository. They may write the release cache (a missing release is fetched) and one temporary copy of the release outside the repository.

```bash
workflow-manager doctor /path/to/your/repo
workflow-manager update /path/to/your/repo --dry-run
```

`doctor` measures the repository against the newest pinned release; put `--release-version` before the command to measure against another. `update --dry-run` prints the same `would ...` lines the real update prints as changes, then `left alone:` for what it keeps (your state files, for one), then the same report.

Reading the report:

- **Installed release, Latest available, Target of this check** are three different versions. The installed release is what the record says, the latest is the newest release this Manager pins, and the target is what the check is measured against.
- **Work items** lists each item's phase, type and governing version. The governing version is a protocol version (`1`, `2.1`, `2.2`), not a release.
- **Findings** have a severity. `blocked`: the real update would be refused, and the refusal is quoted. `warning`: the update would proceed and could disturb something; read it before running. A warning also appears when the inspection could not finish (`incomplete-inspection`): that report is not a clean bill of health. `note`: a fix or default that reaches only new work.
- **Fixes that apply only to new work** says what the update does not change for existing items.
- **Recovery** prints commands for the repository's path. The line that discards uncommitted changes is printed only when the tree is known to be clean; it is an undo only if the tree was clean before the update.

`doctor` exits 0 when it found no `blocked` or `warning` finding, 1 when it found one, and 2 when it could not check (not a managed repository, an unreadable record, or a target release it cannot resolve). `update --dry-run` exits 0 when the update would proceed and 2 when the real update would refuse, with the refusal's own text.

The report is advisory. It looks at the current state files and a few Git facts; it does not search all of history, and it never says an update is safe.

## Steps

1. Check the repository is clean.

   ```bash
   workflow-manager verify /path/to/your/repo
   ```

2. If the Manager does not list the release you want, install the newest Manager release.

   ```bash
   dl=$(mktemp -d)
   gh release download --repo RodrigoFAbreu/workflow-manager --dir "$dl" \
     --pattern SHA256SUMS --pattern '*.whl'
   (cd "$dl" && sha256sum --ignore-missing -c SHA256SUMS)
   pipx uninstall workflow-manager
   pipx install "$dl"/workflow_manager-*-py3-none-any.whl
   rm -rf "$dl"
   workflow-manager releases
   ```

   The temporary folder only holds the download; it is deleted once pipx has installed the Manager.

3. Decide about human approval gates (see above) and commit `GATE_POLICY.json` if you want it.

4. Read the report from "Check before you update" (`doctor`, then `update --dry-run`), then update to the newest pinned release.

   ```bash
   workflow-manager update /path/to/your/repo
   ```

   To pick a release yourself, put the option before the command: `workflow-manager --release-version 2.8.0 update /path/to/your/repo`.

5. Verify again, then review and commit the changes.

   ```bash
   workflow-manager verify /path/to/your/repo
   git -C /path/to/your/repo status
   ```

## What you should see

- Step 4 prints `updated /path/to/your/repo to workflow 2.9.0`, then one line per file: `updated`, `added` or removed. A repository already on that release prints `(no change)`.
- Step 5 prints `installation matches workflow 2.9.0`.
- `WORKFLOW_STATE.json`, `docs/ACTIVE_MILESTONE.md` and `.ai-review/` are untouched.

## If it fails

- `workflow-manager doctor` exits 2 with `is not a managed repository` or an error naming a release: it could not check. See [Troubleshooting](troubleshooting.md).
- `refusing to update: these release files were modified locally`: you edited a release file, and the Manager will not discard it silently. Save the edit elsewhere, then re-run with `--force` to replace the file with the release's.
- The update stopped half way: run the same command again. A resumed update does not need `--force`.
- `is not a managed repository`: use [Install](install.md) instead.
- A download error: see [Troubleshooting](troubleshooting.md).
- `--version` still shows an old number after updating the Manager: remove it and install the freshly downloaded wheel: `pipx uninstall workflow-manager`, then `pipx install <wheel>` (`pipx reinstall` reuses the saved wheel path, which may be gone, and `pipx install --force` can refuse with "a virtual environment already exists").

Releases are listed in the [release history](releases/README.md). The design is in [`ARCHITECTURE.md`](ARCHITECTURE.md#interruption).
