#!/usr/bin/env python3
"""No orphaned Git processes: the tests of `workflow-manager-test-cleanup`.

Checkpoint CP1 (`D-Quiet-Git`, plan 5.1-5.3, 5.5): the chunk environment's
layer (T-QG-1), the per-repository layer and the run's Git template
(T-QG-2), the frozen isolated-test path the template covers (T-QG-5), and
the static routing check that keeps every `git init`/`git clone` site of
this repository on the shared setup (T-QG-4).

Checkpoint CP2 (`D-Orphan-Check`, plan 5.4-5.5): the environment layer
winning under the wrapper (T-QG-3), the wrapper driven directly (T-OC-1),
through the executor's three modes (T-OC-2), the `orphan_sources` schema
and chunking (T-OC-3), and the timeout and interrupt paths (T-OC-4).
"""

from __future__ import annotations

import ast
import filecmp
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401 -- puts src/ on sys.path, bytecode off
from support import REPO_ROOT

import test_parallel_runner as tpr
from parallel import cli, executor, inventory, isolation, plan_schema, planner, resources
from workflow_manager.fixture import (
    THROWAWAY_GIT_CONFIG,
    configure_throwaway_repo,
    init_git_repo,
)

FROZEN_260_SCRIPTS = REPO_ROOT / "distribution" / "workflow" / "2.6.0" / "payload" / "scripts"

#: What neutralises every inherited Git setting a test must not see: the
#: operator's `GIT_CONFIG_*` series and `-c` parameters, a template, and the
#: user and system config (an `init.templateDir` there included).
_INHERITED_GIT = ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_TEMPLATE_DIR",
                  "GIT_CONFIG_SYSTEM")


def _is_inherited_git(name: str) -> bool:
    return name in _INHERITED_GIT or name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))


def stripped_env(**extra: str) -> dict:
    """`os.environ` without any inherited Git setting, global and system
    config off; `extra` is laid over it."""
    env = {k: v for k, v in os.environ.items() if not _is_inherited_git(k)}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.update(extra)
    return env


def git(cwd: Path, *args: str, env: dict | None = None, check: bool = True):
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, check=check,
                          capture_output=True, text=True)


