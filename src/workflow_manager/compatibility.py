"""The compatibility report: what an update would meet in a repository.

`read_repository` reads a managed repository without writing it and without
importing the installed Workflow's `scripts/`; `build_report` turns those
facts, the update plan and the release tables below into findings; `render_*`
print them. Nothing here touches the target beyond reading it, and Git runs
only through `run_git`, hermetically.

Three versions stay distinct everywhere: the *installed release* (the
Workflow release the installation record names), the *governing version* (the
protocol version fixed on a work item: `1`, `2.1` or `2.2`, not a release),
and the *latest available release* (the newest pin). The *target* of a check
is always printed, even when it is the latest (a kept deviation).

Release knowledge the Manager must carry, because only it knows what it
pinned, is three tables below. Each is keyed by release version and must have
an entry, possibly empty, for every pinned version (a test enforces it, so
pinning a release forces someone to decide).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .install import InstallError, UpdatePlan
from .installation import CorruptInstallationError, Installation, is_managed

# ---------------------------------------------------------------------------
# Versions, phases and the Workflow facts this module mirrors
# ---------------------------------------------------------------------------

GOVERNING_VERSIONS = ("1", "2.1", "2.2")
STATE_SCHEMA_VERSION = 1
WORK_ITEM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STATE_PATH = "docs/ai-workflow/WORKFLOW_STATE.json"
CONFIG_PATH = "docs/ai-workflow/WORKFLOW_CONFIG.json"
GATE_POLICY_PATH = "docs/ai-workflow/GATE_POLICY.json"
INSTALLATION_RECORD_PATH = ".workflow-manager/installation.json"
CLAIMS_RELDIR = "ai-workflow/checkpoint-claims"

#: Phases before implementation starts, and the two non-active ones. Every
#: other known phase is implementing-or-later. Copied from 2.9.0 and pinned by
#: a test against the package's `KNOWN_PHASES`.
PLAN_PHASES = frozenset({
    "PLANNING", "SELF_REVIEWING_PLAN", "AWAITING_EXTERNAL_PLAN_REVIEW", "REVISING_PLAN",
    "AWAITING_LOCAL_PLAN_REVIEW", "AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW",
    "AWAITING_PLAN_APPROVAL",
})
IMPLEMENTING_OR_LATER_PHASES = frozenset({
    "IMPLEMENTING", "SELF_REVIEWING_IMPLEMENTATION",
    "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW", "AWAITING_LOCAL_IMPLEMENTATION_REVIEW",
    "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW", "APPLYING_REVIEW_FEEDBACK",
    "AWAITING_TECHNICAL_APPROVAL", "AWAITING_FUNCTIONAL_REVIEW",
    "FIXING_FUNCTIONAL_FINDINGS", "AWAITING_USER_ACCEPTANCE", "AMENDING_PLAN",
})
NON_ACTIVE_EXEMPT_PHASES = frozenset({"MILESTONE_COMPLETE", "LEGACY_READY"})
KNOWN_PHASES = PLAN_PHASES | IMPLEMENTING_OR_LATER_PHASES | NON_ACTIVE_EXEMPT_PHASES

#: `TOOLING_AMBIENT_EXCLUDED_PATHS` of 2.9.0.
AMBIENT_EXCLUDED_PATHS = frozenset({INSTALLATION_RECORD_PATH})

#: 2.9.0's `_ALWAYS_HUMAN`: the gate stays human whatever the policy says.
ALWAYS_HUMAN_GATES = {
    "plan_approval": frozenset({"1"}),
    "technical_approval": frozenset({"1", "2.1"}),
    "acceptance": frozenset(),
}

_HEURISTIC_IMPLEMENTATION_PREFIXES = ("scripts/", ".claude/commands/")


def version_key(version: str) -> tuple[int, ...]:
    """`"2.5.1"` -> `(2, 5, 1)`; raises `ValueError` for anything else."""
    if not isinstance(version, str) or not re.fullmatch(r"\d+(\.\d+)*", version):
        raise ValueError(f"not a release version: {version!r}")
    return tuple(int(part) for part in version.split("."))


def _lt(a: str, b: str) -> bool:
    return version_key(a) < version_key(b)


def _le(a: str, b: str) -> bool:
    return version_key(a) <= version_key(b)


# ---------------------------------------------------------------------------
# Rendering commands
# ---------------------------------------------------------------------------

FAMILY_MANAGER = "manager"
FAMILY_GIT = "git"
FAMILY_SLASH = "slash"
FAMILIES = (FAMILY_MANAGER, FAMILY_GIT, FAMILY_SLASH)


@dataclass(frozen=True)
class Command:
    """A command the report prints: built from an argv, tagged with a family.

    The family says how it is validated: Manager commands through the real
    parser, Git commands by running them, slash commands against the release's
    command files.
    """
    family: str
    argv: tuple[str, ...]
    note: str = ""

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise ValueError(f"unknown command family {self.family!r}")

    def render(self) -> str:
        return render_command(self.argv)


def render_command(argv) -> str:
    """The shell line for an argv: what is printed is what would execute."""
    return shlex.join(str(a) for a in argv)


def manager_command(*args: str, release_version: str | None = None) -> Command:
    """`workflow-manager [--release-version V] <args>`: the global option goes
    before the subcommand."""
    argv = ["workflow-manager"]
    if release_version:
        argv += ["--release-version", release_version]
    return Command(FAMILY_MANAGER, tuple(argv + list(args)))


def git_command(target: Path, *args: str) -> Command:
    return Command(FAMILY_GIT, ("git", "-C", str(target), *args))


def slash_command(name: str, *args: str) -> Command:
    return Command(FAMILY_SLASH, (f"/{name}", *args))


# ---------------------------------------------------------------------------
# Git, hermetically
# ---------------------------------------------------------------------------

GIT_TIMEOUT_SECONDS = 10
_GIT_CONFIG_FLAGS = (
    "--no-optional-locks",
    "-c", "core.fsmonitor=false",
    "-c", "core.untrackedCache=false",
    "-c", "gc.auto=0",
    "-c", "maintenance.auto=false",
    "-c", "core.hooksPath=/dev/null",
)
_GIT_ENVIRONMENT = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1",
}


# Variables that point Git at another repository than `git -C <target>` names,
# as a hook or wrapper exports them.
_REPOSITORY_SELECTORS = frozenset({
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX",
})


@dataclass(frozen=True)
class GitResult:
    """`returncode` is `None` when git could not be run or timed out."""
    returncode: int | None
    stdout: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def git_argv(repo: Path, *args: str) -> list[str]:
    return ["git", "-C", str(repo), *_GIT_CONFIG_FLAGS, *args]


def run_git(repo: Path, *args: str, stdin: str | None = None, raw: bool = False) -> GitResult:
    """The one Git entry point of the read-only paths.

    `raw` is for `-z` output that carries paths: bytes in, bytes out, mapped
    one-to-one through latin-1 (stdin the same way), with no locale decoding
    and no newline translation, so a path that is not UTF-8 or holds a `\\r`
    round-trips unchanged. Text mode that cannot decode is a failed call.

    Hermetic: no fsmonitor, untracked cache, auto gc or maintenance, no hooks,
    no prompts, no optional locks, no lazy fetch. Returns the exit status with
    the output, because the partial-clone probes exit 1 for "key absent".
    """
    env = {k: v for k, v in os.environ.items() if k not in _REPOSITORY_SELECTORS}
    env.update(_GIT_ENVIRONMENT)
    try:
        if raw:
            proc = subprocess.run(git_argv(repo, *args), capture_output=True,
                                  input=None if stdin is None else stdin.encode("latin-1"),
                                  timeout=GIT_TIMEOUT_SECONDS, env=env)
            return GitResult(proc.returncode, proc.stdout.decode("latin-1"))
        proc = subprocess.run(git_argv(repo, *args), capture_output=True, text=True,
                              input=stdin, timeout=GIT_TIMEOUT_SECONDS, env=env)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return GitResult(None)
    return GitResult(proc.returncode, proc.stdout)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageDeclarations:
    """One stage's classification sets from an artifacts file."""
    protected_paths: frozenset[str]
    protected_prefixes: tuple[str, ...]
    excluded_paths: frozenset[str]
    excluded_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ItemDeclarations:
    """What `<id>-artifacts.json` declares: `None` for a stage it lacks."""
    plan_stage: StageDeclarations | None
    implementation_stage: StageDeclarations | None


