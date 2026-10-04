# Verify

> For: someone who wants to know whether a repository's Workflow installation is intact. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Goal: confirm that every installed Workflow file is exactly the one its release shipped.

## Prerequisites

- The `workflow-manager` command ([Install](install.md)).
- A repository the Manager installed the Workflow into.

## Steps

1. Ask for a summary of the repository.

   ```bash
   workflow-manager status /path/to/your/repo
   ```

2. Compare every installed file with its release.

   ```bash
   workflow-manager verify /path/to/your/repo
   ```

   Both `status` and `verify` measure the repository against the release its own installation record names, not against the newest one. A repository on an older release is not reported as broken just because a newer release exists.

3. Check the exit status.

   ```bash
   echo $?
   ```

4. To see which Workflow releases the Manager can install, and which are already downloaded:

   ```bash
   workflow-manager releases
   ```

## What you should see

- Step 1 prints `workflow 2.8.0 (full profile) — clean`, then a `source:` line naming the package and its digest.
- Step 2 prints `<path>: installation matches workflow 2.8.0`.
- Step 3 prints `0`.

## If it fails

- `1 problem(s)` followed by lines such as `modified: scripts/workflow_state.py`: someone edited a release file. Undo the edit with `git checkout -- <file>`, or keep it and expect `update` to refuse until you pass `--force`, which throws your local edit away. Other lines say `missing:` (a release file is gone), `unexpected:` (a file is present but was never installed) or `not-executable:`.
- `not a managed repository`: the Manager did not install the Workflow here. See [Install](install.md).
- An error about a missing release or the network: the release the repository names is not in the cache and cannot be downloaded. See [Troubleshooting](troubleshooting.md).

Exit statuses are listed in [Troubleshooting](troubleshooting.md#exit-codes). For the check behind the command, see [`ARCHITECTURE.md`](ARCHITECTURE.md#release-integrity).
