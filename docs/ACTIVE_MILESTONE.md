# Active Milestone

## Milestone

`update-dry-run-parity` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 2, implementation revision 1, base `da3c774`, branch `milestone/update-dry-run-parity`): roadmap row 46 (#158, points 1 to 5). The pull request title is `fix: make the update dry run match the real update for every record shape`, a patch release (Manager 1.20.1, checked with `tools/release/release.py check-title`).

`update --dry-run` predicts what the real `update` does for every record shape: a null record, a damaged record (`garbage`, `../escaped`), a valid record, and a release directory whose manifest has a null `workflow_version`. A refusal names a cause and one step. The dry run still writes nothing. The happy-path output is unchanged; the changed outputs are the rows of plan section 3.

Implementation: `0749457` (code and tests), `db6be10` (the pages and the record-shape notes), `b240bf5` (the bundle record). The implementation was approved by policy in `12fbd2f`. The automated gate ran green at `db6be10` (see the checklist).

The `docs/ROADMAP.md` row 46 is an uncommitted working-tree edit, deliberately: a planning row, not a deliverable. The checklist commit includes only this file.

## Functional review checklist

`update-dry-run-parity`, implementation revision 1, base `da3c774`, branch `milestone/update-dry-run-parity`. This section is committed by the checklist-evidence commit; that commit's SHA and blob are reported with the checklist, since a file cannot name its own commit.

**Automated verification is current.** The full gate `python3 tests/run_all.py` ran at `db6be10` (the code head): full selection, 2425/2425 units, 16426 tests, `verdict: exit 0` (`.ai-review/update-dry-run-parity/current/TEST_RESULTS.md`). `git diff --stat db6be10 HEAD -- src tests tools` is empty, so nothing needs a rerun.

### Setup

- **Sandbox** (flows marked *sandbox*): offline, with no network, no `gh`, no `claude`, `codex` or `ssh`, and no Workflow release cache. The flows read the source from `git archive` of two commits, so the clone itself is read-only. Tools used: Python 3 (standard library), `git`, `tar`, `find`, `xargs`, `sha256sum`, `sed`, `cmp`, `cp`, `grep`.
- **Working tree** (flow 10's note only): the clone you work in, with the uncommitted `docs/ROADMAP.md` row 46.
- Run the flows in `bash`. Use a scratch directory `S` outside the clone, never `/tmp`. The flows write only under `S`.
- Set-up, with `R` set to the clone path:

```bash
R=<clone>
S=$(mktemp -d "$HOME/.cache/udp-fr.XXXXXX")
mkdir -p "$S/base" "$S/cand" "$S/cache"
git -C "$R" archive da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 src | tar -x -C "$S/base"
git -C "$R" archive db6be105420f33661f0b3a636ab0ba27893e4c0c src | tar -x -C "$S/cand"
export WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache"
wm() { w=$1; shift; python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from workflow_manager.cli import main;raise SystemExit(main())' "$S/$w/src" "$@"; }
tree() { find "$1" -path '*/.git' -prune -o -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum; }
setrec() { python3 -I -c 'import json,sys;p=sys.argv[1];d=json.load(open(p));d["workflow_version"]=json.loads(sys.argv[2]);open(p,"w").write(json.dumps(d,indent=2,sort_keys=True)+"\n")' "$1/.workflow-manager/installation.json" "$2"; }
mk() { rm -rf "$S/$1"; cp -a "$S/ok" "$S/$1"; if [ $# -ge 2 ]; then setrec "$S/$1" "$2"; git -C "$S/$1" commit -qam r; fi; }
rec() { python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]+"/.workflow-manager/installation.json"))["workflow_version"])' "$1"; }
```

- The release builder `$S/mk.py DIR VERSION` (`VERSION` may be `null`):

```python
import hashlib, json, sys
from pathlib import Path
root, version = Path(sys.argv[1]), sys.argv[2]
state = b'{"schema_version": 1, "active_work_item_id": null, "work_items": {}}\n'
config = b'{"schema_version": 1, "default_workflow_version": "2.2", "supported_versions": ["1", "2.1", "2.2"]}\n'
art = {"payload/docs/guide.md": b"# guide\n"}
tpl = {"templates/docs/ai-workflow/WORKFLOW_STATE.json": state,
       "templates/docs/ai-workflow/WORKFLOW_CONFIG.json": config,
       "templates/docs/ACTIVE_MILESTONE.md": b"# a\n",
       "templates/.gitignore.workflow-fragment": b".ai-review/\n",
       "templates/CLAUDE.md": b"# managed\n<!-- workflow-manager:end -->\n"}
m = {"workflow_version": None if version == "null" else version,
     "upstream": {"tag": "workflow-v9.0.0", "commit": "0" * 40}, "artifacts": [], "templates": []}
for group, files in (("artifacts", art), ("templates", tpl)):
    for loc, data in files.items():
        p = root / loc; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        e = {"target_path": loc.split("/", 1)[1], "location": loc,
             "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if group == "artifacts":
            e.update(executable=False, category="distribution")
        m[group].append(e)
(root / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
```

  The `CLAUDE.md` template carries the Manager's end marker (`<!-- workflow-manager:end -->`, `install.py`). Without it the merge prepends the managed section on every run, and no "no change" expectation below can hold. The marker is the only change from the builder the match item used.

- Then, once:

```bash
python3 -I "$S/mk.py" "$S/rel" 9.0.0
python3 -I "$S/mk.py" "$S/relnull" null
git init -q "$S/t"; git -C "$S/t" config user.name t; git -C "$S/t" config user.email t@t
git -C "$S/t" commit -q --allow-empty -m init
wm base --release-dir "$S/rel" bootstrap "$S/t"
git -C "$S/t" add -A; git -C "$S/t" commit -qm b
cp -a "$S/t" "$S/ok"
```

  `mk NAME` gives a fresh copy of `ok` (record `9.0.0`); `mk NAME VALUE` also sets the record to the JSON `VALUE` (`'"garbage"'`, `null`, `'"../escaped"'`) and commits it. Each run gets its own copy, and `base` is the base source, `cand` the candidate.

### Test data

Nothing to seed: the fixture is built by the setup above. The fixture's own release has no `manager` block, so `doctor` reports an incomplete inspection in both runs and exits 1 (flow 8).

### Flows

**Flow 1: A damaged record, a named release (sandbox).**

```bash
mk g1 '"garbage"'; mk g2 '"garbage"'; mk g3 '"garbage"'; mk g4 '"garbage"'
wm base --release-dir "$S/rel" update --dry-run "$S/g1"; echo $?
wm base --release-dir "$S/rel" update "$S/g2"; echo $?
T0=$(tree "$S/g3"); wm cand --release-dir "$S/rel" update --dry-run "$S/g3"; echo $?
[ "$(tree "$S/g3")" = "$T0" ] && echo "g3 unchanged"
wm cand --release-dir "$S/rel" update "$S/g4"; echo $?
```

Expect: base dry run exit 1, `error: the installation record names 'garbage', which is not a version`. Base real run exit 0, `updated .../g2 to workflow 9.0.0`. Candidate dry run exit 0, first line `would update .../g3 from a record whose workflow_version 'garbage' is not a version to workflow 9.0.0     (dry run: nothing written)`, second line `  (no file changes; the installation record would be rewritten to workflow 9.0.0)`, then `g3 unchanged`. Candidate real run exit 0, `updated .../g4 to workflow 9.0.0`.

**Flow 2: A record that names a path (sandbox).**

```bash
mk e1 '"../escaped"'
wm cand --release-dir "$S/rel" update --dry-run "$S/e1"; echo $?
test ! -e "$S/escaped" && echo "no escaped entry"; ls -A "$S/cache" | wc -l
```

Expect: exit 0, the header names `'../escaped'`, the dry run writes nothing, `no escaped entry` and `0` (the cache stays empty).

**Flow 3: A damaged record, no option (sandbox).**

```bash
mk g5 '"garbage"'; mk g6 '"garbage"'
wm cand update --dry-run "$S/g5"; echo $?
wm cand update "$S/g6"; echo $?
```

Expect: both exit 1 with the same `error:` line, and each `next:` line identical apart from the path (`repair or re-bootstrap the installation record ..., or fix it with workflow-manager --release-version X.Y.Z update <path>`). Advice for a damaged record carries no `-- a real update, not a dry run` suffix on either side (the suffix is for null records only). Both trees unchanged.

**Flow 4: A null record and a null-manifest release (sandbox).**

```bash
mk n1 null; mk n2 null; mk n3 null; mk n4 null
wm base --release-dir "$S/relnull" update --dry-run "$S/n1"; echo $?
wm base --release-dir "$S/relnull" update "$S/n2"; echo $?; rec "$S/n2"
wm cand --release-dir "$S/relnull" update --dry-run "$S/n3"; echo $?
wm cand --release-dir "$S/relnull" update "$S/n4"; echo $?; rec "$S/n4"
```

(`rec DIR`, defined in the setup, prints the record's `workflow_version`.)

Expect: base dry run exit 0, `would update .../n1 from a record with no workflow_version to workflow None     (dry run: nothing written)`. Base real run exit 0, `updated .../n2 to workflow None`; its record `None`. Candidate dry run and real run both exit 1, `error: manifest.json at .../relnull is malformed: workflow_version is null, not text`, one `next:` line (`use an unmodified copy of the release directory, or leave --release-dir out ...`). Candidate's record `None` (unchanged), tree unchanged.

**Flow 5: A valid record and a null-manifest release (sandbox).**

```bash
mk o1; mk o2
wm base --release-dir "$S/relnull" update "$S/o1"; echo $?; rec "$S/o1"
wm cand --release-dir "$S/relnull" update "$S/o2"; echo $?; rec "$S/o2"
```

Expect: base exit 0 and its record becomes `None` (the divergence this item fixes). Candidate exit 1 with the flow-4 refusal, and its record stays `9.0.0`.

**Flow 6: Bootstrap, verify and status with the null-manifest release (sandbox).**

```bash
rm -rf "$S/E"; git init -q "$S/E"; git -C "$S/E" config user.name t; git -C "$S/E" config user.email t@t
git -C "$S/E" commit -q --allow-empty -m i
wm cand --release-dir "$S/relnull" bootstrap "$S/E"; echo $?
mk o3; wm cand --release-dir "$S/relnull" verify "$S/o3"; echo $?
mk o4; wm cand --release-dir "$S/relnull" status "$S/o4"; echo $?
```

Expect: each exit 1 with the flow-4 refusal and one `next:` line. `status` prints its usual status block after the refusal (unchanged). Tree of `E`, `o3` and `o4` unchanged.

**Flow 7: A null record and files equal to the release (sandbox).**

```bash
mk n7 null
wm base --release-dir "$S/rel" update --dry-run "$S/n7"; echo $?
wm cand --release-dir "$S/rel" update --dry-run "$S/n7"; echo $?
```

Expect: both exit 0 with the same header `would update .../n7 from a record with no workflow_version to workflow 9.0.0     (dry run: nothing written)`. Base's next line is `  (no change)`; the candidate's is `  (no file changes; the installation record would be rewritten to workflow 9.0.0)`. The other lines (`left alone:` ...) are identical.

**Flow 8: The happy path is byte-identical (sandbox).**

```bash
for c in "update --dry-run" "update" "doctor" "status" "verify"; do
  mk b8; mk c8
  wm base --release-dir "$S/rel" $c "$S/b8" > "$S/fb" 2>&1; eb=$?
  wm cand --release-dir "$S/rel" $c "$S/c8" > "$S/fc" 2>&1; ec=$?
  sed -i "s#$S/b8#TARGET#g" "$S/fb"; sed -i "s#$S/c8#TARGET#g" "$S/fc"
  if cmp -s "$S/fb" "$S/fc" && [ $eb = $ec ]; then echo "$c identical, exit $eb"; else echo "$c DIFFERS ($eb vs $ec)"; fi
done
```

Expect: five `identical` lines, with exit codes `update --dry-run` 0, `update` 0, `doctor` 1, `status` 0, `verify` 0 (`doctor`'s 1 is the fixture's missing `manager` block, in both runs).

**Flow 9: A locally edited managed file (sandbox).**

```bash
mk n9 null
F=$(python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]))["managed"];print(next(k for k in d if k != "CLAUDE.md"))' "$S/n9/.workflow-manager/installation.json")
echo x >> "$S/n9/$F"; T9=$(tree "$S/n9")
wm cand --release-dir "$S/rel" update --dry-run "$S/n9" > "$S/d9" 2>&1; echo $?
[ "$(tree "$S/n9")" = "$T9" ] && echo "unchanged after dry run"
wm cand --release-dir "$S/rel" update "$S/n9" > "$S/r9" 2>&1; echo $?
[ "$(tree "$S/n9")" = "$T9" ] && echo "unchanged after real run"
grep -n 'update' "$S/d9" "$S/r9"
```

Expect: both exit 2 with `refusing to update: these release files were modified locally and would be overwritten:` and `modified: docs/guide.md` (`$F`). Tree unchanged after each. Every printed `update` command, the ordinary and the `--force` one, names `--release-dir`.

Second part of flow 9, the printed `--force` command (sandbox): Run the `--force` command printed by flow 9 exactly, on a fresh copy of the same edit:

```bash
mk n10 null; echo x >> "$S/n10/$F"
wm cand --release-dir "$S/rel" update --force "$S/n10"; echo $?
```

Expect: exit 0, `updated .../n10 to workflow 9.0.0`, the record reads `9.0.0`, and `docs/guide.md` is the release's again.

**Flow 10: The files changed (sandbox; the working-tree list is manual).**

```bash
git -C "$R" diff --stat da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 -- . ':!docs/ai-workflow' ':!.ai-review'
```

Expect, in a sandbox checkout: the 11 files of plan section 2 (`docs/ARCHITECTURE.md`, `docs/common-problems.md`, `docs/exit-codes.md`, `docs/update.md`, `src/workflow_manager/advice.py`, `cli.py`, `compatibility.py`, `source.py`, `tests/test_discovery.py`, `tests/test_operator_ux.py`, `tests/test_operator_ux_readonly.py`) and `docs/ACTIVE_MILESTONE.md` (this checklist's commit). In the working tree, also `docs/ROADMAP.md`.

**Flow 11: The pages (sandbox).**

```bash
git -C "$R" diff --exit-code da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 -- docs/retention.md docs/release-history.md docs/install.md docs/README.md src/workflow_manager/install.py 'src/workflow_manager/retention*.py'; echo $?
grep -n 'whatever the option' docs/update.md docs/common-problems.md docs/exit-codes.md docs/ARCHITECTURE.md
grep -n 'bare .--dry-run' docs/update.md
grep -c 'update-dry-run-parity' docs/update.md docs/common-problems.md docs/exit-codes.md docs/ARCHITECTURE.md
```

Expect: exit `0` (untouched). `whatever the option` appears only in `docs/common-problems.md` (`doctor refuses the record whatever the option`). `docs/update.md`'s bare `--dry-run` sentence says only `doctor --release-dir` prints the step with a directory. The count is `0` for each of the four pages.

**Flow 12: The suite (full environment only; needs the network or a primed release cache).**

```bash
python3 tests/run_all.py --select test_operator_ux.py --select test_discovery.py --select test_operator_ux_readonly.py --select test_operator_ux_docs.py --select test_docs.py
python3 tools/check_docs.py; echo $?
python3 tests/run_all.py
```

Expect: all green, `check_docs` exit 0. Each mutation of plan section 4 fails its named tests.

### Known limitations (by design)

- The null-manifest refusal is at the source, so `bootstrap`, `verify` and `status` now refuse such a directory too; they accepted it before. The old acceptance is what let a real `update` destroy a valid record.
- A manifest version that is a number, `true` or `""` is still accepted: out of scope.
- The real `update` still prints `(no change)` for a record-only rewrite; only the dry run says the record would be rewritten.
- `status` prints its status block after a refusal, as it did before.
- Completed items' test results (`docs/milestones/completed/`) still show the earlier mutation table; that is history, not edited.
- Optional findings from plan review and self-review (`optional_findings` in `WORKFLOW_STATE.json`) get a recorded disposition at acceptance. Finding `O1` (flow 3's suffix) is already reflected above.
- Out of scope: the retention view points (#160), the retention commands, Workflow releases, new options, any new write path.