@dataclass(frozen=True)
class WorkItemFacts:
    id: str
    phase: str
    governing: str
    work_item_type: str | None
    parent: str | None
    entry: dict
    declarations: ItemDeclarations | None   # None: file missing or unreadable
    registry_ids: tuple[str, ...]

    @property
    def active(self) -> bool:
        return self.phase != "MILESTONE_COMPLETE"

    @property
    def legacy(self) -> bool:
        return self.governing == "1" or self.phase == "LEGACY_READY"

    @property
    def implementing_or_later(self) -> bool:
        """An unrecognised phase counts, the cautious side."""
        return (self.phase in IMPLEMENTING_OR_LATER_PHASES
                or self.phase not in KNOWN_PHASES)


@dataclass
class RepositoryFacts:
    target: Path
    managed: bool = False
    installation: Installation | None = None
    installation_error: str | None = None
    config_default: str | None = None
    gate_policy_present: bool = False
    state: dict | None = None
    active_work_item_id: str | None = None
    items: list[WorkItemFacts] = field(default_factory=list)
    plan_inputs_dirs: list[str] = field(default_factory=list)
    dirty: bool | None = None
    worktree_count: int | None = None
    retirement_trailer: bool | None = None
    activation_trailer: bool | None = None
    amendment_witnesses: list[str] | None = None
    partial_clone: bool = False
    #: Reasons an inspection could not be completed: each is a finding.
    problems: list[str] = field(default_factory=list)

    @property
    def inspection_complete(self) -> bool:
        return not self.problems


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _string_set(value) -> frozenset[str]:
    """A declaration's paths: a list, or a mapping from path to reason."""
    if isinstance(value, dict):
        return frozenset(k for k in value if isinstance(k, str))
    if isinstance(value, list):
        return frozenset(v for v in value if isinstance(v, str))
    return frozenset()


def _stage(data) -> StageDeclarations | None:
    if not isinstance(data, dict):
        return None
    return StageDeclarations(
        protected_paths=_string_set(data.get("protected_paths")),
        protected_prefixes=tuple(sorted(_string_set(data.get("protected_prefixes")))),
        excluded_paths=_string_set(data.get("excluded_paths")),
        excluded_prefixes=tuple(sorted(_string_set(data.get("excluded_prefixes")))),
    )


def artifacts_relpath(work_item_id: str) -> str:
    """The Workflow's `artifacts_path_for_work_item`: pure templating."""
    if not WORK_ITEM_ID_RE.match(work_item_id):
        raise ValueError(f"not a valid work item id: {work_item_id!r}")
    return f"docs/ai-workflow/registry/{work_item_id}-artifacts.json"


def _registry_ids(target: Path, work_item_id: str, entry: dict) -> tuple[str, ...]:
    ids = set(entry.get("checkpoints") or {}) if isinstance(entry.get("checkpoints"), dict) else set()
    rel = f"docs/ai-workflow/registry/{work_item_id}-registry.json"
    try:
        data = _read_json(target / rel)
        ids |= {c["id"] for c in data.get("checkpoints", []) if isinstance(c.get("id"), str)}
    except (OSError, ValueError, AttributeError, TypeError, KeyError):
        pass
    return tuple(sorted(ids))


def _load_declarations(target: Path, work_item_id: str) -> ItemDeclarations | None:
    try:
        data = _read_json(target / artifacts_relpath(work_item_id))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return ItemDeclarations(_stage(data.get("plan_stage")), _stage(data.get("implementation_stage")))


def _read_items(target: Path, state: dict, problems: list[str]) -> list[WorkItemFacts]:
    work_items = state.get("work_items")
    if not isinstance(work_items, dict):
        problems.append(f"{STATE_PATH} has no work_items object")
        return []
    items = []
    for wid, entry in sorted(work_items.items()):
        if not isinstance(entry, dict):
            problems.append(f"work item {wid!r} is not an object")
            continue
        phase, governing = entry.get("phase"), entry.get("governing_workflow_version")
        if not isinstance(phase, str):
            problems.append(f"work item {wid!r} has no phase")
            continue
        if governing not in GOVERNING_VERSIONS:
            problems.append(
                f"work item {wid!r} has governing_workflow_version {governing!r}, "
                f"not one of {', '.join(GOVERNING_VERSIONS)}")
            continue
        if phase not in KNOWN_PHASES:
            problems.append(
                f"work item {wid!r} is in unknown phase {phase!r}; "
                "treated as implementing or later")
        wtype, parent = entry.get("work_item_type"), entry.get("parent_work_item_id")
        if wtype is not None and not isinstance(wtype, str):
            problems.append(f"work item {wid!r} has a work_item_type that is not text")
            wtype = None
        if parent is not None and not isinstance(parent, str):
            problems.append(f"work item {wid!r} has a parent_work_item_id that is not text")
            parent = None
        if not WORK_ITEM_ID_RE.match(wid):
            problems.append(f"work item id {wid!r} is not a valid id; its declarations were not read")
            declarations = None
        else:
            declarations = _load_declarations(target, wid)
        items.append(WorkItemFacts(wid, phase, governing, wtype, parent, entry,
                                   declarations, _registry_ids(target, wid, entry)))
    return items


def read_repository(target: Path) -> RepositoryFacts:
    """Read a repository, writing nothing. Never raises for an unreadable
    part: that part becomes a `problems` entry (an `incomplete-inspection`
    finding), so an inspection that could not finish is never a clean one."""
    target = Path(target)
    facts = RepositoryFacts(target=target)
    facts.managed = is_managed(target)
    if facts.managed:
        try:
            facts.installation = Installation.read(target)
        except CorruptInstallationError as error:
            facts.installation_error = str(error)
        except (OSError, ValueError) as error:
            facts.installation_error = f"the installation record cannot be read ({error})"
    else:
        facts.problems.append("the repository is not managed (no installation record)")

    _read_config(target, facts)
    facts.gate_policy_present = (target / GATE_POLICY_PATH).exists()
    _read_state(target, facts)
    _read_plan_inputs(target, facts)
    _read_git(target, facts)
    return facts


