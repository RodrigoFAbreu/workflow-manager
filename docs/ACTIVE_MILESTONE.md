# Active Milestone

## Milestone

`explicit-latest-floor` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan
revision 2, base `0d6ee1f`, branch `milestone/explicit-latest-floor`): roadmap
row 13, issue #85. A `fix:` pull request title (`src/` changes). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_EXPLICIT_LATEST_FLOOR_PLAN.md`.

### CP1: filter the explicit run's latest by `min_manager_version` -- complete

- `compatibility.explicit_latest(known, metadata, needs, upgrade_page)` drops
  candidates `needs` rejects (a minimum not met, `NEWER_BLOCK`, `MALFORMED_BLOCK`,
  or `UNREADABLE`) and names the newest dropped one with the "upgrade the
  Manager" step; `ReleaseMetadata.read_listed` backs `newest_read`.
- `cli._latest_filter` builds `needs`: built-in data ignored, else the block the
  run read, else the cache's trusted manifest; a pin or the default version is
  never dropped for an unreadable minimum, a damaged non-pinned cached entry is.
- Docs: `update.md` "Latest available" bullet.
- Tests (`tests/test_release_metadata.py`): the `explicit_latest` unit test, four
  CLI tests in `TestMinManagerVersion` (minimum, unusable block, no block,
  damaged entry) and the no-listing suffix assertion. The four new CLI/unit tests
  fail at `0d6ee1f` and pass after; the suffix assertion pins existing behaviour.

Verification: `--select` test_release_metadata, test_discovery, test_docs green.

## Functional review checklist

**Scope.** The `Latest available` line of an explicit `--release-version` run
(`doctor`, `update --dry-run`), issue #85. Expected change: a release whose
`min_manager_version` this Manager does not meet, or whose cached `manager`
block this Manager cannot use, is no longer named as the latest; the newest one
left out is named in the parenthesis with the upgrade step. Nothing else
changes: options, exit codes, state, release sources, pins, the bare `update`
path.

**Reviewed content.** Implementation head `397ed56`; no `src/`, `tests/` or
`tools/` change since it. The full gate (`python3 tests/run_all.py`) was green
there (`.ai-review/explicit-latest-floor/current/TEST_RESULTS.md`). The registry
has one checkpoint, CP1, which is COMPLETE.

### Setup (offline)

No network, GitHub, `gh`, `claude` or `ssh` is needed. Everything goes under one
scratch directory, outside the repository. A full gate run on the machine first
primes `~/.cache/workflow-manager/releases`, which the mirror below copies.

```bash
S=$(mktemp -d)                        # scratch; nothing below writes into the repository
REPO=/path/to/workflow-manager        # the checkout, read only here
mkdir -p "$S"/{home,cache,tmp,base,fixed,repo,work} \
  "$S"/fake/workflow_manager-1.13.1.dist-info "$S"/fake99/workflow_manager-99.1.0.dist-info
printf 'Metadata-Version: 2.1\nName: workflow-manager\nVersion: 1.13.1\n' > "$S/fake/workflow_manager-1.13.1.dist-info/METADATA"
printf 'Metadata-Version: 2.1\nName: workflow-manager\nVersion: 99.1.0\n' > "$S/fake99/workflow_manager-99.1.0.dist-info/METADATA"
git -C "$REPO" archive 0d6ee1f | tar -x -C "$S/base"     # before the fix
git -C "$REPO" archive 397ed56 | tar -x -C "$S/fixed"    # after the fix
(cd "$S/repo" && git init -q . && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init)
PYTHONPATH="$REPO/src:$REPO/tests" python3 -B - "$S" <<'EOF'
import shutil, sys
from pathlib import Path
S = Path(sys.argv[1])
import support                        # tests/support.py: the tested releases, from the primed cache
import test_release_metadata as trm   # the CLI tests' own publisher of synthetic releases
shutil.copytree(support.mirror_dir(), S / "mirror", symlinks=True)
t = trm._Published("setUp")
t.tmp = S / "work"
t.publish(S / "mirror", "7.0.2", trm.block(min_manager_version="99.0.0"))
t.publish(S / "mirror", "7.0.3", trm.block())
EOF
export HOME="$S/home" TMPDIR="$S/tmp" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" \
  WORKFLOW_MANAGER_RELEASE_SOURCE="$S/mirror" WORKFLOW_MANAGER_PINNED_ONLY=0
```

The two `fake` entries stand in for an installed Manager of that version:
`_installed_version()` reads the installed distribution's version, so a
`dist-info` on `PYTHONPATH` is a Manager 1.13.1 (below the synthetic 99.0.0
minimum) or 99.1.0 (above it). With no such entry the run is a development
build, which satisfies every minimum.

Bootstrap the scratch repository at 2.19.0 with the old Manager:

```bash
PYTHONPATH="$S/fake:$S/fixed/src" python3 -B -m workflow_manager --release-version 2.19.0 bootstrap "$S/repo"
```

### Flows

