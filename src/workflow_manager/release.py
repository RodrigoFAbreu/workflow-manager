"""Reading one Workflow release directory.

A *release* is one immutable directory tree, the unpacked `tree/` of a
Workflow release package (`package.py`) or an unpackaged `--release-dir`:

    <release>/
        manifest.json   every release file's location, digest and disposition
        payload/        Workflow files
        fixtures/       host documents the frozen conformance suite asserts on
        templates/      clean repository-local initial state

A release is self-contained and verifiable from its own manifest. Where one
comes from, and which versions are published, is `source.py`'s business.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

#: Payload files a target repository needs in order to *operate* the Workflow.
INSTALL_PROFILE_RUNTIME = "runtime"
#: Everything the frozen conformance suite needs as well.
INSTALL_PROFILE_FULL = "full"
INSTALL_PROFILES = (INSTALL_PROFILE_RUNTIME, INSTALL_PROFILE_FULL)

_PROFILE_CATEGORIES = {
    INSTALL_PROFILE_RUNTIME: ("distribution",),
    INSTALL_PROFILE_FULL: ("distribution", "conformance"),
}

#: Templates that become repository-local state in a target: written once when
#: the repository is first managed, and never replaced afterwards. The Workflow
#: writes to all of these at run time, so replacing one would destroy someone's
#: work.
STATE_TEMPLATES = (
    "docs/ai-workflow/WORKFLOW_STATE.json",
    "docs/ai-workflow/WORKFLOW_CONFIG.json",
    "docs/ACTIVE_MILESTONE.md",
)

#: Templates the *release* owns rather than the repository. Nothing in the
#: Workflow writes to these at run time; they exist to run a particular
#: release's suites, so they are installed, replaced and drift-checked exactly
#: like payload files. The category each one belongs to decides which profiles
#: install it -- the conformance CI is pointless in a repository that did not
#: install what it runs.
RELEASE_TEMPLATES = {
    ".github/workflows/workflow-conformance.yml": "conformance",
}

#: Templates contributed as a section to a file the target may already own.
GITIGNORE_TEMPLATE = ".gitignore.workflow-fragment"
CLAUDE_TEMPLATE = "CLAUDE.md"
MERGED_TEMPLATES = (GITIGNORE_TEMPLATE, CLAUDE_TEMPLATE)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseIntegrityError(RuntimeError):
    """Release content on disk does not match the digest its manifest records.

    `kind` names the cause for `advice` (which step the operator is told to
    take); `None` is an unclassified cause with no step of its own."""

    def __init__(self, message: str = "", *, kind: str | None = None):
        super().__init__(message)
        self.kind = kind


_VERSION_TEXT = re.compile(r"\d+(\.\d+)*")
_KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MANAGER_SCHEMA_VERSION = 1
#: The closed detector vocabulary of `manager` schema 1 (docs/release-metadata.md):
#: kind -> the keys its `detect` object carries besides `kind`.
DETECTOR_KINDS = {
    "state-key": ("key",),
    "state-value": ("key", "value"),
    "item-governing": ("value",),
    "item-phase": ("phases",),
    "item-field": ("key", "value"),
}


def _shape(message: str) -> ReleaseIntegrityError:
    return ReleaseIntegrityError(f"manifest `manager` block: {message}", kind="manifest-shape")


def parse_version_tuple(text) -> tuple[int, ...]:
    """`1.13.0` as `(1, 13, 0)`; anything but `\\d+(\\.\\d+)*` is a shape error."""
    if not isinstance(text, str) or _VERSION_TEXT.fullmatch(text) is None:
        raise _shape(f"{text!r} is not a version (digits separated by dots)")
    return tuple(int(part) for part in text.split("."))


def manager_version_ok(minimum: str | None, manager: str | None) -> bool:
    """Whether a Manager of version `manager` satisfies `min_manager_version`.
    A development build (no version, or `.dev` in it) satisfies every minimum:
    an integer-tuple compare would otherwise refuse every release on it."""
    if minimum is None or not manager or ".dev" in manager:
        return True
    try:
        have = parse_version_tuple(manager)
    except ReleaseIntegrityError:
        return True
    return have >= parse_version_tuple(minimum)


@dataclass(frozen=True)
class DetectorSpec:
    kind: str
    key: str | None = None
    value: object = None
    phases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignalSpec:
    name: str
    label: str
    detect: DetectorSpec


@dataclass(frozen=True)
class BoundarySpec:
    posture: str
    undetectable: str | None
    signals: tuple[SignalSpec, ...]


@dataclass(frozen=True)
class PortabilityException:
    suite: str
    test: str
    reason: str
    requires: str | None = None
    defect: str | None = None


@dataclass(frozen=True)
class Conformance:
    suites: dict
    portability_exceptions: tuple[PortabilityException, ...]


@dataclass(frozen=True)
class ManagerBlock:
    """A release manifest's validated `manager` block. A field is `None` when
    the block lacks that item (no data, not "nothing to say")."""
    min_manager_version: str | None = None
    downgrade_boundary: BoundarySpec | None = None
    new_work_only: tuple[str, ...] | None = None
    gate_default_change: str | None = None
    conformance: Conformance | None = None

    #: The items a block may carry, in the order a finding names them.
    ITEMS = ("downgrade_boundary", "new_work_only", "gate_default_change", "conformance")

    def missing_items(self) -> tuple[str, ...]:
        return tuple(item for item in self.ITEMS if getattr(self, item) is None)


def _object(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise _shape(f"{where} must be an object")
    return value


def _text(value, where: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise _shape(f"{where} must be a string")
    return value


def _required(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise _shape(f"{where} needs `{key}`")
    return mapping[key]


def _scalar(value, where: str):
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return value
    raise _shape(f"{where} must be a string, an integer, a boolean or null")


def _detector(raw, where: str) -> DetectorSpec:
    raw = _object(raw, where)
    kind = _required(raw, "kind", where)
    if not isinstance(kind, str) or kind not in DETECTOR_KINDS:
        raise _shape(f"{where} names the unknown detector kind {kind!r}; this Manager knows "
                     f"{', '.join(DETECTOR_KINDS)} (a newer Manager may know more)")
    wanted = DETECTOR_KINDS[kind]
    key = value = None
    phases: tuple[str, ...] = ()
    if "key" in wanted:
        key = _required(raw, "key", where)
        if not isinstance(key, str) or not key:
            raise _shape(f"{where} `key` must be a non-empty string")
    if "value" in wanted:
        value = _scalar(_required(raw, "value", where), f"{where} `value`")
        if kind == "item-governing" and not isinstance(value, str):
            raise _shape(f"{where} `value` must be a string")
    if "phases" in wanted:
        listed = _required(raw, "phases", where)
        if not isinstance(listed, list) or not listed \
                or not all(isinstance(p, str) for p in listed):
            raise _shape(f"{where} `phases` must be a non-empty list of strings")
        phases = tuple(listed)
    return DetectorSpec(kind, key, value, phases)


def _boundary(raw) -> BoundarySpec:
    raw = _object(raw, "`downgrade_boundary`")
    posture = _text(_required(raw, "posture", "`downgrade_boundary`"), "`posture`")
    undetectable = _text(raw.get("undetectable"), "`undetectable`", optional=True)
    listed = raw.get("signals", [])
    if not isinstance(listed, list):
        raise _shape("`signals` must be a list")
    signals = []
    for index, item in enumerate(listed):
        where = f"signal {index}"
        item = _object(item, where)
        name = _text(_required(item, "name", where), f"{where} `name`")
        if _KEBAB.fullmatch(name) is None:
            raise _shape(f"{where} `name` {name!r} is not kebab-case")
        signals.append(SignalSpec(
            name, _text(_required(item, "label", where), f"{where} `label`"),
            _detector(_required(item, "detect", where), f"{where} `detect`")))
    return BoundarySpec(posture, undetectable, tuple(signals))


def _conformance(raw) -> Conformance:
    raw = _object(raw, "`conformance`")
    suites = _object(_required(raw, "suites", "`conformance`"), "`suites`")
    for name, count in suites.items():
        if type(count) is not int or count < 0:
            raise _shape(f"suite {name!r} needs a non-negative integer count")
    listed = _required(raw, "portability_exceptions", "`conformance`")
    if not isinstance(listed, list):
        raise _shape("`portability_exceptions` must be a list")
    found = []
    for index, item in enumerate(listed):
        where = f"portability exception {index}"
        item = _object(item, where)
        found.append(PortabilityException(
            suite=_text(_required(item, "suite", where), f"{where} `suite`"),
            test=_text(_required(item, "test", where), f"{where} `test`"),
            reason=_text(_required(item, "reason", where), f"{where} `reason`"),
            requires=_text(item.get("requires"), f"{where} `requires`", optional=True),
            defect=_text(item.get("defect"), f"{where} `defect`", optional=True)))
    return Conformance(dict(suites), tuple(found))


def parse_manager_block(raw) -> ManagerBlock:
    """Validate a `manager` block (docs/release-metadata.md); a wrong shape, an
    unknown detector kind, a `schema_version` other than 1 or a bad version
    string is `ReleaseIntegrityError(kind="manifest-shape")`."""
    raw = _object(raw, "block")
    schema = raw.get("schema_version")
    if type(schema) is not int:
        raise _shape("needs an integer `schema_version`")
    if schema != MANAGER_SCHEMA_VERSION:
        raise _shape(f"has schema_version {schema}, which needs a newer Manager than this one "
                     f"(it reads {MANAGER_SCHEMA_VERSION})")
    minimum = raw.get("min_manager_version")
    if minimum is not None:
        parse_version_tuple(minimum)
    new_work = raw.get("new_work_only")
    if new_work is not None:
        if not isinstance(new_work, list) or not all(isinstance(t, str) for t in new_work):
            raise _shape("`new_work_only` must be a list of strings")
        new_work = tuple(new_work)
    gate = _text(raw.get("gate_default_change"), "`gate_default_change`", optional=True)
    return ManagerBlock(
        min_manager_version=minimum,
        downgrade_boundary=_boundary(raw["downgrade_boundary"]) if "downgrade_boundary" in raw
        else None,
        new_work_only=new_work,
        gate_default_change=gate,
        conformance=_conformance(raw["conformance"]) if "conformance" in raw else None)


def parse_manifest_manager(manifest_bytes: bytes) -> ManagerBlock | None:
    """The block of a manifest held as bytes (a fetched manifest asset), or None."""
    try:
        manifest = json.loads(manifest_bytes)
    except ValueError as exc:
        raise ReleaseIntegrityError(f"manifest is not JSON: {exc}", kind="manifest-shape") from exc
    if not isinstance(manifest, dict):
        raise ReleaseIntegrityError("manifest is not an object", kind="manifest-shape")
    return parse_manager_block(manifest["manager"]) if "manager" in manifest else None


@dataclass(frozen=True)
class Artifact:
    """One payload, fixture, or release-template file, addressed by where it
    goes in a target."""

    target_path: str
    location: str
    sha256: str
    size: int
    executable: bool
    category: str


class Release:
    def __init__(self, root: Path):
        self.root = Path(root)
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"no manifest at {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text())
        self.version = self.manifest["workflow_version"]
        self.upstream = self.manifest["upstream"]
        # Additive: every extracted release predates this field and has none,
        # so it defaults to the only origin that existed before an authored
        # (overlay-built) release could exist (D-Authored-Release-2).
        self.provenance = self.manifest.get("provenance", {"origin": "upstream"})
        self._manager: ManagerBlock | None = None
        self._manager_read = False

    @property
    def manager(self) -> ManagerBlock | None:
        """The manifest's validated `manager` block, or None when it has none.
        Read lazily, so a release whose data is built into the Manager (which
        ignores the block) never fails on it; a bad block raises
        `ReleaseIntegrityError(kind="manifest-shape")` here."""
        if not self._manager_read:
            raw = self.manifest.get("manager")
            self._manager = parse_manager_block(raw) if "manager" in self.manifest else None
            self._manager_read = True
        return self._manager

    # -- artifacts ---------------------------------------------------------

    @property
    def artifacts(self) -> list[Artifact]:
        return [
            Artifact(
                target_path=record["target_path"],
                location=record["location"],
                sha256=record["sha256"],
                size=record["size"],
                executable=record["executable"],
                category=record["category"],
            )
            for record in self.manifest["artifacts"]
        ]

    def payload_artifacts(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        if profile not in INSTALL_PROFILES:
            raise ValueError(f"unknown install profile {profile!r}")
        wanted = _PROFILE_CATEGORIES[profile]
        return [a for a in self.artifacts if a.category in wanted]

    def fixture_artifacts(self) -> list[Artifact]:
        return [a for a in self.artifacts if a.category == "host-evidence"]

    def templates(self) -> list[dict]:
        return list(self.manifest["templates"])

    def release_template_artifacts(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        """Release-owned templates, in the same shape as payload artifacts.

        They are rendered by migration rather than copied byte-for-byte, but a
        target treats them identically: installed from the release, replaced on
        update, and compared against the release when checking for drift.
        """
        if profile not in INSTALL_PROFILES:
            raise ValueError(f"unknown install profile {profile!r}")
        wanted = _PROFILE_CATEGORIES[profile]
        found = []
        for record in self.manifest["templates"]:
            category = RELEASE_TEMPLATES.get(record["target_path"])
            if category is None or category not in wanted:
                continue
            found.append(Artifact(
                target_path=record["target_path"],
                location=record["location"],
                sha256=record["sha256"],
                size=record["size"],
                executable=False,
                category=category,
            ))
        return found

    def installable(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        """Everything a target installs *from the release* under `profile`.

        The single set `bootstrap`, `update` and `drift` all work from, so the
        three cannot disagree about what the release owns.
        """
        return self.payload_artifacts(profile) + self.release_template_artifacts(profile)

    def state_templates(self) -> list[dict]:
        """Templates that seed repository-local state, in `STATE_TEMPLATES` order."""
        by_path = {t["target_path"]: t for t in self.manifest["templates"]}
        return [by_path[rel] for rel in STATE_TEMPLATES]

    # -- content -----------------------------------------------------------

    def read(self, location: str) -> bytes:
        return (self.root / location).read_bytes()

    def read_verified(self, location: str, expected_sha256: str) -> bytes:
        """Release bytes, checked against the manifest before they are used.

        Installing is the moment the release's identity is asserted to a target
        repository. A release directory that was damaged, partially copied, or
        edited must not be able to pass itself off as the release it claims
        to be, so nothing is copied out of one without this check.
        """
        data = self.read(location)
        actual = sha256(data)
        if actual != expected_sha256:
            raise ReleaseIntegrityError(
                f"release {self.version} is damaged: {location} has digest {actual[:12]}, "
                f"its manifest records {expected_sha256[:12]}",
                kind="damaged",
            )
        return data

    def verify(self) -> list[str]:
        """Every manifest entry present on disk with the recorded digest.

        Returns the list of problems; empty means the release is intact.
        """
        problems = []
        recorded = {}
        for record in self.manifest["artifacts"] + self.manifest["templates"]:
            recorded[record["location"]] = record
            path = self.root / record["location"]
            if not path.exists():
                problems.append(f"missing: {record['location']}")
                continue
            data = path.read_bytes()
            if sha256(data) != record["sha256"]:
                problems.append(f"digest mismatch: {record['location']}")
            if record.get("executable") and not path.stat().st_mode & 0o111:
                problems.append(f"not executable: {record['location']}")
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if rel == "manifest.json" or rel in recorded:
                continue
            if "__pycache__" in path.parts:
                # An interpreter that imported a payload module left bytecode
                # here. It is a build artifact, not release content.
                continue
            problems.append(f"untracked file in release: {rel}")
        return problems


def _version_key(name: str) -> tuple:
    """Order versions numerically where they are numeric, textually where they
    are not, so `2.3.10` sorts after `2.3.9` and anything unexpected still has
    a defined place instead of raising."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"[.\-_]", name)
    )

