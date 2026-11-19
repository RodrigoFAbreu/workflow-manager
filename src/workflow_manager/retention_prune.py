"""The unattended retention prune: which archives to delete, and the two argv forms.

`select` is a pure function of a retention report and the adopted `unattended`
object: it starts no process and reads no file. It proposes the archives the policy
has aged out, under the bounds the owner set; the engine's own dry run must then
agree (the prune phase, a later step), and only then is anything deleted.

An archive is selected only when it is of class `finished`, strictly older than
`unattended.ttl_days` (by `age_days`, never by the report's own `prunable` flag,
which the engine computed with its default ttl), its item's review folder is
already gone (the engine does not look at it, and deleting the archive of an item
whose folder remains would leave the item unarchivable for good), the id is not
under an interrupted removal and the id is one the engine accepts. The oldest come
first and `unattended.prune_max_per_run` cuts the list.

`run_phase` is the phase itself: policy re-read before every engine call, a fresh
report, the selection, the `started` audit line, the engine's own dry run (which must
list exactly the planned ids), then one `--apply` per id. The first failure stops it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import retention, retention_alert, retention_run

PRUNE, APPLY = "prune", "apply"
FINISHED = "finished"
# Why an old, finished archive is left alone (the `skipped` reasons).
FOLDER_PRESENT = "review-folder-present"
REMOVAL_INTERRUPTED = "removal-interrupted"
UNACCEPTABLE_ID = "unacceptable-id"
AGE_NOT_KNOWN = "age-not-known"


@dataclass(frozen=True)
class Entry:
    work_item_id: str
    age_days: int
    modified: str


@dataclass(frozen=True)
class PrunePlan:
    repository: str
    policy_digest: str
    ttl_days: int
    cap: int
    entries: tuple          # Entry, oldest first, at most `cap`
    skipped: tuple = ()     # (id as shown, reason): old and finished, but left alone
    capped: int = 0         # selectable archives beyond the cap, not in `entries`

    @property
    def ids(self) -> tuple:
        return tuple(entry.work_item_id for entry in self.entries)


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _folder_present(report: dict, item_id: str) -> bool:
    """Whether the item's review folder may still exist. Fails closed: no matching
    `finished[]` entry, or one whose `review_folder.present` is not exactly false,
    counts as present."""
    found = False
    for entry in report.get("finished") or ():
        if isinstance(entry, dict) and entry.get("work_item_id") == item_id:
            found = True
            folder = entry.get("review_folder")
            if not isinstance(folder, dict) or folder.get("present") is not False:
                return True
    return not found


def _shown(value) -> str:
    return value if isinstance(value, str) else "?"


def select(report: dict, unattended: dict, *, policy_digest: str = "") -> PrunePlan:
    """The archives to prune, from a fresh `report` and the adopted `unattended`
    object (its `ttl_days` and `prune_max_per_run`)."""
    ttl, cap = unattended["ttl_days"], unattended["prune_max_per_run"]
    removing = report.get("removing") or ()
    chosen, skipped, seen = [], [], set()
    for archive in report.get("archives") or ():
        if not isinstance(archive, dict) or archive.get("item") != FINISHED:
            continue
        age, item_id = archive.get("age_days"), archive.get("work_item_id")
        if not _integer(age) or age <= ttl:
            continue
        if isinstance(item_id, str):
            if item_id in seen:
                continue
            seen.add(item_id)
        reason = None
        if not isinstance(item_id, str) or not retention_alert.plannable_id(item_id):
            reason = UNACCEPTABLE_ID
        elif not isinstance(archive.get("modified"), str):
            reason = AGE_NOT_KNOWN
        elif item_id in removing:
            reason = REMOVAL_INTERRUPTED
        elif _folder_present(report, item_id):
            reason = FOLDER_PRESENT
        if reason:
            skipped.append((_shown(item_id), reason))
        else:
            chosen.append(Entry(item_id, age, archive["modified"]))
    chosen.sort(key=lambda entry: (entry.modified, entry.work_item_id))
    return PrunePlan(repository=report.get("repository", ""), policy_digest=policy_digest,
                     ttl_days=ttl, cap=cap, entries=tuple(chosen[:cap]),
                     skipped=tuple(skipped), capped=max(len(chosen) - cap, 0))


def prune_digest(plan: PrunePlan) -> str:
    """The full sha256 of the plan: the repository, the policy digest, the ttl and
    the ids in order."""
    body = {"repository": plan.repository, "policy": plan.policy_digest,
            "ttl_days": plan.ttl_days, "ids": list(plan.ids)}
    data = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def argv_for(form: str, ids, ttl_days: int, root: str) -> tuple[str, ...]:
    """The script's arguments: the dry run (`PRUNE`, every planned id) or one apply
    (`APPLY`, exactly one id), each ending `--repo-root ROOT` and carrying the ttl.
    `--archive-root` has no form."""
    ids = tuple(ids)
    if not _integer(ttl_days):
        raise ValueError(f"the ttl is not an integer: {ttl_days!r}")
    if not ids or not all(isinstance(i, str) and retention_alert.plannable_id(i) for i in ids):
        raise ValueError(f"no such ids: {ids!r}")
    tail = ("--json", "--ttl-days", str(ttl_days), "--repo-root", root)
    if form == PRUNE:
        return ("prune", *ids, *tail)
    if form == APPLY:
        if len(ids) != 1:
            raise ValueError("an apply carries exactly one id")
        return ("prune", ids[0], "--apply", *tail)
    raise ValueError(f"no such form: {form!r}")


# ---------------------------------------------------------------------------
# The phase
# ---------------------------------------------------------------------------

CALL_TIMEOUT_SECONDS = retention_run.CALL_TIMEOUT_SECONDS
NOTHING_TO_PRUNE, DONE, STOPPED = "nothing-to-prune", "done", "stopped"
REPORT, DRY_RUN = "report", "dry-run"
KIND, MODE_DRY, MODE_APPLY = "retention-prune", "dry-run", "apply"


@dataclass
class PruneResult:
    """How the phase ended. `outcome`: `NOTHING_TO_PRUNE`, `DONE` or `STOPPED`.
    `results` has one entry per planned id (`id`, `result` `done`, `stopped` or
    `not-attempted`, `engine_code`, `error`). `stop`: step, item_id, engine_code, error.
    `apply_attempted`: whether any `--apply` call was issued."""
    outcome: str
    plan: PrunePlan | None = None
    digest: str | None = None
    results: list = field(default_factory=list)
    stop: dict | None = None
    error: str | None = None
    next_step: str | None = None
    apply_attempted: bool = False
    audit_error: str | None = None
    calls: list = field(default_factory=list)     # (form, ids) in the order issued

    @property
    def done(self) -> int:
        return sum(1 for entry in self.results if entry["result"] == "done")


def prune_still_allowed(state) -> bool:
    """The extra predicate of the policy re-read: `unattended.prune` is still true."""
    return state.unattended is not None and state.unattended.get("prune") is True


class _Halt(Exception):
    def __init__(self, text, *, engine_code=None, result="refused", next_step=None):
        super().__init__(text)
        self.text, self.engine_code, self.result = text, engine_code, result
        self.next_step = next_step


def _difference(document, plan: PrunePlan, form: str, item_id=None) -> str | None:
    """What differs between the engine's document and what was asked, or None. The
    dry run must list exactly the planned ids (a set comparison: the engine sorts
    them) and nothing removed; an apply must remove exactly its id."""
    if not isinstance(document, dict):
        return "the engine's output is not one JSON object"
    if document.get("kind") != KIND:
        return f"the engine's output has kind {retention.shown(document.get('kind'))}, not {KIND}"
    want = MODE_APPLY if form == APPLY else MODE_DRY
    if document.get("mode") != want:
        return f"the engine's output has mode {retention.shown(document.get('mode'))}, not {want}"
    ttl = document.get("ttl_days")
    if not _integer(ttl) or ttl != plan.ttl_days:
        return f"the engine's ttl_days is {retention.shown(ttl)}, not {plan.ttl_days}"
    result = document.get("result")
    removed = result.get("removed") if isinstance(result, dict) else None
    if form == APPLY:
        if removed != [item_id]:
            return f"the engine removed {retention.shown(removed)}, not exactly [{item_id}]"
        return None
    if removed != []:
        return f"the engine's dry run reports removed {retention.shown(removed)}, not []"
    archives = document.get("archives")
    if not isinstance(archives, list):
        return "the engine's dry run lists no archives"
    listed = []
    for entry in archives:
        if not isinstance(entry, dict) or not isinstance(entry.get("work_item_id"), str):
            return "the engine's dry run lists an entry without a work item id"
        if entry.get("item") != FINISHED:
            return (f"the engine's dry run lists {entry['work_item_id']} as "
                    f"{retention.shown(entry.get('item'))}, not {FINISHED}")
        listed.append(entry["work_item_id"])
    if len(set(listed)) != len(listed):
        return "the engine's dry run lists an id twice"
    planned = set(plan.ids)
    if set(listed) != planned:
        missing, extra = sorted(planned - set(listed)), sorted(set(listed) - planned)
        parts = ([f"it did not list {', '.join(missing)}"] if missing else []) + \
                ([f"it also listed {', '.join(extra)}"] if extra else [])
        return "the engine's dry run differs from the plan: " + "; ".join(parts)
    return None


def _engine(root: str, plan: PrunePlan, form: str, ids, calls: list, item_id=None):
    """One engine call; returns its parsed document or raises `_Halt`."""
    calls.append((form, tuple(ids)))
    what = "dry run" if form == PRUNE else f"apply for {item_id}"
    result = "refused" if form == PRUNE else "failed"
    try:
        code, out, err = retention.launch_script(
            Path(root), *argv_for(form, ids, plan.ttl_days, root), timeout=CALL_TIMEOUT_SECONDS)
    except retention.ScriptTimeout:
        raise _Halt(f"the {what} did not finish within {CALL_TIMEOUT_SECONDS} seconds",
                    result=result) from None
    except OSError as error:
        raise _Halt(f"the {what} could not be started ({retention_run._clean(str(error))})",
                    result=result) from None
    if code != 0:
        refusal = retention_run._engine_refusal(err) if code == 2 else None
        if refusal is not None:
            raise _Halt(f"the engine refused the {what} "
                        f"({refusal[0].split(':', 1)[0]}): "
                        f"{retention_run._clean(refusal[0].split(': ', 1)[1])}",
                        engine_code=refusal[0].split(":", 1)[0], result=result,
                        next_step=retention_run._clean(refusal[1]) if refusal[1] else None)
        first = next(iter(err.decode("utf-8", "replace").splitlines()), "")
        raise _Halt(f"the {what} exited with status {code} "
                    f"({retention_run._clean(first) or 'no message'})", result=result)
    try:
        document = json.loads(out.decode("utf-8"))
    except (ValueError, RecursionError):
        raise _Halt(f"the {what}'s output is not one JSON object", result=result) from None
    differs = _difference(document, plan, APPLY if form == APPLY else PRUNE, item_id)
    if differs is not None:
        raise _Halt(differs, result=result)
    return document


def run_phase(target, unattended: dict, policy_digest: str, emit=None, *, observer=None,
              audit_where: str = "") -> PruneResult:
    """The prune phase of an unattended run. `unattended` is the adopted object (its
    `ttl_days` and `prune_max_per_run`) and `policy_digest` the digest the run started
    under. `observer(step, item_id, result, engine_code, text, plan_digest)` writes one
    audit line; it raises when the line cannot be written. Never raises for a failure
    of the engine, the policy or the audit file: those are the `stop` of the result."""
    if emit is None:
        def emit(line: str) -> None:
            print(line, flush=True)
    root = str(Path(target).resolve())
    result = PruneResult(NOTHING_TO_PRUNE)
    digest = None

    def note(step, item_id, outcome, engine_code=None, text=None, *, first=False):
        """Write one line. A failure is recorded on the result; with `first` (the
        `started` line) it is the caller's to act on, so it is re-raised."""
        if observer is None:
            return
        try:
            observer(step, item_id, outcome, engine_code, text, digest)
        except Exception as audit:  # noqa: BLE001 -- any observer failure
            if first:
                raise
            result.audit_error = getattr(audit, "cause", None) or str(audit)
            emit(f"retention prune: the audit line for this stop could not be written "
                 f"({result.audit_error}); the audit file is {audit_where}")

    def stop(step, item_id, text, engine_code=None, next_step=None):
        result.outcome = STOPPED
        result.error = f"retention prune: {text}"
        result.next_step = next_step or ("read the report above, fix what it names, then run "
                                         f"{retention.PROGRAM} retention-cleanup --unattended "
                                         "again")
        result.stop = {"step": step, "item_id": item_id, "engine_code": engine_code,
                       "error": result.error}
        for entry in result.results:
            if entry["result"] == "not-attempted" and entry["id"] == item_id:
                entry.update(result="stopped", engine_code=engine_code, error=result.error)
        emit(f"retention prune: stopped after {result.done} of {len(result.results)} "
             f"archives; {text}")
        return result

    def policy_changed(item_id):
        note("policy", item_id, "stopped", None,
             "retention prune: the policy changed during the run")
        return stop("policy", item_id, "the policy changed during the run (or no longer "
                    "allows prune); nothing further was called",
                    next_step="check the policy with "
                              f"{retention.PROGRAM} adopt-retention-policy and run the preview "
                              "again")

    def holds() -> bool:
        return retention_run.policy_holds(target, policy_digest, unattended=True,
                                          extra=prune_still_allowed)

    interrupted_line = "interrupted"

    def policy_interrupted(item_id):
        note("policy", item_id, "interrupted", None, interrupted_line)
        return stop("policy", item_id, interrupted_line)

    # 1. policy, then the fresh report
    try:
        still = holds()
    except KeyboardInterrupt:
        return policy_interrupted(None)
    if not still:
        return policy_changed(None)
    try:
        outcome = retention.fetch(Path(target))
    except KeyboardInterrupt:
        note("prune", None, "interrupted", None, interrupted_line)
        return stop("prune", None, interrupted_line)
    if outcome.report is None:
        cause = outcome.refusal.cause
        note("prune", None, "refused", None, cause)
        return stop("prune", None, f"the fresh report is not available ({cause})",
                    next_step=outcome.refusal.step)
    report = outcome.report
    if retention_alert.incomplete(report):
        note("prune", None, "refused", None, "the fresh report is incomplete")
        return stop("prune", None, "the fresh report is incomplete",
                    next_step=retention.STEP_INCOMPLETE)
    # 2. the selection
    plan = select(report, unattended, policy_digest=policy_digest)
    result.plan = plan
    if not plan.entries:
        return result
    digest = result.digest = prune_digest(plan)
    result.results = [{"id": item_id, "result": "not-attempted", "engine_code": None,
                       "error": None} for item_id in plan.ids]
    try:
        note("prune", None, "started", first=True)
    except Exception as failed:  # noqa: BLE001
        result.audit_error = getattr(failed, "cause", None) or str(failed)
        result.next_step = getattr(failed, "step", None) or (
            f"inspect {audit_where or 'the audit file'} and run again")
        stop("prune", None, f"the audit file cannot be written ({result.audit_error}); "
             "no prune call was made", next_step=result.next_step)
        return result
    # 3. policy, then the engine's own dry run
    try:
        still = holds()
    except KeyboardInterrupt:
        return policy_interrupted(None)
    if not still:
        return policy_changed(None)
    try:
        _engine(root, plan, PRUNE, plan.ids, result.calls)
    except _Halt as halt:
        note("prune", None, halt.result, halt.engine_code, halt.text)
        return stop("prune", None, halt.text, halt.engine_code, halt.next_step)
    except KeyboardInterrupt:
        note("prune", None, "interrupted", None, interrupted_line)
        return stop("prune", None, interrupted_line)
    # 4. one apply per id, oldest first
    for entry in result.results:
        item_id = entry["id"]
        try:
            still = holds()
        except KeyboardInterrupt:
            return policy_interrupted(item_id)
        if not still:
            return policy_changed(item_id)
        result.apply_attempted = True
        try:
            _engine(root, plan, APPLY, (item_id,), result.calls, item_id)
        except _Halt as halt:
            note("prune", item_id, "failed", halt.engine_code, halt.text)
            return stop("prune", item_id, f"{item_id}: {halt.text}", halt.engine_code,
                        halt.next_step)
        except KeyboardInterrupt:
            note("prune", item_id, "interrupted", None, interrupted_line)
            return stop("prune", item_id, f"{item_id}: {interrupted_line}")
        entry["result"] = "done"
        try:
            if observer is not None:
                observer("prune", item_id, "ok", None, None, digest)
        except Exception as audit:  # noqa: BLE001 -- the step succeeded, its line did not
            cause = getattr(audit, "cause", None) or str(audit)
            result.audit_error = cause
            emit(f"  {item_id}: pruned, but its audit line could not be written")
            stop("prune", item_id, f"the audit line for {item_id} could not be written "
                 f"({cause}); the apply had succeeded; no further call was made; the audit "
                 f"file is {audit_where}",
                 next_step=getattr(audit, "step", None) or
                 f"inspect {audit_where or 'the audit file'} and run again")
            return result
        emit(f"  {item_id}: pruned")
    result.outcome = DONE
    return result
