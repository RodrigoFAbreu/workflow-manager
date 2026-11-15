#!/usr/bin/env python3
"""The release and title workflows, the repository settings as reviewed data,
and `release.py assert-full-plan`'s permanent cases.

Checkpoint CP5 of `workflow-manager-trunk-model`:

- T-REL-1: `.github/workflows/publish.yml` (`D-Release-Workflow`, plan 5.4),
  the reusable release workflow ci.yml's `publish` job calls after its
  `aggregate`, also dispatchable by hand (its guard and `dry-run`), and the
  rule that only that job and its caller hold `contents: write`;
- T-PRT-1: `.github/workflows/pr-title.yml` (`D-PR-Title-Check`, 5.5);
- T-SET-1: `.github/repository/ruleset-main.json` and `merge-settings.json`
  (`D-Required-Check`, 6.3 and 6.5);
- `assert-full-plan` against real `--plan-only` output of a scratch
  checkout, with the inventory rediscovered from that checkout: a full plan
  of this tree passes; a targeted plan, another tree's plan, and a
  `--select` covering the whole inventory are refused; so is a plan marked
  `full` whose selection omits a unit or selects a class partially.

The workflows are parsed with `test_parallel_runner`'s stdlib YAML subset
(`load_workflow_yaml`). None of this is stopgap code: M2 keeps it all.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from support import REPO_ROOT

import test_parallel_runner as runner_tests
from parallel import canonical_json
from workflow_manager import package as package_module
from workflow_manager import source as release_source

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "publish.yml"
TITLE_WORKFLOW = WORKFLOWS / "pr-title.yml"
#: The entry point that calls the verification and the release.
CI_WORKFLOW = WORKFLOWS / "ci.yml"
#: The reusable verification workflow (plan, shard, package, aggregate).
VERIFY_WORKFLOW = WORKFLOWS / "validate.yml"
SETTINGS = REPO_ROOT / ".github" / "repository"
RELEASE_PY = REPO_ROOT / "tools" / "release" / "release.py"

#: The GitHub Actions app: every required check comes from it (plan 6.3).
ACTIONS_APP = 15368
REQUIRED_CHECKS = {"aggregate", "Conventional Commit title", "workflow-conformance"}


def _load_release_tool():
    spec = importlib.util.spec_from_file_location("workflow_manager_release_workflows", RELEASE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load_release_tool()


def _workflow(path: Path) -> dict:
    return runner_tests.load_workflow_yaml(path.read_text(encoding="utf-8"))


def _step_index(steps: list[dict], predicate, what: str) -> int:
    hits = [i for i, step in enumerate(steps) if predicate(step)]
    if len(hits) != 1:
        raise AssertionError(f"{len(hits)} steps {what}, not 1")
    return hits[0]


def _runs(step: dict, text: str) -> bool:
    return text in (step.get("run") or "")


def _uses(step: dict, action: str) -> bool:
    return (step.get("uses") or "").split("@")[0] == action


# -- T-REL-1: the release workflow ----------------------------------------------------------

#: The verification workflow's release-cache key, without the nightly's suffix (#58).
RELEASE_CACHE_KEY = ("workflow-releases-${{ hashFiles('src/workflow_manager/published_releases.json', "
                     "'tests/tested_releases.json') }}")
#: The `dry-run` input both of publish.yml's triggers declare.
DRY_RUN_INPUT = {"description": "Run every gate and the build, but create no tag or release",
                 "required": False, "type": "boolean", "default": False}
#: The release job's condition: main only (a call from ci.yml is a push to main).
RELEASE_IF = "github.ref == 'refs/heads/main'"
#: The dispatch guard's condition: only a dispatched run is unvalidated.
DISPATCH_IF = "github.event_name == 'workflow_dispatch'"
#: The steps a dry run gates; the publish step adds `&& !inputs.dry-run`.
RELEASE_STEP_IF = "steps.version.outputs.version != '' && steps.superseded.outputs.superseded != 'true'"


def release_workflow_problems(doc: dict) -> list[str]:
    """T-REL-1's structural checks over the parsed release workflow; `[]`
    when it holds."""
    problems = []

    def need(condition, message):
        if not condition:
            problems.append(message)

    triggers = doc.get("on") or {}
    need(sorted(triggers) == ["workflow_call", "workflow_dispatch"],
         f"the release's triggers are {sorted(triggers)}, not workflow_call and workflow_dispatch")
    for name in ("workflow_call", "workflow_dispatch"):
        inputs = (triggers.get(name) or {}).get("inputs") or {}
        need(inputs == {"dry-run": DRY_RUN_INPUT},
             f"{name}: the inputs are {inputs!r}, not a dry-run boolean defaulting false")
    need("concurrency" not in doc, "the concurrency group is on the workflow, not the job")
    need(doc.get("permissions") == {"contents": "read"},
         "the workflow's own permissions are not contents: read")

    jobs = doc.get("jobs") or {}
    need(sorted(jobs) == ["release"], f"jobs are {sorted(jobs)}, not [release]")
    job = jobs.get("release") or {}
    need(job.get("if") == RELEASE_IF, f"the job's if is {job.get('if')!r}, not main only")
    need(job.get("concurrency") == {"group": "workflow-manager-release",
                                    "cancel-in-progress": False},
         f"the job's concurrency is {job.get('concurrency')!r}, not a serialized release group")
    need(job.get("timeout-minutes") == 60, "the release job's timeout is not 60 minutes")
    need(job.get("permissions") == {"contents": "write", "actions": "read"},
         f"the job's permissions are {job.get('permissions')!r}")
    for name, other in jobs.items():
        if name != "release":
            need((other.get("permissions") or {}).get("contents") != "write",
                 f"{name}: contents: write outside the release job")

    steps = job.get("steps") or []
    try:
        checkouts = [i for i, s in enumerate(steps) if _uses(s, "actions/checkout")]
        resolve = _step_index(steps, lambda s: _runs(s, "release.py resolve-target"),
                              "resolve the target")
        target_checkout = [i for i in checkouts
                           if (steps[i].get("with") or {}).get("ref")
                           == "${{ steps.target.outputs.target_sha }}"]
        python = _step_index(steps, lambda s: _uses(s, "actions/setup-python"), "set up python")
        download = _step_index(steps, lambda s: _uses(s, "actions/download-artifact"),
                               "download the plan")
        full_plan = _step_index(steps, lambda s: _runs(s, "release.py assert-full-plan"),
                                "assert the full plan")
        version = _step_index(steps, lambda s: _runs(s, "release.py next-version"),
                              "compute the next version")
        superseded = _step_index(steps, lambda s: _runs(s, "release.py assert-not-superseded"),
                                 "assert not superseded")
        package = _step_index(steps, lambda s: _runs(s, "tools/release/package.py"),
                              "build the package")
        cache = _step_index(steps, lambda s: _uses(s, "actions/cache"),
                            "restore the release cache")
        publish = _step_index(steps, lambda s: _runs(s, "gh release create"), "publish")
        guard = _step_index(steps, lambda s: s.get("if") == DISPATCH_IF, "guard a dispatch")
        dry = _step_index(steps, lambda s: "inputs.dry-run" in (s.get("if") or "")
                          and "!inputs.dry-run" not in (s.get("if") or ""), "note a dry run")
    except AssertionError as exc:
        return problems + [str(exc)]

    # The trigger is this run: the CI run that called it (a `main` push whose
    # `aggregate` succeeded), or the dispatch. Only the call is validated.
    env = steps[resolve].get("env") or {}
    need(env.get("TRIGGER_SHA") == "${{ github.sha }}", "the trigger commit is not github.sha")
    need(env.get("TRIGGER_RUN") == "${{ github.run_id }}", "the trigger run is not this run")
    need(env.get("EVENT") == "${{ github.event_name }}", "the resolve step does not see the event")
    need("--trigger-validated" in steps[resolve]["run"]
         and '[ "$EVENT" != workflow_dispatch ]' in steps[resolve]["run"],
         "the call's trigger is not passed as validated, or a dispatch's is")
    need(not any("workflow_run" in json.dumps(step) for step in steps),
         "a step still reads the workflow_run payload")
    # A dispatch whose target fell back to its own run found no green CI push
    # run for the commit: it never publishes that.
    guard_env = steps[guard].get("env") or {}
    need(resolve < guard and (not target_checkout or guard < target_checkout[0]),
         "the dispatch guard does not follow resolve-target before the target checkout")
    need(guard_env == {"TARGET_RUN": "${{ steps.target.outputs.target_run }}",
                       "THIS_RUN": "${{ github.run_id }}"},
         "the dispatch guard does not compare the target run with this run")
    need('[ "$TARGET_RUN" = "$THIS_RUN" ]' in (steps[guard].get("run") or "")
         and "::error::" in (steps[guard].get("run") or "")
         and "exit 1" in (steps[guard].get("run") or ""),
         "the dispatch guard does not fail on its own run")
    # A dry run runs every gate and the build, and skips only the publication.
    for index in (resolve, guard, full_plan, version, superseded, package):
        need("dry-run" not in json.dumps(steps[index]), f"step {index} depends on the dry run")
    need(steps[publish].get("if") == f"{RELEASE_STEP_IF} && !inputs.dry-run",
         "the publication is not skipped on a dry run")
    need(steps[dry].get("if") == f"{RELEASE_STEP_IF} && inputs.dry-run"
         and "::notice::" in (steps[dry].get("run") or "")
         and "gh " not in (steps[dry].get("run") or ""),
         "a dry run does not log a notice instead of publishing")
    need(package < dry < publish, "the dry-run notice is not between the build and the publication")

    need(checkouts and checkouts[0] < resolve, "no checkout of main before resolve-target")
    need(checkouts and (steps[checkouts[0]].get("with") or {}).get("fetch-depth") == 0,
         "the first checkout is shallow: resolve-target reads main's first-parent history")
    need(len(target_checkout) == 1, "the target is not checked out exactly once")
    if target_checkout:
        need(resolve < target_checkout[0], "the target is checked out before it is resolved")
        need((steps[target_checkout[0]].get("with") or {}).get("fetch-depth") == 0,
             "the target checkout is shallow: next-version reads tags and history")
        need(target_checkout[0] < python < full_plan,
             "python 3.12 is not set up between the target checkout and assert-full-plan")
    need((steps[python].get("with") or {}) == {"python-version": "3.12"}, "python is not 3.12")
    need(not any("UPSTREAM" in (s.get("run") or "") for s in steps) and "env" not in doc,
         "the release still fetches an upstream: every release comes through the pins")
    artifact = steps[download].get("with") or {}
    need(artifact.get("run-id") == "${{ steps.target.outputs.target_run }}",
         f"the plan is downloaded from {artifact.get('run-id')!r}, not the target's run")
    need("workflow_run.id" not in json.dumps(artifact),
         "the plan is downloaded from the triggering run")
    need(artifact.get("name") == "plan", "the artifact is not the plan")
    need(target_checkout and target_checkout[0] < download < full_plan,
         "the plan is not downloaded between the target checkout and assert-full-plan")
    plan_path = str(artifact.get("path", "")).replace("${{ runner.temp }}", "$RUNNER_TEMP")
    need(f'"{plan_path}/plan.json"' in steps[full_plan]["run"],
         "assert-full-plan does not read the downloaded plan")
    need(full_plan < version < superseded < package < publish,
         "the order is not assert-full-plan, next-version, assert-not-superseded, package, "
         "gh release create")
    # The release cache (plan 5.6, #58): the verification workflow's, under its
    # key without the nightly's suffix (the pins and the lock), restored before
    # assert-full-plan, which primes the tested set into it before it
    # rediscovers the inventory, and named to the build, so the wheel's
    # `verify` downloads only on a cache miss.
    cache_dir = "${{ runner.temp }}/workflow-manager-releases"
    need(download < cache < full_plan,
         "the release cache is not restored before assert-full-plan")
    need((steps[cache].get("with") or {}) == {"path": cache_dir, "key": RELEASE_CACHE_KEY},
         "the release cache is not keyed on the pins and the lock")
    need("if" not in steps[cache], "the release cache is not restored for assert-full-plan")
    need((steps[full_plan].get("env") or {}).get("WORKFLOW_MANAGER_RELEASE_CACHE") == cache_dir,
         "assert-full-plan does not prime the restored release cache")
    need((steps[package].get("env") or {}).get("WORKFLOW_MANAGER_RELEASE_CACHE") == cache_dir,
         "the build does not use the restored release cache")
    need("--manager-root" not in steps[package]["run"],
         "the build names a checkout: the wheel resolves releases through its pins")
    need("published_releases.json" in steps[publish]["run"]
         and "distribution/" not in steps[publish]["run"],
         "the release notes do not list the pinned Workflow releases")
    need("--target \"$TARGET_SHA\"" in steps[publish]["run"],
         "the release is not created at the resolved target")
    need((steps[publish].get("env") or {}).get("TARGET_SHA")
         == "${{ steps.target.outputs.target_sha }}", "TARGET_SHA is not the resolved target")
    for index in (package, dry, publish):
        need("steps.superseded.outputs.superseded != 'true'" in (steps[index].get("if") or "")
             and "steps.version.outputs.version != ''" in (steps[index].get("if") or ""),
             f"step {index} runs with nothing to release or when superseded")
    need("-eq 3" in steps[superseded]["run"], "exit 3 is not treated as covered by a newer release")
    return problems


def _all_workflows() -> dict[str, dict]:
    return {path.name: _workflow(path) for path in sorted(WORKFLOWS.glob("*.yml"))}


def contents_write_grants(docs: dict[str, dict]) -> set[tuple[str, str]]:
    """`(workflow file, job id)` for every job of `docs` (file name to parsed
    workflow) that can write contents, with `"*"` for a workflow-level grant.
    `write-all` counts as a grant."""
    def writes(permissions) -> bool:
        if isinstance(permissions, str):
            return permissions == "write-all"
        return (permissions or {}).get("contents") == "write"

    found = set()
    for name, doc in docs.items():
        if writes(doc.get("permissions")):
            found.add((name, "*"))
        for job_id, job in (doc.get("jobs") or {}).items():
            if writes(job.get("permissions")):
                found.add((name, job_id))
    return found


#: The release job, and ci.yml's job that calls it (a called workflow cannot
#: exceed its caller job's permissions). Nothing else writes.
CONTENTS_WRITERS = {("publish.yml", "release"), ("ci.yml", "publish")}


class TestReleaseWorkflow(unittest.TestCase):

    def test_the_release_workflow_holds_every_structural_rule(self):
        doc = _workflow(RELEASE_WORKFLOW)
        self.assertEqual(doc["name"], "Publish")
        self.assertEqual(release_workflow_problems(doc), [])

    def test_only_the_release_job_and_its_caller_write_contents(self):
        self.assertEqual(contents_write_grants(_all_workflows()), CONTENTS_WRITERS)
        publish = _workflow(CI_WORKFLOW)["jobs"]["publish"]
        self.assertEqual(publish["uses"], "./.github/workflows/publish.yml")
        self.assertEqual(publish["permissions"], {"contents": "write", "actions": "read"})
        self.assertEqual(_workflow(VERIFY_WORKFLOW)["permissions"], {"contents": "read"})

    def test_each_mutation_is_caught(self):
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        mutants = {
            "the trigger's own run": ("run-id: ${{ steps.target.outputs.target_run }}",
                                      "run-id: ${{ github.run_id }}"),
            "any branch": ("    if: github.ref == 'refs/heads/main'\n", ""),
            "another branch": ("refs/heads/main'\n", "refs/heads/release'\n"),
            "the old workflow_run trigger": ("  workflow_call:\n", "  workflow_run:\n"),
            "no manual run": ("  workflow_dispatch:\n", "  repository_dispatch:\n"),
            "a dry run by default": ("        default: false\n", "        default: true\n"),
            "an unvalidated call": ("validated=--trigger-validated", "validated="),
            "a validated dispatch": ('[ "$EVENT" != workflow_dispatch ]', '[ -n "$EVENT" ]'),
            "the workflow_run payload": ("TRIGGER_SHA: ${{ github.sha }}",
                                         "TRIGGER_SHA: ${{ github.event.workflow_run.head_sha }}"),
            "another trigger run": ("TRIGGER_RUN: ${{ github.run_id }}",
                                    "TRIGGER_RUN: ${{ github.run_number }}"),
            "no dispatch guard": ("        if: github.event_name == 'workflow_dispatch'\n",
                                  "        if: false\n"),
            "a guard that passes its own run": ('[ "$TARGET_RUN" = "$THIS_RUN" ]',
                                                '[ "$TARGET_RUN" = "" ]'),
            "a dry run that publishes": ("&& !inputs.dry-run\n", "\n"),
            "a dry run that skips the build": (
                "      - name: Build and verify the package\n"
                "        if: steps.version.outputs.version != '' && "
                "steps.superseded.outputs.superseded != 'true'\n",
                "      - name: Build and verify the package\n"
                "        if: steps.version.outputs.version != '' && "
                "steps.superseded.outputs.superseded != 'true' && !inputs.dry-run\n"),
            "a cancelled release": ("cancel-in-progress: false", "cancel-in-progress: true"),
            "contents: write for the workflow": ("permissions:\n  contents: read",
                                                 "permissions:\n  contents: write"),
            "no full-plan check": ('python3 tools/release/release.py assert-full-plan',
                                   'echo'),
            "the trigger's own commit": ('--target "$TARGET_SHA"', '--target "$GITHUB_SHA"'),
            "exit 3 fails the release": ('"$status" -eq 3', '"$status" -eq 4'),
            "no superseded guard": ("        if: steps.version.outputs.version != '' && "
                                    "steps.superseded.outputs.superseded != 'true' && "
                                    "!inputs.dry-run\n        env:\n          GH_TOKEN",
                                    "        if: ${{ !inputs.dry-run }}\n        env:\n"
                                    "          GH_TOKEN"),
            "python 3.11": ('python-version: "3.12"', 'python-version: "3.11"'),
            "no release cache": ("          WORKFLOW_MANAGER_RELEASE_CACHE: "
                                 "${{ runner.temp }}/workflow-manager-releases\n", ""),
            "a cache key off the pins": ("hashFiles('src/workflow_manager/published_releases.json', ",
                                         "hashFiles('pyproject.toml', "),
            "a cache key off the lock": (", 'tests/tested_releases.json') }}", ") }}"),
            "no cache for assert-full-plan": (
                "      - name: Require the full plan\n        env:\n          "
                "WORKFLOW_MANAGER_RELEASE_CACHE: ${{ runner.temp }}/workflow-manager-releases\n",
                "      - name: Require the full plan\n"),
            "the cache restored only for a release": (
                "      - name: Restore the release cache\n",
                "      - name: Restore the release cache\n        if: steps.version.outputs.version != ''\n"),
            "a checkout's releases": ('--out "$RUNNER_TEMP/assets"',
                                      '--out "$RUNNER_TEMP/assets" --manager-root "$GITHUB_WORKSPACE"'),
            "an upstream again": ("\njobs:\n", "\nenv:\n  UPSTREAM_URL: x\n\njobs:\n"),
        }
        for label, (old, new) in mutants.items():
            with self.subTest(mutation=label):
                mutated = text.replace(old, new, 1)
                self.assertNotEqual(mutated, text, "the mutation did not apply")
                self.assertNotEqual(release_workflow_problems(
                    runner_tests.load_workflow_yaml(mutated)), [])

    def test_a_write_grant_anywhere_else_is_caught(self):
        for path, old, new in (
                (VERIFY_WORKFLOW, "permissions:\n  contents: read", "permissions:\n  contents: write"),
                (CI_WORKFLOW, "  aggregate:\n    needs: [validate]\n",
                 "  aggregate:\n    needs: [validate]\n    permissions:\n      contents: write\n"),
                (CI_WORKFLOW, "permissions:\n  contents: read", "permissions: write-all")):
            with self.subTest(workflow=path.name, mutation=new):
                text = path.read_text(encoding="utf-8")
                mutated = text.replace(old, new, 1)
                self.assertNotEqual(mutated, text)
                docs = _all_workflows()
                docs[path.name] = runner_tests.load_workflow_yaml(mutated)
                self.assertNotEqual(contents_write_grants(docs), CONTENTS_WRITERS)

    def test_the_cache_restored_after_assert_full_plan_is_caught(self):
        """#58: the inventory reads a lock-only release's counts from the cache."""
        doc = _workflow(RELEASE_WORKFLOW)
        steps = doc["jobs"]["release"]["steps"]
        cache = _step_index(steps, lambda s: _uses(s, "actions/cache"), "restore the cache")
        steps.insert(cache + 1, steps.pop(cache))
        self.assertIn("the release cache is not restored before assert-full-plan",
                      release_workflow_problems(doc))

    def test_the_cache_key_is_the_verification_workflows(self):
        """The release restores what a green `main` run of the verification
        workflow saved: its key without the nightly's suffix."""
        for job in _workflow(VERIFY_WORKFLOW)["jobs"].values():
            for step in job.get("steps") or []:
                if _uses(step, "actions/cache"):
                    self.assertEqual(step["with"]["restore-keys"].strip(), RELEASE_CACHE_KEY)
                    self.assertTrue(step["with"]["key"].startswith(RELEASE_CACHE_KEY))

    def test_no_cache_key_uses_the_run_id_and_package_has_no_digest(self):
        """#52: the nightly's key was unique per run, so it saved an entry every
        night. The digest suffix replaces it in `plan`, `shard` and `aggregate`;
        `package` primes only the committed set and keeps the base key."""
        jobs = _workflow(VERIFY_WORKFLOW)["jobs"]
        keys = {}
        for name, job in jobs.items():
            for step in job.get("steps") or []:
                if _uses(step, "actions/cache"):
                    keys[name] = step["with"]["key"]
        self.assertEqual(sorted(keys), ["aggregate", "package", "plan", "shard"])
        for name, key in keys.items():
            with self.subTest(job=name):
                self.assertNotIn("run_id", key)
                self.assertTrue(key.startswith(RELEASE_CACHE_KEY))
        self.assertEqual(keys["package"], RELEASE_CACHE_KEY)
        for name in ("plan", "shard", "aggregate"):
            with self.subTest(job=name):
                self.assertEqual(keys[name], RELEASE_CACHE_KEY + "${{ steps.digest.outputs.suffix }}")
                steps = jobs[name]["steps"]
                digest = _step_index(steps, lambda st: st.get("id") == "digest", "digest")
                cache = _step_index(steps, lambda st: _uses(st, "actions/cache"), "cache")
                self.assertLess(digest, cache)
                self.assertIn("tools/lock_digest.py", steps[digest]["run"])
                # An assignment, so `bash -e` fails the step when the tool exits 2
                # (an echo of a command substitution would hide it and drop the suffix).
                self.assertIn('suffix="$(python3 tools/lock_digest.py ', steps[digest]["run"])
                self.assertNotIn('echo "suffix=$(', steps[digest]["run"])
        self.assertNotIn("run_id", VERIFY_WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1])

    def test_the_resolved_target_reaches_the_output_the_steps_read(self):
        """`resolve-target` prints the two `key=value` lines the later steps'
        `steps.target.outputs.*` expressions read."""
        steps = _workflow(RELEASE_WORKFLOW)["jobs"]["release"]["steps"]
        resolve = next(s for s in steps if _runs(s, "resolve-target"))
        self.assertEqual(resolve["id"], "target")
        self.assertIn('>> "$GITHUB_OUTPUT"', resolve["run"])
        self.assertEqual(resolve["env"]["TRIGGER_SHA"], "${{ github.sha }}")
        self.assertEqual(resolve["env"]["TRIGGER_RUN"], "${{ github.run_id }}")
        with unittest.mock.patch.object(release, "resolve_target",
                                        return_value=("a" * 40, 12)):
            out = _capture(release.main, ["resolve-target", "--repo", "o/r", "--trigger-sha",
                                          "a" * 40, "--trigger-run", "12"])
        self.assertEqual(out, (0, f"target_sha={'a' * 40}\ntarget_run=12\n"))


