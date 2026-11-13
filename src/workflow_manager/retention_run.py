"""The confirmed retention cleanup run: archive, verify, remove.

`run` walks a plan's items in the preview's order and, per item, calls the target's
own `scripts/workflow_retention.py`: `archive ID --apply`, then the engine's own
verification (the dry run of `remove`, which writes nothing), then `remove ID
--apply`. It reimplements none of them: no tar, no zstd, no hashing, no deletion
here. The first failure of any step stops the run; the report says what was done
and what was not. Prune is never run: the argv is one of three closed forms and
carries no user text.

The caller (`cmd_retention_cleanup`) has already run the preflight and checked the
confirmation sentence; nothing here is reached before both hold.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import retention, retention_cleanup, retention_policy

CALL_TIMEOUT_SECONDS = 600
ARCHIVE, VERIFY, REMOVE = "archive", "verify", "remove"
POLICY = "policy"             # the per-item policy check, before any call
MESSAGE_LIMIT = 400          # characters of the engine's text echoed on one line

_REFUSAL = re.compile(r"^error: ([A-Za-z0-9_]+): (.*)$")
_NEXT_STEP = re.compile(r"^next step: (.*)$")
# The engine's own prefix when its undo of a failed archive could not remove all it made
# (`scripts/workflow_retention.py`, `_undo`): after it an archive may still exist.
UNDO_WARNING = "warning: the undo could not remove"
# What an archive-step stop leaves known about the archive (None: not known).
NOT_ARCHIVED, UNSETTLED, FOREIGN = "not-archived", "unsettled", "foreign"
ALREADY_ARCHIVED = "already_archived"


def argv_for(step: str, item_id: str, root: str) -> tuple[str, ...]:
    """The script's arguments for `step`: one of exactly three forms, each ending
    in `--repo-root ROOT`. `prune`, `--archive-root` and `--ttl-days` have no form."""
    if step == ARCHIVE:
        return ("archive", item_id, "--apply", "--json", "--repo-root", root)
    if step == VERIFY:
        return ("remove", item_id, "--json", "--repo-root", root)
    if step == REMOVE:
        return ("remove", item_id, "--apply", "--json", "--repo-root", root)
    raise ValueError(f"no such step: {step!r}")


@dataclass
class Result:
    """How the run ended. `exit_code`: 0 every item done; 1 stopped after its first
    per-item call (`archive --apply`, the verification or `remove --apply`) was
    attempted, even if its script could not be started; 2 refused, or stopped before
    that first call (nothing written). The preflight's `report` is not one."""
    exit_code: int
    done: int = 0
    total: int = 0
    started: bool = False
    error: str | None = None
    next_step: str | None = None
    calls: list = field(default_factory=list)   # (step, item id) in the order issued


def _clean(text: str) -> str:
    """Engine text on one printable line: control characters escaped, cut."""
    text = " ".join(text.split())
    text = "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)
    return text if len(text) <= MESSAGE_LIMIT else text[:MESSAGE_LIMIT] + "..."


def _engine_refusal(stderr: bytes) -> tuple[str, str] | None:
    lines = stderr.decode("utf-8", "replace").splitlines()
    cause = next((m.groups() for m in map(_REFUSAL.match, lines) if m), None)
    step = next((m.group(1) for m in map(_NEXT_STEP.match, lines) if m), None)
    if cause is None:
        return None
    return f"{cause[0]}: {cause[1]}", step or ""


def _undo_unsettled(stderr: bytes) -> bool:
    """Whether the engine said its undo could not remove everything it created."""
    return any(line.startswith(UNDO_WARNING)
               for line in stderr.decode("utf-8", "replace").splitlines())


def _expected(step: str, item_id: str, document) -> bool:
    """Whether the script's JSON is the success of `step` for `item_id`."""
    if not isinstance(document, dict) or document.get("work_item_id") != item_id:
        return False
    result = document.get("result")
    if step == ARCHIVE:
        return (document.get("kind") == "retention-archive" and isinstance(result, dict)
                and result.get("archived") is True)
    verify = document.get("verify")
    if step == VERIFY:
        return (document.get("kind") == "retention-remove" and document.get("mode") == "dry-run"
                and isinstance(verify, dict) and verify.get("matches") is True)
    return (document.get("kind") == "retention-remove" and document.get("mode") == "apply"
            and isinstance(result, dict) and result.get("removed") is True)


