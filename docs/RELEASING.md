# Releasing the Workflow Manager

This repository releases one product: the Workflow Manager's own package.
It never creates a Workflow release. Workflow releases are built and
published as packages in the `workflow` repository
(`RodrigoFAbreu/workflow`); this repository pins them (see "Workflow
packages: adding a pin" below). The design records are
`docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`, sections 5 and 9,
and `docs/ai-workflow/WORKFLOW_MANAGER_PACKAGED_DISTRIBUTION_PLAN.md`.

## How a release happens

Nobody edits a version and nobody tags by hand. The Git tag `vX.Y.Z` is the
only version authority; `pyproject.toml` holds the placeholder
`0.0.0.dev0`, and the release sets the real version in a temporary copy at
build time.

1. A pull request is merged into `main` by squash. Its title, a Conventional
   Commit checked by the required `Conventional Commit title` check, becomes
   the squash commit's subject, with a blank body.
2. `main`'s push run of `workflow-manager-verify.yml` runs the **full**
   selection.
3. When that run completes green, `.github/workflows/release.yml` starts
   (`workflow_run`). It:
   - picks the newest commit on `main`'s first parent whose own push run is
     green (`release.py resolve-target`), and checks it out;
   - requires that run's plan to be the full selection of exactly that tree
     (`release.py assert-full-plan`, against an inventory rediscovered
     there), so a red or reduced run never releases;
   - computes the next version from the highest reachable `vX.Y.Z` tag and
     the subjects since it (`release.py next-version`); nothing to release
     ends the job green;
   - refuses a commit a newer release already covers
     (`release.py assert-not-superseded`, exit 3, a notice);
   - builds and verifies the wheel and sdist (`tools/release/package.py`):
     the wheel must carry `published_releases.json`, and, installed outside
     any checkout, its `releases` must list exactly the pins and its
     `verify` of the checkout must pass, through a release cache restored
     like the test jobs' (on a miss it downloads the checkout's release from
     the published source);
   - publishes them with `SHA256SUMS` through `gh release create`, which
     creates the tag and the release in one call. The release notes list the
     pinned Workflow versions.

Release jobs are serialized by one concurrency group and never cancelled.

### Release impact of a title

| impact | types |
| --- | --- |
| **major** | any type with `!` (`feat!:`, `fix(cli)!:`) |
| **minor** | `feat` |
| **patch** | `fix`, `perf`, `refactor`, `build`, `revert` |
| **none** | `docs`, `chore`, `ci`, `test`, `style` |

The form is `type(optional-scope)!: description`, lowercase type, a space
after the colon. A `BREAKING CHANGE:` footer is not read: the squash commit
has no body. Check a title locally:

```bash
python3 tools/release/release.py check-title "feat: trunk model"
python3 tools/release/release.py next-version    # what main would release now
```

Several unreleased commits are released together at the newest one, with
the highest impact among them. A subject that is not a Conventional Commit
(only possible through a bypass) counts as a patch and warns.

## The first release

