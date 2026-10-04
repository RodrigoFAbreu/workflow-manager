# Update

> For: someone moving a repository to a newer Workflow release, or moving the Manager itself to a newer version. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Goal: bring a repository to the newest pinned Workflow release without losing its work-item state.

## Before you start: two things to know

**Workflow 2.8.0 changes a repository's approval gates.** With no committed `docs/ai-workflow/GATE_POLICY.json`, plan approval and milestone acceptance are satisfied automatically, from evidence, for new work items. Implementation (technical) approval becomes automatic only for work items on governing version "2.2"; items on version "2.1" keep a person for it, and items on version "1" keep a person for plan and implementation approval. Earlier releases always asked a person. If your repository wants a person at every gate, commit this file **before** you update:

```json
{"schema_version": 1, "human_approval": true}
```

`human_approval` is the master switch for every gate. To make only some gates a person's, the policy file also accepts a per-gate switch, `gates.<gate>.human`; see the Workflow's `docs/ai-workflow/GATE_POLICY.md`, installed with the release.

The update changes no state file by itself. The Workflow's [gates page](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/gates.md) explains each gate, and the [lifecycle](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/overview.md#lifecycle) shows where they sit.

**Going back to an older release is unsupported.** Once a repository has used a release, do not run `update` with an older `--release-version`. Newer releases add values to the repository's state files that older releases ignore or cannot read. The result can be silent loss of guarantees or a stuck work item. In short: once a repository has run on a release, never move it back to an older one. To undo a bad update, restore the repository from Git instead.

## Prerequisites

- A repository the Manager installed the Workflow into ([Install](install.md)).
- No unfinished edits to release files. Run `workflow-manager verify` first.
- A Manager that knows the release you want. Each Manager release pins a fixed set of Workflow releases; `workflow-manager releases` lists them.

## Steps

1. Check the repository is clean.

   ```bash
   workflow-manager verify /path/to/your/repo
   ```

2. If the Manager does not list the release you want, install the newest Manager release.

   ```bash
   rm -rf wm-latest
   gh release download --repo RodrigoFAbreu/workflow-manager --dir wm-latest \
     --pattern SHA256SUMS --pattern '*.whl'
   (cd wm-latest && sha256sum --ignore-missing -c SHA256SUMS)
   pipx install --force ./wm-latest/workflow_manager-*-py3-none-any.whl
   workflow-manager releases
   ```

3. Decide about human approval gates (see above) and commit `GATE_POLICY.json` if you want it.

4. Update to the newest pinned release.

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

- Step 4 prints `updated /path/to/your/repo to workflow 2.8.0`, then one line per file: `updated`, `added` or removed. A repository already on that release prints `(no change)`.
- Step 5 prints `installation matches workflow 2.8.0`.
- `WORKFLOW_STATE.json`, `docs/ACTIVE_MILESTONE.md` and `.ai-review/` are untouched.

## If it fails

- `refusing to update: these release files were modified locally`: you edited a release file, and the Manager will not discard it silently. Save the edit elsewhere, then re-run with `--force` to replace the file with the release's.
- The update stopped half way: run the same command again. A resumed update does not need `--force`.
- `is not a managed repository`: use [Install](install.md) instead.
- A download error: see [Troubleshooting](troubleshooting.md).
- `--version` still shows an old number after updating the Manager: install the downloaded wheel again with `pipx install --force <wheel>` (`pipx reinstall` reuses the saved wheel path, which may be gone).

Releases are listed in the [release history](releases/README.md). The design is in [`ARCHITECTURE.md`](ARCHITECTURE.md#interruption).
