#!/usr/bin/env python3
"""The release and title workflows, the repository settings as reviewed data,
and `release.py assert-full-plan`'s permanent cases.

Checkpoint CP5 of `workflow-manager-trunk-model`:

- T-REL-1: `.github/workflows/release.yml` (`D-Release-Workflow`, plan 5.4);
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
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from support import REPO_ROOT

import test_parallel_runner as runner_tests
from parallel import canonical_json

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
TITLE_WORKFLOW = WORKFLOWS / "pr-title.yml"
VERIFY_WORKFLOW = WORKFLOWS / "workflow-manager-verify.yml"
SETTINGS = REPO_ROOT / ".github" / "repository"
RELEASE_PY = REPO_ROOT / "tools" / "release" / "release.py"

#: The GitHub Actions app: every required check comes from it (plan 6.3).
ACTIONS_APP = 15368
REQUIRED_CHECKS = {"aggregate", "Conventional Commit title"}


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

def release_workflow_problems(doc: dict, verify_name: str) -> list[str]:
    """T-REL-1's structural checks over the parsed release workflow; `[]`
    when it holds. `verify_name` is the verification workflow's own `name:`."""
    problems = []

    def need(condition, message):
        if not condition:
            problems.append(message)

    trigger = (doc.get("on") or {}).get("workflow_run") or {}
    need(sorted(doc.get("on") or {}) == ["workflow_run"], "the release is not only workflow_run")
    need(trigger.get("workflows") == [verify_name],
         f"the trigger is {trigger.get('workflows')!r}, not [{verify_name!r}]")
    need(trigger.get("types") == ["completed"], "the trigger is not `completed`")
    need(trigger.get("branches") == ["main"], "the trigger is not limited to main")
    need(doc.get("permissions") == {"contents": "read"},
         "the workflow's own permissions are not contents: read")

    jobs = doc.get("jobs") or {}
    need(sorted(jobs) == ["release"], f"jobs are {sorted(jobs)}, not [release]")
    job = jobs.get("release") or {}
    condition = job.get("if") or ""
    need("github.event.workflow_run.event == 'push'" in condition,
         "the job does not require a push run")
    need("github.event.workflow_run.conclusion == 'success'" in condition,
         "the job does not require a successful run")
    need(job.get("concurrency") == {"group": "workflow-manager-release",
                                    "cancel-in-progress": False},
         f"the job's concurrency is {job.get('concurrency')!r}, not a serialized release group")
    need("concurrency" not in doc, "the concurrency group is on the workflow, not the job")
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
        fetch = _step_index(steps, lambda s: _runs(s, "UPSTREAM_URL"), "fetch the upstream")
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
        publish = _step_index(steps, lambda s: _runs(s, "gh release create"), "publish")
    except AssertionError as exc:
        return problems + [str(exc)]

    need(checkouts and checkouts[0] < resolve, "no checkout of main before resolve-target")
    need(checkouts and (steps[checkouts[0]].get("with") or {}).get("fetch-depth") == 0,
         "the first checkout is shallow: resolve-target reads main's first-parent history")
    need(len(target_checkout) == 1, "the target is not checked out exactly once")
    if target_checkout:
        need(resolve < target_checkout[0], "the target is checked out before it is resolved")
        need((steps[target_checkout[0]].get("with") or {}).get("fetch-depth") == 0,
             "the target checkout is shallow: next-version reads tags and history")
        need(target_checkout[0] < python < full_plan and target_checkout[0] < fetch < full_plan,
             "python 3.12 and the upstream are not set up between the target checkout and "
             "assert-full-plan")
    need((steps[python].get("with") or {}) == {"python-version": "3.12"}, "python is not 3.12")
    need('rev-parse "$UPSTREAM_TAG^{commit}")" = "$UPSTREAM_COMMIT"' in steps[fetch]["run"],
         "the fetched upstream tag is not checked against the pinned commit")
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
    need("--target \"$TARGET_SHA\"" in steps[publish]["run"],
         "the release is not created at the resolved target")
    need((steps[publish].get("env") or {}).get("TARGET_SHA")
         == "${{ steps.target.outputs.target_sha }}", "TARGET_SHA is not the resolved target")
    for index in (package, publish):
        need("steps.superseded.outputs.superseded != 'true'" in (steps[index].get("if") or "")
             and "steps.version.outputs.version != ''" in (steps[index].get("if") or ""),
             f"step {index} runs with nothing to release or when superseded")
    need("-eq 3" in steps[superseded]["run"], "exit 3 is not treated as covered by a newer release")
    return problems


