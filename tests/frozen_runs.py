#!/usr/bin/env python3
"""Frozen-suite runs as independently executable chunks, and their fail-closed
merge into the unchanged matrix host assertions (plan section 5.5,
`D-Frozen-Matrix-Decomposition`). Stdlib only.

A *chunk* is some classes of one frozen suite, for one release, in one
fixture kind. `execute` builds a fresh disposable repository with the
fixture's existing builder, runs `python3 <suite>.py <Class> ...` through
`support.run_suite` -- the frozen file still runs as `__main__`, through its
own bare `unittest.main()` -- and returns a `FrozenRecord`.

The 15 matrix host classes get their per-suite view from `open_matrix_run`:

- **direct mode** (`WM_FROZEN_RECORDS` unset -- every unchanged entry
  point): one repository, every suite run whole in `CI_SUITES` order, each
  result wrapped by `MergedResult.from_single`. Today's behaviour.
- **merged mode** (`WM_FROZEN_RECORDS` and `WM_FROZEN_CONTEXT` set by
  whoever owns the plan): the chunk records are merged against a
  `MergeContext` read from `WM_FROZEN_CONTEXT`, never derived from the
  records themselves.

`merge` refuses a structurally incomplete, duplicated or foreign record set
(`FrozenMergeError`) and never judges outcomes: a chunk that lost tests,
errored in `setUpClass` or crashed at import flows into the merged view and
fails the unchanged host assertion, as it would today.

    python3 tests/frozen_runs.py --evidence {merged,one-class,residue,compare} \
        --out DIR [--version V ...]

runs CP2's evidence (plan section 6.2, E-MRG-1..3) serially; `--version`
restricts it to some releases so several invocations can share the work.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import os
import re
import subprocess
import tempfile
import time
import traceback
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from support import CI_SUITES, REPO_ROOT, failing_tests, run_suite

from parallel import canonical_json, strict_json_loads
from parallel.tree import describe, tree_digest

from workflow_manager.fixture import build_conformance_repo, build_target_repo
from workflow_manager.install import bootstrap, drift
from workflow_manager.release import find_release

RECORDS_ENV = "WM_FROZEN_RECORDS"
CONTEXT_ENV = "WM_FROZEN_CONTEXT"
RECORD_SCHEMA_VERSION = 1
CONTEXT_SCHEMA_VERSION = 1

#: The same summary regex the host assertions used on a `CompletedProcess`.
RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
#: The host assertions quote at most the last 4000 characters of a suite's
#: output; a record keeps far more than that.
OUTPUT_LIMIT = 200_000
FIXED_NOW = "2026-01-01T00:00:00Z"


class FrozenMergeError(Exception):
    """A record set is structurally incomplete, duplicated or foreign to its
    merge context -- an infrastructure fault, never a test outcome."""


# -- fixtures ------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout


def empty_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "e2e@example.invalid")
    _git(root, "config", "user.name", "E2E")
    _git(root, "config", "commit.gpgsign", "false")
    return root


def build_bootstrapped_repo(release, dest: Path) -> Path:
    """What `install.bootstrap` makes of an empty repository, committed --
    the repository a real consumer would have."""
    target = empty_repo(dest)
    bootstrap(target, release, now=FIXED_NOW)
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "bootstrap workflow")
    return target


#: fixture kind -> (builder, name of the repository directory it builds)
FIXTURE_BUILDERS = {
    "conformance": (build_conformance_repo, "repo"),
    "target": (build_target_repo, "repo"),
    "bootstrapped": (build_bootstrapped_repo, "consumer"),
}


def release_digest(repo_root: Path, version: str) -> str:
    """sha256 of the release's own `manifest.json`."""
    manifest = Path(repo_root) / "distribution" / "workflow" / version / "manifest.json"
    try:
        return hashlib.sha256(manifest.read_bytes()).hexdigest()
    except OSError as exc:
        raise FrozenMergeError(f"release {version}: cannot read {manifest}: {exc}") from exc


# -- chunks and records --------------------------------------------------------