def _read_config(target: Path, facts: RepositoryFacts) -> None:
    path = target / CONFIG_PATH
    if not path.exists():
        return
    try:
        data = _read_json(path)
        default = data.get("default_workflow_version")
    except (OSError, ValueError, AttributeError) as error:
        facts.problems.append(f"{CONFIG_PATH} cannot be read ({error})")
        return
    if default is not None and not isinstance(default, str):
        facts.problems.append(f"{CONFIG_PATH} has a default_workflow_version that is not text")
        return
    facts.config_default = default


def _read_state(target: Path, facts: RepositoryFacts) -> None:
    path = target / STATE_PATH
    if not path.exists():
        if facts.managed:
            facts.problems.append(f"{STATE_PATH} is missing from a managed repository")
        return
    try:
        state = _read_json(path)
    except (OSError, ValueError) as error:
        facts.problems.append(f"{STATE_PATH} cannot be read as JSON ({error})")
        return
    if not isinstance(state, dict):
        facts.problems.append(f"{STATE_PATH} is not a JSON object")
        return
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        facts.problems.append(
            f"{STATE_PATH} has schema_version {state.get('schema_version')!r}; "
            f"this report understands {STATE_SCHEMA_VERSION}")
        return
    facts.state = state
    active = state.get("active_work_item_id")
    facts.active_work_item_id = active if isinstance(active, str) else None
    facts.items = _read_items(target, state, facts.problems)


def _read_plan_inputs(target: Path, facts: RepositoryFacts) -> None:
    for item in facts.items:
        if WORK_ITEM_ID_RE.match(item.id) and (target / ".ai-review" / item.id / "plan-inputs").is_dir():
            facts.plan_inputs_dirs.append(f".ai-review/{item.id}/plan-inputs")


def _resolve_git_path(target: Path, printed: str) -> Path:
    """`rev-parse` may print a path relative to the target; resolve it there,
    not against the process's cwd. (`--path-format=absolute` needs Git 2.31.)"""
    path = Path(printed.strip())
    return path if path.is_absolute() else Path(os.path.normpath(target / path))


def detect_partial_clone(target: Path) -> bool | None:
    """True for a partial clone, False for an ordinary repository, None when
    the detection itself failed. Both probes exit 1 when the key is absent."""
    probes = (
        ("config", "--get", "extensions.partialClone"),
        ("config", "--get-regexp", r"^remote\..*\.(promisor|partialclonefilter)$"),
    )
    partial = False
    for probe in probes:
        result = run_git(target, *probe)
        if result.returncode == 0 and result.stdout.strip():
            partial = True
        elif result.returncode not in (0, 1):
            return None
    return partial


def _trailer_found(target: Path, pattern: str) -> bool | None:
    result = run_git(target, "log", "-n", "1", "--format=%H", "--extended-regexp",
                     f"--grep={pattern}", "HEAD")
    if not result.ok:
        return None
    return bool(result.stdout.strip())


RETIREMENT_GREP = r"^Workflow-Legacy-Retirement:"
ACTIVATION_GREP = r"^Workflow-Activation: 2\.2[[:space:]]*$"


def _filter_selected_by_a_tracked_path(target: Path) -> bool:
    """True when a configured clean/process filter driver is selected by the
    `filter` attribute of a tracked path, or when that could not be ruled out.
    Read-only, and runs no filter: `config`, the index listing and
    `check-attr` (which honors `.gitattributes`, `info/attributes` and
    `core.attributesFile`) execute nothing."""
    configured = run_git(target, "config", "-z", "--get-regexp", r"^filter\..*\.(clean|process)$",
                         raw=True)
    if configured.returncode == 1:
        return False
    if configured.returncode != 0:
        return True
    drivers = set()
    for entry in configured.stdout.split("\0"):
        key = entry.split("\n", 1)[0]
        if key.startswith("filter.") and "." in key[len("filter."):]:
            drivers.add(key[len("filter."):key.rindex(".")])
    if not drivers:
        return True
    # `git status` scans the whole work tree, not only a target below its
    # root, so list every tracked path with the top-level pathspec `:/`. Git
    # prints the paths relative to the target, and `check-attr` run from the
    # same directory resolves them the same way: no root path is read back, so
    # no path normalization can point the selection at another repository.
    listed = run_git(target, "--no-literal-pathspecs", "ls-files", "-z", "--", ":/", raw=True)
    if not listed.ok:
        return True
    if not listed.stdout:
        return False
    attrs = run_git(target, "check-attr", "-z", "--stdin", "filter", stdin=listed.stdout, raw=True)
    if not attrs.ok:
        return True
    fields = attrs.stdout.split("\0")
    # `<path> NUL <attribute> NUL <value> NUL`, repeated: the values.
    return any(value in drivers for value in fields[2::3])


def _read_git(target: Path, facts: RepositoryFacts) -> None:
    inside = run_git(target, "rev-parse", "--git-dir")
    if not inside.ok:
        facts.problems.append(
            "not a Git repository, or Git could not be run: the tree state, worktrees "
            "and history trailers were not checked")
        return
    worktrees = run_git(target, "worktree", "list", "--porcelain")
    if worktrees.ok:
        facts.worktree_count = sum(1 for line in worktrees.stdout.splitlines()
                                   if line.startswith("worktree "))
    else:
        facts.problems.append("`git worktree list` failed: linked worktrees were not counted")

    common = run_git(target, "rev-parse", "--git-common-dir")
    if common.ok and common.stdout.strip():
        claims = _resolve_git_path(target, common.stdout) / CLAIMS_RELDIR
        try:
            facts.amendment_witnesses = sorted(p.name for p in claims.glob("*.amendment.json")) \
                if claims.is_dir() else []
        except OSError as error:
            facts.problems.append(f"the amendment witnesses cannot be listed ({error})")
    else:
        facts.problems.append("`git rev-parse --git-common-dir` failed: amendment witnesses were not checked")

    partial = detect_partial_clone(target)
    if partial is None:
        facts.problems.append(
            "partial-clone detection failed: the tree state and history trailers were not read")
        return
    if partial:
        facts.partial_clone = True
        facts.problems.append(
            "this is a partial clone: the tree state and history trailers were not read, "
            "because reading them could fetch objects")
        return

    # `git status` runs a configured clean/process filter on a tracked file
    # whose stat data changed and whose attributes select that driver, and a
    # filter is arbitrary code: it may write the target. No flag disables
    # filters generically, so skip the status when a configured driver is
    # selected by a tracked path, or when that could not be ruled out. A
    # driver configured but selected by no tracked path (Git LFS installed
    # system-wide, say) never runs, so the status is safe.
    if _filter_selected_by_a_tracked_path(target):
        facts.problems.append(
            "a configured Git clean/process filter is selected by a tracked path (or that could not be ruled out): whether the "
            "tree is clean was not checked, because `git status` could run the filter")
    else:
        # `--ignore-submodules=dirty`: the child `git status` in a submodule
        # reads the submodule's own config, where a filter could still run.
        # `dirty` compares only the submodule's HEAD with the recorded commit,
        # so a moved gitlink (staged or not) is still reported, and edits
        # inside a submodule's work tree are not: an update never writes there.
        # (`all` would hide a moved gitlink; `untracked` runs the child status.)
        status = run_git(target, "status", "--porcelain", "--no-renames", "--untracked-files=normal",
                         "--ignore-submodules=dirty")
        if status.ok:
            facts.dirty = bool(status.stdout.strip())
        else:
            facts.problems.append("`git status` failed: whether the tree is clean is unknown")

    head = run_git(target, "rev-parse", "--verify", "--quiet", "HEAD")
    if head.returncode == 1:
        facts.retirement_trailer = facts.activation_trailer = False   # no commits yet
        return
    facts.retirement_trailer = _trailer_found(target, RETIREMENT_GREP)
    facts.activation_trailer = _trailer_found(target, ACTIVATION_GREP)
    if facts.retirement_trailer is None or facts.activation_trailer is None:
        facts.problems.append("`git log` failed: history trailers were not searched")


