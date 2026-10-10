# Verify

> For: someone who wants to know whether a repository's Workflow installation is intact. Last checked with: Workflow Manager 1.8.0, Workflow 2.9.1.

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

- Step 1 prints `workflow 2.9.1 (full profile) — clean`, then a `source:` line naming the package and its digest, then `work in flight:`: `none`, or one line per active work item with its phase, type and governing version. A `next:` line ends the output.
- Step 2 prints `<path>: installation matches workflow 2.9.1`.
- Step 3 prints `0`.

## If it fails

- `1 problem(s)` followed by lines such as `modified: scripts/workflow_state.py`: someone edited a release file. The `next:` line names `update` to put the release's files back (`--force` replaces your edit, so keep a copy first); or undo the edit with `git checkout -- <file>`. Other lines say `missing:` (a release file is gone), `unexpected:` (a file is present but was never installed) or `not-executable:`.
- `is not a managed repository`: the Manager did not install the Workflow here. Run `workflow-manager bootstrap TARGET`; see [Install](install.md).
- `the installation record ... is unreadable`: see [Common problems](common-problems.md).
- An error about a missing release or the network: the release the repository names is not in the cache and cannot be downloaded. See [Common problems](common-problems.md).

Exit statuses are listed in [Exit codes](exit-codes.md). For the check behind the command, see [`ARCHITECTURE.md`](ARCHITECTURE.md#release-integrity).