class TestReleaseWorkflow(unittest.TestCase):

    def setUp(self):
        self.verify_name = _workflow(VERIFY_WORKFLOW)["name"]

    def test_the_release_workflow_holds_every_structural_rule(self):
        self.assertEqual(self.verify_name, "Workflow manager verification")
        self.assertEqual(release_workflow_problems(_workflow(RELEASE_WORKFLOW), self.verify_name),
                         [])

    def test_each_mutation_is_caught(self):
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        mutants = {
            "the trigger's own run": ("run-id: ${{ steps.target.outputs.target_run }}",
                                      "run-id: ${{ github.event.workflow_run.id }}"),
            "a pull-request run": ("github.event.workflow_run.event == 'push'",
                                   "github.event.workflow_run.event != ''"),
            "a red run": ("github.event.workflow_run.conclusion == 'success'",
                          "github.event.workflow_run.conclusion != ''"),
            "another workflow": ('workflows: ["Workflow manager verification"]',
                                 'workflows: ["Workflow manager verify"]'),
            "any branch": ("    branches: [main]\n", ""),
            "a cancelled release": ("cancel-in-progress: false", "cancel-in-progress: true"),
            "contents: write for the workflow": ("permissions:\n  contents: read",
                                                 "permissions:\n  contents: write"),
            "no full-plan check": ('python3 tools/release/release.py assert-full-plan',
                                   'echo'),
            "the trigger's own commit": ('--target "$TARGET_SHA"', '--target "$GITHUB_SHA"'),
            "exit 3 fails the release": ('"$status" -eq 3', '"$status" -eq 4'),
            "no superseded guard": ("        if: steps.version.outputs.version != '' && "
                                    "steps.superseded.outputs.superseded != 'true'\n        env:\n"
                                    "          GH_TOKEN",
                                    "        env:\n          GH_TOKEN"),
            "python 3.11": ('python-version: "3.12"', 'python-version: "3.11"'),
        }
        for label, (old, new) in mutants.items():
            with self.subTest(mutation=label):
                mutated = text.replace(old, new, 1)
                self.assertNotEqual(mutated, text, "the mutation did not apply")
                self.assertNotEqual(release_workflow_problems(
                    runner_tests.load_workflow_yaml(mutated), self.verify_name), [])

    def test_the_resolved_target_reaches_the_output_the_steps_read(self):
        """`resolve-target` prints the two `key=value` lines the later steps'
        `steps.target.outputs.*` expressions read."""
        steps = _workflow(RELEASE_WORKFLOW)["jobs"]["release"]["steps"]
        resolve = next(s for s in steps if _runs(s, "resolve-target"))
        self.assertEqual(resolve["id"], "target")
        self.assertIn('>> "$GITHUB_OUTPUT"', resolve["run"])
        self.assertEqual(resolve["env"]["TRIGGER_SHA"], "${{ github.event.workflow_run.head_sha }}")
        self.assertEqual(resolve["env"]["TRIGGER_RUN"], "${{ github.event.workflow_run.id }}")
        with unittest.mock.patch.object(release, "resolve_target",
                                        return_value=("a" * 40, 12)):
            out = _capture(release.main, ["resolve-target", "--repo", "o/r", "--trigger-sha",
                                          "a" * 40, "--trigger-run", "12"])
        self.assertEqual(out, (0, f"target_sha={'a' * 40}\ntarget_run=12\n"))


def _capture(main, argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    return code, out.getvalue()


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

def _pull_request_check_names() -> set[str]:
    """The status-check context of every job in a workflow triggered on
    `pull_request`: the job's `name`, else its id."""
    names = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = _workflow(path)
        if "pull_request" not in (doc.get("on") or {}):
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            names.add(job.get("name") or job_id)
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

def run_assert_full_plan(scratch: Path, plan: Path, env: dict) -> subprocess.CompletedProcess:
    """The real `release.py assert-full-plan`, rediscovering `scratch`'s inventory
    with `scratch`'s own runner."""
    return subprocess.run([sys.executable, str(RELEASE_PY), "assert-full-plan", "--repo-dir",
                           str(scratch), str(plan)], cwd=str(scratch), capture_output=True,
                          text=True, env=env, timeout=600)


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
