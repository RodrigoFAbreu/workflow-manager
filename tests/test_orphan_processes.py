#!/usr/bin/env python3
"""No orphaned Git processes: the tests of `workflow-manager-test-cleanup`.

Checkpoint CP1 (`D-Quiet-Git`, plan 5.1-5.3, 5.5): the chunk environment's
layer (T-QG-1), the per-repository layer and the run's Git template
(T-QG-2), the frozen isolated-test path the template covers (T-QG-5), and
the static routing check that keeps every `git init`/`git clone` site of
this repository on the shared setup (T-QG-4).
"""

from __future__ import annotations

import ast
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401 -- puts src/ on sys.path, bytecode off
from support import REPO_ROOT

from parallel import cli, isolation
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


class TestFrozenEvidenceClone(_Tmp):
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


if __name__ == "__main__":
    unittest.main()
