# Release metadata

> For: whoever builds a Workflow release in the `workflow` repository (the contract to implement), and anyone reading a release's `manifest.json`. Last checked with: Workflow Manager 1.12.0, Workflow 2.12.0.

A Workflow release published after the Manager release an operator runs installs without a pin and without a Manager release (see [Releasing](RELEASING.md#a-new-workflow-release)). What the Manager used to hard-code per release is carried by the release itself: an optional `manager` block in `manifest.json`. The manifest is already covered by every digest (`SHA256SUMS`, the manifest asset), so the block is covered too. This page is the normative contract, schema version 1. The design record is `docs/ai-workflow/WORKFLOW_MANAGER_RELEASE_AGNOSTIC_PLAN.md`, 3.4 and 5.

## The block

```json
"manager": {
  "schema_version": 1,
  "min_manager_version": "1.13.0",
  "downgrade_boundary": {
    "posture": "text; empty string when a downgrade loses nothing",
    "undetectable": "text or null",
    "signals": [
      {"name": "kebab-case", "label": "text",
       "detect": {"kind": "state-key", "key": "gate_evidence"}}
    ]
  },
  "new_work_only": ["text"],
  "gate_default_change": "text; empty string for none",
  "conformance": {
    "suites": {"workflow_state_test.py": 1115},
    "portability_exceptions": [
      {"suite": "x_test.py", "test": "Class.test_name", "requires": "path or null",
       "reason": "text", "defect": "path or null"}
    ]
  }
}
```

Keys the Manager reads:

- `manager`: `schema_version`, `min_manager_version`, `downgrade_boundary`, `new_work_only`, `gate_default_change`, `conformance`.
- `downgrade_boundary`: `posture`, `undetectable`, `signals`.
- each signal: `name`, `label`, `detect`.
- `conformance`: `suites`, `portability_exceptions`.
- each portability exception: `suite`, `test`, `requires`, `reason`, `defect`.

## Rules

- **Top-level keys are optional**, each independently. A missing key means "no data for this item". `schema_version` is required and is `1`; another value is refused as needing a newer Manager.
- **Nested objects are all-or-nothing on their required fields.** `conformance`, when present, needs both `suites` (a mapping from a suite file name to a non-negative integer) and `portability_exceptions` (a list); either alone, or `{}`, is refused, not defaulted. `downgrade_boundary`, when present, needs `posture` (a string); `undetectable` defaults to `null` and `signals` to `[]`. Each signal needs `name` (kebab-case), `label` and `detect`. Each portability exception needs `suite`, `test` and `reason`; `requires` and `defect` default to `null`.
- **`min_manager_version`** is a string of digits separated by dots (`1.13.0`): the lowest Manager that reads this release correctly. A Manager older than it refuses an explicit `--release-version` of the release and skips it when it chooses; a development build of the Manager satisfies every minimum. Set it when the release needs a Manager change (below).
- **The detector vocabulary is closed, version 1.** A `detect` object has a `kind` and the keys listed:

  | `kind` | Keys | Matches when |
  |---|---|---|
  | `state-key` | `key` | the key appears anywhere in `WORKFLOW_STATE.json` |
  | `state-value` | `key`, `value` | the key has that value anywhere in it |
  | `item-governing` | `value` | a work item's `governing_workflow_version` equals the string |
  | `item-phase` | `phases` | a work item's phase is one of the listed strings |
  | `item-field` | `key`, `value` | a work item has the key with that value |

  `key` is a non-empty string; `value` is a JSON scalar (string, integer, boolean or null) compared by equality after parsing, type-aware (`true` is not `1`, `"1"` is not `1`); `phases` is a non-empty list of strings. An unknown kind is refused. A condition the vocabulary cannot express is stated in `undetectable`, or the release declares a `min_manager_version` of a Manager that adds the detector.
- **Fail closed.** A block of the wrong shape, an unknown detector kind, another `schema_version` or a malformed version string refuses *that release* (`manifest-shape`) when it is chosen to install or report on. The check runs before a fetched release is stored in the cache, so a refused release never replaces a cache entry.
- **Releases up to 2.12.0** have their data built into the Manager, which uses it always; a block in such a manifest is ignored with a note.
- **Without the block (or an item of it)** a later release installs, but the Manager reports `incomplete-inspection` ("a release carries no compatibility data"): its downgrade guarantees and notes cannot be assessed, `doctor` exits 1, and `update` itself is not refused. That finding describes the release's metadata, never the repository's data.

## What stays in the Manager

Some release knowledge is code, not data: `RETIRED_DEFAULT_FROM`, the `2.6.0` worktree finding and `gate_modes(governing)`, and the five detectors outside the vocabulary (activation, plan-input directories, amendment witnesses, the retirement trailer, the letter-suffixed amendment). A Workflow release that changes any of them, the package format, the schema or the CLI contract needs a Manager release, and says so with `min_manager_version`.

## The Workflow-side follow-up

Not done by this repository, and it does not wait for it. For the `workflow` repository to plan as its own milestone:

1. **Fields.** The build writes the block above into `manifest.json`.
2. **Who fills them.** The release author writes `release/MANAGER_METADATA.json` in the milestone's pull request (posture, notes, gate change, exceptions, `min_manager_version`). The build copies it into the manifest and **computes** `conformance.suites` by test discovery (never hand-written), and refuses a hand-written value that disagrees.
3. **How its CI checks them.** (a) Schema validation against this page, including the detector vocabulary; (b) the counts equal discovery; (c) `min_manager_version` is not newer than the latest released Manager tag; (d) `posture` is non-empty when the release adds a persisted key, phase or status; (e) the manifest of a release up to 2.12.0 is never given a block (immutability); (f) a pre-publish fixture: bootstrap the previous published release, update to the candidate with the released Manager named by `min_manager_version`, and run the candidate's frozen suites in the result.
4. **Order.** The Manager reads the block when present and falls back otherwise, so the Workflow release may land before or after this milestone's Manager release. Until it lands, a new Workflow release installs with the `incomplete-inspection` warning and the maintainer's `chore:` lock bump supplies the suite counts.