def series(env: dict) -> list[tuple[str, str]]:
    """`env`'s `GIT_CONFIG_COUNT` series, in order."""
    count = int(env.get("GIT_CONFIG_COUNT", "0"))
    return [(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"]) for i in range(count)]


def with_series(pairs, **extra: str) -> dict:
    env = stripped_env(**extra)
    env["GIT_CONFIG_COUNT"] = str(len(pairs))
    for index, (key, value) in enumerate(pairs):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


OURS = list(THROWAWAY_GIT_CONFIG.items())


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="wm-quiet-git-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def plain_repo(self, name: str = "plain") -> Path:
        """A repository with Git's defaults: no helper, no template."""
        path = self.tmp / name
        git(self.tmp, "init", "-q", str(path), env=stripped_env())
        return path

    def local_config(self, repo: Path, env: dict | None = None) -> dict[str, str | None]:
        found = {}
        for key in THROWAWAY_GIT_CONFIG:
            proc = git(repo, "config", "--local", "--get", key, env=env or stripped_env(),
                       check=False)
            found[key] = proc.stdout.strip() if proc.returncode == 0 else None
        return found


# -- T-QG-1: the chunk environment's layer ----------------------------------------------------

class TestChunkEnvGitConfig(_Tmp):

    def chunk_env(self, base: dict) -> dict:
        return isolation.chunk_env(self.tmp / "chunk-tmp", base=base)

    def test_the_settings_are_the_fixture_constant(self):
        self.assertEqual(isolation.THROWAWAY_GIT_CONFIG, THROWAWAY_GIT_CONFIG)
        self.assertEqual(THROWAWAY_GIT_CONFIG, {"maintenance.auto": "false", "gc.auto": "0",
                                                "maintenance.autoDetach": "false",
                                                "gc.autoDetach": "false"})

    def test_the_four_pairs_are_added(self):
        self.assertEqual(series(self.chunk_env(stripped_env())), OURS)

    def test_a_parents_matching_pairs_are_kept_and_not_duplicated(self):
        watchdog = [("maintenance.autoDetach", "false"), ("gc.autoDetach", "false")]
        env = self.chunk_env(with_series(watchdog))
        self.assertEqual(series(env), watchdog + [("maintenance.auto", "false"),
                                                  ("gc.auto", "0")])

    def test_a_parents_different_value_is_kept_and_ours_wins(self):
        env = self.chunk_env(with_series([("gc.autoDetach", "true"), ("a.b", "c")]))
        self.assertEqual(series(env)[:2], [("gc.autoDetach", "true"), ("a.b", "c")])
        self.assertEqual(series(env)[-1], ("gc.autoDetach", "false"))
        repo = self.plain_repo()
        self.assertEqual(git(repo, "config", "--get", "gc.autoDetach", env=env).stdout.strip(),
                         "false")
        self.assertEqual(git(repo, "config", "--get", "a.b", env=env).stdout.strip(), "c")

    def test_the_last_inherited_value_decides(self):
        env = self.chunk_env(with_series([("maintenance.auto", "false"),
                                          ("maintenance.auto", "true")]))
        self.assertEqual(series(env).count(("maintenance.auto", "false")), 2)
        repo = self.plain_repo()
        self.assertEqual(
            git(repo, "config", "--get", "maintenance.auto", env=env).stdout.strip(), "false")

    def test_keys_match_case_insensitively(self):
        env = self.chunk_env(with_series([("Maintenance.AutoDetach", "true")]))
        self.assertIn(("maintenance.autoDetach", "false"), series(env))
        repo = self.plain_repo()
        self.assertEqual(
            git(repo, "config", "--get", "maintenance.autodetach", env=env).stdout.strip(),
            "false")
        same = self.chunk_env(with_series([("Maintenance.AutoDetach", "false")]))
        self.assertNotIn(("maintenance.autoDetach", "false"), series(same))

    def test_a_nested_call_is_a_no_op(self):
        once = self.chunk_env(stripped_env())
        twice = self.chunk_env(once)
        self.assertEqual(series(twice), series(once))

    def test_a_malformed_count_is_refused(self):
        for base in (stripped_env(GIT_CONFIG_COUNT="x"), stripped_env(GIT_CONFIG_COUNT="-1"),
                     stripped_env(GIT_CONFIG_COUNT=""),
                     stripped_env(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="a.b",
                                  GIT_CONFIG_VALUE_0="c", GIT_CONFIG_KEY_1="d.e"),
                     stripped_env(GIT_CONFIG_COUNT="1", GIT_CONFIG_VALUE_0="c")):
            with self.subTest(count=base.get("GIT_CONFIG_COUNT")), \
                    self.assertRaises(isolation.GitConfigEnvError):
                self.chunk_env(base)

    def test_parameters_setting_one_of_the_keys_are_refused(self):
        for parameters in ("'maintenance.auto'='true'", "'gc.auto=1'",
                           "'a.b'='c' 'Gc.AutoDetach'='true'", "'maintenance.auto'="):
            with self.subTest(parameters=parameters), \
                    self.assertRaises(isolation.GitConfigEnvError):
                self.chunk_env(stripped_env(GIT_CONFIG_PARAMETERS=parameters))

    def _active_include(self) -> Path:
        included = self.tmp / "active.cfg"
        included.write_text("[gc]\n\tauto = 1\n\tautoDetach = true\n"
                            "[maintenance]\n\tauto = true\n\tautoDetach = true\n")
        return included

    def test_parameters_including_a_file_are_refused(self):
        # The included file would outrank the appended series (external
        # implementation review, round 1).
        included = self._active_include()
        for key in ("include.path", "Include.Path", "includeIf.gitdir:/.path",
                    "includeif.onbranch:main.PATH"):
            parameters = f"'a.b'='c' '{key}'='{included}'"
            with self.subTest(key=key):
                with self.assertRaises(isolation.GitConfigEnvError):
                    self.chunk_env(stripped_env(GIT_CONFIG_PARAMETERS=parameters))
                with self.assertRaises(isolation.GitConfigEnvError):
                    isolation.check_git_env(stripped_env(GIT_CONFIG_PARAMETERS=parameters))

    def test_an_include_in_the_series_is_kept_and_ours_win(self):
        included = self._active_include()
        env = self.chunk_env(with_series([("include.path", str(included))]))
        self.assertEqual(series(env), [("include.path", str(included))] + OURS)
        repo = self.plain_repo()
        for key, value in THROWAWAY_GIT_CONFIG.items():
            with self.subTest(key=key):
                self.assertEqual(git(repo, "config", "--get", key, env=env).stdout.strip(),
                                 value)

    def test_an_include_after_the_quiet_keys_in_the_series_is_overridden(self):
        # The four quiet pairs followed by an include of the active file: Git
        # expands the include where it stands, so ours are re-appended after
        # it (local implementation review, round 2).
        included = self._active_include()
        inherited = with_series(OURS + [("include.path", str(included))])
        env = self.chunk_env(inherited)
        self.assertEqual(series(env), OURS + [("include.path", str(included))] + OURS)
        repo = self.plain_repo()
        for key, value in THROWAWAY_GIT_CONFIG.items():
            with self.subTest(key=key):
                self.assertEqual(git(repo, "config", "--get", key, env=env).stdout.strip(),
                                 value)
        self.assertEqual(series(self.chunk_env(env)), series(env))

    def test_unparsable_parameters_are_refused(self):
        for parameters in ("garbage", "'unterminated", "'a.b'='c'x", "'a.b'x"):
            with self.subTest(parameters=parameters), \
                    self.assertRaises(isolation.GitConfigEnvError):
                self.chunk_env(stripped_env(GIT_CONFIG_PARAMETERS=parameters))

    def test_parameters_setting_an_unrelated_key_are_kept(self):
        parameters = "'a.b'='c' 'x.y'='it'\\''s'"
        env = self.chunk_env(stripped_env(GIT_CONFIG_PARAMETERS=parameters))
        self.assertEqual(env["GIT_CONFIG_PARAMETERS"], parameters)
        self.assertEqual(series(env), OURS)

    def test_the_parser_reads_what_git_writes(self):
        repo = self.plain_repo()
        git(repo, "config", "alias.params", "!printenv GIT_CONFIG_PARAMETERS", env=stripped_env())
        written = git(repo, "-c", "a.b=c", "-c", "x.y=it's !", "-c", "flag.only",
                      "-c", "maintenance.auto=true", "params", env=stripped_env()).stdout.strip()
        self.assertEqual(isolation.parse_git_config_parameters(written),
                         [("a.b", "c"), ("x.y", "it's !"), ("flag.only", None),
                          ("maintenance.auto", "true")])
        with self.assertRaises(isolation.GitConfigEnvError):
            self.chunk_env(stripped_env(GIT_CONFIG_PARAMETERS=written))

    def test_the_refusal_is_a_tagged_exit_2_before_any_chunk(self):
        self.assertTrue(issubclass(isolation.GitConfigEnvError, cli.REFUSALS))
        with self.assertRaises(isolation.GitConfigEnvError):
            isolation.check_git_env(stripped_env(GIT_CONFIG_COUNT="nope"))
        isolation.check_git_env(stripped_env())


# -- T-QG-2: the per-repository layer and the run's template ----------------------------------

class TestThrowawayRepositories(_Tmp):

    def test_init_git_repo_writes_the_four_keys(self):
        repo = self.tmp / "fixture"
        init_git_repo(repo)
        self.assertEqual(self.local_config(repo), THROWAWAY_GIT_CONFIG)

    def test_a_configured_clone_has_the_four_keys(self):
        source = self.tmp / "source"
        init_git_repo(source)
        (source / "f").write_text("x")
        git(source, "add", "f", env=stripped_env())
        git(source, "commit", "-q", "-m", "c", env=stripped_env())
        clone = self.tmp / "clone"
        git(self.tmp, "clone", "-q", str(source), str(clone), env=stripped_env())
        self.assertEqual(set(self.local_config(clone).values()), {None})
        configure_throwaway_repo(clone)
        self.assertEqual(self.local_config(clone), THROWAWAY_GIT_CONFIG)

    def test_the_template_covers_a_plain_init_and_a_plain_clone(self):
        template = isolation.build_git_template(self.tmp / "run")
        self.assertEqual(template, self.tmp / "run" / isolation.GIT_TEMPLATE_DIR_NAME)
        self.assertFalse((self.tmp / "run" / "git-template-scratch").exists())
        env = isolation.chunk_env(self.tmp / "chunk-tmp", base=stripped_env(),
                                  git_template=template)
        default = self.plain_repo("default")
        initialised = self.tmp / "initialised"
        git(self.tmp, "init", "-q", str(initialised), env=env)
        (initialised / "f").write_text("x")
        git(initialised, "add", "f", env=env)
        git(initialised, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
            "commit", "-q", "-m", "c", env=env)
        cloned = self.tmp / "cloned"
        git(self.tmp, "clone", "-q", str(initialised), str(cloned), env=env)
        for repo in (initialised, cloned):
            with self.subTest(repo=repo.name):
                # Read with no inherited series: the keys are in the local config.
                self.assertEqual(self.local_config(repo), THROWAWAY_GIT_CONFIG)
                for sub in ("hooks", "info"):
                    self.assertEqual(_tree(repo / ".git" / sub), _tree(default / ".git" / sub),
                                     sub)

    def test_a_direct_run_chunk_without_a_template_drops_an_inherited_one(self):
        run_dir = self.tmp / "run"
        record = isolation.chunk_paths(run_dir, "env").record
        code = textwrap.dedent("""
            import json, os, sys
            count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
            pairs = [(os.environ[f"GIT_CONFIG_KEY_{i}"], os.environ[f"GIT_CONFIG_VALUE_{i}"])
                     for i in range(count)]
            json.dump({"passed": True, "template": os.environ.get("GIT_TEMPLATE_DIR"),
                       "pairs": pairs}, open(sys.argv[1], "w"))
        """)
        with mock.patch.dict(os.environ, {"GIT_TEMPLATE_DIR": str(self.tmp / "operator")}):
            run = isolation.run_chunk(self.tmp, "env", [sys.executable, "-c", code, record],
                                      run_dir=run_dir, timeout=60)
        self.assertEqual(run.outcome, isolation.PASSED, run.detail)
        self.assertIsNone(run.record["template"])
        last = {key.lower(): value for key, value in run.record["pairs"]}
        for key, value in THROWAWAY_GIT_CONFIG.items():
            self.assertEqual(last[key.lower()], value, key)


def _tree(root: Path) -> dict[str, bytes | None]:
    """Every entry under `root`: a file's bytes, `None` for a directory."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            found[os.path.relpath(os.path.join(dirpath, name), root)] = None
        for name in filenames:
            path = os.path.join(dirpath, name)
            found[os.path.relpath(path, root)] = Path(path).read_bytes()
    return found


# -- T-QG-5: the frozen isolated-test path ----------------------------------------------------

_MATERIALIZE = textwrap.dedent("""
    import sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    import workflow_state
    print(workflow_state._materialize_pinned_worktree_at_commit(Path(sys.argv[2]), sys.argv[3]))
""")


class _FrozenCloneCase(_Tmp):
    """The frozen `2.6.0` engine's `_materialize_pinned_worktree_at_commit`
    clones with `env=None`, and `_run_named_test_in_scratch` then runs Git
    in that clone with an environment of `PATH` alone: only the template
    reaches it. The frozen function runs unmodified, imported from the
    committed payload in a fresh interpreter (`-B`: nothing is written into
    the payload)."""

    def setUp(self):
        super().setUp()
        self.source = self.tmp / "source"
        init_git_repo(self.source)
        (self.source / "f").write_text("x")
        git(self.source, "add", "f", env=stripped_env())
        git(self.source, "commit", "-q", "-m", "c", env=stripped_env())
        self.commit = git(self.source, "rev-parse", "HEAD", env=stripped_env()).stdout.strip()
        self.template = isolation.build_git_template(self.tmp / "run")

    def materialize(self, template: Path | None) -> Path:
        scratch_tmp = self.tmp / ("with" if template else "without")
        scratch_tmp.mkdir()
        overrides = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
                     "TMPDIR": str(scratch_tmp)}
        if template is not None:
            overrides["GIT_TEMPLATE_DIR"] = str(template)
        with mock.patch.dict(os.environ):
            for name in [n for n in os.environ if _is_inherited_git(n)]:
                del os.environ[name]
            os.environ.update(overrides)
            out = subprocess.run(
                [sys.executable, "-B", "-c", _MATERIALIZE, str(FROZEN_260_SCRIPTS),
                 str(self.source), self.commit],
                check=True, capture_output=True, text=True, cwd=str(self.tmp)).stdout
        clone = Path(out.strip().splitlines()[-1])
        self.assertTrue(clone.is_relative_to(scratch_tmp), clone)
        self.addCleanup(shutil.rmtree, clone, True)
        return clone

    def scopes(self, clone: Path) -> dict[str, str | None]:
        path_only = {"PATH": os.environ.get("PATH", "")}
        found = {}
        for key in THROWAWAY_GIT_CONFIG:
            proc = git(clone, "config", "--show-scope", "--get", key, env=path_only, check=False)
            found[key] = proc.stdout.strip() if proc.returncode == 0 else None
        return found



class TestFrozenEvidenceClone(_FrozenCloneCase):
    """T-QG-5."""

    def test_the_template_puts_the_keys_in_the_clones_local_config(self):
        with_template = self.scopes(self.materialize(self.template))
        self.assertEqual(with_template,
                         {key: f"local\t{value}" for key, value in THROWAWAY_GIT_CONFIG.items()})
        without = self.scopes(self.materialize(None))
        self.assertEqual(without, {key: None for key in THROWAWAY_GIT_CONFIG})

    def test_the_frozen_payload_is_untouched(self):
        before = _tree(FROZEN_260_SCRIPTS)
        self.materialize(self.template)
        self.assertEqual(_tree(FROZEN_260_SCRIPTS), before)
        status = git(REPO_ROOT, "status", "--porcelain", "--", str(FROZEN_260_SCRIPTS)).stdout
        self.assertEqual(status, "")


# -- T-QG-4: the static routing check ---------------------------------------------------------

VERBS = frozenset({"init", "clone"})
CONFIGURE = "configure_throwaway_repo"
_UNWRAP = ("str", "fspath", "Path")

#: `(relative path, enclosing function, verb)` of a site the check does not
#: apply to, each with its reason. A false positive goes here, never into a
#: looser rule.
EXEMPTIONS = {
    ("tests/parallel/isolation.py", "build_git_template", "init"):
        "reads Git's own default template into the run's template; the scratch repository "
        "never commits and is deleted at once",
    ("tests/test_orphan_processes.py", "plain_repo", "init"):
        "makes a default-config repository on purpose: the baseline T-QG-1 and T-QG-2 "
        "compare against",
    ("tests/test_orphan_processes.py",
     "test_the_template_covers_a_plain_init_and_a_plain_clone", "init"):
        "a plain init under the chunk environment, which the run's template must cover",
    ("tests/test_orphan_processes.py",
     "test_the_template_covers_a_plain_init_and_a_plain_clone", "clone"):
        "a plain clone under the chunk environment, which the run's template must cover",
}

SCANNED = ("tests/*.py", "tests/parallel/*.py", "src/workflow_manager/*.py")
SKIPPED = ("src/workflow_manager/fixture.py",)


def _const(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _unwrap(node):
    while (isinstance(node, ast.Call) and _callee(node) in _UNWRAP and len(node.args) == 1
           and not node.keywords):
        node = node.args[0]
    return node


def _key(node) -> str:
    return ast.dump(_unwrap(node))


def _verb_at(items) -> tuple[str, int] | None:
    for index, item in enumerate(items):
        if _const(item) and item.value in VERBS:
            return item.value, index
    return None


def _after_verb(items, index):
    rest = [item for item in items[index + 1:] if not _const(item)]
    return rest[-1] if rest else None


def _sites(tree):
    """`(node, shape, verb, destination or None)` for every site of 5.3."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (_callee(node) or "").endswith("git"):
            found = _verb_at(node.args)
            if found:
                verb, index = found
                dest = _after_verb(node.args, index)
                if dest is None and verb == "init" and index > 0 and not _const(node.args[0]):
                    dest = node.args[0]
                yield node, 1, verb, dest
        elif isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            first = node.elts[0]
            if _const(first) and first.value in VERBS:
                yield node, 3, first.value, None
            elif any(_const(e) and e.value == "git" for e in node.elts):
                git_at = next(i for i, e in enumerate(node.elts) if _const(e) and e.value == "git")
                found = _verb_at(node.elts[git_at + 1:])
                if found:
                    verb, offset = found
                    index = git_at + 1 + offset
                    dest = _after_verb(node.elts, index)
                    if dest is None and verb == "init":
                        for i, e in enumerate(node.elts[:index]):
                            if _const(e) and e.value == "-C" and i + 1 < index:
                                dest = node.elts[i + 1]
                    yield node, 2, verb, dest


_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def check_source(source: str, filename: str) -> list[dict]:
    """Every site of `source` that is not followed, in its own enclosing
    function (or module), by `configure_throwaway_repo(<its destination>)`."""
    tree = ast.parse(source, filename=filename)
    scope_of = {}

    def mark(node, scope):
        for child in ast.iter_child_nodes(node):
            scope_of[child] = scope
            mark(child, child if isinstance(child, _SCOPES) else scope)

    mark(tree, tree)
    configured = [(scope_of[n], _key(n.args[0]), (n.lineno, n.col_offset))
                  for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and _callee(n) == CONFIGURE and len(n.args) == 1]
    failures = []
    for node, shape, verb, dest in _sites(tree):
        scope = scope_of.get(node, tree)
        end = (node.end_lineno, node.end_col_offset)
        ok = dest is not None and not _const(dest) and any(
            s is scope and key == _key(dest) and at > end for s, key, at in configured)
        if not ok:
            failures.append({
                "file": filename, "line": node.lineno, "shape": shape, "verb": verb,
                "function": getattr(scope, "name", "<module>"),
                "destination": "unresolved" if dest is None or _const(dest)
                else ast.unparse(dest)})
    return failures


def check_tree(root: Path) -> list[dict]:
    failures = []
    for pattern in SCANNED:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            if rel in SKIPPED:
                continue
            for failure in check_source(path.read_text(encoding="utf-8"), rel):
                if (rel, failure["function"], failure["verb"]) not in EXEMPTIONS:
                    failures.append(failure)
    return failures


def _describe(failure: dict) -> str:
    helper = ("call init_git_repo(<repository>)" if failure["verb"] == "init"
              else f"call {CONFIGURE}(<the clone's destination>) after it")
    return (f"{failure['file']}:{failure['line']}: shape {failure['shape']} git "
            f"{failure['verb']}, destination {failure['destination']}: {helper} "
            "(src/workflow_manager/fixture.py)")


class TestRoutingCheck(unittest.TestCase):

    def flagged(self, source: str) -> list[dict]:
        return check_source(textwrap.dedent(source), "<synthetic>")

    def test_the_real_tree_routes_every_site_through_the_shared_setup(self):
        failures = check_tree(REPO_ROOT)
        self.assertEqual(failures, [], "\n".join(map(_describe, failures)))

    def test_every_exemption_still_matches_a_site(self):
        seen = set()
        for rel, function, verb in EXEMPTIONS:
            for failure in check_source((REPO_ROOT / rel).read_text(encoding="utf-8"), rel):
                seen.add((rel, failure["function"], failure["verb"]))
        self.assertEqual(set(EXEMPTIONS) - seen, set())

    def test_the_three_shapes_are_found(self):
        cases = {
            1: ('def f(root):\n    _git(root, "init", "-q")\n', "init", "root"),
            2: ('def f(src, dest):\n    run(["git", "clone", "-q", str(src), str(dest)])\n',
                "clone", "str(dest)"),
            3: ('def f(root):\n    for args in (["init", "-q", "-b", "main"],):\n'
                '        run(["git", "-C", str(root), *args])\n', "init", "unresolved"),
        }
        for shape, (source, verb, dest) in cases.items():
            with self.subTest(shape=shape):
                (failure,) = self.flagged(source)
                self.assertEqual((failure["shape"], failure["verb"], failure["destination"]),
                                 (shape, verb, dest))

    def test_a_configured_clone_passes_through_str_unwrapping(self):
        self.assertEqual(self.flagged("""
            def f(tmp, src, dest):
                _git(tmp, "clone", "-q", str(src), str(dest))
                configure_throwaway_repo(dest)
            def g(src, path):
                subprocess.run(["git", "clone", "-q", str(src), str(path)], check=True)
                configure_throwaway_repo(Path(path))
        """), [])

    def test_a_clone_configured_only_on_another_repository_is_flagged(self):
        for tail in ("configure_throwaway_repo(root)", "init_git_repo(root)"):
            with self.subTest(tail=tail):
                (failure,) = self.flagged(f"""
                    class C:
                        @classmethod
                        def _build(cls, tmp):
                            root = cls.root
                            init_git_repo(root)
                            cls.clone = tmp / "clone"
                            _git(tmp, "clone", "-q", "--no-local", str(root), str(cls.clone))
                            {tail}
                """)
                self.assertEqual({"verb": failure["verb"], "destination": failure["destination"]},
                                 {"verb": "clone", "destination": "str(cls.clone)"})

    def test_configuring_before_the_clone_is_flagged(self):
        (failure,) = self.flagged("""
            def f(tmp, src, dest):
                configure_throwaway_repo(dest)
                _git(tmp, "clone", str(src), str(dest))
        """)
        self.assertEqual(failure["verb"], "clone")

    def test_configuring_in_another_function_is_flagged(self):
        (failure,) = self.flagged("""
            def f(tmp, src, dest):
                _git(tmp, "clone", str(src), str(dest))
                def later():
                    configure_throwaway_repo(dest)
        """)
        self.assertEqual(failure["verb"], "clone")

    def test_an_init_with_a_branch_option_resolves_to_its_repository(self):
        self.assertEqual(self.flagged("""
            def f(root):
                _git(root, "init", "-q", "-b", "main")
                configure_throwaway_repo(root)
        """), [])

    def test_a_trailing_option_value_is_not_the_destination(self):
        self.assertEqual(self.flagged("""
            def f(tmp, src, dest):
                _git(tmp, "clone", str(src), str(dest), "--origin", "up")
                configure_throwaway_repo(dest)
        """), [])

    def test_a_string_literal_destination_fails_closed(self):
        (failure,) = self.flagged("""
            def f(tmp):
                _git(tmp, "clone", "../src", "dest")
                configure_throwaway_repo("dest")
        """)
        self.assertEqual(failure["destination"], "unresolved")
        # With a non-constant source, the source is read as the destination,
        # which no later configuration of the literal matches.
        (failure,) = self.flagged("""
            def f(tmp, src):
                _git(tmp, "clone", str(src), "dest")
                configure_throwaway_repo("dest")
        """)
        self.assertEqual(failure["destination"], "str(src)")

    def test_shape_3_is_always_unresolved(self):
        (failure,) = self.flagged("""
            def f(root):
                for args in (["init", "-q"],):
                    run(["git", "-C", str(root), *args])
                configure_throwaway_repo(root)
        """)
        self.assertEqual((failure["shape"], failure["destination"]), (3, "unresolved"))

    def test_a_verb_inside_a_longer_string_and_worktree_add_are_not_sites(self):
        self.assertEqual(self.flagged("""
            def f(root, path, text):
                assert 'git init -q "$upstream"' in text
                _git(root, "worktree", "add", "-q", "-b", "wt", str(path))
                run(["git", "worktree", "add", str(path)])
        """), [])



# == CP2: the leak check (D-Orphan-Check, plan 5.4) ====================================

REAPER = REPO_ROOT / "tests" / "parallel" / "reaper.py"
#: `comm` of a process forked (not exec'd) from a chunk started as `sys.executable`.
PY_COMM = f"[{Path(sys.executable).name[:15]}]"


def _dead(pid: int) -> bool:
    """Gone, or at least not a live process (a zombie counts as not reaped)."""
    return not Path(f"/proc/{pid}").exists()


def _state(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


class _ReaperCase(_Tmp):
    """Drives `reaper.py` directly (T-OC-1): each call gets its own report."""

    def reap(self, code: str | None = None, *args: str, argv=None, pass_fds=(), env=None,
             timeout: float = 120):
        self._n = getattr(self, "_n", 0) + 1
        report = self.tmp / f"report-{self._n}.json"
        chunk = argv if argv is not None else [sys.executable, "-B", "-c", textwrap.dedent(code)]
        wrapper = [sys.executable, "-I", "-S", "-B", str(REAPER), "--report", str(report),
                   "--chunk-id", f"chunk-{self._n}", *args, "--", *map(str, chunk)]
        started = time.monotonic()
        proc = subprocess.run(wrapper, capture_output=True, text=True, env=env, timeout=timeout,
                              pass_fds=pass_fds)
        elapsed = time.monotonic() - started
        doc = json.loads(report.read_text()) if report.exists() else None
        return proc, doc, elapsed


#: A chunk that double-forks a daemon (`setsid`) running `DAEMON`, waits
#: until the daemon is in the state `READY` names, and exits. The daemon's
#: pid goes to `argv[1]`. For `READY == "zombie"` the middle process waits,
#: without reaping, until the daemon is a zombie before it exits, so the
#: daemon is re-parented only once its command line reads empty.
_DOUBLE_FORK = """
import os, sys, time

DAEMON = {daemon!r}
READY = {ready!r}

r, w = os.pipe()
middle = os.fork()
if middle == 0:
    os.setsid()
    daemon = os.fork()
    if daemon == 0:
        os.close(r)
        exec(DAEMON)
        os._exit(0)
    os.write(w, str(daemon).encode())
    while READY == "zombie":
        stat = open(f"/proc/{{daemon}}/stat").read()
        if stat.rsplit(")", 1)[1].split()[0] == "Z":
            break
        time.sleep(0.01)
    os._exit(0)
os.close(w)
daemon = int(os.read(r, 64))
os.waitpid(middle, 0)
open(sys.argv[1], "w").write(str(daemon))
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        stat = open(f"/proc/{{daemon}}/stat").read()
        state = stat.rsplit(")", 1)[1].split()[0]
        cmdline = open(f"/proc/{{daemon}}/cmdline", "rb").read()
    except OSError:
        state, cmdline = "gone", b""
    if READY == "exec" and cmdline.startswith(b"sleep"):
        break
    if READY == "zombie" and state in ("Z", "gone"):
        break
    if READY == "none":
        break
    time.sleep(0.01)
"""


def double_fork(daemon: str, ready: str) -> str:
    return _DOUBLE_FORK.format(daemon=daemon, ready=ready)


class TestReaperDirect(_ReaperCase):
    """T-OC-1: the wrapper, driven directly."""

    def test_a_clean_chunk_passes_its_status_through_without_a_grace_period(self):
        for code, status in (("import sys; sys.exit(0)", 0), ("import sys; sys.exit(1)", 1),
                             ("import sys; sys.exit(3)", 3),
                             ("import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
                              -signal.SIGTERM)):
            with self.subTest(status=status):
                proc, doc, elapsed = self.reap(code)
                self.assertEqual(proc.returncode, status, proc.stderr)
                self.assertEqual(doc["chunk_status"], status)
                self.assertEqual(doc["orphans"], [])
                self.assertEqual((doc["supported"], doc["unsupported_reason"], doc["platform"]),
                                 (True, None, sys.platform))
                self.assertLess(elapsed, 2.5, "a clean chunk must end on ECHILD, not the grace")

    def test_a_chunk_killed_by_sigpipe_or_sigint_kills_the_wrapper_the_same_way(self):
        for signum in (signal.SIGPIPE, signal.SIGINT):
            with self.subTest(signal=signum.name):
                proc, doc, _ = self.reap(f"""
                    import os, signal
                    signal.signal({int(signum)}, signal.SIG_DFL)
                    os.kill(os.getpid(), {int(signum)})
                """)
                self.assertEqual(proc.returncode, -signum, proc.stderr)
                self.assertEqual(doc["chunk_status"], -signum)

    def test_a_double_forked_setsid_sleeper_is_one_killed_orphan(self):
        pid_file = self.tmp / "daemon.pid"
        proc, doc, _ = self._double(pid_file, "exec", 'os.execvp("sleep", ["sleep", "300"])')
        daemon = int(pid_file.read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(doc["orphans"], [{"pid": daemon, "cmdline": "sleep 300",
                                           "fate": "killed"}])
        self.assertTrue(_dead(daemon), "the orphan was left behind, or left as a zombie")

    def _double(self, pid_file: Path, ready: str, daemon: str):
        return self.reap(argv=[sys.executable, "-B", "-c", double_fork(daemon, ready), pid_file])

    def test_an_orphan_whose_cmdline_reads_empty_is_labelled_by_its_comm(self):
        pid_file = self.tmp / "daemon.pid"
        # The daemon outlives the middle process by 0.2 s: re-parented alive,
        # it would be labelled by its command line on the wrapper's first poll.
        proc, doc, elapsed = self._double(pid_file, "zombie",
                                          "import time; time.sleep(0.2); os._exit(0)")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(doc["orphans"], [{"pid": int(pid_file.read_text()), "cmdline": PY_COMM,
                                           "fate": "exited"}])
        self.assertLess(elapsed, 4)

    def test_a_short_lived_daemon_is_one_exited_orphan(self):
        pid_file = self.tmp / "daemon.pid"
        proc, doc, elapsed = self._double(pid_file, "none", "import time; time.sleep(0.5)")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([(o["pid"], o["fate"]) for o in doc["orphans"]],
                         [(int(pid_file.read_text()), "exited")])
        self.assertLess(elapsed, 4.5, "the grace period must end on ECHILD")

    def test_many_short_lived_daemons_are_each_counted(self):
        count = 60
        proc, doc, _ = self.reap(f"""
            import os
            for _ in range({count}):
                middle = os.fork()
                if middle == 0:
                    os.setsid()
                    if os.fork() == 0:
                        os._exit(0)
                    os._exit(0)
                os.waitpid(middle, 0)
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(doc["orphans"]), count, doc["orphans"])
        self.assertEqual(len({o["pid"] for o in doc["orphans"]}), count)
        self.assertTrue(all(o["cmdline"] and o["fate"] == "exited" for o in doc["orphans"]))

    def test_an_orphan_forking_right_up_to_its_kill_leaves_nothing_behind(self):
        pids = self.tmp / "forked.pids"
        spawner = f"""
import os, time
for _ in range(400):
    child = os.fork()
    if child == 0:
        time.sleep(300)
        os._exit(0)
    with open({str(pids)!r}, "a") as handle:
        handle.write(f"{{child}}\\n")
    time.sleep(0.02)
time.sleep(300)
"""
        pid_file = self.tmp / "daemon.pid"
        proc, doc, _ = self._double(pid_file, "none", spawner)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        forked = {int(p) for p in pids.read_text().split()}
        recorded = {o["pid"] for o in doc["orphans"]}
        self.assertGreater(len(forked), 20)
        self.assertIn(int(pid_file.read_text()), recorded)
        self.assertLessEqual(forked, recorded, "a forked child escaped the wrapper")
        self.assertEqual([p for p in recorded if not _dead(p)], [])
        self.assertTrue(all(o["fate"] == "killed" for o in doc["orphans"]))

    def test_the_wrapper_leaves_no_zombie_child_behind(self):
        proc, doc, _ = self.reap("""
            import os
            for _ in range(5):
                if os.fork() == 0:
                    os._exit(0)
            os._exit(0)
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(doc["orphans"]), 5)
        self.assertEqual([o["pid"] for o in doc["orphans"] if _state(o["pid"]) is not None], [])

    def test_the_passed_lock_fd_is_open_in_the_chunk(self):
        lock = os.open(self.tmp / "lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC)
        self.addCleanup(os.close, lock)
        out = self.tmp / "fd.txt"
        proc, doc, _ = self.reap(f"""
            import os
            os.fstat({lock})
            open({str(out)!r}, "w").write("open")
        """, "--pass-fd", str(lock), pass_fds=(lock,))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_text(), "open")

    def test_an_unavailable_check_runs_the_chunk_and_says_why(self):
        for reason in ("no-prctl", "prctl-failed", "no-children-file"):
            with self.subTest(reason=reason):
                proc, doc, _ = self.reap("import sys; sys.exit(3)", "--force-unsupported", reason)
                self.assertEqual(proc.returncode, 3, proc.stderr)
                self.assertEqual(doc, {"schema_version": 1, "chunk_id": doc["chunk_id"],
                                       "platform": sys.platform, "supported": False,
                                       "unsupported_reason": reason, "chunk_status": 3,
                                       "orphans": []})

    def test_its_own_fault_is_exit_125_with_no_report(self):
        proc, doc, _ = self.reap("pass", "--pass-fd", "987")
        self.assertEqual(proc.returncode, 125)
        self.assertIsNone(doc)
        self.assertIn("Traceback", proc.stderr)


# -- T-QG-3: the environment layer wins where it must, under the wrapper ------------------

def _default_config_repo(root: Path, env: dict) -> Path:
    """A repository from `init_git_repo` with the four keys unset, two packs
    and `gc.autoPackLimit=1`, so that its next commit starts Git's detached
    maintenance on any Git; prepared with maintenance forced off."""
    init_git_repo(root)
    for key in THROWAWAY_GIT_CONFIG:
        git(root, "config", "--local", "--unset-all", key, env=env, check=False)
    git(root, "config", "--local", "gc.autoPackLimit", "1", env=env)
    quiet = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")
    for index in range(2):
        (root / f"f{index}").write_text(str(index))
        git(root, *quiet, "add", "-A", env=env)
        git(root, *quiet, "commit", "-q", "-m", f"c{index}", env=env)
        git(root, *quiet, "repack", "-q", env=env)
    return root


def is_git_label(label: str) -> bool:
    """Whether an orphan's recorded label names Git. The wrapper records a
    live orphan's command line, and `[<comm>]` only once the command line is
    empty (plan 5.4 step 2), so which form a detached `git maintenance` gets
    depends on timing: `[git]` locally, `/usr/lib/git-core/git maintenance
    run --auto --quiet --detach` on a faster CI runner. Both are Git."""
    if label == "[git]":
        return True
    program = Path(label.split()[0]).name if label.split() else ""
    return program == "git" or program.startswith("git-")


class TestIsGitLabel(unittest.TestCase):
    """Functional review F1: the control's Git orphan is recognised under
    either label form, whichever one the timing produced."""

    def test_both_label_forms_are_git(self):
        self.assertTrue(is_git_label("[git]"))
        self.assertTrue(is_git_label("/usr/lib/git-core/git maintenance run --auto --quiet --detach"))
        self.assertTrue(is_git_label("git gc --auto"))
        self.assertTrue(is_git_label("/usr/lib/git-core/git-maintenance run"))

    def test_other_processes_are_not_git(self):
        for label in ("[python3]", "sleep 1", "/usr/bin/python3 -c import os", "[gitk-like]", ""):
            with self.subTest(label=label):
                self.assertFalse(is_git_label(label))


_COMMIT = """
import pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
(root / "measured").write_text("m")
subprocess.run(["git", "add", "-A"], cwd=root, check=True)
subprocess.run(["git", *sys.argv[2:], "commit", "-q", "-m", "measured"], cwd=root, check=True)
"""


class TestEnvironmentLayerUnderTheWrapper(_ReaperCase):
    """T-QG-3."""

    @classmethod
    def setUpClass(cls):
        version = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
        print(f"\nT-QG-3 on {version.strip()}", file=sys.stderr)

    def commit_under_wrapper(self, repo: Path, env: dict, *config: str):
        return self.reap(argv=[sys.executable, "-B", "-c", _COMMIT, repo, *config], env=env)

    def test_the_control_orphans_and_the_chunk_environment_does_not(self):
        base = stripped_env()
        control = _default_config_repo(self.tmp / "control", base)
        proc, doc, _ = self.commit_under_wrapper(control, base)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertGreaterEqual(len(doc["orphans"]), 1,
                                "the control saw no orphan, so the test could not see one")
        labels = {o["cmdline"] for o in doc["orphans"]}
        self.assertTrue(any(is_git_label(label) for label in labels), labels)

        treated = _default_config_repo(self.tmp / "treated", base)
        env = isolation.chunk_env(self.tmp / "chunk-tmp", base=base)
        proc, doc, _ = self.commit_under_wrapper(treated, env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(doc["orphans"], [])
        self.assertFalse((treated / ".git" / "gc.pid").exists())
        self.assertFalse((treated / ".git" / "gc.log").exists())
        scope = git(treated, "config", "--show-scope", "--get", "maintenance.auto", env=env)
        self.assertEqual(scope.stdout.split(), ["command", "false"])



class TestFrozenCloneUnderTheWrapper(_FrozenCloneCase, _ReaperCase):
    """T-QG-3, the frozen path: T-QG-5's clone under the wrapper."""

    def commit_under_wrapper(self, repo: Path, env: dict, *config: str):
        return self.reap(argv=[sys.executable, "-B", "-c", _COMMIT, repo, *config], env=env)

    def test_the_frozen_evidence_clone_path(self):
        """The frozen engine's scratch clone, committed to by a `PATH`-only Git:
        no orphan with the template, at least one without it (this path's own
        control, its clone made in T-QG-5's "without" environment)."""
        identity = ("-c", "user.email=t@example.invalid", "-c", "user.name=t")
        path_only = {"PATH": os.environ["PATH"]}
        for arm, expect_orphans in (("with", False), ("without", True)):
            with self.subTest(arm=arm):
                clone = self.materialize(self.template if arm == "with" else None)
                git(clone, "config", "--local", "gc.autoPackLimit", "1", env=path_only)
                quiet = ("-c", "maintenance.auto=false", "-c", "gc.auto=0", *identity)
                for index in range(2):
                    (clone / f"f{index}").write_text(str(index))
                    git(clone, *quiet, "add", "-A", env=path_only)
                    git(clone, *quiet, "commit", "-q", "-m", f"c{index}", env=path_only)
                    git(clone, *quiet, "repack", "-q", env=path_only)
                proc, doc, _ = self.commit_under_wrapper(clone, path_only, *identity)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                if expect_orphans:
                    self.assertGreaterEqual(len(doc["orphans"]), 1)
                else:
                    self.assertEqual(doc["orphans"], [])


# -- T-OC-2: through `run_chunk`, `verdict_of` and the executor's three modes ---------------

#: A scratch host module whose test leaves one daemon behind: a double-forked
#: `setsid` process that outlives its chunk by about a second.
ORPHANING_MODULE = """
import os
import time
import unittest


class TestScratchOrphan(unittest.TestCase):
    def test_leaves_a_daemon(self):
        middle = os.fork()
        if middle == 0:
            os.setsid()
            if os.fork() == 0:
                time.sleep(1)
                os._exit(0)
            os._exit(0)
        os.waitpid(middle, 0)
"""
ORPHAN_UNIT = "host:test_scratch_orphan.py::TestScratchOrphan"
DECLARED_MODULE = ORPHANING_MODULE.replace("TestScratchOrphan", "TestScratchDeclared")
DECLARED_UNIT = "host:test_scratch_declared.py::TestScratchDeclared"


def _scratch_resources(**orphan_sources) -> dict:
    doc = json.loads(json.dumps(tpr.SCRATCH_RESOURCES))
    if orphan_sources:
        doc["orphan_sources"] = {u: {"reason": r} for u, r in orphan_sources.items()}
    return doc


class _ModesCase(tpr._CliCase):
    """A scratch checkout run in local mode, and as one CI shard followed by
    the aggregate, both in this process (`main_in_process`)."""

    def local(self, scratch: Path, *select: str) -> tuple[int, str, str]:
        return tpr.main_in_process(scratch, *(a for s in select for a in ("--select", s)))

    def shard_then_aggregate(self, scratch: Path, *select: str):
        specs = [a for s in select for a in ("--select", s)]
        self._round = getattr(self, "_round", 0) + 1
        plan = self.tmp / f"plan-{self._round}.json"
        results = self.tmp / f"results-{self._round}"
        code, out, err = tpr.main_in_process(scratch, "--plan-only", "--profile", "ci",
                                             "--shards", "1", "--out", plan, *specs)
        self.assertEqual(code, 0, out + err)
        shard = tpr.main_in_process(scratch, "--run-shard", "0", "--plan", plan,
                                    "--results", results / "s0")
        aggregate = tpr.main_in_process(scratch, "--aggregate", results, "--plan", plan)
        return shard, aggregate


class TestOrphansThroughTheExecutor(_ModesCase):
    """T-OC-2."""

    def test_an_undeclared_orphan_fails_every_mode(self):
        scratch = tpr.scratch_checkout(self.tmp / "scratch",
                                       modules={"test_scratch_orphan.py": ORPHANING_MODULE})
        runs = {"local": self.local(scratch, "test_scratch_orphan.py")}
        runs["shard"], runs["aggregate"] = self.shard_then_aggregate(scratch,
                                                                     "test_scratch_orphan.py")
        for mode, (code, out, err) in runs.items():
            with self.subTest(mode=mode):
                tpr.assert_refusal(self, code, err, "OrphanProcessError")
                self.assertIn(f"{ORPHAN_UNIT}: 1 orphaned process(es): 1 x ", err)
                self.assertIn("orphan check: on", out)

    def test_a_declared_orphan_is_tolerated_and_listed(self):
        scratch = tpr.scratch_checkout(
            self.tmp / "scratch",
            modules={"test_scratch_orphan.py": ORPHANING_MODULE,
                     "test_scratch_declared.py": DECLARED_MODULE},
            resources=_scratch_resources(**{DECLARED_UNIT: "leaves a daemon on purpose",
                                            tpr.SCRATCH_SHARED_UNIT: "declared, never used"}))
        code, out, err = self.local(scratch, "test_scratch_declared.py", "test_scratch_shared.py")
        self.assertEqual(code, 0, out + err)
        self.assertIn("tolerated orphans (declared in resources.json's orphan_sources): "
                      "1 chunk(s)", out)
        self.assertIn(f"    {DECLARED_UNIT}: 1 x ", out)
        self.assertIn(f"orphan_sources unused in this run: {tpr.SCRATCH_SHARED_UNIT}", out)
        # ... and an undeclared one in the same run is not.
        code, out, err = self.local(scratch, "test_scratch_declared.py", "test_scratch_orphan.py")
        tpr.assert_refusal(self, code, err, "OrphanProcessError")
        self.assertIn(ORPHAN_UNIT, err)
        self.assertNotIn(f"{DECLARED_UNIT}: 1 orphaned", out + err)

    def test_a_linux_chunk_without_the_check_fails_every_mode(self):
        scratch = tpr.scratch_checkout(self.tmp / "scratch")
        with mock.patch.object(isolation, "REAPER_TEST_ARGS", ("--force-unsupported", "no-prctl")):
            runs = {"local": self.local(scratch, "test_scratch_shared.py")}
            runs["shard"], runs["aggregate"] = self.shard_then_aggregate(
                scratch, "test_scratch_shared.py")
        for mode, (code, out, err) in runs.items():
            with self.subTest(mode=mode):
                tpr.assert_refusal(self, code, err, "OrphanCheckUnavailableError")
                self.assertIn(f"{tpr.SCRATCH_SHARED_UNIT}: orphan check unavailable on "
                              f"{sys.platform}: no-prctl", err)
                self.assertNotIn("orphan check: on", out)

    def test_a_non_linux_chunk_without_the_check_is_a_notice(self):
        scratch = tpr.scratch_checkout(self.tmp / "scratch")
        with mock.patch.object(isolation, "REAPER_TEST_ARGS",
                               ("--force-unsupported", "no-prctl", "--platform", "darwin")):
            code, out, err = self.local(scratch, "test_scratch_shared.py")
        self.assertEqual(code, 0, out + err)
        self.assertIn("orphan check: unavailable on this platform", out)


#: A fake wrapper for `bad_orphan_report`: it runs the chunk, then does what
#: its `--mode` says to the report.
_FAKE_REAPER = """
import argparse, json, os, subprocess, sys
parser = argparse.ArgumentParser()
parser.add_argument("--report")
parser.add_argument("--chunk-id")
parser.add_argument("--pass-fd", action="append", default=[])
parser.add_argument("--mode")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
status = subprocess.run(command).returncode
doc = {"schema_version": 1, "chunk_id": args.chunk_id, "platform": sys.platform,
       "supported": True, "unsupported_reason": None, "chunk_status": status, "orphans": []}
if args.mode == "malformed":
    open(args.report, "w").write("{")
elif args.mode == "foreign":
    open(args.report, "w").write(json.dumps({**doc, "chunk_id": "another"}))
elif args.mode == "exit125":
    open(args.report, "w").write(json.dumps(doc))
    sys.exit(125)
sys.exit(status)
"""


class TestBadOrphanReports(_ReaperCase):
    """T-OC-2: a report that is missing, stale, malformed or another chunk's,
    and a wrapper exit 125, are each `bad_orphan_report`."""

    def run_mode(self, mode: str | None, chunk_id: str, *, stale: bool = False):
        run_dir = self.tmp / "run"
        record = isolation.chunk_paths(run_dir, chunk_id).record
        report = isolation.chunk_paths(run_dir, chunk_id).orphans
        if stale:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({
                "schema_version": 1, "chunk_id": chunk_id, "platform": sys.platform,
                "supported": True, "unsupported_reason": None, "chunk_status": 0,
                "orphans": []}))
        fake = self.tmp / "fake_reaper.py"
        fake.write_text(_FAKE_REAPER)
        args = ("--mode", mode) if mode else ()
        code = f"import json; open({str(record)!r}, 'w').write(json.dumps({{'passed': True}}))"
        with mock.patch.object(isolation, "REAPER", fake), \
                mock.patch.object(isolation, "REAPER_TEST_ARGS", args):
            return isolation.run_chunk(self.tmp, chunk_id, [sys.executable, "-c", code],
                                       run_dir=run_dir, timeout=60), report

    def test_each_bad_report_is_an_infrastructure_fault_naming_the_chunk_and_path(self):
        for mode, stale in ((None, False), (None, True), ("malformed", False),
                            ("foreign", False), ("exit125", False)):
            chunk_id = f"host:test_x.py::{mode or 'missing'}{'-stale' if stale else ''}"
            with self.subTest(mode=mode, stale=stale):
                run, report = self.run_mode(mode, chunk_id, stale=stale)
                self.assertEqual(run.outcome, isolation.BAD_ORPHAN_REPORT, run.detail)
                self.assertIn(str(report), run.infrastructure_fault)
                chunk = plan_schema.ChunkDescriptor(chunk_id, 0, (chunk_id,), 1.0)
                result = executor.ChunkResult(chunk, "A", 0, "host", run.outcome,
                                              detail=run.detail)
                verdict = executor.verdict_of([result], lambda r: False)
                self.assertEqual(verdict.code, 2)
                self.assertEqual([n for n, _ in verdict.faults], ["InfrastructureFaultError"])
                self.assertIn(chunk_id, verdict.faults[0][1])
                self.assertIn(str(report), verdict.faults[0][1])

    def test_the_real_wrappers_own_fault_is_a_bad_report(self):
        run_dir = self.tmp / "run"
        record = isolation.chunk_paths(run_dir, "c").record
        code = f"import json; open({str(record)!r}, 'w').write(json.dumps({{'passed': True}}))"
        with mock.patch.object(isolation, "REAPER_TEST_ARGS", ("--pass-fd", "987")):
            run = isolation.run_chunk(self.tmp, "c", [sys.executable, "-c", code],
                                      run_dir=run_dir, timeout=60)
        self.assertEqual((run.outcome, run.returncode), (isolation.BAD_ORPHAN_REPORT, 125))


class TestVerdictOfOrphans(unittest.TestCase):
    """T-OC-2, `verdict_of` alone."""

    ORPHAN = ({"pid": 1, "cmdline": "[git]", "fate": "exited"},)

    def result(self, *units, orphans=(), supported=True, platform="linux"):
        chunk = plan_schema.ChunkDescriptor("c", 0, tuple(units), 1.0)
        return executor.ChunkResult(chunk, "A", 0, "host", "passed", orphans=orphans,
                                    platform=platform, supported=supported)

    def test_a_declared_frozen_unit_sharing_a_chunk_is_an_orphan_declaration_error(self):
        frozen = ("frozen:1.0.0/conformance/s.py::A", "frozen:1.0.0/conformance/s.py::B")
        declared = {frozen[0]: resources.OrphanSource(frozen[0], "r")}
        verdict = executor.verdict_of([self.result(*frozen)], lambda r: False,
                                      orphan_sources=declared)
        self.assertEqual([n for n, _ in verdict.faults], ["OrphanDeclarationError"])
        alone = executor.verdict_of([self.result(frozen[0], orphans=self.ORPHAN)],
                                    lambda r: False, orphan_sources=declared)
        self.assertEqual((alone.code, alone.faults), (0, []))

    def test_undeclared_orphans_are_counted_most_frequent_first(self):
        orphans = tuple({"pid": i, "cmdline": label, "fate": "exited"}
                        for i, label in enumerate(["[git]", "sleep 1", "[git]"]))
        verdict = executor.verdict_of([self.result("host:test_a.py::A", orphans=orphans)],
                                      lambda r: False)
        self.assertEqual(verdict.faults, [("OrphanProcessError",
                                           "c: 3 orphaned process(es): 2 x [git], 1 x sleep 1")])


# -- T-OC-3: the `orphan_sources` schema, and chunking -----------------------------------------

HOST = "host:test_a.py::A"
FROZEN_A = "frozen:1.0.0/conformance/s.py::TestA"
FROZEN_B = "frozen:1.0.0/conformance/s.py::TestB"
FROZEN_C = "frozen:1.0.0/conformance/s.py::TestC"


def _doc(orphan_sources=None, **extra) -> dict:
    doc = {"schema_version": 1, "resources": {}, "exclusive": {}, **extra}
    if orphan_sources is not None:
        doc["orphan_sources"] = orphan_sources
    return doc


class TestOrphanSourcesSchema(unittest.TestCase):
    """T-OC-3."""

    def test_the_declaration_is_validated(self):
        every = [HOST, FROZEN_A]
        ok = resources.parse(_doc({FROZEN_A: {"reason": "r"}, HOST: {"reason": "s"}}), [HOST],
                             orphan_unit_ids=every)
        self.assertEqual(sorted(ok.orphan_sources), [FROZEN_A, HOST])
        self.assertEqual(resources.parse(_doc(), [HOST]).orphan_sources, {})
        refused = {
            "an unknown unit": _doc({"host:test_z.py::Z": {"reason": "r"}}),
            "an empty reason": _doc({HOST: {"reason": " "}}),
            "another key": _doc({HOST: {"reason": "r", "count": 3}}),
            "an unknown top-level key": _doc(extra_key={}),
            "a frozen exclusive unit": _doc(
                resources={"r": {"paths": ["src/"], "description": "d"}},
                exclusive={FROZEN_A: {"resources": ["r"], "reason": "r"}}),
        }
        for what, doc in refused.items():
            with self.subTest(what=what), self.assertRaises(resources.ResourcesFileError):
                resources.parse(doc, [HOST], orphan_unit_ids=every)
        with self.assertRaises(resources.ResourcesFileError):
            resources.parse(_doc({FROZEN_A: {"reason": "r"}}), [HOST])  # no orphan_unit_ids

    def chunks(self, res, whole_groups=False):
        units = [FROZEN_A, FROZEN_B, FROZEN_C, HOST]
        return [(c.id, c.units) for c in planner.make_chunks(
            units, {u: 100.0 for u in units}, profile="local", config=dict(tpr.PLAN_CONFIG),
            timings=tpr._timings(local={}), resources=res, whole_groups=whole_groups)]

    def test_a_declared_frozen_class_gets_a_chunk_of_its_own(self):
        none = resources.parse(_doc(), [HOST])
        declared = resources.parse(_doc({FROZEN_B: {"reason": "r"}}), [HOST],
                                   orphan_unit_ids=[HOST, FROZEN_A, FROZEN_B, FROZEN_C])
        without_b = [HOST, FROZEN_A, FROZEN_C]
        for whole_groups in (False, True):
            with self.subTest(whole_groups=whole_groups):
                got = self.chunks(declared, whole_groups)
                self.assertIn(("frozen:1.0.0/conformance/s.py#TestB", (FROZEN_B,)), got)
                rest = [c for c in got if FROZEN_B not in c[1]]
                expected = [(c.id, c.units) for c in planner.make_chunks(
                    without_b, {u: 100.0 for u in without_b}, profile="local",
                    config=dict(tpr.PLAN_CONFIG), timings=tpr._timings(local={}),
                    resources=none, whole_groups=whole_groups)]
                self.assertEqual(rest, expected)

    def test_without_a_frozen_declaration_the_chunks_are_unchanged(self):
        host_only = resources.parse(_doc({HOST: {"reason": "r"}}), [HOST])
        self.assertEqual(self.chunks(host_only), self.chunks(resources.parse(_doc(), [HOST])))
        self.assertEqual(self.chunks(host_only, True),
                         self.chunks(resources.parse(_doc(), [HOST]), True))


class TestFrozenDeclarationThroughTheModes(_ModesCase):
    """T-OC-3: a frozen `orphan_sources` key loads through
    `planner.plan_checkout` and the executor's three `resources.load` calls."""

    def test_a_frozen_declaration_loads_in_every_mode(self):
        unit = f"{tpr.SCRATCH_FROZEN_SUITE}::TestBeta"
        scratch = tpr.scratch_checkout(self.tmp / "scratch",
                                       resources=_scratch_resources(**{unit: "r"}))
        inv = inventory.discover(scratch)
        self.assertIn(unit, inv.unit_ids())
        plan = planner.plan_checkout(scratch, inv, inventory.select(inv.host, [unit], inv.frozen),
                                     profile="local")
        self.assertIn([unit], [c["units"] for s in plan["shards"] for c in s["chunks"]])
        code, out, err = self.local(scratch, unit)
        self.assertEqual(code, 0, out + err)
        (s_code, s_out, s_err), (a_code, a_out, a_err) = self.shard_then_aggregate(scratch, unit)
        self.assertEqual((s_code, a_code), (0, 0), s_out + s_err + a_out + a_err)


# -- T-OC-4: the timeout and interrupt paths ---------------------------------------------------

class TestKilledChunks(_ModesCase):
    """T-OC-4: the wrapper and the chunk die together, and the run fails for
    the existing reason only -- on timeout, and on an interrupt through the
    executor (exit 2 for being interrupted, never for an orphan or a bad
    report). Killing a wrapper hands the chunk it had not yet reaped to the
    next subreaper up (plan 5.6), so this class is a declared orphan source."""

    def test_a_timeout_kills_the_wrapper_and_the_chunk_together(self):
        pid_file = self.tmp / "chunk.pid"
        code = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); " \
               "time.sleep(120)"
        run = isolation.run_chunk(self.tmp, "c", [sys.executable, "-c", code],
                                  run_dir=self.tmp / "run", timeout=1.5)
        self.assertEqual(run.outcome, isolation.TIMED_OUT)
        self.assertTrue(tpr._wait_until(lambda: tpr._dead(int(pid_file.read_text()))))
        self.assertTrue(tpr._dead(run.pgid))
        self.assertEqual((run.orphans, run.supported), ((), None))
        chunk = plan_schema.ChunkDescriptor("c", 0, (HOST,), 1.0)
        result = executor.ChunkResult(chunk, "A", 0, "host", run.outcome, detail=run.detail)
        verdict = executor.verdict_of([result], lambda r: False)
        self.assertEqual([n for n, _ in verdict.faults], ["InfrastructureFaultError"])
        self.assertIn("timed_out", verdict.faults[0][1])

    def test_an_interrupt_is_not_an_orphan_or_a_bad_report(self):
        scratch = tpr.scratch_checkout(self.tmp / "scratch",
                                       modules={"test_scratch_wait.py": tpr.WAIT_MODULE})
        stop = self.tmp / "stop"
        self.addCleanup(stop.write_text, "")

        def interrupt_once_the_chunk_runs():
            # The run's SIGTERM handler is installed before any chunk starts.
            if tpr._wait_until(lambda: tpr._lock_holder(scratch).get("chunk_pgids"), 60):
                os.kill(os.getpid(), signal.SIGTERM)

        interrupter = threading.Thread(target=interrupt_once_the_chunk_runs)
        with mock.patch.dict(os.environ, {"WM_SCRATCH_STOP": str(stop)}):
            interrupter.start()
            code, out, err = self.local(scratch, "test_scratch_wait.py")
        interrupter.join()
        tpr.assert_refusal(self, code, err, "InterruptedRunError")
        self.assertNotIn("OrphanProcessError", out + err)
        self.assertNotIn(isolation.BAD_ORPHAN_REPORT, out + err)


if __name__ == "__main__":
    unittest.main()