@dataclass(frozen=True)
class FrozenChunk:
    id: str
    version: str
    fixture: str
    suite: str
    #: Sorted class names; empty means the whole suite, invoked with no class
    #: arguments exactly as today (direct mode only).
    classes: tuple[str, ...] = ()
    #: `Class.test` ids the chunk is expected to run (attribution only).
    enumerated: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrozenRecord:
    chunk_id: str
    version: str
    fixture: str
    suite: str
    classes: tuple[str, ...]
    returncode: int
    ran: int | None
    failing: tuple[str, ...]
    output: str
    tree_digest: str | None = None
    plan_digest: str | None = None
    release_digest: str | None = None
    enumerated: tuple[str, ...] = ()
    residue: tuple[str, ...] | None = None
    drift: tuple[str, ...] | None = None
    build_error: str | None = None
    timed_out: bool = False
    duration: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0

    def to_json(self) -> str:
        return canonical_json({
            "schema_version": RECORD_SCHEMA_VERSION,
            "chunk_id": self.chunk_id, "version": self.version, "fixture": self.fixture,
            "suite": self.suite, "classes": list(self.classes),
            "returncode": self.returncode, "ran": self.ran, "failing": list(self.failing),
            "output": self.output, "tree_digest": self.tree_digest,
            "plan_digest": self.plan_digest, "release_digest": self.release_digest,
            "enumerated": list(self.enumerated),
            "residue": None if self.residue is None else list(self.residue),
            "drift": None if self.drift is None else list(self.drift),
            "build_error": self.build_error, "timed_out": self.timed_out,
            "duration": self.duration, "started_at": self.started_at,
            "ended_at": self.ended_at,
        })

    @classmethod
    def from_json(cls, text: str) -> "FrozenRecord":
        try:
            obj = strict_json_loads(text)
            if obj.pop("schema_version") != RECORD_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for key in ("classes", "failing", "enumerated"):
                obj[key] = tuple(obj[key])
            for key in ("residue", "drift"):
                obj[key] = None if obj[key] is None else tuple(obj[key])
            return cls(**obj)
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenMergeError(f"malformed frozen record: {exc}") from exc


def record_from_process(chunk: FrozenChunk, proc: subprocess.CompletedProcess, **fields
                        ) -> FrozenRecord:
    """The record of one suite invocation. `ran` and `failing` are computed
    from the full output by the same `RAN_RE`/`failing_tests` the host
    assertions applied to a `CompletedProcess`."""
    output = proc.stdout + proc.stderr
    match = RAN_RE.search(output)
    return FrozenRecord(
        chunk_id=chunk.id, version=chunk.version, fixture=chunk.fixture, suite=chunk.suite,
        classes=chunk.classes, enumerated=chunk.enumerated, returncode=proc.returncode,
        ran=None if match is None else int(match.group(1)),
        failing=tuple(sorted(failing_tests(output))), output=output[-OUTPUT_LIMIT:], **fields)


def _post_run_state(fixture: str, repo: Path, release) -> dict:
    """The `bootstrapped` host class's post-run checks: `git status
    --porcelain` residue and `install.drift`. Not measured for the other
    fixtures, whose host classes assert neither."""
    if fixture != "bootstrapped":
        return {}
    return {"residue": tuple(_git(repo, "status", "--porcelain").splitlines()),
            "drift": tuple(str(d) for d in drift(repo, release))}


def execute(chunk: FrozenChunk, *, tree_digest: str | None, plan_digest: str | None,
            repo_root: Path = REPO_ROOT, timeout: int = 1800) -> FrozenRecord:
    """Run one chunk in a freshly built repository and return its record.
    Provenance is stamped from the arguments (tree and plan digest) and from
    the release's own manifest. A builder that raises still yields a record
    -- `returncode` 1, `ran` None, the traceback as output -- so it fails the
    unchanged assertions as a test failure, not as a missing record."""
    provenance = {"tree_digest": tree_digest, "plan_digest": plan_digest,
                  "release_digest": release_digest(repo_root, chunk.version)}
    builder, name = FIXTURE_BUILDERS[chunk.fixture]
    started_at, started = time.time(), time.monotonic()

    def timing() -> dict:
        return {"duration": round(time.monotonic() - started, 3),
                "started_at": started_at, "ended_at": time.time()}

    with tempfile.TemporaryDirectory(prefix="wm-frozen-") as tmp:
        try:
            release = find_release(repo_root, chunk.version)
            repo = builder(release, Path(tmp) / name)
        except Exception:  # noqa: BLE001 -- any builder failure is the chunk's outcome
            error = traceback.format_exc()
            return FrozenRecord(
                chunk_id=chunk.id, version=chunk.version, fixture=chunk.fixture,
                suite=chunk.suite, classes=chunk.classes, enumerated=chunk.enumerated,
                returncode=1, ran=None, failing=(), output=error, build_error=error,
                **provenance, **timing())
        try:
            proc = run_suite(repo, chunk.suite, timeout=timeout, classes=chunk.classes)
        except subprocess.TimeoutExpired as exc:
            partial = "".join(p.decode(errors="replace") if isinstance(p, bytes) else (p or "")
                              for p in (exc.stdout, exc.stderr))
            return FrozenRecord(
                chunk_id=chunk.id, version=chunk.version, fixture=chunk.fixture,
                suite=chunk.suite, classes=chunk.classes, enumerated=chunk.enumerated,
                returncode=-9, ran=None, failing=(), timed_out=True,
                output=(partial + f"\n[timed out after {timeout}s]")[-OUTPUT_LIMIT:],
                **provenance, **timing())
        return record_from_process(chunk, proc, **provenance,
                                   **_post_run_state(chunk.fixture, repo, release), **timing())


