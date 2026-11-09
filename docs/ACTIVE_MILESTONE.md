# Active Milestone

## Milestone

`hermetic-cache-gap-test` -- in implementation (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `8569235`, branch `milestone/hermetic-cache-gap-test`): roadmap row 35 (#189). A `test:` pull request title (releases nothing).

The required check failed in 3 of the last 4 runs of 2026-11-09 only because of `test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap`: it ran the real CLI with a release cache inside `.git` and no release source, so `status` downloaded the release from GitHub, and a GitHub 504 turned the check red. The test now takes its release from a local mirror (`TestStatusContainment` extends `ux.ReleaseCase`; the test passes `--release-source str(self.mirror())`), keeps its cache inside `.git`, keeps its exit-0 and "not a managed repository" assertions, and gains one: the release landed at `<target>/.git/c/<PINNED_NEWEST>`, so a cache moved out of git cannot pass. `docs/ARCHITECTURE.md` says that no test fetches a release at test time. No `src/` change, no other test, no workflow file, no shard change.

### CP1: the hermetic test and its sentence -- complete

- Commit `351fa0c`: `tests/test_operator_ux_report.py`, `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 35 (Done at acceptance); this record.

### Offline measurement (plan sections 1 and 5)

On a clone of `351fa0c`, non-root, under `unshare -rn` (no network), with a read-only link to the primed release cache, from `tests/` with `python3 -B -m unittest`.

| Run | Result |
| --- | --- |
| the known-gap test | OK |
| `test_operator_ux_report.TestStatusContainment` | OK, 10 tests |
| the known-gap test at the base `8569235` (plan section 1) | fails: exit 1, `Network is unreachable` fetching `SHA256SUMS` from github.com |

### Failure-only mutations (plan section 3)

Each on a fresh copy of the clone of `351fa0c`, the known-gap test alone, offline. The unmutated copy passes.

| # | Mutation | Result |
| --- | --- | --- |
| M1 | delete `"--release-source", str(self.mirror()),` | fails: `1 != 0`, `Network is unreachable` |
| M2 | cache `self.workdir() / "c"` (outside `.git`) | fails on the literal-path pin (`False is not true`) |
| M3 | expected message `a managed repository ` (as the plan words it) | **passes**: that text is a substring of the real message `not a managed repository`, so the mutation does not change what is pinned |
| M3' | expected message `is a managed repository` | fails: `'is a managed repository' not found` |
| M4 | expected exit code `0` to `1` | fails: `0 != 1` |

M3 as written in plan section 3 was not a failing mutation; M3' (a message the output does not contain) is the one that proves the message pin, and flow 5 of the functional review should apply M3' in its place.

### Network-reaching tests (plan section 6)

The plan's measurement of the full selection of `8569235` under `unshare -rn` found exactly one test that fetches from github.com: this one. No follow-up is listed on #189.
