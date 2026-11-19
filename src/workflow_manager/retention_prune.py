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
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import retention_alert

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
