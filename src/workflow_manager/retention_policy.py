"""The retention policy file, its strict loader and its adoption record.

A managed repository's owner writes `.workflow-manager/retention-policy.json`
and adopts it with `workflow-manager adopt-retention-policy`, which writes
`.workflow-manager/retention-adoption.json`. The file is only a proposal: the
mode in force is `off` unless the file is valid and the record is valid and
names the file's exact digest. Every failure falls back to `off`.

This module reads and (for the adoption only) writes those two files. It never
raises from `load`, never runs the retention script, and sends and cleans
nothing: a later release evaluates the thresholds.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .retention import _shown

PROGRAM = "workflow-manager"
DIRECTORY = ".workflow-manager"
POLICY_FILE = "retention-policy.json"
RECORD_FILE = "retention-adoption.json"
POLICY_LIMIT = 4096  # bytes; the figure retention.PATH_LIMIT uses
RECORD_LIMIT = 16384
SCHEMA_VERSION = 1
MODES = ("off", "notify", "cleanup", "both")
THRESHOLDS = {  # key: (maximum, label)
    "finished_items": (100000, "finished items"),
    "finished_folder_mib": (1048576, "finished folders"),
    "archives": (100000, "archives"),
    "prunable_archives": (100000, "prunable archives"),
}
_UNITS = {"finished_folder_mib": " MiB"}
PROBLEM_LIMIT = 5
DIGEST_SHOWN = 12

ABSENT = "absent"
FILE_MISSING = "file-missing"
INVALID = "invalid"
NOT_ADOPTED = "not-adopted"
RECORD_INVALID = "record-invalid"
CHANGED = "changed"
ADOPTED = "adopted"

_RECORD_KEYS = ("schema_version", "sha256", "adopted_at", "confirmation", "policy")
_SENTENCE = re.compile(r"adopt the retention policy ([0-9a-f]{%d})\." % DIGEST_SHOWN)
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class PolicyState:
    """What `load` found. `mode` is the mode in force; `policy` and `digest` are
    the file's when it is valid, whatever the record says."""
    state: str
    mode: str = "off"
    problems: tuple = ()
    policy: dict | None = None
    digest: str | None = None
    adopted_at: str | None = None


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------

class _Refused(ValueError):
    pass


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Refused(f"duplicate key {_shown(key)}")
        result[key] = value
    return result


def _no_constant(name):
    raise _Refused(f"the constant {name} is not allowed")