def _run_step(step: dict, env: dict, path: str | None = None) -> subprocess.CompletedProcess:
    """A step's `run:` script, verbatim, as GitHub runs it (`bash -e` with
    pipefail), with only `env` (and `PATH`) set."""
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                          capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
                          env={"PATH": path or os.environ.get("PATH", ""), **env})


class TestCalledAndDispatchedModes(unittest.TestCase):
    """The resolve step passes `--trigger-validated` in called mode only, and
    the dispatch guard refuses a dispatched release that found no green CI
    push run (its target fell back to its own run); both scripts run verbatim."""

    def setUp(self):
        self.steps = _workflow(RELEASE_WORKFLOW)["jobs"]["release"]["steps"]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_only_a_call_passes_the_trigger_as_validated(self):
        """A stub `python3` records the argv the step gives resolve-target."""
        resolve = next(s for s in self.steps if _runs(s, "resolve-target"))
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "python3"
        stub.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$ARGV_OUT"\n'
                        'echo target_sha=x\necho target_run=1\n')
        stub.chmod(0o755)
        for event, validated in (("push", True), ("schedule", True),
                                 ("workflow_dispatch", False)):
            with self.subTest(event=event):
                argv_out = self.tmp / f"argv-{event}"
                output = self.tmp / f"output-{event}"
                proc = _run_step(resolve, {
                    "EVENT": event, "REPO": "o/r", "TRIGGER_SHA": "a" * 40, "TRIGGER_RUN": "7",
                    "GITHUB_OUTPUT": str(output), "ARGV_OUT": str(argv_out)},
                    path=f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                argv = argv_out.read_text().split()
                self.assertEqual(argv[:2], ["tools/release/release.py", "resolve-target"])
                self.assertEqual(argv[2:8], ["--repo", "o/r", "--trigger-sha", "a" * 40,
                                             "--trigger-run", "7"])
                self.assertEqual("--trigger-validated" in argv, validated)
                self.assertEqual(len(argv), 9 if validated else 8)
                self.assertEqual(output.read_text(), "target_sha=x\ntarget_run=1\n")

    def test_the_dispatch_guard_refuses_its_own_run(self):
        guard = next(s for s in self.steps if s.get("if") == DISPATCH_IF)
        for target, code in (("41", 0), ("42", 1), ("", 1)):
            with self.subTest(target_run=target):
                proc = _run_step(guard, {"TARGET_RUN": target, "THIS_RUN": "42"})
                self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
                self.assertEqual("::error::no green ci.yml push run" in proc.stdout, bool(code))

    def test_a_dry_run_notes_and_does_not_publish(self):
        dry = next(s for s in self.steps if s.get("if") == f"{RELEASE_STEP_IF} && inputs.dry-run")
        proc = _run_step(dry, {"VERSION": "1.2.3", "TARGET_SHA": "a" * 40})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.startswith("::notice::dry run:"), proc.stdout)
        self.assertIn(f"v1.2.3 at {'a' * 40}", proc.stdout)