# ---------------------------------------------------------------------------
# Path classification: copies of the Workflow's two classifiers
# ---------------------------------------------------------------------------
# `compatibility.py` must not import the installed `scripts/`, so these are
# copies; a test runs both over a table of paths against the 2.9.0 package's.

PROTECTED = "protected"
EXCLUDED = "excluded"
UNCLASSIFIED = "unclassified"


def classify_plan_stage(path: str, stage: StageDeclarations) -> str:
    """`classify_path`: exact protected path, excluded path, excluded prefix,
    the ambient exclusion, else unclassified. The plan stage has no protected
    prefixes, and a stray key is ignored."""
    if path in stage.protected_paths:
        return PROTECTED
    if path in stage.excluded_paths:
        return EXCLUDED
    if any(path.startswith(p) for p in stage.excluded_prefixes):
        return EXCLUDED
    if path in AMBIENT_EXCLUDED_PATHS:
        return EXCLUDED
    return UNCLASSIFIED


def classify_implementation_stage(path: str, stage: StageDeclarations) -> str:
    """`classify_path_implementation_stage`: protected path, protected prefix,
    excluded path, excluded prefix, the ambient exclusion, else unclassified;
    an exclusion never overrides an earlier protection."""
    if path in stage.protected_paths:
        return PROTECTED
    if any(path.startswith(p) for p in stage.protected_prefixes):
        return PROTECTED
    if path in stage.excluded_paths:
        return EXCLUDED
    if any(path.startswith(p) for p in stage.excluded_prefixes):
        return EXCLUDED
    if path in AMBIENT_EXCLUDED_PATHS:
        return EXCLUDED
    return UNCLASSIFIED


def update_paths(plan: UpdatePlan) -> list[str]:
    """Every path the update writes or removes, merges included."""
    return sorted({w.path for w in plan.writes} | set(plan.removals))


# ---------------------------------------------------------------------------
# The three release tables
# ---------------------------------------------------------------------------


def _present(value) -> bool:
    return value not in (None, [], {}, "")


def keys_anywhere(obj, name: str, prefix: str = "") -> list[str]:
    """Where in a JSON value a non-empty `name` key occurs."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{prefix}/{key}" if prefix else str(key)
            if key == name and _present(value):
                found.append(here)
            found += keys_anywhere(value, name, here)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found += keys_anywhere(value, name, f"{prefix}[{index}]")
    return found


def values_anywhere(obj, key: str, value, prefix: str = "") -> list[str]:
    """Where a `key` equal to `value` occurs."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{prefix}/{k}" if prefix else str(k)
            if k == key and v == value:
                found.append(here)
            found += values_anywhere(v, key, value, here)
    elif isinstance(obj, list):
        for index, v in enumerate(obj):
            found += values_anywhere(v, key, value, f"{prefix}[{index}]")
    return found


Detector = Callable[[RepositoryFacts], list[str]]


@dataclass(frozen=True)
class Signal:
    """Something in the repository that an older release could not read right."""
    name: str
    description: str
    detect: Detector


@dataclass(frozen=True)
class Boundary:
    """A release that introduced downgrade-relevant vocabulary."""
    posture: str                  # the CLAUDE.md posture sentence
    signals: tuple[Signal, ...] = ()
    #: A hazard the report cannot detect, said instead of omitted.
    undetectable: str | None = None


def _state_keys(name: str) -> Detector:
    def detect(facts: RepositoryFacts) -> list[str]:
        return [f"{name} at {where}" for where in keys_anywhere(facts.state or {}, name)]
    return detect


def _state_value(key: str, value) -> Detector:
    def detect(facts: RepositoryFacts) -> list[str]:
        return [f"{key}: {value} at {where}"
                for where in values_anywhere(facts.state or {}, key, value)]
    return detect


def _items_where(predicate: Callable[[WorkItemFacts], bool], text: Callable[[WorkItemFacts], str]) -> Detector:
    def detect(facts: RepositoryFacts) -> list[str]:
        return [text(i) for i in facts.items if predicate(i)]
    return detect


def _any(*detectors: Detector) -> Detector:
    def detect(facts: RepositoryFacts) -> list[str]:
        return [e for d in detectors for e in d(facts)]
    return detect


def _amended(item: WorkItemFacts) -> bool:
    return item.phase == "AMENDING_PLAN" or _present(item.entry.get("amendment_history"))


def _letter_suffixed(item: WorkItemFacts) -> list[str]:
    return [i for i in item.registry_ids if re.fullmatch(r"CP\d+[A-Z]", i)]


def _detect_suffixed_amendment(facts: RepositoryFacts) -> list[str]:
    return [f"{i.id}: amended, with letter-suffixed checkpoint {', '.join(_letter_suffixed(i))}"
            for i in facts.items if _amended(i) and _letter_suffixed(i)]


def _detect_activation(facts: RepositoryFacts) -> list[str]:
    found = []
    if facts.config_default == "2.2":
        found.append(f"{CONFIG_PATH} default_workflow_version is 2.2")
    if facts.activation_trailer:
        found.append("a Workflow-Activation: 2.2 trailer-shaped line in HEAD's history")
    return found


def _detect_plan_inputs(facts: RepositoryFacts) -> list[str]:
    return [f"{d}/ exists" for d in facts.plan_inputs_dirs]


def _detect_witnesses(facts: RepositoryFacts) -> list[str]:
    return [f"amendment witness {n}" for n in (facts.amendment_witnesses or [])]


def _detect_retirement(facts: RepositoryFacts) -> list[str]:
    if facts.retirement_trailer:
        return ["a Workflow-Legacy-Retirement trailer-shaped line in HEAD's history"]
    return []


_PHASES_2_5_0 = ("AWAITING_LOCAL_IMPLEMENTATION_REVIEW",
                 "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW")