class _Stop(Exception):
    """A step failed: `line` is the item line, `known` whether the folder's place is
    known (False after a step-3 timeout, interrupt or unreadable output)."""

    def __init__(self, line: str, *, engine=None, known: bool = True, ran: bool = True,
                 unsettled: bool = False):
        super().__init__(line)
        self.line = line
        self.engine = engine          # (cause, next step) the engine printed, or None
        self.known = known
        self.ran = ran                # False: the script never started
        self.unsettled = unsettled    # the engine's undo warning was on stderr


def _call(root: str, step: str, item_id: str, calls: list):
    calls.append((step, item_id))
    try:
        code, out, err = retention.launch_script(
            Path(root), *argv_for(step, item_id, root), timeout=CALL_TIMEOUT_SECONDS)
    except retention.ScriptTimeout:
        raise _Stop(f"stopped at {step}: the script did not finish within "
                    f"{CALL_TIMEOUT_SECONDS} seconds", known=step != REMOVE) from None
    except OSError as error:
        raise _Stop(f"stopped at {step}: the script could not be started ({_clean(str(error))})",
                    known=True, ran=False) from None
    if code != 0:
        refusal = _engine_refusal(err) if code == 2 else None
        if refusal is not None:
            raise _Stop(f"stopped at {step} ({refusal[0].split(':', 1)[0]}): "
                        f"{_clean(refusal[0].split(': ', 1)[1])}", engine=refusal,
                        unsettled=_undo_unsettled(err))
        first = next(iter(err.decode("utf-8", "replace").splitlines()), "")
        raise _Stop(f"stopped at {step}: the script exited with status {code} "
                    f"({_clean(first) or 'no message'})", known=step != REMOVE)
    try:
        document = json.loads(out.decode("utf-8"))
    except (ValueError, RecursionError):
        raise _Stop(f"stopped at {step}: the script's output is not one JSON object",
                    known=step != REMOVE) from None
    if not _expected(step, item_id, document):
        raise _Stop(f"stopped at {step}: the script's output is not the expected "
                    f"{'success' if step != VERIFY else 'verification'} for {item_id}",
                    known=step != REMOVE)


def _mib(count: int) -> int:
    return count // 2**20


def _closing(step: str, known: bool, item, total: int, done: int,
             archive_state: str | None = None) -> str:
    """`archive_state`, for a stop at the archive step: `NOT_ARCHIVED` (a parsed engine
    refusal without the undo warning, or the script never started), `UNSETTLED` (a
    refusal with the undo warning: an archive may remain), `FOREIGN` (`already_archived`:
    one exists that this run did not create); None: not known."""
    item_id = item.work_item_id
    head = f"retention cleanup: stopped after {done} of {total} items; "
    if step == ARCHIVE:
        if archive_state == FOREIGN:
            fact = f"this run did not create an archive for {item_id} (one already exists)"
        elif archive_state == UNSETTLED:
            fact = (f"{item_id} may or may not be archived (the engine's undo could not "
                    "remove everything it created; the next preview shows which)")
        elif archive_state == NOT_ARCHIVED:
            fact = f"{item_id} was not archived"
        else:
            fact = (f"{item_id} may or may not be archived (the next preview shows which)")
        return (head + f"{fact} and its folder is untouched (a "
                f"`.{item_id}.partial` may remain in the archive store if the script was "
                "stopped); nothing was committed or needs committing")
    if step == VERIFY:
        return (head + f"{item_id}'s folder is untouched; nothing was "
                "committed or needs committing")
    if known:
        return (head + f"{item_id} was archived and verified; where its folder is: see the "
                "engine's message; nothing was committed or needs committing")
    return (head + f"{item_id} was archived and verified, but its folder's state is unknown "
            "and may be partly removed: finish it with the user-only `python3 -I "
            f"scripts/workflow_retention.py remove {item_id} --apply` in the repository; "
            "nothing was committed or needs committing")