def _capture(main, argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    return code, out.getvalue()


# -- Expression contexts in workflow-level and job-level `env` -----------------------------

#: The contexts GitHub Actions admits in a workflow-level and a job-level
#: `env` (its "Context availability" table). `runner`, `steps`, `job` and
#: `env` exist only inside a step. A workflow that uses one of them there is
#: rejected whole and runs no job: that is how the verification workflow lost
#: its required `aggregate` check on pull request #11 (functional finding F1
#: of `workflow-manager-packaged-distribution`).
WORKFLOW_ENV_CONTEXTS = frozenset({"github", "secrets", "inputs", "vars"})
JOB_ENV_CONTEXTS = frozenset({"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"})
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
#: A bare identifier: not a property (`.name`), not a function call
#: (`name(`), so a context root whether dereferenced or used whole.
_IDENTIFIER = re.compile(r"(?<![\w.-])([A-Za-z_][\w-]*)(?![\w-])(?!\s*\()")
_LITERALS = frozenset({"true", "false", "null", "NaN", "Infinity"})


def _expressions(text: str) -> list[str]:
    """Each `${{ }}` body, with its string literals blanked. A `}}` inside a
    string literal does not end the expression."""
    bodies, i = [], 0
    while (start := text.find("${{", i)) != -1:
        j = start + 3
        while j < len(text) and not text.startswith("}}", j):
            literal = _STRING_LITERAL.match(text, j)
            j = literal.end() if literal else j + 1
        bodies.append(_STRING_LITERAL.sub("''", text[start + 3:j]))
        i = j + 2
    return bodies


def _contexts(value) -> set[str]:
    """The context names an `env` value's `${{ }}` expressions use."""
    roots: set[str] = set()
    for expression in _expressions(str(value)):
        roots.update(_IDENTIFIER.findall(expression))
    return roots - _LITERALS


def env_context_violations(workflow: dict) -> list[str]:
    """Every workflow-level or job-level `env` entry using a context GitHub does not admit there."""
    found = []
    for name, value in (workflow.get("env") or {}).items():
        for context in sorted(_contexts(value) - WORKFLOW_ENV_CONTEXTS):
            found.append(f"env.{name}: {context}")
    for job_id, job in (workflow.get("jobs") or {}).items():
        for name, value in (job.get("env") or {}).items():
            for context in sorted(_contexts(value) - JOB_ENV_CONTEXTS):
                found.append(f"jobs.{job_id}.env.{name}: {context}")
    return found


class TestLockDigest(unittest.TestCase):
    """#52: `tools/lock_digest.py`, the nightly's cache-key suffix."""

    LOCK = {"schema_version": 1, "releases": {"2.18.3": {"a": 1, "b": [1, 2]}}}

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "lock_digest", REPO_ROOT / "tools" / "lock_digest.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_an_equal_lock_gives_nothing_even_when_reformatted(self):
        committed = self.write("committed.json", json.dumps(self.LOCK, indent=2) + "\n")
        compact = self.write("lock.json", json.dumps(self.LOCK, separators=(",", ":")))
        reordered = self.write("reordered.json", json.dumps(self.LOCK, sort_keys=True))
        self.assertEqual(self.module.digest(compact, committed), "")
        self.assertEqual(self.module.digest(reordered, committed), "")

    def test_another_lock_gives_a_stable_sixteen_hex_digest(self):
        committed = self.write("committed.json", json.dumps(self.LOCK))
        other = dict(self.LOCK, releases={**self.LOCK["releases"], "2.19.0": {"a": 2}})
        first = self.write("first.json", json.dumps(other, indent=4))
        second = self.write("second.json", json.dumps(other, separators=(",", ":")))
        found = self.module.digest(first, committed)
        self.assertRegex(found, r"^[0-9a-f]{16}$")
        self.assertEqual(self.module.digest(second, committed), found)
        self.assertNotEqual(found, self.module.digest(
            self.write("third.json", json.dumps(dict(other, releases={}))), committed))

    def test_the_command_line_prints_the_suffix_and_refuses_bad_input(self):
        committed = self.write("committed.json", json.dumps(self.LOCK))
        same = self.write("same.json", json.dumps(self.LOCK))
        other = self.write("other.json", json.dumps({"releases": {}}))

        def run(*args):
            return subprocess.run(
                [sys.executable, "-I", str(REPO_ROOT / "tools" / "lock_digest.py"), *args],
                capture_output=True, text=True)

        proc = run(str(same), str(committed))
        self.assertEqual((proc.returncode, proc.stdout), (0, "\n"))
        proc = run(str(other), str(committed))
        self.assertEqual(proc.returncode, 0)
        self.assertRegex(proc.stdout, r"^-[0-9a-f]{16}\n$")
        self.assertEqual(run(str(self.tmp / "missing.json"), str(committed)).returncode, 2)
        self.assertEqual(run(str(same)).returncode, 2)
        self.assertIn("tools/lock_digest.py",
                      (REPO_ROOT / "docs" / "exit-codes.md").read_text(encoding="utf-8"))


class TestEnvExpressionContexts(unittest.TestCase):
    def test_every_workflow_uses_only_admitted_contexts_in_workflow_and_job_env(self):
        workflows = sorted(WORKFLOWS.glob("*.yml"))
        self.assertTrue(workflows)
        for path in workflows:
            with self.subTest(workflow=path.name):
                self.assertEqual(env_context_violations(_workflow(path)), [])

    def test_a_runner_context_in_a_job_env_is_reported(self):
        text = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        marker = "  plan:\n    runs-on: ubuntu-latest\n"
        self.assertIn(marker, text)
        mutated = text.replace(marker, marker + "    env:\n      CACHE: ${{ runner.temp }}/cache\n", 1)
        self.assertEqual(env_context_violations(runner_tests.load_workflow_yaml(mutated)),
                         ["jobs.plan.env.CACHE: runner"])

    def test_admitted_contexts_and_string_literals_are_not_reported(self):
        workflow = {
            "env": {"A": "${{ github.sha }}", "B": "${{ vars.X || 'runner.temp' }}"},
            "jobs": {"j": {"env": {"C": "${{ matrix.shard }}-${{ needs.plan.outputs.shards }}",
                                   "D": "${{ hashFiles('a/b.json') }}", "E": "plain"}}},
        }
        self.assertEqual(env_context_violations(workflow), [])

    def test_a_bare_context_is_reported(self):
        workflow = {"jobs": {"j": {"env": {"A": "${{ toJSON(runner) }}", "B": "${{ job }}",
                                           "C": "${{ fromJSON(steps)[0] }}"}}}}
        self.assertEqual(env_context_violations(workflow),
                         ["jobs.j.env.A: runner", "jobs.j.env.B: job", "jobs.j.env.C: steps"])

    def test_a_closing_brace_pair_in_a_string_does_not_end_the_expression(self):
        workflow = {"env": {"A": "${{ format('}}{0}', runner.temp) }}"},
                    "jobs": {"j": {"env": {"B": "x-${{ format('{{}}', env.Z) }}-${{ github.sha }}"}}}}
        self.assertEqual(env_context_violations(workflow), ["env.A: runner", "jobs.j.env.B: env"])

    def test_literals_function_names_and_properties_are_not_contexts(self):
        workflow = {"jobs": {"j": {"env": {
            "A": "${{ true && null || false }}", "B": "${{ contains(github.ref, 'runner') }}",
            "C": "${{ github.event.runner.job }}", "D": "${{ 1.5e3 }}-${{ 0xff }}",
            "E": "${{ matrix['runner'] }}"}}}}
        self.assertEqual(env_context_violations(workflow), [])

    def test_step_only_contexts_are_reported_at_both_levels(self):
        workflow = {"env": {"A": "${{ runner.os }}"},
                    "jobs": {"j": {"env": {"B": "${{ steps.x.outputs.y }}", "C": "${{ env.Z }}"}}}}
        self.assertEqual(env_context_violations(workflow),
                         ["env.A: runner", "jobs.j.env.B: steps", "jobs.j.env.C: env"])


# -- T-PRT-1: the title workflow ------------------------------------------------------------

class TestTitleWorkflow(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = runner_tests._python3_on_path(Path(tmp.name) / "bin") + os.pathsep + \
            os.environ.get("PATH", "")  # noqa: SLF001

    def test_the_title_check(self):
        doc = _workflow(TITLE_WORKFLOW)
        self.assertEqual(doc["name"], "PR title")
        self.assertEqual(doc["on"], {"pull_request": {"types": ["opened", "edited", "reopened",
                                                                "synchronize"]}})
        self.assertEqual(doc["permissions"], {"contents": "read"})
        [job] = doc["jobs"].values()
        self.assertEqual(job["name"], "Conventional Commit title")
        [check] = [s for s in job["steps"] if _runs(s, "check-title")]
        self.assertEqual(check["env"], {"TITLE": "${{ github.event.pull_request.title }}"})
        self.assertEqual(check["run"].strip(),
                         'python3 tools/release/release.py check-title "$TITLE"')
        for step in job["steps"]:
            self.assertNotIn("github.event.pull_request.title", step.get("run") or "",
                             "the title is interpolated into a script")

    def test_the_step_runs_the_real_check(self):
        """The step's script, verbatim, with a title that would be an injection
        if it were interpolated."""
        [job] = _workflow(TITLE_WORKFLOW)["jobs"].values()
        [check] = [s for s in job["steps"] if _runs(s, "check-title")]
        for title, code, said in (("feat(cli): add --version", 0, "release impact minor"),
                                  ('docs: "$(exit 7)" and `x`', 0, "release impact none"),
                                  ("Update things", 1, "no 'type: description' shape")):
            with self.subTest(title=title):
                proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                                       check["run"]], cwd=str(REPO_ROOT), capture_output=True,
                                      text=True, env={"PATH": self.path, "TITLE": title},
                                      timeout=60)
                self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
                self.assertIn(said, proc.stdout + proc.stderr)