DOWNGRADE_BOUNDARIES: dict[str, Boundary] = {
    # Source: CLAUDE.md "Downgrade posture", one paragraph per release.
    "2.3.1": Boundary(""),
    "2.4.0": Boundary(
        "2.4.0 added the NEEDS_REVALIDATION checkpoint status and the SUPERSEDED plan-approval "
        "status; an older release reads state that ever held one as permanently undecidable, "
        "and checkpoint resume wedges with no in-band escape.",
        (
            Signal("needs-revalidation", "a checkpoint status NEEDS_REVALIDATION",
                   _state_value("status", "NEEDS_REVALIDATION")),
            Signal("superseded", "a plan approval status SUPERSEDED",
                   _state_value("status", "SUPERSEDED")),
            Signal("amendment", "a plan amendment requested",
                   _items_where(_amended, lambda i: f"{i.id}: phase {i.phase}, amendment_history present"
                                if _present(i.entry.get("amendment_history")) else f"{i.id}: phase {i.phase}")),
        ),
    ),
    "2.5.0": Boundary(
        "2.5.0 added governing version 2.2, the two implementation-review phases, the "
        "implementation_review_stages ledger and a version-aware activation trailer; an older "
        "release reads such an item as unknown, and answers the activation question wrongly, "
        "silently.",
        (
            Signal("governing-2.2", "a work item governed by 2.2",
                   _items_where(lambda i: i.governing == "2.2",
                                lambda i: f"{i.id}: governing_workflow_version 2.2")),
            Signal("implementation-review-phase", "an implementation-review phase 2.5.0 added",
                   _items_where(lambda i: i.phase in _PHASES_2_5_0,
                                lambda i: f"{i.id}: phase {i.phase}")),
            Signal("implementation-review-stages", "an implementation_review_stages ledger",
                   _state_keys("implementation_review_stages")),
            Signal("activation", "2.2 activated", _detect_activation),
        ),
    ),
    "2.5.1": Boundary(
        "2.5.1 widened the amendment checkpoint-id grammar to letter-suffixed ids; an older "
        "release wedges an amended item that carries one, with no in-band exit.",
        (Signal("suffixed-amendment", "an amended work item with a letter-suffixed checkpoint id",
                _detect_suffixed_amendment),),
    ),
    "2.6.0": Boundary(
        "2.6.0 added persisted keys an older release ignores rather than rejects, so a downgraded "
        "repository silently loses 2.6.0's guarantees.",
        (
            Signal("feedback-layout", 'a work item stamped feedback_layout: "scoped"',
                   _items_where(lambda i: i.entry.get("feedback_layout") == "scoped",
                                lambda i: f"{i.id}: feedback_layout scoped")),
            Signal("plan-review-binding", "a plan_review_binding record",
                   _state_keys("plan_review_binding")),
            Signal("plan-inputs", "a .ai-review/<id>/plan-inputs/ directory", _detect_plan_inputs),
            Signal("amendment-witness", "an amendment witness in the common Git directory",
                   _detect_witnesses),
            Signal("resolved-review-content-id", "a resolved amendment (resolved_review_content_id)",
                   _state_keys("resolved_review_content_id")),
        ),
    ),
    "2.7.0": Boundary(
        "2.7.0 added consumed_plan_review_content_ids and the Orchestration Protocol; an older "
        "release ignores the key, shrinking the never-re-bind guarantee silently.",
        (Signal("consumed-plan-review-content-ids", "consumed_plan_review_content_ids",
                _state_keys("consumed_plan_review_content_ids")),),
        undetectable="a repository driven by an orchestrator through the Orchestration Protocol",
    ),
    "2.8.0": Boundary(
        "2.8.0 made gates automatic by default; an older release refuses the POLICY_SATISFIED "
        "approval basis, and accepts the other keys 2.8.0 adds without acting on them.",
        (
            Signal("policy-satisfied", "an approval satisfied by policy",
                   _state_value("basis", "POLICY_SATISFIED")),
            Signal("gate-evidence", "gate_evidence", _state_keys("gate_evidence")),
            Signal("reopenings", "reopenings", _state_keys("reopenings")),
            Signal("acceptance-satisfaction", "acceptance_satisfaction",
                   _state_keys("acceptance_satisfaction")),
            Signal("ledger-audit", "ledger audit keys (verdict_sha256, run_ref, reviewer_model)",
                   _any(_state_keys("verdict_sha256"), _state_keys("run_ref"),
                        _state_keys("reviewer_model"))),
            Signal("gate-policy-adoption", "gate_policy_adoption", _state_keys("gate_policy_adoption")),
            Signal("gate-policy-floor", "gate_policy_floor", _state_keys("gate_policy_floor")),
        ),
    ),
    "2.9.0": Boundary(
        "2.9.0 keeps a retired legacy work item closed; an older release has no retired-item "
        "guard, so a red pull-request fact can reopen it, silently.",
        (Signal("legacy-retirement", "a retired legacy work item", _detect_retirement),),
    ),
}

#: Fixes and defaults that reach only new work items or new installations.
NEW_WORK_ONLY: dict[str, tuple[str, ...]] = {
    "2.3.1": (),
    "2.4.0": (),
    "2.5.0": ("Implementation review stages exist only for work items governed by 2.2.",),
    "2.5.1": (),
    "2.6.0": (
        'The feedback_layout: "scoped" stamp is written only on work items created under 2.6.0.',
        "The v2.4.0-001 repair reaches earlier work items through the release, not through "
        "their declarations files.",
    ),
    "2.7.0": (),
    "2.8.0": (),   # gate defaults reach existing items: see GATE_DEFAULT_CHANGES
    "2.9.0": (
        "The 2.2 default (default_workflow_version) is for new installations; an update never "
        "edits an existing WORKFLOW_CONFIG.json.",
        "The v2.6.0-003 fix covers new governing-1 implementation entries only.",
    ),
}

#: Per pinned release, how it changes the gate defaults for existing work too;
#: "" for a release that does not. A report names each change in (installed,
#: target] when the repository has no GATE_POLICY.json.
#: Only `2.8.0` has a non-empty entry; `build_findings` shows the last one in
#: range with 2.8.0-specific wording. A second non-empty entry needs the
#: `gates-change` finding generalized first.
GATE_DEFAULT_CHANGES: dict[str, str] = {
    "2.3.1": "",
    "2.4.0": "",
    "2.5.0": "",
    "2.5.1": "",
    "2.6.0": "",
    "2.7.0": "",
    "2.8.0": "a repository with no GATE_POLICY.json moves from human gates to automatic ones",
    "2.9.0": "",
}

#: What to commit first to keep the 2.7.0 gates.
HUMAN_GATE_POLICY = {"schema_version": 1, "human_approval": True}


def gate_modes(governing: str, human_approval: bool = False) -> dict[str, str]:
    """`human` or `automatic` for each gate, mirroring 2.9.0's `gate_mode`."""
    return {gate: "human" if governing in always or human_approval else "automatic"
            for gate, always in ALWAYS_HUMAN_GATES.items()}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

BLOCKED, WARNING, NOTE = "blocked", "warning", "note"
SEVERITIES = (BLOCKED, WARNING, NOTE)


@dataclass(frozen=True)
class Finding:
    severity: str
    id: str
    title: str
    detail: str = ""
    commands: tuple[Command, ...] = ()


@dataclass(frozen=True)
class RecoveryStep:
    text: str
    commands: tuple[Command, ...] = ()


@dataclass(frozen=True)
class Report:
    repository: str
    installed: str | None
    profile: str | None
    installed_at: str | None
    source: str | None
    latest: str | None
    target: str | None
    pinned: tuple[str, ...]
    config_default: str | None
    items: tuple[WorkItemFacts, ...]
    active_work_item_id: str | None
    findings: tuple[Finding, ...]
    new_work_only: tuple[tuple[str, str], ...]
    recovery: tuple[RecoveryStep, ...]
    inspection_complete: bool
    updated_at: str | None = None

    @property
    def headline(self) -> str:
        if not self.inspection_complete:
            return "inspection incomplete"
        if any(f.severity == BLOCKED for f in self.findings):
            return "the update would be refused"
        if any(f.severity == WARNING for f in self.findings):
            return "warnings found"
        if any(_is_listed_note(f) for f in self.findings):
            return "notes only"
        return "nothing found"

    def has(self, finding_id: str) -> bool:
        return any(f.id == finding_id for f in self.findings)

    def ids(self, severity: str | None = None) -> list[str]:
        return [f.id for f in self.findings if severity in (None, f.severity)]

    @property
    def doctor_exit_code(self) -> int:
        """0 when no `blocked` or `warning` finding (an incomplete inspection
        is a warning), else 1. 2 (an error) is the CLI's."""
        return 1 if any(f.severity in (BLOCKED, WARNING) for f in self.findings) else 0