def run(target: Path, plan, emit=None) -> Result:
    """Run `plan` item by item. `emit(line)` prints a line as it happens (default:
    stdout, flushed), so a killed Manager leaves a record. Returns the `Result`."""
    if emit is None:
        def emit(line: str) -> None:
            print(line, flush=True)
    root = str(Path(target).resolve())
    items = list(plan.items)
    total = len(items)
    short = lambda digest: digest[:retention_policy.DIGEST_SHOWN]  # noqa: E731
    result = Result(exit_code=0, total=total)
    digest = short(retention_cleanup.plan_digest(plan))
    emit(f"retention cleanup: running plan {digest} (mode {plan.mode}, policy "
         f"{short(plan.policy_digest)}), {total} items")
    for index, item in enumerate(items):
        number = index + 1
        step = POLICY           # until the first call: nothing has touched this item
        try:
            try:
                state = retention_policy.load(Path(target))
                unchanged = (state.state == retention_policy.ADOPTED
                             and state.digest == plan.policy_digest)
            except Exception:  # noqa: BLE001 -- an unreadable policy is a changed policy
                unchanged = False
            if not unchanged:
                raise _Stop("stopped before any call for this item: the policy changed")
            done_steps = []
            if item.action != retention_cleanup.REMOVE_ONLY:
                step = ARCHIVE
                _call(root, ARCHIVE, item.work_item_id, result.calls)
                done_steps.append(f"archived {_mib(item.bytes)} MiB")
            step = VERIFY
            _call(root, VERIFY, item.work_item_id, result.calls)
            done_steps.append("remove only, verified" if item.action == retention_cleanup.REMOVE_ONLY
                              else "verified")
            step = REMOVE
            _call(root, REMOVE, item.work_item_id, result.calls)
            done_steps.append("removed")
            emit(f"  {number}. {item.work_item_id}: {', '.join(done_steps)}")
            result.done += 1
        except (_Stop, KeyboardInterrupt) as stop:
            interrupted = isinstance(stop, KeyboardInterrupt)
            archive_state = None
            if not interrupted:
                if stop.engine is not None:
                    if stop.engine[0].split(":", 1)[0] == ALREADY_ARCHIVED:
                        archive_state = FOREIGN
                    else:
                        archive_state = UNSETTLED if stop.unsettled else NOT_ARCHIVED
                elif not stop.ran:
                    archive_state = NOT_ARCHIVED
            if interrupted:
                known = step != REMOVE
                line = ("stopped before any call for this item: interrupted" if step == POLICY
                        else f"stopped at {step}: interrupted")
                emit(f"  {number}. {item.work_item_id}: {line}")
            else:
                known, line = stop.known, stop.line
                emit(f"  {number}. {item.work_item_id}: {line}")
                if stop.engine is not None and stop.engine[1]:
                    emit(f"     next step (the engine's): {_clean(stop.engine[1])}")
            for later, rest in enumerate(items[index + 1:], number + 1):
                emit(f"  {later}. {rest.work_item_id}: not attempted")
            if step == POLICY:
                if interrupted:
                    result.error = f"retention cleanup: {item.work_item_id}: {line}"
                    result.next_step = (f"run {retention.PROGRAM} retention-cleanup again to "
                                        "see the current plan")
                else:
                    result.error = "retention cleanup: the policy changed during the run"
                    result.next_step = (f"check the policy with {retention.PROGRAM} "
                                        "adopt-retention-policy and run the preview again")
                emit(f"retention cleanup: stopped after {result.done} of {total} items; "
                     f"{item.work_item_id} was not touched; nothing was committed or needs "
                     "committing")
            else:
                emit(_closing(step, known, item, total, result.done, archive_state))
                result.error = f"retention cleanup: {item.work_item_id}: {line}"
                engine = getattr(stop, "engine", None)
                engine_step = engine[1] if engine is not None else ""
                result.next_step = (_clean(engine_step) if engine_step else
                                    "read the report above, fix what it names, then run "
                                    f"{retention.PROGRAM} retention-cleanup again to see the "
                                    "current plan")
            result.started = bool(result.calls)
            result.exit_code = 1 if result.started else 2
            return result
    emit(f"retention cleanup: done, {result.done} of {total} items archived and removed; "
         "Git is unchanged (the review folders were untracked); prune was not run")
    return result