Run them in this order: F5 adds a release to the cache that F1 and F2 would
otherwise see, so run F5 last or in a fresh `$S`. For each flow, record PASS or
FAIL and the line you saw. The seeding runs (`--release-version 7.0.2` and `7.0.3` under
the newer Manager) exit 1 from the scratch repository's own findings; only the
cache write matters there.

- **F1 — the defect and its fix.** Seed the cache with the newer Manager, then
  run the old one on both trees:

  ```bash
  PYTHONPATH="$S/fake99:$S/fixed/src" python3 -B -m workflow_manager --release-version 7.0.2 doctor "$S/repo"
  PYTHONPATH="$S/fake:$S/fixed/src"   python3 -B -m workflow_manager --release-version 2.19.0 doctor "$S/repo" | grep '^Latest available'
  PYTHONPATH="$S/fake:$S/base/src"    python3 -B -m workflow_manager --release-version 2.19.0 doctor "$S/repo" | grep '^Latest available'
  ```

  Expected, fixed tree: `Latest available    2.19.0  [discovered, not pinned]  (this Manager pins 2.3.1 ... 2.12.0)  (7.0.2 needs workflow-manager 99.0.0 or newer: upgrade the Manager (https://github.com/RodrigoFAbreu/workflow-manager/blob/main/docs/update.md#update-the-manager); the release source was not listed)`.
  Expected, base tree (the defect, reproduced): `Latest available    7.0.2 ...`, a release that Manager 1.13.1 cannot install.

- **F2 — a newer Manager is unaffected.** `PYTHONPATH="$S/fake99:$S/fixed/src"`
  with `--release-version 2.19.0 doctor`: `Latest available    7.0.2  [discovered, not pinned] ...  (the release source was not listed)`.

- **F3 — a development build is unaffected.** `PYTHONPATH="$S/fixed/src"` with
  `--release-version 2.19.0 doctor`: the same line as F2.

- **F4 — the bare run is unchanged.** `doctor "$S/repo"` (no `--release-version`)
  with `$S/fake` on both trees gives identical output. It states once that
  `Workflow 7.0.2 needs workflow-manager 99.0.0 or newer; this is 1.13.1`, with
  the upgrade step.

- **F5 — a damaged cached entry is not named.** Cache `7.0.3` with the newer
  Manager, then damage it:

  ```bash
  PYTHONPATH="$S/fake99:$S/fixed/src" python3 -B -m workflow_manager --release-version 7.0.3 doctor "$S/repo"
  printf damaged >> "$S/cache/7.0.3/tree/fixtures/CLAUDE.md"
  PYTHONPATH="$S/fake:$S/base/src"  python3 -B -m workflow_manager --release-version 2.19.0 doctor "$S/repo" | grep '^Latest available'
  PYTHONPATH="$S/fake:$S/fixed/src" python3 -B -m workflow_manager --release-version 2.19.0 doctor "$S/repo" | grep '^Latest available'
  ```

  Expected, base tree (the defect): `Latest available    7.0.3 ...`. Expected, fixed
  tree: `Latest available    2.19.0 ...` with the `7.0.2 needs workflow-manager 99.0.0 or newer` note as in F1, and `7.0.3` named nowhere.

**Expected unchanged:** the exit code of each explicit `doctor` run (1 on both
trees in this setup, from the scratch repository's own findings), every other
line, and the state files.

**Covered by automated tests, not by these flows:** a cached block written for a
newer Manager (`schema_version: 2`), a malformed cached block, the no-listing
suffix through a URL-template source (needs a loopback server, which the sandbox
does not allow), and a cached release with no `manager` block staying the latest.
Run `python3 tests/run_all.py --select test_release_metadata.py`.

### Known limits and open wording

- `docs/update.md`'s "Latest available" bullet says "a pin or the default version
  is always named". That holds only when no trusted cached manifest is readable:
  a pin or the default version whose readable minimum is not met, or whose cached
  block is unusable, is dropped and named. Reviewers ELF-IR1-O1 and EIR-001 raised
  this. It is not reworded in this round, because `docs/update.md` is protected at
  the implementation stage and a change would stale the technical approval. Judge
  it as a finding; the disposition is recorded at acceptance.
- The `version == default` arm of `_latest_filter` has no test (ELF-IR1-O2). It
  matters only when no pins are patched and the default is an alias checkout.
- Pins up to 2.12.0 carry built-in data and ignore a `manager` block, so the drop
  path cannot be exercised with real pins; the flows use discovered releases.
- The real network path is not in these flows. On a machine with network,
  `workflow-manager --release-version 2.19.0 doctor <repo>` should name
  `Latest available 2.19.0` with no `needs` note: the real releases from 2.13.0
  to 2.19.0 carry `min_manager_version` 1.13.0, which Manager 1.13.2 meets.

### Reporting

A FAIL, or any finding, goes to the resolved feedback file
`.ai-review/explicit-latest-floor/feedback/FUNCTIONAL_REVIEW.md`. `/apply-functional-review`
routes it. When testing is clean, `/accept-milestone` is the acceptance command.