def _hits(paths: list[str], classify: Callable[[str], str], wanted: str) -> list[str]:
    return [p for p in paths if classify(p) == wanted]


def _first(paths: list[str], limit: int = 5) -> str:
    shown = ", ".join(paths[:limit])
    return shown + (f" and {len(paths) - limit} more" if len(paths) > limit else "")


def _item_findings(facts: RepositoryFacts, plan: UpdatePlan | None, target: str | None
                   ) -> list[Finding]:
    """`v2.4.0-001`, `v2.4.0-001-old`, `unclassified-paths` and the
    incomplete-inspection reasons the declarations add."""
    findings: list[Finding] = []
    extra_problems: list[str] = []
    paths = update_paths(plan) if plan is not None else []
    active = [i for i in facts.items if i.active]

    for item in active:
        decl = item.declarations
        if decl is None:
            extra_problems.append(
                f"{item.id}: {artifacts_relpath(item.id) if WORK_ITEM_ID_RE.match(item.id) else 'its artifacts file'} "
                "is missing or unreadable, so the paths the update rewrites could not be classified")
        else:
            if decl.plan_stage is None:
                extra_problems.append(f"{item.id}: its artifacts file declares no plan_stage")
            if item.implementing_or_later and decl.implementation_stage is None:
                extra_problems.append(
                    f"{item.id}: its artifacts file declares no implementation_stage")

        protected_plan: list[str] = []
        unclassified_plan: list[str] = []
        if decl is not None and decl.plan_stage is not None:
            classify = lambda p, s=decl.plan_stage: classify_plan_stage(p, s)   # noqa: E731
            protected_plan = _hits(paths, classify, PROTECTED)
            unclassified_plan = _hits(paths, classify, UNCLASSIFIED)

        protected_impl: list[str] = []
        unclassified_impl: list[str] = []
        fell_back = False
        if item.implementing_or_later:
            if decl is not None and decl.implementation_stage is not None:
                classify = lambda p, s=decl.implementation_stage: classify_implementation_stage(p, s)  # noqa: E731
                if item.work_item_type == "process":
                    protected_impl = _hits(paths, classify, PROTECTED)
                unclassified_impl = _hits(paths, classify, UNCLASSIFIED)
            elif item.work_item_type == "process":
                fell_back = True
                protected_impl = [p for p in paths if p.startswith(_HEURISTIC_IMPLEMENTATION_PREFIXES)]

        if protected_impl or protected_plan:
            parts = []
            if protected_impl:
                how = ("by the heuristic scripts/ and .claude/commands/ rule, because its "
                       "declarations file is missing or lacks the stage"
                       if fell_back else "by its declarations")
                parts.append(
                    f"implementation stage, {len(protected_impl)} path(s) protected {how}: "
                    f"{_first(protected_impl)}. They enter the item's implementation diff and "
                    "review content, and from AWAITING_TECHNICAL_APPROVAL on its technical "
                    "approval goes stale.")
            if protected_plan:
                parts.append(
                    f"plan stage, {len(protected_plan)} path(s) protected: {_first(protected_plan)}. "
                    "The plan-stage review_content_id changes: a bound plan bundle drifts "
                    "(ReviewedContentDriftError) and an implementing item's plan approval goes stale.")
            findings.append(Finding(
                WARNING, "v2.4.0-001",
                f"{item.id} ({item.phase}): the update rewrites paths the item protects",
                "\n".join(parts) + "\nFinish or park the item first, or update before it starts."))
        if unclassified_plan or unclassified_impl:
            parts = []
            if unclassified_plan:
                parts.append(f"plan stage: {_first(unclassified_plan)}")
            if unclassified_impl:
                parts.append(f"implementation stage: {_first(unclassified_impl)}")
            findings.append(Finding(
                WARNING, "unclassified-paths",
                f"{item.id} ({item.phase}): the update writes paths its declarations leave unclassified",
                "; ".join(parts) + ". The Workflow would refuse with UnclassifiedPathError at that "
                "stage (plan-bundle generation, implementing_entry_reachable, or implementation "
                "review); the item's declarations need review or amendment."))

        if target and _lt(target, "2.6.0") and item.work_item_type == "process" \
                and item.implementing_or_later:
            findings.append(Finding(
                WARNING, "v2.4.0-001-old",
                f"{item.id} ({item.phase}): a target before 2.6.0 does not repair v2.4.0-001",
                "Committing .workflow-manager/installation.json then makes "
                "implementing_entry_reachable raise for declarations that predate the 2.4.0 fix. "
                "The repair reaches earlier items only through a release of 2.6.0 or later."))

    if extra_problems:
        findings.append(Finding(
            WARNING, "incomplete-inspection", "declarations could not be fully read",
            "\n".join(extra_problems)))
    return findings


def _retirement_advice(facts: RepositoryFacts, item: WorkItemFacts, target: str | None
                       ) -> tuple[Command | None, str]:
    """The `/retire-legacy-work-item` offer, or why it is not offered,
    matching the published writer's refusals."""
    if item.phase != "LEGACY_READY":
        return None, f"not offered: it is in phase {item.phase}, not LEGACY_READY"
    if facts.active_work_item_id == item.id:
        return None, "not offered: it is the active work item, and a dormant item is never active"
    children = sorted(i.id for i in facts.items if i.parent == item.id and i.active)
    if children:
        return None, f"not offered: it has unfinished children ({', '.join(children)})"
    if target is None or _lt(target, "2.9.0"):
        return None, "not offered: /retire-legacy-work-item exists from 2.9.0, and the target is older"
    return slash_command("retire-legacy-work-item", item.id), \
        "after the update, if it was finished long ago"