No strict `vX.Y.Z` tag exists yet. Until one does, the base is the recorded
baseline `1.0.0` at `b856a97` (the trunk-model milestone's base), which
must be an ancestor of the released commit. The trunk-model milestone's own
pull request is a `feat:`, so the first release is **`v1.1.0`**. `1.0.0` is
not reused: every existing install already reports it, and the local tag
`workflow-manager-v1.0.0` names an older tree. The legacy local tags are not
strict tags and are ignored.

## When something goes wrong

- **Red `main`: fix forward.** A red push run publishes nothing. Open a
  `fix:` pull request. Its green merge releases everything unreleased up to
  it.
- **Catch-up.** Any later green `main` push releases every earlier
  unreleased commit with it, so a skipped or superseded release is never
  lost as long as `main` moves.
- **A failed release run.** A failure before `gh release create` leaves no
  tag. Re-run the failed `Release` run from the Actions UI, or:

  ```bash
  gh run list --workflow release.yml --limit 10
  gh run rerun <run-id>
  ```

  A `workflow_run` re-run uses the same payload, and resolves its target
  afresh.
- **A stranded release on a quiet `main`.** Only one case can leave a green
  commit unreleased: the one release job that replaced a newer commit's
  pending job fell back to its own trigger (an API or git failure in
  `resolve-target`, which warns). The next green `main` push releases it.
  If `main` stays quiet, re-run the `Release` run of the latest green
  `main` push run, as above; it picks the newest green commit.

## Installing a release, without a checkout

A Manager release is self-contained: its wheel carries the pins, and it
downloads, verifies and caches the Workflow release it installs. No checkout
of this repository is needed.

```bash
v=X.Y.Z    # the Manager release
gh release download "v$v" --repo RodrigoFAbreu/workflow-manager --dir "wm-$v"
(cd "wm-$v" && sha256sum -c SHA256SUMS)
pipx install "./wm-$v/workflow_manager-$v-py3-none-any.whl"
workflow-manager --version                 # workflow-manager X.Y.Z
workflow-manager releases                  # the pinned Workflow releases, and which are cached
workflow-manager bootstrap /path/to/repo   # the newest pinned release, fetched and verified
workflow-manager verify /path/to/repo
```

The first use of a Workflow release downloads its three assets from
`https://github.com/RodrigoFAbreu/workflow/releases/download/v<version>/`,
checks them against the pin and `SHA256SUMS`, and caches the verified tree in
`~/.cache/workflow-manager/releases` (or `$XDG_CACHE_HOME/…`,
`WORKFLOW_MANAGER_RELEASE_CACHE`, `--release-cache`). After that every command
works offline. With no network and nothing cached, a command fails with exit
`1`, naming the version, the source URL and the cache directory.

- **Air-gapped or mirrored.** Put each version's three assets in
  `<dir>/<version>/` and pass `--release-source <dir>` (or set
  `WORKFLOW_MANAGER_RELEASE_SOURCE`); a URL template with `{version}` works
  too. The pins still decide what is accepted.
- **A release in development.** `--release-dir <dir>` installs an unpackaged
  release directory, for example a `workflow` checkout. A directory claiming
  a pinned version must match its pin exactly; an unpinned version installs
  as `source.kind: "local"`, which `status` reports as `(local, unpublished)`.
- **`--manager-root`** is a deprecated alias kept for one release: it reads
  an old checkout's `distribution/workflow/<version>/` as a `--release-dir`,
  and otherwise falls through to the pins. It prints a deprecation notice.

A checkout at a release tag, run in place (`PYTHONPATH=src python3 -m
workflow_manager`), is that release too (`workflow-manager X.Y.Z (checkout at
vX.Y.Z)`). Anything else reports a development build.

**An existing editable install keeps its old metadata.** A `pipx install
--editable` made before the trunk model still reports `workflow-manager
1.0.0`. Run `pipx reinstall workflow-manager` once.

## Workflow packages: adding a pin

A Workflow release `V` is published by the `workflow` repository as the
GitHub release `vV` with three assets: `workflow-V.tar.gz`,
`workflow-V.manifest.json` and `SHA256SUMS`. That repository's settings keep
release immutability on, so a published asset cannot be replaced. The Manager
installs `V` only once it is pinned, through one pull request here:

1. Download and check the assets:

   ```bash
   V=2.7.0
   gh release download "v$V" --repo RodrigoFAbreu/workflow --dir "pkg/$V"
   (cd "pkg/$V" && sha256sum -c --strict SHA256SUMS)
   PYTHONPATH=src python3 -m workflow_manager package verify "pkg/$V/workflow-$V.tar.gz" \
       --sha256 "$(sha256sum "pkg/$V/workflow-$V.tar.gz" | cut -d' ' -f1)"
   sha256sum "pkg/$V/workflow-$V.manifest.json"
   ```

   `package verify` extracts the archive under the same rules an install
   uses and checks every file against the carried manifest.
2. Add the entry to `src/workflow_manager/published_releases.json`'s
   `releases`, keyed by `V`: `archive` (`workflow-V.tar.gz`), `sha256` (the
   archive's digest) and `manifest_sha256` (the manifest asset's digest).
3. Add `V`'s frozen suite counts to `tests/support.py`'s `CI_SUITES`, and its
   entry, possibly empty, to `tests/portability_exceptions.json`'s
   `by_version`. `TestPinnedVersionsCarryTheirRecords` fails until the pins
   and both records name the same versions.
   Also extend the three release tables in
   `src/workflow_manager/compatibility.py` (`DOWNGRADE_BOUNDARIES`,
   `NEW_WORK_ONLY`, `GATE_DEFAULT_CHANGES`) with an entry for `V`, possibly
   empty; a test fails until you do. `doctor` reads them.
4. Run `python3 tests/run_all.py`. Priming fetches `V` once; the frozen matrix
   moves to it, and the `updated` fixture updates the previous newest release
   to it. The conformance fixture must be green, and the clean target's
   failure set must equal the documented exceptions.
5. Open the pull request with a `feat:` title (`feat: pin Workflow V`): a new
   pin is a new capability, so it releases a minor Manager version. CI's
   release-cache key is the pin file's hash, so the first run after the change
   downloads every pinned package once and caches them.

A published package never changes, so a pin is never edited. A wrong or
withdrawn release is superseded by a new version, never re-published under
the old one: a re-published asset would fail every Manager that pins the
original.

## Repository settings, as reviewed data

The merge settings and the `main` ruleset live in `.github/repository/` and
are applied by the repository owner with `gh api`, never by CI or an agent:

```bash
repo=RodrigoFAbreu/workflow-manager
gh api -X PATCH "repos/$repo" --input .github/repository/merge-settings.json
gh api -X POST "repos/$repo/rulesets" --input .github/repository/ruleset-main.json
```

To change the ruleset later, edit the file in a pull request, then replace
it:

```bash
id="$(gh api "repos/$repo/rulesets" --jq '.[] | select(.name == "main") | .id')"
gh api -X PUT "repos/$repo/rulesets/$id" --input .github/repository/ruleset-main.json
```

Read them back with `gh api "repos/$repo" --jq '{allow_squash_merge,
allow_merge_commit, allow_rebase_merge, squash_merge_commit_title,
squash_merge_commit_message, allow_auto_merge, delete_branch_on_merge}'`
and `gh api "repos/$repo/rulesets/$id"`. The required checks are
`aggregate` and `Conventional Commit title`; `strict` is off, so a pull
request need not be up to date with `main`. There are no bypass actors: an
administrator recovers from a lockout by editing or disabling the ruleset.
Never make a check required before it has reported under that exact name on
an open pull request.

## The nightly run

`workflow-manager-verify.yml` runs the full selection of `main` at 03:17
UTC. The README's nightly badge shows the latest result; a red nightly opens
no issue, so check the badge or the Actions tab.

GitHub disables scheduled workflows in a public repository after 60 days
without activity. The nightly then silently stops: re-enable it from the
Actions tab or with `gh workflow enable workflow-manager-verify.yml --repo
RodrigoFAbreu/workflow-manager`.

## The Workflow Controller (C1)

The Controller's own release model (its roadmap's C1) should use the same
impact table as this repository, including the choices for the types the
original brief did not name: `perf`, `refactor`, `build` and `revert`
release a patch; `test` and `style` release nothing. A Controller repository
policy for this repository waits for a Controller release with C1
(`docs/ROADMAP.md`, "Controller repository policy for this repository").