def _has_surrogate(value) -> bool:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return True
        return False
    if isinstance(value, dict):
        return any(_has_surrogate(k) or _has_surrogate(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_surrogate(v) for v in value)
    return False


def _parse(data: bytes):
    """`(value, None)` or `(None, problem)`: strict JSON from bytes."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "the file is not UTF-8 text"
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except _Refused as error:
        return None, f"the file is not accepted: {error}"
    except RecursionError:
        return None, "the file is nested too deeply"
    except ValueError as error:
        return None, f"the file is not valid JSON: {error}"
    if _has_surrogate(value):
        return None, "the file holds a lone surrogate"
    return value, None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def policy_errors(policy) -> list[str]:
    """Every way `policy` breaks the schema (an empty list: it is valid)."""
    if not isinstance(policy, dict):
        return [f"the policy is not an object: {_shown(policy)}"]
    errors = []
    for key in policy:
        if key not in ("schema_version", "mode", "thresholds"):
            errors.append(f"unknown key {_shown(key)}")
    if "schema_version" not in policy:
        errors.append("schema_version is missing")
    elif not _is_int(policy["schema_version"]) or policy["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be the integer {SCHEMA_VERSION}, "
                      f"not {_shown(policy['schema_version'])}")
    mode = policy.get("mode")
    if "mode" not in policy:
        errors.append("mode is missing")
    elif not isinstance(mode, str) or mode not in MODES:
        errors.append(f"mode must be one of {', '.join(MODES)}, not {_shown(mode)}")
    thresholds = policy.get("thresholds", {})
    count = 0
    if not isinstance(thresholds, dict):
        errors.append(f"thresholds must be an object, not {_shown(thresholds)}")
    else:
        for key, value in thresholds.items():
            if key not in THRESHOLDS:
                errors.append(f"unknown threshold {_shown(key)}")
            elif not _is_int(value):
                errors.append(f"thresholds.{key} must be an integer, not {_shown(value)}")
            elif not 1 <= value <= THRESHOLDS[key][0]:
                errors.append(f"thresholds.{key} must be from 1 to {THRESHOLDS[key][0]}, "
                              f"not {_shown(value)}")
            else:
                count += 1
    if isinstance(mode, str) and mode in MODES and mode != "off" and count == 0 \
            and isinstance(thresholds, dict):
        errors.append(f"mode {mode} needs at least one valid threshold")
    return errors


def canonical(policy: dict) -> bytes:
    return json.dumps(policy, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest_of(policy: dict) -> str:
    return hashlib.sha256(canonical(policy)).hexdigest()


# ---------------------------------------------------------------------------
# The confirmation sentence
# ---------------------------------------------------------------------------

def sentence(digest: str) -> str:
    return f"Adopt the retention policy {digest[:DIGEST_SHOWN]}."


def confirmation_holds(text, digest: str) -> bool:
    """Whether `text` names `digest`: after whitespace collapse and ignoring
    case, every match of the sentence carries the digest's first 12 characters,
    and there is at least one."""
    if not isinstance(text, str):
        return False
    found = _SENTENCE.findall(" ".join(text.split()).lower())
    return bool(found) and all(prefix == digest[:DIGEST_SHOWN] for prefix in found)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def serialize_record(record: dict) -> bytes:
    return (json.dumps(record, indent=2) + "\n").encode("utf-8")


def check_record(record) -> list[str]:
    """The problems of an adoption record (an empty list: the loader accepts it).
    The loader runs it on what it reads and the adoption command on what it has
    built, so a record the loader would refuse is never written."""
    if not isinstance(record, dict):
        return [f"the record is not an object: {_shown(record)}"]
    problems = []
    if _has_surrogate(record):
        return ["the record holds a lone surrogate"]
    for key in record:
        if key not in _RECORD_KEYS:
            problems.append(f"unknown record key {_shown(key)}")
    for key in _RECORD_KEYS:
        if key not in record:
            problems.append(f"record key {key} is missing")
    if problems:
        return problems
    if not _is_int(record["schema_version"]) or record["schema_version"] != SCHEMA_VERSION:
        problems.append(f"record schema_version must be the integer {SCHEMA_VERSION}")
    if not isinstance(record["adopted_at"], str) or not _TIMESTAMP.match(record["adopted_at"]):
        problems.append(f"record adopted_at is not a UTC timestamp: {_shown(record['adopted_at'])}")
    inner = policy_errors(record["policy"])
    if inner:
        problems.extend(f"record policy: {problem}" for problem in inner)
        return problems
    digest = digest_of(record["policy"])
    if record["sha256"] != digest:
        problems.append("record sha256 is not the digest of its policy")
    if not confirmation_holds(record["confirmation"], digest):
        problems.append("record confirmation does not name its policy")
    if not problems and len(serialize_record(record)) > RECORD_LIMIT:
        problems.append(f"the record is larger than {RECORD_LIMIT} bytes")
    return problems


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def directory(target: Path) -> Path:
    return Path(target) / DIRECTORY


def policy_path(target: Path) -> Path:
    return directory(target) / POLICY_FILE


def record_path(target: Path) -> Path:
    return directory(target) / RECORD_FILE


def _read(path: Path, limit: int):
    """`(bytes, None)`, `(None, None)` when nothing is there, or `(None, problem)`.
    The file is opened without following a link, must be a regular file, and is
    refused unparsed when larger than `limit`."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None, None
    except NotADirectoryError:
        return None, None
    except OSError as error:
        if os.path.islink(path):
            return None, f"{path.name} is a link"
        return None, f"{path.name} cannot be opened: {error.strerror or error}"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, f"{path.name} is not a regular file"
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
        if len(data) > limit:
            return None, f"{path.name} is larger than {limit} bytes"
        return data, None
    except OSError as error:
        return None, f"{path.name} cannot be read: {error.strerror or error}"
    finally:
        os.close(fd)


def load(target: Path) -> PolicyState:
    """The policy's state and the mode in force. Never raises, never writes."""
    try:
        return _load(Path(target))
    except Exception as error:  # one boundary: no file may crash a report
        return PolicyState(INVALID, problems=(f"the policy could not be read: {type(error).__name__}",))


def _load(target: Path) -> PolicyState:
    if directory(target).is_symlink():
        return PolicyState(INVALID, problems=(f"{DIRECTORY} is a link",))
    data, problem = _read(policy_path(target), POLICY_LIMIT)
    record_there = os.path.lexists(record_path(target))
    if problem is not None:
        return PolicyState(INVALID, problems=(problem,))
    if data is None:
        return PolicyState(FILE_MISSING if record_there else ABSENT)
    policy, problem = _parse(data)
    problems = [problem] if problem else policy_errors(policy)
    if problems:
        return PolicyState(INVALID, problems=tuple(problems))
    digest = digest_of(policy)
    shown = dict(policy=policy, digest=digest)
    if not record_there:
        return PolicyState(NOT_ADOPTED, **shown)
    raw, problem = _read(record_path(target), RECORD_LIMIT)
    if problem is not None or raw is None:
        return PolicyState(RECORD_INVALID, problems=(problem or f"{RECORD_FILE} is missing",), **shown)
    record, problem = _parse(raw)
    problems = [problem] if problem else check_record(record)
    if problems:
        return PolicyState(RECORD_INVALID, problems=tuple(problems), **shown)
    if record["sha256"] != digest:
        return PolicyState(CHANGED, adopted_at=record["adopted_at"], **shown)
    return PolicyState(ADOPTED, mode=policy["mode"], adopted_at=record["adopted_at"], **shown)


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------

class Refusal(Exception):
    """A refusal to adopt: `cause` and the one `step` to take. Nothing was written."""

    def __init__(self, cause: str, step: str):
        super().__init__(cause)
        self.cause = cause
        self.step = step


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def adopt_command(target: Path) -> str:
    return f"{PROGRAM} adopt-retention-policy {shlex.quote(str(target))}"


def describe(policy: dict) -> str:
    thresholds = policy.get("thresholds", {})
    parts = [f"{THRESHOLDS[key][1]} {thresholds[key]}{_UNITS.get(key, '')}"
             for key in THRESHOLDS if key in thresholds]
    return ", ".join(parts) if parts else "none"


def _write_atomically(path: Path, data: bytes) -> None:
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def usable_policy(target: Path) -> PolicyState:
    """The loaded state, or a `Refusal` when there is no valid file to adopt."""
    state = load(target)
    if state.policy is not None:
        return state
    if state.problems:
        cause = f"the retention policy file is refused: {'; '.join(state.problems[:PROBLEM_LIMIT])}"
        step = f"fix {DIRECTORY}/{POLICY_FILE} as named, then run the command again"
    else:
        cause = f"there is no retention policy file at {DIRECTORY}/{POLICY_FILE}"
        step = f"write {DIRECTORY}/{POLICY_FILE}, then run the command again"
    raise Refusal(cause, step)


def apply(target: Path, state: PolicyState, confirmation: str) -> dict:
    """Write the adoption record for the file `state` holds, when `confirmation`
    names its digest. Raises `Refusal` before writing anything."""
    again = adopt_command(target)
    if directory(target).is_symlink():
        raise Refusal(f"{DIRECTORY} is a link", f"replace {DIRECTORY} with a directory")
    existing = record_path(target)
    try:
        mode = os.lstat(existing).st_mode
    except FileNotFoundError:
        mode = None
    if mode is not None and not stat.S_ISREG(mode):
        raise Refusal(f"{DIRECTORY}/{RECORD_FILE} exists and is not a regular file",
                      f"remove {DIRECTORY}/{RECORD_FILE}, then run {again} again")
    if not confirmation_holds(confirmation, state.digest):
        raise Refusal("--confirm does not contain the sentence for this policy's digest",
                      f"run {again} to see the digest and the sentence, then run it again "
                      "with --confirm")
    record = {"schema_version": SCHEMA_VERSION, "sha256": state.digest, "adopted_at": _now(),
              "confirmation": confirmation, "policy": state.policy}
    problems = check_record(record)
    if problems:
        raise Refusal(f"the adoption record would be refused: {problems[0]}",
                      "give --confirm as the one sentence only")
    _write_atomically(existing, serialize_record(record))
    return record


# ---------------------------------------------------------------------------
# The block of `status --retention` and `doctor --retention`
# ---------------------------------------------------------------------------

_WORDS = {
    FILE_MISSING: "the adoption record has no policy file",
    INVALID: "the policy file is refused",
    NOT_ADOPTED: "the policy file is valid and not adopted",
    RECORD_INVALID: "the adoption record is refused",
    CHANGED: "the policy file changed since it was adopted",
}


def block(state: PolicyState, target: Path) -> list[str]:
    """The lines printed before the retention report; none when there is neither
    a file nor a record. No `next:` line is unindented, so `status` keeps its one."""
    if state.state == ABSENT:
        return []
    if state.state == ADOPTED:
        return [
            f"retention policy: adopted, mode {state.mode} (digest {state.digest[:DIGEST_SHOWN]}, "
            f"adopted {state.adopted_at})",
            f"  thresholds: {describe(state.policy)}",
            "  this Manager release only reads the policy: it sends nothing and cleans nothing",
        ]
    lines = [f"retention policy: {state.state} ({_WORDS[state.state]}); mode off is in force"]
    lines.extend(f"  problem: {problem}" for problem in state.problems[:PROBLEM_LIMIT])
    if len(state.problems) > PROBLEM_LIMIT:
        lines.append(f"  and {len(state.problems) - PROBLEM_LIMIT} more")
    if state.state in (NOT_ADOPTED, CHANGED, RECORD_INVALID):
        step = adopt_command(target)
    elif state.state == INVALID:
        step = f"fix {DIRECTORY}/{POLICY_FILE} as named, then run the command again"
    else:
        step = (f"restore {DIRECTORY}/{POLICY_FILE}, or remove {DIRECTORY}/{RECORD_FILE} "
                "if the policy is withdrawn")
    lines.append(f"  next: {step}")
    return lines