def build_findings(facts: RepositoryFacts, plan: UpdatePlan | None, *, target: str | None,
                   installed_resolved: bool = True, refusal: Exception | None = None
                   ) -> list[Finding]:
    installed = facts.installation.workflow_version if facts.installation else None
    findings: list[Finding] = []

    if refusal is not None:
        from .install import CollisionError, DriftError
        if isinstance(refusal, DriftError):
            findings.append(Finding(
                BLOCKED, "refused-drift", "the update would be refused: release files were edited locally",
                f"{refusal}\nSave the edits, then run the update with --force to discard them."))
        elif isinstance(refusal, CollisionError):
            findings.append(Finding(
                BLOCKED, "refused-collision", "the update would be refused: paths are in use", str(refusal)))
        elif isinstance(refusal, InstallError):
            findings.append(Finding(BLOCKED, "refused-install", "the update would be refused", str(refusal)))

    if facts.installation_error:
        findings.append(Finding(WARNING, "incomplete-inspection",
                                "the installation record could not be read", facts.installation_error))
    if facts.problems:
        findings.append(Finding(
            WARNING, "incomplete-inspection", "the inspection could not be completed",
            "\n".join(facts.problems)
            + "\nThis report is not a clean bill of health."))

    findings += _item_findings(facts, plan, target)

    for item in facts.items:
        if item.active and item.legacy:
            command, advice = _retirement_advice(facts, item, target)
            findings.append(Finding(
                WARNING, "legacy-active", f"{item.id} is an active legacy work item ({item.phase})",
                f"The update does not retire or migrate it. /retire-legacy-work-item {advice}.",
                (command,) if command else ()))

    gate_changes = [(v, GATE_DEFAULT_CHANGES[v]) for v in sorted(GATE_DEFAULT_CHANGES, key=version_key)
                    if GATE_DEFAULT_CHANGES[v] and installed and target
                    and _lt(installed, v) and _le(v, target)]
    if gate_changes and not facts.gate_policy_present:
        change_version, change_text = gate_changes[-1]
        lines = []
        for item in facts.items:
            if not item.active:
                continue
            after = gate_modes(item.governing)
            changed = [g for g, m in after.items() if m == "automatic"]
            kept = [g for g, m in after.items() if m == "human"]
            lines.append(f"{item.id} (governing {item.governing}): becomes automatic: "
                         f"{', '.join(changed) or 'none'}; stays human: {', '.join(kept) or 'none'}")
        findings.append(Finding(
            WARNING, "gates-change", f"gates become automatic by default ({change_version})",
            f"{change_text[0].upper()}{change_text[1:]}. "
            "With no GATE_POLICY.json the gates are satisfied by their evidence, for existing work "
            "items as well as new ones.\n" + ("\n".join(lines) + "\n" if lines else "")
            + f"To keep human gates, commit {GATE_POLICY_PATH} with "
            + json.dumps(HUMAN_GATE_POLICY) + " before the update; decide the policy first."))

    if installed and target and _lt(target, installed):
        crossed = [v for v in sorted(DOWNGRADE_BOUNDARIES, key=version_key, reverse=True)
                   if DOWNGRADE_BOUNDARIES[v].posture and _lt(target, v) and _le(v, installed)]
        lines = []
        for version in crossed:
            boundary = DOWNGRADE_BOUNDARIES[version]
            lines.append(f"Crossing {version}: {boundary.posture}")
            hits = [(s, s.detect(facts)) for s in boundary.signals]
            found = [f"{s.description}: {'; '.join(e)}" for s, e in hits if e]
            lines.append("  Found in the current state: " + (" | ".join(found) if found
                                                            else "no signal"))
            if boundary.undetectable:
                lines.append(f"  This boundary has a hazard the report cannot detect: "
                             f"{boundary.undetectable}.")
        findings.append(Finding(
            WARNING, "downgrade", f"target {target} is older than the installed release {installed}",
            "A downgrade is unsupported.\n" + "\n".join(lines)
            + "\nOnly the current state, the retirement and activation trailer searches of HEAD's "
            "history, the amendment witnesses and plan-inputs directories were searched; the rest "
            "of Git history was not. This is not a statement that the downgrade is safe."))

    if facts.worktree_count and facts.worktree_count > 1 and installed and target \
            and _lt(installed, "2.6.0") and _le("2.6.0", target):
        findings.append(Finding(
            WARNING, "worktrees", f"{facts.worktree_count} Git worktrees, updating across 2.6.0",
            "Merge the update into every linked worktree's branch before driving checkpoints or "
            "amendments from more than one of them."))

    if facts.dirty:
        findings.append(Finding(
            WARNING, "dirty-tree", "the working tree has uncommitted changes",
            "Commit or set aside your edits first, so the update is the only diff."))

    if installed and target:
        try:
            for version, text in new_work_only(installed, target):
                findings.append(Finding(NOTE, "new-work-only", f"{version}: {text}"))
        except ValueError:
            pass

    if not installed_resolved:
        findings.append(Finding(
            NOTE, "not-verified", "the installed release could not be resolved",
            "Local edits to release files are still detected from the install record. "
            "This Manager cannot compare the installation with the installed release's "
            "published package (offline, or the release is not pinned), the comparison "
            "`workflow-manager verify` makes."))
    return findings


def new_work_only(installed: str, target: str) -> list[tuple[str, str]]:
    """The `NEW_WORK_ONLY` entries for releases in (installed, target]."""
    out = []
    for version in sorted(NEW_WORK_ONLY, key=version_key):
        if _lt(installed, version) and _le(version, target):
            out += [(version, text) for text in NEW_WORK_ONLY[version]]
    return out


