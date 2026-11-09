# Active Milestone

## Milestone

`hermetic-cache-gap-test` -- complete, accepted by policy 2026-11-09 (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `8569235`, branch `milestone/hermetic-cache-gap-test`): roadmap row 35 (#189). A `test:` pull request title (releases nothing).

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

## Functional review checklist

Code under test: branch `milestone/hermetic-cache-gap-test` at `3924163` (the code is `351fa0c`; the rest is records). The checks are offline and write nothing into the product clone. Run them in a scratch clone, not in the product clone.

### Setup

- Tools on the `PATH` the sandbox allows (`/usr/bin:/bin`): `python3` 3.x, `git`, `unshare` (util-linux), `sed`, `tr`, `grep`. Run the shell commands under bash; the `off` function below relies on word-splitting rules that zsh does not share.
- The primed release cache for `2.12.0` (`~/.cache/workflow-manager/releases/2.12.0`, present on the reviewing machine). Flows 5 and 7 read it through a link. If it is missing, prime it once with network or a mirror (`WORKFLOW_MANAGER_RELEASE_SOURCE`), then rerun.
- No network, no GitHub, no `gh`, `claude`, `codex` or `ssh`: none of these flows calls them. The release "mirror" the test uses is a local directory, not a socket.

```bash
PC=/home/rodrigo/Workspace/workflow-manager          # the product clone (read only)
S=$(mktemp -d "$HOME/.cache/hc-fr.XXXXXX")           # scratch; an empty writable directory
mkdir -p "$S/home" "$S/tmp" "$S/cache/workflow-manager"
ln -s "$HOME/.cache/workflow-manager/releases" "$S/cache/workflow-manager/releases"
git clone -q --no-hardlinks "$PC" "$S/cand" && git -C "$S/cand" checkout -q milestone/hermetic-cache-gap-test
python3 -m compileall -q "$S/cand/src"
off() { env -i PATH=/usr/bin:/bin HOME="$S/home" XDG_CACHE_HOME="$S/cache" TMPDIR="$S/tmp" PYTHONDONTWRITEBYTECODE=1 unshare -rn "$@"; }
T=test_operator_ux_report.TestStatusContainment.test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap
```

If `unshare -rn` is refused in the sandbox, the sandbox's own network isolation is the no-network guarantee and the `unshare` step is only extra proof; say which one applied.

### Test data

Nothing to seed. The test builds its own target repository, a mirror of the three `2.12.0` assets, and a cache inside `.git` in temporary folders it cleans up.

### Flows

1. **Scope.** `git -C "$S/cand" diff --stat 8569235357ed88edd5487bbc6db98fd4c4166bc7 HEAD -- src tools tests docs/ARCHITECTURE.md .github`
   - Expect: exactly `tests/test_operator_ux_report.py` and `docs/ARCHITECTURE.md`. Nothing under `src/`, `tools/` or `.github/`.

2. **The test takes a mirror and keeps its cache in git.** `sed -n '/^class TestStatusContainment/p' "$S/cand/tests/test_operator_ux_report.py"` and `sed -n '/def test_an_unmanaged_target_with_a_cache_inside_git/,/^$/p' "$S/cand/tests/test_operator_ux_report.py"`
   - Expect: the class is `TestStatusContainment(ux.ReleaseCase)`. The test's argv has `"--release-source", str(self.mirror()),` and `"--release-cache", str(cache)` with `cache = target / ".git" / "c"`.

3. **The assertions.** The same `sed` output from flow 2.
   - Expect: `returncode, 0`, `assertIn("not a managed repository", proc.stdout)`, and `assertTrue((target / ".git" / "c" / PINNED_NEWEST).is_dir(), ...)`. The docstring says the release comes from a local mirror.

4. **The sentence in `docs/ARCHITECTURE.md`.** `tr '\n' ' ' < "$S/cand/docs/ARCHITECTURE.md" | tr -s ' ' | grep -o 'After priming, a run needs no network.\{0,400\}'` and `git -C "$PC" diff 8569235 HEAD -- docs/ARCHITECTURE.md | grep '^+' | grep -ci 'milestone\|hermetic-cache-gap'`
   - Expect: the sentence reads "...no test fetches a release at test time: a test that runs the CLI against a release the cache does not hold gives it a `--release-source` mirror or a `--release-dir`." The count is `0`. (`grep -c` prints `0` and exits 1 when nothing matches; that exit is expected.)

5. **The known-gap test passes, and each mutation makes it fail (offline).** Apply each mutation to its own copy of `$S/cand` with `sed` or an equivalent edit, then run the test there. Each copy must differ from the candidate; a mutation that changes nothing proves nothing.
   - Unmutated copy: `cd "$S/cand/tests" && off python3 -B -m unittest "$T"` → `OK`.
   - **M1** delete `"--release-source", str(self.mirror()),` → FAILED, `1 != 0`, `Network is unreachable`.
   - **M2** change `cache = target / ".git" / "c"` to `cache = self.workdir() / "c"` → FAILED, `False is not true` (the literal-path pin).
   - **M3'** change the expected message to `is a managed repository` → FAILED, `'is a managed repository' not found`. **Use M3', not the plan's M3** (see "Known limitations"): the plan's M3 passes by design and is not a defect.
   - **M4** change the expected exit code `0` to `1` → FAILED, `0 != 1`.
   - Do not expect M3 (`a managed repository `) to fail. It is a substring of the real message and passes.

6. **Full-environment checks (run on the reviewing machine, not in the sandbox).** `python3 tools/check_docs.py`; `python3 tests/run_all.py --select test_operator_ux_report.py`; `python3 tests/run_all.py --select test_docs.py`, all run inside `$S/cand` (never in the product clone).
   - Expect: each exits 0, with no `OrphanProcessError`. These are the gate-style checks; they need the cache and may take minutes.

7. **The whole class, offline.** `cd "$S/cand/tests" && off python3 -B -m unittest test_operator_ux_report.TestStatusContainment`
   - Expect: `OK`, `Ran 10 tests`.

### Expected results summary

Flows 1–5 and 7 pass offline in the scratch clone with the cache linked (measured on the reviewing machine while preparing this checklist: all as listed above, including the four mutations with M3'). Flow 6 is for the reviewing machine.

### Known limitations and out of scope

- **Open optional findings, not fixed in this item (for the owner at acceptance).** The sentence "no test fetches a release at test time" is literally inaccurate. The `_Stub` loopback servers in `tests/test_discovery.py` serve release data over HTTP at test time, and the mirror itself is a fetch from the test's point of view. The reviewers suggest "no test fetches a release from a remote host". Recorded as `F-970ec6f6974f`, `F-196f4418ed11`, `F-a46413272791` (LIR1-001) and `F-ebd534ec9f25`. A wording change now would be a new implementation round, so the disposition is the owner's at acceptance.
- **M3 deviation.** The approved plan's M3 (`a managed repository `) is a substring of the real message, so it does not fail. M3' is used in its place (`F-004f88a655fc`, LIR1-002). Plan section 3's table still lists M3.
- **Loopback tests are not claimed green offline.** Under `unshare -rn` the loopback interface is down, so the discovery tests with a `127.0.0.1` server fail there. That is a sandbox fact, not this item's claim (plan section 6).
- **Only the one network test is fixed.** The plan's measurement at `8569235` found no other test that fetches from github.com. Any other network-reaching test would be a follow-up on #189, not fixed here.
- **The gap is pinned, not closed.** `status` on an unmanaged target still accepts a cache inside `.git` (exit 0). The test now proves that without the network; the behaviour is unchanged.
- **Not verified here:** the required CI check on the pull request, and the 504 flake, which only the CI run can show.