def write_record(record: FrozenRecord, records_dir: Path) -> Path:
    """Atomically, under a name derived from the chunk id (which may contain
    `/` and `:`)."""
    records_dir = Path(records_dir)
    records_dir.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(record.chunk_id.encode()).hexdigest()[:24] + ".record.json"
    path = records_dir / name
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(record.to_json(), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_records(records_dir: Path, version: str, fixture: str) -> list[FrozenRecord]:
    """Every record in `records_dir` for `(version, fixture)`. A record that
    does not parse is refused rather than skipped."""
    records_dir = Path(records_dir)
    if not records_dir.is_dir():
        raise FrozenMergeError(f"{RECORDS_ENV}={records_dir} is not a directory")
    records = []
    for path in sorted(records_dir.glob("*.record.json")):
        record = FrozenRecord.from_json(path.read_text(encoding="utf-8"))
        if (record.version, record.fixture) == (version, fixture):
            records.append(record)
    return records


# -- merge context -------------------------------------------------------------

@dataclass(frozen=True)
class SuitePlan:
    #: chunk id -> the sorted class names planned for it
    chunks: dict[str, tuple[str, ...]]
    #: every class discovery found in the suite, sorted
    classes: tuple[str, ...]


@dataclass(frozen=True)
class MergeContext:
    """For one `(version, fixture)`: every value `merge` checks a record
    against. Built by whoever owns the plan, never read out of the records."""

    version: str
    fixture: str
    tree_digest: str
    plan_digest: str
    suites: dict[str, SuitePlan] = field(default_factory=dict)

    @classmethod
    def from_chunks(cls, version: str, fixture: str, chunks, discovered: dict,
                    *, tree_digest: str, plan_digest: str) -> "MergeContext":
        """`chunks`: the planned `FrozenChunk`s of this `(version, fixture)`;
        `discovered`: `{suite: class names}` from the frozen inventory."""
        suites = {suite: SuitePlan({}, tuple(sorted(names))) for suite, names in discovered.items()}
        for chunk in chunks:
            if (chunk.version, chunk.fixture) != (version, fixture):
                raise FrozenMergeError(f"chunk {chunk.id} is not {version}/{fixture}")
            if chunk.suite not in suites:
                raise FrozenMergeError(f"chunk {chunk.id}: suite {chunk.suite} was not discovered")
            suites[chunk.suite].chunks[chunk.id] = tuple(sorted(chunk.classes))
        context = cls(version, fixture, tree_digest, plan_digest, suites)
        context.validate()
        return context

    def validate(self) -> None:
        """The planned chunks of each suite are non-empty, pairwise disjoint,
        and together exactly the discovered classes."""
        for suite, plan in self.suites.items():
            if not plan.chunks:
                raise FrozenMergeError(f"{self.label}/{suite}: no chunk is planned")
            owner: dict[str, str] = {}
            for chunk_id, classes in plan.chunks.items():
                if not classes:
                    raise FrozenMergeError(f"{self.label}/{suite}: chunk {chunk_id} has no class")
                for name in classes:
                    if name in owner:
                        raise FrozenMergeError(
                            f"{self.label}/{suite}: class {name} is planned in both "
                            f"{owner[name]} and {chunk_id}")
                    owner[name] = chunk_id
            unplanned = sorted(set(plan.classes) - set(owner))
            foreign = sorted(set(owner) - set(plan.classes))
            if unplanned:
                raise FrozenMergeError(f"{self.label}/{suite}: classes in no chunk: {unplanned}")
            if foreign:
                raise FrozenMergeError(f"{self.label}/{suite}: planned classes the suite "
                                       f"does not have: {foreign}")

    @property
    def label(self) -> str:
        return f"{self.version}/{self.fixture}"

    def to_json(self) -> str:
        return canonical_json({
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": self.version, "fixture": self.fixture,
            "tree_digest": self.tree_digest, "plan_digest": self.plan_digest,
            "suites": {suite: {"chunks": {cid: list(c) for cid, c in plan.chunks.items()},
                               "classes": list(plan.classes)}
                       for suite, plan in self.suites.items()},
        })

    @classmethod
    def from_json(cls, text: str) -> "MergeContext":
        try:
            obj = strict_json_loads(text)
            if obj["schema_version"] != CONTEXT_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            suites = {suite: SuitePlan({cid: tuple(c) for cid, c in plan["chunks"].items()},
                                       tuple(plan["classes"]))
                      for suite, plan in obj["suites"].items()}
            context = cls(obj["version"], obj["fixture"], obj["tree_digest"],
                          obj["plan_digest"], suites)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise FrozenMergeError(f"malformed merge context: {exc}") from exc
        context.validate()
        return context


def context_path(context_dir: Path, version: str, fixture: str) -> Path:
    return Path(context_dir) / f"{version}_{fixture}.context.json"


def write_context(context: MergeContext, context_dir: Path) -> Path:
    path = context_path(context_dir, context.version, context.fixture)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(context.to_json(), encoding="utf-8")
    os.replace(tmp, path)
    return path


# -- merge ---------------------------------------------------------------------

def _unique(items) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


@dataclass(frozen=True)
class MergedResult:
    """One suite's view for the host assertions, whether it came from one
    whole-suite run (direct mode) or from several chunks (merged mode)."""

    suite: str
    returncode: int
    ran: int | None
    failing: frozenset[str]
    output: str
    residue: tuple[str, ...] = ()
    drift: tuple[str, ...] = ()
    records: tuple[FrozenRecord, ...] = ()

    @classmethod
    def combine(cls, records) -> "MergedResult":
        records = tuple(sorted(records, key=lambda r: r.chunk_id))
        if not records or len({r.suite for r in records}) != 1:
            raise FrozenMergeError("a merged result needs records of exactly one suite")
        ran = None if any(r.ran is None for r in records) else sum(r.ran for r in records)
        if len(records) == 1:
            output = records[0].output
        else:
            output = "".join(
                f"\n===== chunk {r.chunk_id} ({', '.join(r.classes)}) =====\n{r.output}"
                for r in records)
        return cls(
            suite=records[0].suite,
            returncode=max(r.returncode for r in records),
            ran=ran,
            failing=frozenset().union(*(r.failing for r in records)),
            output=output,
            residue=_unique(line for r in records for line in (r.residue or ())),
            drift=_unique(d for r in records for d in (r.drift or ())),
            records=records,
        )

    @classmethod
    def from_single(cls, record: FrozenRecord) -> "MergedResult":
        return cls.combine([record])

    def attribution(self) -> dict[str, int]:
        """`{chunk id: enumerated tests the chunk did not run}` for every
        chunk that ran fewer than it was expected to -- report text, never a
        refusal."""
        lost = {}
        for record in self.records:
            if record.enumerated and (record.ran or 0) < len(record.enumerated):
                lost[record.chunk_id] = len(record.enumerated) - (record.ran or 0)
        return lost


def merge(records, context: MergeContext, repo_root: Path = REPO_ROOT
          ) -> dict[str, MergedResult]:
    """`{suite: MergedResult}` for the context's `(version, fixture)`.
    Structural checks only; every expected value comes from `context` (and
    the release digest from the release's own manifest), never from the
    records being checked."""
    context.validate()
    expected_release = release_digest(repo_root, context.version)
    by_suite: dict[str, list[FrozenRecord]] = {}
    seen: set[str] = set()
    for record in records:
        where = f"{context.label}: record for chunk {record.chunk_id}"
        if (record.version, record.fixture) != (context.version, context.fixture):
            raise FrozenMergeError(f"{where} belongs to {record.version}/{record.fixture}")
        if record.chunk_id in seen:
            raise FrozenMergeError(f"{where} appears more than once")
        seen.add(record.chunk_id)
        plan = context.suites.get(record.suite)
        if plan is None:
            raise FrozenMergeError(f"{where}: suite {record.suite} is not in the context")
        if record.chunk_id not in plan.chunks:
            raise FrozenMergeError(f"{where} is not a planned chunk of {record.suite}")
        if tuple(record.classes) != plan.chunks[record.chunk_id]:
            raise FrozenMergeError(
                f"{where} ran classes {list(record.classes)}, planned "
                f"{list(plan.chunks[record.chunk_id])}")
        for name, expected in (("tree_digest", context.tree_digest),
                               ("plan_digest", context.plan_digest),
                               ("release_digest", expected_release)):
            if getattr(record, name) != expected:
                raise FrozenMergeError(
                    f"{where} carries {name} {getattr(record, name)!r}, expected {expected!r}")
        if record.timed_out:
            raise FrozenMergeError(f"{where}: the chunk was killed on timeout")
        by_suite.setdefault(record.suite, []).append(record)
    for suite, plan in context.suites.items():
        missing = sorted(set(plan.chunks) - {r.chunk_id for r in by_suite.get(suite, ())})
        if missing:
            raise FrozenMergeError(f"{context.label}/{suite}: no record for planned "
                                   f"chunks {missing}")
    return {suite: MergedResult.combine(by_suite[suite]) for suite in context.suites}


# -- the matrix host classes' entry point --------------------------------------

@dataclass
class MatrixRun:
    """What one matrix host class's `setUpClass` works with: its own
    repository (for the assertions that read one) and the per-suite view."""

    version: str
    fixture: str
    mode: str  # "direct" or "merged"
    root: Path
    release: object
    results: dict[str, MergedResult]
    _tmp: tempfile.TemporaryDirectory | None = None

    @property
    def residue(self) -> list[str]:
        return list(_unique(line for r in self.results.values() for line in r.residue))

    @property
    def drift(self) -> list[str]:
        return list(_unique(d for r in self.results.values() for d in r.drift))

    def cleanup(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None


def load_merge_inputs(version: str, fixture: str, *, repo_root: Path = REPO_ROOT,
                      environ=None) -> dict[str, MergedResult] | None:
    """Merged mode's results, or None in direct mode. Refuses
    (`FrozenMergeError`) a records directory without a context directory, a
    `(version, fixture)` with no context file, and a context from another
    tree."""
    environ = os.environ if environ is None else environ
    records_dir = environ.get(RECORDS_ENV)
    if not records_dir:
        return None
    context_dir = environ.get(CONTEXT_ENV)
    if not context_dir:
        raise FrozenMergeError(f"{RECORDS_ENV} is set but {CONTEXT_ENV} is not; merged mode "
                               f"never derives a context from the records")
    path = context_path(context_dir, version, fixture)
    if not path.is_file():
        raise FrozenMergeError(f"no merge context for {version}/{fixture} at {path}")
    context = MergeContext.from_json(path.read_text(encoding="utf-8"))
    if (context.version, context.fixture) != (version, fixture):
        raise FrozenMergeError(f"{path} holds the context of {context.label}")
    actual = tree_digest(repo_root)
    if context.tree_digest != actual:
        raise FrozenMergeError(f"merge context {path} is for tree {context.tree_digest}, "
                               f"this checkout is {actual}")
    return merge(load_records(Path(records_dir), version, fixture), context, repo_root)


def open_matrix_run(version: str, fixture: str, *, repo_root: Path = REPO_ROOT,
                    environ=None) -> MatrixRun:
    """Direct mode: build one repository and run every `CI_SUITES[version]`
    suite whole in it, in order (today's behaviour). Merged mode: merge the
    records first -- so a refusal costs nothing -- then build the repository
    the non-suite assertions read."""
    merged = load_merge_inputs(version, fixture, repo_root=repo_root, environ=environ)
    builder, name = FIXTURE_BUILDERS[fixture]
    tmp = tempfile.TemporaryDirectory()
    try:
        release = find_release(repo_root, version)
        root = builder(release, Path(tmp.name) / name)
        if merged is None:
            results = {}
            for suite in CI_SUITES[version]:
                chunk = FrozenChunk(f"direct:{version}/{fixture}/{suite}", version, fixture, suite)
                record = record_from_process(chunk, run_suite(root, suite),
                                             **_post_run_state(fixture, root, release))
                results[suite] = MergedResult.from_single(record)
        else:
            results = merged
    except BaseException:
        tmp.cleanup()
        raise
    return MatrixRun(version, fixture, "direct" if merged is None else "merged",
                     root, release, results, tmp)


# -- full repository and git-dir state (E-MRG-3) -------------------------------

def _git_bytes(repo: Path, *args: str, check: bool = True) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", str(repo), *args], check=check,
                          capture_output=True, env=env).stdout


#: Files under the git common dir that the full-state snapshot skips:
#: `objects/` is content-addressed (unreachable objects are unobservable
#: through refs), `index` is covered by `git status`, and `logs/` moves with
#: the refs it already captures.
GIT_DIR_SKIPPED = ("objects", "index", "logs")


def full_state(repo: Path) -> dict[str, str]:
    """Everything a later suite could observe in `repo`: every changed,
    untracked or ignored worktree file with its content hash, and the git
    common dir's `HEAD`, refs (stash included), local config, registered
    worktrees and every other file (hooks, info, Workflow claims, witnesses
    and authorizations)."""
    repo = Path(repo)
    state: dict[str, str] = {}
    raw = _git_bytes(repo, "status", "--porcelain=v1", "-z", "--ignored",
                     "--untracked-files=all")
    tokens = raw.split(b"\0")
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        code, path = token[:2].decode(), os.fsdecode(token[3:])
        if "R" in code or "C" in code:
            i += 1
        target = repo / path
        if target.is_dir() and not target.is_symlink():
            for sub in sorted(p for p in target.rglob("*") if not p.is_dir()):
                state[f"worktree:{sub.relative_to(repo).as_posix()}"] = f"{code}:{describe(sub)}"
        else:
            state[f"worktree:{path}"] = f"{code}:{describe(target)}"
    common = Path(_git_bytes(repo, "rev-parse", "--path-format=absolute",
                             "--git-common-dir").decode().strip())
    state["git:HEAD"] = _git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    state["git:symbolic-ref"] = _git_bytes(repo, "symbolic-ref", "-q", "HEAD",
                                           check=False).decode().strip()
    for line in _git_bytes(repo, "for-each-ref",
                           "--format=%(objectname) %(refname)").decode().splitlines():
        obj, ref = line.split(" ", 1)
        state[f"ref:{ref}"] = obj
    state["git:config"] = _git_bytes(repo, "config", "--local", "--list").decode()
    state["git:worktrees"] = _git_bytes(repo, "worktree", "list", "--porcelain").decode()
    for path in sorted(common.rglob("*")):
        rel = path.relative_to(common)
        if rel.parts[0] in GIT_DIR_SKIPPED or path.is_dir():
            continue
        state[f"gitdir:{rel.as_posix()}"] = describe(path)
    return state


def state_delta(before: dict[str, str], after: dict[str, str]) -> list[tuple[str, str, str]]:
    return [(key, before.get(key, "absent"), after.get(key, "absent"))
            for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]


#: Every file the frozen Workflow code opens `O_RDWR | O_CREAT` only to hold
#: `fcntl.flock` on, and never writes, with the line that opens it in 2.6.0's
#: `workflow_state.py` (the same paths in every earlier release that has
#: them): `(key prefix, compiled path pattern)`.
FLOCK_TARGETS = (
    # STATE_LOCK_PATH :1596, opened by state_lock :1681
    ("worktree", re.compile(r"\.ai-review/runtime/WORKFLOW_STATE\.lock")),
    # PLAN_APPROVAL_GUARD_LOCK_PATH :3270, opened by _plan_approval_guard_lock :3396
    ("worktree", re.compile(r"\.ai-review/runtime/PLAN_APPROVAL_MUTATION\.guardlock")),
    # WORKTREE_IDENTITY_LOCK_PATH :4786, opened by identity_document_lock :4824
    ("worktree", re.compile(r"\.ai-review/runtime/WORKTREE_IDENTITY\.lock")),
    # guard_mutation_lock_path :5248, opened by guard_mutation_lock :5279
    ("gitdir", re.compile(r"ai-workflow/checkpoint-claims/[0-9a-f]{64}\.guardlock")),
    # lifecycle_lock_path :6806, opened by lifecycle_lock :6840
    ("gitdir", re.compile(r"ai-workflow/checkpoint-claims/[0-9a-f]{64}\.lifecycle\.lock")),
    # IDENTITY_GAP_LOCK_RELPATH :8575, opened by identity_gap_lock :8797
    ("gitdir", re.compile(r"ai-workflow/identity-gap\.lock")),
)
_EMPTY_FILE_RE = re.compile(r"(?:^|:)file:[-x]:" + hashlib.sha256(b"").hexdigest() + "$")


def classify_delta(key: str, after: str) -> str | None:
    """`bytecode` or `flock` for 5.5's two pre-classified kinds, else None.

    A `flock` delta is one of `FLOCK_TARGETS`, still empty. A file at such a
    path with content -- something the code could read -- is not in this
    class, and neither is any other lock-named file."""
    kind, path = key.split(":", 1)
    if "__pycache__/" in path or path.endswith(".pyc"):
        return "bytecode"
    if _EMPTY_FILE_RE.search(after) and any(
            kind == prefix and pattern.fullmatch(path) for prefix, pattern in FLOCK_TARGETS):
        return "flock"
    return None


# -- evidence (plan section 6.2) -----------------------------------------------

def _matrix(versions):
    """The frozen inventory, and `(host unit id, version, fixture)` for every
    matrix host class, restricted to `versions` if given."""
    from parallel import inventory
    frozen = inventory.discover_frozen(REPO_ROOT)
    rows = [(unit, v, f) for unit, (v, f) in frozen.matrix.items()
            if not versions or v in versions]
    return frozen, rows


def fixed_chunking(frozen, version: str, fixture: str, mode: str) -> list[FrozenChunk]:
    """`two-chunk`: each suite's classes, sorted, split at the midpoint (a
    one-class suite is one chunk). `one-class`: every class its own chunk."""
    chunks = []
    for suite in frozen.ci_suites[version]:
        classes = sorted(frozen.classes[version][suite])
        if mode == "two-chunk":
            mid = (len(classes) + 1) // 2
            groups = [g for g in (classes[:mid], classes[mid:]) if g]
        else:
            groups = [[name] for name in classes]
        for index, group in enumerate(groups):
            enumerated = tuple(f"{c}.{m}" for c in group
                               for m in frozen.classes[version][suite][c])
            chunks.append(FrozenChunk(f"{version}/{fixture}/{suite}#{index}", version, fixture,
                                      suite, tuple(group), enumerated))
    return chunks


def chunking_digest(chunks) -> str:
    return hashlib.sha256(canonical_json(
        {c.id: [c.version, c.fixture, c.suite, list(c.classes)] for c in chunks}
    ).encode()).hexdigest()


@contextlib.contextmanager
def _environ(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update({k: v for k, v in values.items() if v is not None})
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _OutcomeResult(unittest.TestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes: dict[str, str] = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes[test._testMethodName] = "pass"  # noqa: SLF001

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test._testMethodName] = "fail"  # noqa: SLF001

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[getattr(test, "_testMethodName", str(test))] = "error"

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test._testMethodName] = "skip"  # noqa: SLF001


def run_host_class(unit_id: str) -> dict:
    """Run one matrix host class in this process, in whichever mode the
    environment selects, and summarise per-suite results and per-assertion
    outcomes."""
    module_file, cls_name = unit_id[len("host:"):].split("::")
    cls = getattr(importlib.import_module(module_file[:-3]), cls_name)
    result = _OutcomeResult()
    started = time.monotonic()
    unittest.defaultTestLoader.loadTestsFromTestCase(cls).run(result)
    view = getattr(cls, "Run", cls).results
    return {
        "seconds": round(time.monotonic() - started, 1),
        "assertions": dict(sorted(result.outcomes.items())),
        "errors": [text[-3000:] for _, text in result.errors + result.failures],
        "suites": {suite: {"ran": r.ran, "failing": sorted(r.failing),
                           "returncode": r.returncode, "chunks": len(r.records),
                           "lost": r.attribution()}
                   for suite, r in view.items()},
    }


def _evidence_chunked(mode: str, versions, out: Path) -> dict:
    """E-MRG-1 (`merged`: direct mode, then the fixed two-chunk chunking) or
    E-MRG-2 (`one-class`)."""
    frozen, rows = _matrix(versions)
    digest = tree_digest(REPO_ROOT)
    summary: dict = {}
    for unit, version, fixture in rows:
        key = f"{version}/{fixture}"
        entry = summary.setdefault(key, {"unit": unit})
        if mode == "merged":
            with _environ(**{RECORDS_ENV: None, CONTEXT_ENV: None}):
                entry["direct"] = run_host_class(unit)
            print(f"[direct]    {key}: {entry['direct']['seconds']}s "
                  f"{entry['direct']['assertions']}", flush=True)
        chunks = fixed_chunking(frozen, version, fixture,
                                "two-chunk" if mode == "merged" else "one-class")
        plan_digest = chunking_digest(chunks)
        records_dir = out / f"{mode}-records"
        started = time.monotonic()
        with _environ(PYTHONDONTWRITEBYTECODE="1"):
            for chunk in chunks:
                write_record(execute(chunk, tree_digest=digest, plan_digest=plan_digest),
                             records_dir)
        context = MergeContext.from_chunks(
            version, fixture, chunks,
            {suite: sorted(frozen.classes[version][suite]) for suite in frozen.ci_suites[version]},
            tree_digest=digest, plan_digest=plan_digest)
        context_dir = out / f"{mode}-context"
        write_context(context, context_dir)
        chunk_seconds = round(time.monotonic() - started, 1)
        with _environ(**{RECORDS_ENV: str(records_dir), CONTEXT_ENV: str(context_dir)}):
            entry[mode] = run_host_class(unit)
        entry[mode]["chunk_seconds"] = chunk_seconds
        entry[mode]["chunk_count"] = len(chunks)
        print(f"[{mode:<9}] {key}: {len(chunks)} chunks in {chunk_seconds}s "
              f"{entry[mode]['assertions']}", flush=True)
    return summary


def _evidence_residue(versions, out: Path) -> dict:
    """E-MRG-3: every suite, in today's order, in one repository per
    `(version, fixture)`; the full-state delta each suite leaves."""
    frozen, rows = _matrix(versions)
    summary: dict = {}
    for _unit, version, fixture in rows:
        key = f"{version}/{fixture}"
        builder, name = FIXTURE_BUILDERS[fixture]
        with tempfile.TemporaryDirectory(prefix="wm-residue-") as tmp:
            repo = builder(find_release(REPO_ROOT, version), Path(tmp) / name)
            suites = {}
            for suite in CI_SUITES[version]:
                before = full_state(repo)
                proc = run_suite(repo, suite)
                deltas = [{"key": k, "before": b, "after": a, "class": classify_delta(k, a)}
                          for k, b, a in state_delta(before, full_state(repo))]
                suites[suite] = {"returncode": proc.returncode, "deltas": deltas}
                unclassified = [d["key"] for d in deltas if d["class"] is None]
                print(f"[residue]   {key} {suite}: {len(deltas)} deltas, "
                      f"unclassified {unclassified}", flush=True)
        summary[key] = suites
    return summary


def _compare(out: Path) -> int:
    """E-MRG-1/-2/-3 verdict over every summary in `out`."""
    merged, one_class, residue = {}, {}, {}
    for path in sorted(out.glob("*.summary.json")):
        data = strict_json_loads(path.read_text(encoding="utf-8"))
        for prefix, target in (("merged-", merged), ("one-class-", one_class),
                               ("residue-", residue)):
            if path.name.startswith(prefix):
                target.update(data)
    problems = []

    def view(entry):
        return ({s: (r["ran"], r["failing"], r["returncode"] != 0)
                 for s, r in entry["suites"].items()}, entry["assertions"])

    for key in sorted(merged):
        direct, chunked = merged[key]["direct"], merged[key]["merged"]
        if view(direct) != view(chunked):
            problems.append(f"E-MRG-1 {key}: direct {view(direct)} != merged {view(chunked)}")
        if key in one_class and view(one_class[key]["one-class"]) != view(direct):
            problems.append(f"E-MRG-2 {key}: one-class {view(one_class[key]['one-class'])} "
                            f"!= direct {view(direct)}")
        failing_assertions = [a for a, o in direct["assertions"].items() if o != "pass"]
        if failing_assertions:
            problems.append(f"{key}: direct mode itself is not green: {failing_assertions}")
        one = ("missing" if key not in one_class else
               f"== direct {view(one_class[key]['one-class']) == view(direct)}")
        print(f"{key}: direct==merged {view(direct) == view(chunked)}; one-class {one}; "
              f"non-passing assertions {failing_assertions}")
    missing = sorted(set(one_class) - set(merged))
    if missing:
        problems.append(f"one-class summaries without a merged baseline: {missing}")
    for key, suites in sorted(residue.items()):
        kinds: dict[str, int] = {}
        for suite, entry in suites.items():
            for delta in entry["deltas"]:
                if delta["class"] is None:
                    problems.append(f"E-MRG-3 {key} {suite}: unclassified delta {delta}")
                else:
                    kinds[delta["class"]] = kinds.get(delta["class"], 0) + 1
            if entry["returncode"] != 0 and "bootstrapped" not in key and "target" not in key:
                problems.append(f"E-MRG-3 {key} {suite}: exit {entry['returncode']}")
        print(f"{key}: residue pre-classified {kinds or 'none'}")
    for problem in problems:
        print("PROBLEM:", problem)
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 tests/frozen_runs.py")
    parser.add_argument("--evidence", required=True,
                        choices=("merged", "one-class", "residue", "compare"))
    parser.add_argument("--out", required=True, type=Path,
                        help="evidence directory, outside the checkout")
    parser.add_argument("--version", action="append", default=[])
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out == REPO_ROOT or REPO_ROOT in out.parents:
        parser.error("--out must be outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    if args.evidence == "compare":
        return _compare(out)
    started = time.monotonic()
    if args.evidence == "residue":
        summary = _evidence_residue(args.version, out)
    else:
        summary = _evidence_chunked(args.evidence, args.version, out)
    tag = "-".join(args.version) or "all"
    (out / f"{args.evidence}-{tag}.summary.json").write_text(canonical_json(summary),
                                                            encoding="utf-8")
    print(f"{args.evidence} {tag}: {time.monotonic() - started:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