def recovery_steps(facts: RepositoryFacts, findings: list[Finding], *, target_arg: str | None,
                   release_version: str | None, downgrade: bool = False) -> list[RecoveryStep]:
    """Static recovery text with the path filled in. `target_arg` is the
    repository as printed; `release_version` goes in only when it is not the
    latest (the caller decides). `downgrade` withholds every update command:
    the target is older than the installed release."""
    repo = Path(target_arg or facts.target)
    steps = [RecoveryStep(
        "Before the update: make sure the tree is clean, or the edits are committed, and "
        "update on a branch.",
        (git_command(repo, "status", "--short"),))]
    if downgrade:
        steps.append(RecoveryStep(
            "No update command is offered: the target is older than the installed release, and "
            "a downgrade is unsupported."))
    else:
        steps.append(RecoveryStep(
            "An update that stopped half way is re-run with the same command; it needs no --force.",
            (manager_command("update", str(repo), release_version=release_version),)))
    if facts.dirty is False:
        steps.append(RecoveryStep(
            "To undo an update that has not been committed: this is an undo only if the tree was "
            "clean before the update; it discards ALL uncommitted changes, not only the update's. "
            "Review untracked leftovers with the preview; a committed update is undone by "
            "reverting its commit. Not `update --release-version <older>`: that is the "
            "unsupported downgrade.",
            (git_command(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", "."),
             git_command(repo, "clean", "-n", "-d"))))
    elif facts.dirty:
        steps.append(RecoveryStep(
            "No undo command: the tree has uncommitted changes, so an undo would discard them too."))
    else:
        steps.append(RecoveryStep(
            "No undo command: whether the tree has uncommitted changes could not be checked."))
    if not downgrade and any(f.id == "refused-drift" for f in findings):
        steps.append(RecoveryStep(
            "A locally modified release file: save your edit, then run the update with --force.",
            (manager_command("update", str(repo), "--force", release_version=release_version),)))
    for finding in findings:
        for command in finding.commands:
            if command.family == FAMILY_SLASH:
                steps.append(RecoveryStep(f"{finding.title}:", (command,)))
    return steps


def build_report(facts: RepositoryFacts, plan: UpdatePlan | None, *, target_version: str | None,
                 latest_version: str | None, pinned_versions: list[str],
                 refusal: Exception | None = None, installed_resolved: bool = True,
                 target_arg: str | None = None) -> Report:
    findings = build_findings(facts, plan, target=target_version,
                              installed_resolved=installed_resolved, refusal=refusal)
    installation = facts.installation
    explicit = target_version if target_version and target_version != latest_version else None
    source = None
    if installation is not None:
        src = installation.source
        if isinstance(src, dict) and src.get("kind") == "package":
            source = f"package {src.get('archive')}"
        elif isinstance(src, dict) and src.get("kind") == "local":
            source = "local, unpublished"
        else:
            source = "not recorded"
    installed = installation.workflow_version if installation else None
    notes = tuple(new_work_only(installed, target_version)) if installed and target_version else ()
    return Report(
        repository=str(target_arg or facts.target),
        installed=installed,
        profile=installation.profile if installation else None,
        installed_at=installation.installed_at if installation else None,
        updated_at=installation.updated_at if installation else None,
        source=source,
        latest=latest_version,
        target=target_version,
        pinned=tuple(pinned_versions),
        config_default=facts.config_default,
        items=tuple(facts.items),
        active_work_item_id=facts.active_work_item_id,
        findings=tuple(findings),
        new_work_only=notes,
        recovery=tuple(recovery_steps(facts, findings, target_arg=target_arg,
                                      release_version=explicit,
                                      downgrade=bool(installed and target_version
                                                     and _lt(target_version, installed)))),
        inspection_complete=not any(f.id == "incomplete-inspection" for f in findings),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _indent(text: str, prefix: str) -> list[str]:
    return [prefix + line if line else line for line in text.splitlines()]


def _is_listed_note(finding: Finding) -> bool:
    """A note that is listed under Findings (the new-work-only ones have their own section)."""
    return finding.severity == NOTE and finding.id != "new-work-only"


def render_report(report: Report) -> str:
    """The report as text. The three version labels never share a line."""
    lines = [f"Repository          {report.repository}"]
    if report.installed:
        extra = [f"profile {report.profile}"]
        if report.installed_at:
            extra.append(f"installed {report.installed_at}")
        if report.updated_at and report.updated_at != report.installed_at:
            extra.append(f"updated {report.updated_at}")
        if report.source:
            extra.append(f"source {report.source}")
        lines.append(f"Installed release   {report.installed}  ({', '.join(extra)})")
    else:
        lines.append("Installed release   unknown")
    if report.latest:
        pins = f"  (this Manager pins {report.pinned[0]} ... {report.pinned[-1]})" if report.pinned else ""
        lines.append(f"Latest available    {report.latest}{pins}")
    if report.target:
        lines.append(f"Target of this check {report.target}  (--release-version, else latest)")
    lines += ["", "Work items (governing version is a protocol version, not a release)"]
    if report.items:
        width = max(len(i.id) for i in report.items)
        phase_width = max(len(i.phase) for i in report.items)
        lines.append(f"  {'ID':<{width}}  {'PHASE':<{phase_width}}  {'TYPE':<8}  GOVERNING")
        for item in report.items:
            mark = "  (active)" if item.id == report.active_work_item_id else ""
            lines.append(f"  {item.id:<{width}}  {item.phase:<{phase_width}}  "
                         f"{item.work_item_type or '-':<8}  {item.governing}{mark}")
    else:
        lines.append("  none")
    lines.append(f"Config default for new work items: {report.config_default or 'not set'}")
    lines += ["", f"Findings -- {report.headline}"]
    listed = [f for f in report.findings if f.severity != NOTE] + \
             [f for f in report.findings if _is_listed_note(f)]
    for finding in listed:
        lines.append(f"  [{finding.severity}] {finding.id}: {finding.title}")
        lines += _indent(finding.detail, "      ")
        for command in finding.commands:
            lines.append(f"      {command.render()}")
    if not listed:
        lines.append("  none")
    lines += ["", "Fixes that apply only to new work"]
    notes = [f for f in report.findings if f.severity == NOTE and f.id == "new-work-only"]
    lines += [f"  {f.title}" for f in notes] or ["  none"]
    lines += ["", "Recovery"]
    for number, step in enumerate(report.recovery, 1):
        lines.append(f"  {number}. {step.text}")
        for command in step.commands:
            lines.append(f"       {command.render()}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Read-only destinations (plan 3.6)
# ---------------------------------------------------------------------------


class ContainmentError(InstallError):
    """A destination the read-only commands would write lies inside the target."""


@dataclass(frozen=True)
class Destinations:
    """Where the read-only commands may write, decided before any write."""
    snapshot_parent: Path
    cache_root: Path
    protected: tuple[Path, ...]


#: `tempfile`'s documented order after the environment: the fixed directories.
_TEMP_ENVIRONMENT = ("TMPDIR", "TEMP", "TMP")
_TEMP_FIXED = ("/tmp", "/var/tmp", "/usr/tmp")


def _inside(path: Path, protected: tuple[Path, ...]) -> Path | None:
    """The protected root `path` lies in (or is), else None. Both are real paths."""
    for root in protected:
        if path == root or root in path.parents:
            return root
    return None


def protected_set(target: Path) -> tuple[Path, ...]:
    """The real paths of the work tree and of the actual and common Git
    directories. Fails closed: a target with a `.git` entry whose directories
    cannot be resolved is refused, never checked by its work tree alone."""
    target = Path(target)
    roots = [Path(os.path.realpath(target))]
    dot_git = target / ".git"
    if os.path.lexists(dot_git):
        for flag in ("--absolute-git-dir", "--git-common-dir"):
            result = run_git(target, "rev-parse", flag)
            if not (result.ok and result.stdout.strip()):
                raise ContainmentError(
                    f"could not check containment: `git rev-parse {flag}` failed in {target}")
            roots.append(Path(os.path.realpath(_resolve_git_path(target, result.stdout))))
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def _walk_links(directory: Path) -> str | None:
    """A symlink found inside `directory` (walked, not followed), else None."""
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            if os.path.islink(os.path.join(base, name)):
                return os.path.join(base, name)
    return None


def plan_destinations(options, environ, target: Path, versions=()) -> Destinations:
    """Decide, by path arithmetic alone, where the release cache and the
    temporary snapshot go, or refuse. Creates, opens and probes nothing: it
    must not call `tempfile.gettempdir()` (whose first call writes a probe
    file in the directory it picks) or `mkdtemp()` without `dir=`.

    `options.release_cache` is `--release-cache`; `versions` are the releases
    the resolver will open under the cache.
    """
    from .source import cache_root
    protected = protected_set(target)

    root = Path(os.path.realpath(cache_root(getattr(options, "release_cache", None), environ)))
    if (hit := _inside(root, protected)) is not None:
        raise ContainmentError(
            f"the release cache {root} lies inside {hit}: the repository is never written by "
            f"this command; choose another with --release-cache or $WORKFLOW_MANAGER_RELEASE_CACHE")
    for version in versions:
        for leaf in (root / f"{version}.lock", root / version):
            real = Path(os.path.realpath(leaf))
            if (hit := _inside(real, protected)) is not None:
                raise ContainmentError(
                    f"the release cache entry {leaf} resolves to {real}, inside {hit}: "
                    f"the repository is never written by this command")
        entry = root / version
        if entry.is_dir() and not entry.is_symlink():
            link = _walk_links(entry)
            if link is not None:
                raise ContainmentError(
                    f"the release cache entry {entry} holds a link ({link}); remove the entry "
                    f"or choose another cache with --release-cache")

    candidates: list[tuple[str, bool]] = []
    for name in _TEMP_ENVIRONMENT:
        if environ.get(name):
            candidates.append((environ[name], True))
    candidates += [(path, False) for path in _TEMP_FIXED]
    try:
        candidates.append((os.getcwd(), False))
    except OSError:
        pass
    parent = None
    for candidate, named in candidates:
        real = Path(os.path.realpath(candidate))
        hit = _inside(real, protected)
        if named and hit is not None:
            raise ContainmentError(
                f"a temporary directory named in the environment ({candidate}) lies inside "
                f"{hit}; unset it or point it outside the repository")
        if parent is None and hit is None and real.is_dir() and os.access(real, os.W_OK | os.X_OK):
            parent = real
    if parent is None:
        raise ContainmentError("no temporary directory outside the target")
    return Destinations(parent, root, protected)