# -- T-SET-1: repository settings as reviewed data ------------------------------------------

def _job_check_names(doc: dict) -> set[str]:
    """The status-check contexts `doc`'s jobs report: a job's `name`, else its
    id; a job that calls a local reusable workflow (`uses: ./...`) reports
    none of its own, only `<its name or id> / <each called job's context>`."""
    names = set()
    for job_id, job in (doc.get("jobs") or {}).items():
        own = job.get("name") or job_id
        uses = job.get("uses") or ""
        if uses.startswith("./"):
            names.update(f"{own} / {called}"
                         for called in _job_check_names(_workflow(REPO_ROOT / uses)))
        else:
            names.add(own)
    return names


def _pull_request_check_names() -> set[str]:
    """The status-check context of every job in a workflow triggered on
    `pull_request`, called workflows' jobs included."""
    names = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = _workflow(path)
        if "pull_request" not in (doc.get("on") or {}):
            continue
        names |= _job_check_names(doc)
    return names


class TestRepositorySettings(unittest.TestCase):

    def setUp(self):
        self.ruleset = json.loads((SETTINGS / "ruleset-main.json").read_text(encoding="utf-8"))
        self.rules = {rule["type"]: rule.get("parameters") for rule in self.ruleset["rules"]}
        self.assertEqual(len(self.rules), len(self.ruleset["rules"]), "a rule type is repeated")

    def test_the_required_checks_exist_and_report_on_pull_requests(self):
        checks = self.rules["required_status_checks"]["required_status_checks"]
        self.assertEqual({c["context"] for c in checks}, REQUIRED_CHECKS)
        self.assertEqual({c["integration_id"] for c in checks}, {ACTIONS_APP})
        missing = REQUIRED_CHECKS - _pull_request_check_names()
        self.assertEqual(missing, set(), "a required check no pull_request job reports would "
                                         "lock every pull request out")

    def test_the_required_aggregate_is_the_entry_points_own_job(self):
        """ci.yml's `aggregate`, with no `name:`, reports exactly `aggregate`;
        the validation's own aggregate reports as `validate / aggregate`, and a
        called job never reports its bare id."""
        names = _pull_request_check_names()
        self.assertIn("aggregate", names)
        self.assertIn("validate / aggregate", names)
        self.assertIn("validate / package", names)
        self.assertNotIn("validate", names)
        self.assertNotIn("publish / release", _job_check_names(_workflow(VERIFY_WORKFLOW)))
        jobs = _workflow(CI_WORKFLOW)["jobs"]
        self.assertNotIn("name", jobs["aggregate"])
        self.assertNotIn("uses", jobs["aggregate"])

    def test_a_typo_in_a_required_check_is_caught(self):
        names = _pull_request_check_names()
        for typo in ("Conventional Commits title", "PR title / Conventional Commit title",
                     "Aggregate", "shard 0"):
            with self.subTest(context=typo):
                self.assertNotIn(typo, names)

    def test_the_ruleset(self):
        self.assertEqual(self.ruleset["target"], "branch")
        self.assertEqual(self.ruleset["enforcement"], "active")
        self.assertEqual(self.ruleset["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        self.assertEqual(self.ruleset["bypass_actors"], [])
        self.assertIs(self.rules["required_status_checks"]["strict_required_status_checks_policy"],
                      False)
        self.assertEqual(self.rules["pull_request"]["allowed_merge_methods"], ["squash"])
        self.assertEqual(self.rules["pull_request"]["required_approving_review_count"], 0)
        for rule in ("deletion", "non_fast_forward", "required_linear_history"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.rules)
        self.assertEqual(set(self.rules), {"deletion", "non_fast_forward",
                                           "required_linear_history", "pull_request",
                                           "required_status_checks"})

    def test_the_merge_settings(self):
        settings = json.loads((SETTINGS / "merge-settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, {
            "allow_squash_merge": True,
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "squash_merge_commit_title": "PR_TITLE",
            "squash_merge_commit_message": "BLANK",
            "allow_auto_merge": True,
            "delete_branch_on_merge": True,
        })


# -- assert-full-plan: the permanent cases --------------------------------------------------

def run_assert_full_plan(scratch: Path, plan: Path, env: dict, *,
                         cache: Path | None = None) -> subprocess.CompletedProcess:
    """The real `release.py assert-full-plan`, rediscovering `scratch`'s inventory
    with `scratch`'s own runner, on `scratch`'s release source and private
    cache (`cache` instead, when given)."""
    env = {**env, **runner_tests.scratch_release_env(scratch)}
    if cache is not None:
        env[release_source.CACHE_ENV] = str(cache)
    return subprocess.run([sys.executable, str(RELEASE_PY), "assert-full-plan", "--repo-dir",
                           str(scratch), str(plan)], cwd=str(scratch), capture_output=True,
                          text=True, env=env, timeout=600)


#: A release `lock_only_release` names in a scratch's lock alone.
LOCK_ONLY = "0.0.2"


def lock_only_release(scratch: Path, version: str = LOCK_ONLY) -> None:
    """Publish `version` from `scratch`'s release source, its manifest's
    `manager` block carrying the frozen suite counts, and name it in `scratch`'s
    lock alone: no pin, and no counts in the lock entry, so only the cached
    manifest can supply them (#58). Committed, so a plan sees it."""
    releases = runner_tests.scratch_releases(scratch)
    files = {"payload/scripts/tiny_test.py": runner_tests.SCRATCH_SUITE.encode()}
    bodies = {t: body.encode() for t, body in runner_tests.SCRATCH_TEMPLATES.items()}
    tree = releases / "trees" / version
    for rel, data in [*files.items(), *((f"templates/{t}", b) for t, b in bodies.items())]:
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_bytes(data)
    manifest = runner_tests._scratch_manifest(files, bodies, version)  # noqa: SLF001
    manifest["manager"] = {"schema_version": 1, "conformance": {
        "suites": {"tiny_test.py": runner_tests.SCRATCH_SUITE_TESTS},
        "portability_exceptions": []}}
    (tree / "manifest.json").write_text(canonical_json(manifest))
    built = package_module.build_package(tree, releases / "source" / version)
    (scratch / "tests" / "tested_releases.json").write_text(canonical_json(
        {"schema_version": 1, "releases": {version: {
            "archive": built.archive.name, "sha256": package_module.file_sha256(built.archive),
            "manifest_sha256": package_module.file_sha256(built.manifest)}}}))
    runner_tests._commit_all(scratch, "a lock-only release")  # noqa: SLF001


def full_plan_units(plan: Path) -> dict:
    return json.loads(plan.read_text())["selection"]


class TestAssertFullPlan(runner_tests._CliCase):  # noqa: SLF001

    def test_a_full_plan_for_this_tree_passes(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        plan = runner_tests._plan_only(self, scratch, "--profile", "ci")  # noqa: SLF001
        self.assertEqual(json.loads(plan.read_text())["selection_kind"], "full")
        proc = run_assert_full_plan(scratch, plan, self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("the plan is the full selection of this tree", proc.stdout)
        self.assertEqual(runner_tests._git(scratch, "status", "--porcelain").strip(), "",  # noqa: SLF001
                         "the rediscovery wrote into the checkout")

    def test_a_lock_only_release_is_primed_before_the_rediscovery(self):
        """#58: with a release only the lock names, whose counts only its
        manifest carries, the rediscovery from a cache that starts empty
        succeeds because assert-full-plan primes the tested set first; the
        same discovery unprimed is the Release run's failure."""
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        lock_only_release(scratch)
        plan = runner_tests._plan_only(self, scratch, "--profile", "ci")  # noqa: SLF001
        unprimed = subprocess.run(
            [sys.executable, "-B", "-c", "from pathlib import Path\n"
             "from parallel import inventory\ninventory.discover(Path('..'))"],
            cwd=str(scratch / "tests"), capture_output=True, text=True, timeout=600,
            env={**self.env, **runner_tests.scratch_release_env(scratch),
                 release_source.CACHE_ENV: str(self.tmp / "unprimed"),
                 "PYTHONPATH": str(scratch / "src")})
        self.assertNotEqual(unprimed.returncode, 0, unprimed.stdout)
        self.assertIn("neither its manifest nor its lock entry carries the frozen suite counts",
                      unprimed.stderr)
        cache = self.tmp / "release-cache"
        proc = run_assert_full_plan(scratch, plan, self.env, cache=cache)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("the plan is the full selection of this tree", proc.stdout)
        # Primed under the lock's digests, as the runner primes it.
        self.assertTrue((cache / LOCK_ONLY / "complete").is_file())
        self.assertFalse((cache / LOCK_ONLY / "SOURCE").exists())

    def test_a_targeted_plan_is_refused(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        plan = runner_tests._plan_only(self, scratch, "--select",  # noqa: SLF001
                                       "test_scratch_shared.py")
        proc = run_assert_full_plan(scratch, plan, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("selection_kind is 'targeted'", proc.stderr)

    def test_a_select_covering_the_whole_inventory_is_refused(self):
        """Full by set equality, not by flag (plan 6.1)."""
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        full = runner_tests._plan_only(self, scratch)  # noqa: SLF001
        modules = sorted({unit.split(":", 1)[1].split("::", 1)[0]
                          for unit in full_plan_units(full) if unit.startswith("host:")})
        argv = [arg for module in modules for arg in ("--select", module)]
        covering = runner_tests._plan_only(self, scratch, *argv)  # noqa: SLF001
        self.assertEqual(full_plan_units(covering), full_plan_units(full))
        proc = run_assert_full_plan(scratch, covering, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("selection_kind is 'targeted'", proc.stderr)

    def test_another_trees_plan_is_refused(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        plan = runner_tests._plan_only(self, scratch)  # noqa: SLF001
        (scratch / "tools" / ".keep").write_text("another tree\n")
        runner_tests._commit_all(scratch, "another tree")  # noqa: SLF001
        proc = run_assert_full_plan(scratch, plan, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("the plan is not runnable here", proc.stderr)
        self.assertIn("plan is for tree", proc.stderr)

    def test_a_tampered_plan_is_refused(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        plan = runner_tests._plan_only(self, scratch)  # noqa: SLF001
        doc = json.loads(plan.read_text())
        doc["selection_kind"] = "full"
        doc["predicted"]["total_work"] += 1
        plan.write_text(canonical_json(doc))
        proc = run_assert_full_plan(scratch, plan, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("plan_digest", proc.stderr)


class TestCheckFullPlan(unittest.TestCase):
    """The set-equality half, on a plan whose own label claims `full`."""

    UNITS = ("host:test_a.py::A", "host:test_b.py::B", "frozen:1.0.0/conformance/s.py::K")

    def plan(self, **changes) -> dict:
        doc = {"selection_kind": "full", "tree_digest": "T",
               "selection": dict.fromkeys(self.UNITS)}
        doc.update(changes)
        return doc

    def check(self, plan: dict) -> None:
        release.check_full_plan(plan, tree_digest="T", unit_ids=self.UNITS)

    def test_the_full_selection_passes(self):
        self.check(self.plan())

    def test_a_full_label_that_omits_a_unit_is_refused(self):
        selection = dict.fromkeys(self.UNITS[:-1])
        with self.assertRaisesRegex(release.ReleaseError, r"1 unit\(s\) missing"):
            self.check(self.plan(selection=selection))

    def test_a_full_label_with_an_unknown_unit_is_refused(self):
        selection = dict.fromkeys(self.UNITS + ("host:test_c.py::C",))
        with self.assertRaisesRegex(release.ReleaseError, r"1 unknown"):
            self.check(self.plan(selection=selection))

    def test_a_partial_class_is_refused(self):
        selection = dict(dict.fromkeys(self.UNITS), **{self.UNITS[0]: ["test_x"]})
        with self.assertRaisesRegex(release.ReleaseError, "partially"):
            self.check(self.plan(selection=selection))

    def test_another_kind_or_tree_is_refused(self):
        for changes, said in (({"selection_kind": "targeted"}, "selection_kind"),
                              ({"selection_kind": None}, "selection_kind"),
                              ({"tree_digest": "U"}, "tree"),
                              ({"selection": None}, "no selection")):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(release.ReleaseError, said):
                    self.check(self.plan(**changes))


if __name__ == "__main__":
    unittest.main(verbosity=1)