## Cutover: M2, packaged Workflow releases (K1-K5)

These steps run after M2's implementation is technically approved and its
functional review is done, before acceptance
(`docs/ai-workflow/WORKFLOW_MANAGER_PACKAGED_DISTRIBUTION_PLAN.md`, section 9).
Each is the repository owner's action, or one the owner explicitly authorizes;
an agent states the commands and reads results back. Record each step's
evidence in `docs/ACTIVE_MILESTONE.md`. A problem found in K2-K5 goes back
through `/apply-functional-review`.

The assets to publish are the ones CP4 built and primed into the local cache,
`~/.cache/workflow-manager/releases/<version>/` (`workflow-<version>.tar.gz`,
`workflow-<version>.manifest.json`, `SHA256SUMS`). Their digests are the pins
and `docs/MIGRATION.md`'s table; `tools/workflow_packages.py build --commit
ec38979 --out <dir> --pins src/workflow_manager/published_releases.json
--check` rebuilds and re-checks them.

1. **K1.** Create the public repository and turn on its release immutability
   setting (the owner, or with explicit authorization):

   ```bash
   gh repo create RodrigoFAbreu/workflow --public \
     --description "The AI development Workflow: versioned, immutable releases"
   ```

2. **K2.** Seed the history and publish the five releases (`OD-M2-6`): five
   commits on `main`, oldest first, each tree equal to that release's
   directory at `ec38979` plus a short `README.md`, each tagged `v<version>`;
   then one GitHub release per tag with its three assets, `v2.6.0` marked
   latest.

   ```bash
   seed=$(mktemp -d) && git -C "$seed" init -q -b main
   for v in 2.3.1 2.4.0 2.5.0 2.5.1 2.6.0; do
     git -C "$seed" rm -rq --ignore-unmatch .
     git archive ec38979 "distribution/workflow/$v" \
       | tar -x -C "$seed" --strip-components=3
     printf '# Workflow %s\n\nThe AI development Workflow, release %s.\n' "$v" "$v" > "$seed/README.md"
     git -C "$seed" add -A && git -C "$seed" commit -qm "Workflow $v"
     git -C "$seed" tag "v$v"
   done
   git -C "$seed" remote add origin https://github.com/RodrigoFAbreu/workflow.git
   git -C "$seed" push origin main --tags
   for v in 2.3.1 2.4.0 2.5.0 2.5.1 2.6.0; do
     c=~/.cache/workflow-manager/releases/$v
     latest=false; [ "$v" = 2.6.0 ] && latest=true
     gh release create "v$v" --repo RodrigoFAbreu/workflow --verify-tag \
       --title "Workflow $v" --notes "Workflow release $v." --latest=$latest \
       "$c/workflow-$v.tar.gz" "$c/workflow-$v.manifest.json" "$c/SHA256SUMS"
   done
   ```

   Before pushing, check that each tag differs from its release only by
   `README.md`:

   ```bash
   for v in 2.3.1 2.4.0 2.5.0 2.5.1 2.6.0; do
     x=$(mktemp -d) y=$(mktemp -d)
     git -C "$seed" archive "v$v" | tar -x -C "$x"
     git archive ec38979 "distribution/workflow/$v" | tar -x -C "$y" --strip-components=3
     diff -r "$x" "$y"      # prints only: Only in $x: README.md
   done
   ```
3. **K3.** Verify from the network, with an empty temporary cache:

   ```bash
   export WORKFLOW_MANAGER_RELEASE_CACHE=$(mktemp -d)
   PYTHONPATH=src python3 -m workflow_manager releases        # every pin, "not cached"
   for v in 2.3.1 2.4.0 2.5.0 2.5.1 2.6.0; do
     t=$(mktemp -d) && git -C "$t" init -q
     PYTHONPATH=src python3 -m workflow_manager --release-version "$v" bootstrap "$t"
     PYTHONPATH=src python3 -m workflow_manager verify "$t"
     d=$(mktemp -d) && gh release download "v$v" --repo RodrigoFAbreu/workflow --dir "$d"
     (cd "$d" && sha256sum -c --strict SHA256SUMS && sha256sum "workflow-$v.tar.gz")
   done
   ```

   Every downloaded archive digest must equal its pin.
4. **K4.** Push the branch and open the pull request under the chosen title
   (`OD-M2-3`'s recommendation: `feat: Workflow releases are downloaded,
   verified packages`). CI's full selection must be green; its first run
   downloads the packages K2 published, which proves that path.

   ```bash
   git push -u origin milestone/workflow-manager-packaged-distribution
   gh pr create --base main --head milestone/workflow-manager-packaged-distribution \
     --title "feat: Workflow releases are downloaded, verified packages" \
     --body "Milestone workflow-manager-packaged-distribution."
   ```

5. **K5.** After `/accept-milestone`, squash-merge (report before and after).
   Then check that `main`'s full run is green and that the Manager release
   (`v1.2.0` under that title) is published, and install its wheel with
   `pipx` into a scratch environment and bootstrap a scratch repository with
   no checkout, as in "Installing a release, without a checkout" above.

## Cutover history: the trunk-model milestone

This is the record of the trunk-model milestone's cutover. Its C1 probe for
the `newest-release` pull-request profile no longer applies: M2 removed that
profile, and every pull request runs the full selection.

Every step here is the repository owner's: a push, a pull request, a
settings change or a merge. An agent states the commands and reads results
back read-only.

1. **C0.** After the last checkpoint, push the branch and open a draft pull
   request:

   ```bash
   git push -u origin milestone/workflow-manager-trunk-model
   gh pr create --draft --base main --head milestone/workflow-manager-trunk-model \
     --title "feat: trunk model, Manager releases and the stopgap PR test profile" \
     --body "Milestone workflow-manager-trunk-model."
   ```

   Its runs are the milestone's CI evidence: `PR title` green, the
   verification profile `full`, `package` and `aggregate` green. Record the
   run URLs in `docs/ACTIVE_MILESTONE.md`.
2. **C1: probes**, throwaway draft pull requests against the milestone
   branch, closed unmerged: a docs-only change must choose `newest-release`;
   a change under `src/` must choose `full`; the title `Update things` must
   fail the title check; a `docs: ...` title must pass it with impact
   `none`.
3. **C2**, after `/accept-milestone`: apply `merge-settings.json` (above).
4. **C3:** push the acceptance commits, then confirm the checks at the
   pull request's final head:

   ```bash
   gh pr checks <number> --json name,state
   ```

   Both `aggregate` and `Conventional Commit title` must have reported,
   green, under exactly those names. Then create the ruleset (above).
5. **C4:** mark the pull request ready and merge it by squash, directly or
   through auto-merge.
6. **C5:** `main`'s push run must be full and green; the release then
   publishes `v1.1.0`. Check `sha256sum -c SHA256SUMS`, that the installed
   wheel prints `workflow-manager 1.1.0`, and that `git fetch --tags` shows
   `v1.1.0` on the squash commit. A red `main` publishes nothing: fix
   forward.
7. **C6:** from the next milestone on, one branch per milestone, merged by
   squash under a Conventional Commit title.
