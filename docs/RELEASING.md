# Releasing the Workflow Manager

This repository releases one product: the Workflow Manager's own package.
It never creates a Workflow release; those are composed under
`distribution/` by `tools/migrate.py` and `tools/build_release.py` (see
`CLAUDE.md`), and until M2 they ship only inside the repository at a tag.
The design record is
`docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`, sections 5 and 9.

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
   - builds and verifies the wheel and sdist (`tools/release/package.py`)
     and publishes them with `SHA256SUMS` through `gh release create`, which
     creates the tag and the release in one call.

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
  `fix:` pull request (while `main`'s latest full run is red, every pull
  request runs the full matrix). Its green merge releases everything
  unreleased up to it.
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

## Installing a release

Until M2, a release is the Manager's code only; the Workflow releases stay
in `distribution/` of the repository at the same tag.

```bash
gh release download v1.1.0 --repo RodrigoFAbreu/workflow-manager --dir wm-1.1.0
cd wm-1.1.0 && sha256sum -c SHA256SUMS
pipx install ./workflow_manager-1.1.0-py3-none-any.whl
workflow-manager --version        # workflow-manager 1.1.0
git clone --branch v1.1.0 https://github.com/RodrigoFAbreu/workflow-manager.git ~/wm-1.1.0
workflow-manager --manager-root ~/wm-1.1.0 releases
```

A checkout at a release tag, run in place, is that release too
(`workflow-manager X.Y.Z (checkout at vX.Y.Z)`). Anything else reports a
development build.

**An existing editable install keeps its old metadata.** A `pipx install
--editable` made before the trunk model still reports `workflow-manager
1.0.0`. Run `pipx reinstall workflow-manager` once.

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
UTC. A red nightly opens a `nightly-red` issue (or comments on the open
one), and the next green nightly closes it. The README's nightly badge shows
the latest result.

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
(`docs/ROADMAP.md`, 10.1).

## Cutover: the trunk-model milestone itself

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
<!-- functional-review probe, closed unmerged -->
