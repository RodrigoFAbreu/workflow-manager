# Workflow Manager: A Retention Report That Cannot Forge or Recolour the Terminal (Revision 3)

`work_item_id: retention-view-hardening` -- `governing_workflow_version: "2.2"`

**Deliverable:** `status --retention` and `doctor --retention` print nothing
from the engine's JSON report until the report has passed a stricter
validation: no string with a control character, every integer in a stated
range, every string within a stated length, and every value echoed in a refusal
truncated (roadmap row 23, issue #116 items 1 and 2, follow-ups of row 17,
#90).

**Work item type:** `process`. **Base commit:** `e5fa61f` (tip of `main`;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/retention-view-hardening`. **Scope source:** `docs/ROADMAP.md`
row 23. A `src/` change in the Manager: the pull request title is `fix: ...`,
which releases a patch (**Manager 1.14.3**; checked with
`python3 tools/release/release.py check-title`). One mechanism: the validation
of the report in `retention.py`. Two checkpoints. Items 3 to 6 of #116 are out
of scope and stay open.

## 1. The two points, reproduced on main (Manager 1.14.2)

With a stub `scripts/workflow_retention.py` printing a crafted report:

1. `repository` = `"a\nretention: forged"` prints a second, forged line;
   `read_errors[].error` = `"\x1b[31m..."` prints the escape (the terminal is
   recoloured). `_printable` (`retention.py`) only tries `encode("utf-8")`.
2. `finished_folder_bytes` = `-1` prints `-1 B`; `10**400` prints a
   465-character line; `kind` = `"x" * 5000` and `schema_version` = `10**400`
   are echoed whole, by `repr`, in the refusal.

## 2. Decisions

* **One place.** `_need` already types every field, so the new rules live in
  `_need` (integers, strings) and in `_printable` (strings, `removing`). No new
  pass, no new function except `_shown` (the echo helper below).
* **A string is refused if it holds a control character**: any character of
  Unicode category `Cc` (C0, DEL and C1, so newline, return, tab, ESC, NUL and
  NEL included), or U+2028 or U+2029 (the line and paragraph separators, which
  terminals and many viewers treat as line breaks). Nothing is escaped or
  replaced: a report that needs it is not the engine's. Other format
  characters (category `Cf`, for example a bidirectional override) are not
  refused: the owner's rule is `Cc` plus the two separators; they are noted as
  a follow-up (section 5).
* **Which ids are subject to the string rules.** Only the ids the Manager can
  print. The engine puts every `WORKFLOW_STATE.json` key that fails its id
  pattern (`^[a-z0-9][a-z0-9_-]{0,63}$`) into `not_finished` with the reason
  `invalid_id`, and `work_item_id` is then the raw key, of any length and with
  any characters. The Manager never prints that id (`not_finished` entries are
  read for their `reason` only), so a repository holding such a key must still
  get its retention section. The rules are therefore: `finished[]` and
  `kept_recent[]` ids are always checked; a `not_finished[]` id is checked
  unless its `reason` is exactly `invalid_id`, in which case it need only be a
  string that encodes as UTF-8 (today's check). `reason` is always checked and
  is read before the id. This is a decision, not a fallback: the limits below
  stay true for every id that is checked, because the engine's own pattern
  bounds those to 64 characters.
* **How the rules reach `_need`.** `_need(obj, key, kinds, where, limit=None)`
  gains one parameter: for a string, `limit` is the maximum length, or `None`
  for the encodability check alone (used only for the exempt `invalid_id` id);
  every other string field passes its limit from the table below, so the
  field-to-limit mapping is written at the call site. For an integer (`kinds is
  int`) the range 0 to 2**63 - 1 is applied to every field with no parameter,
  so no integer field can be missed.
* **Length limits, in characters (`len`)**, checked with `len` (a limit, not a
  cost bound: the JSON is already decoded): **4096** for `repository`, `archive_dir` and `read_errors[].path`
  (Linux `PATH_MAX`, the longest legitimate path); **8192** for
  `read_errors[].error` (a `PATH_MAX` path plus the operating system's message,
  as the engine builds it); **256** for work-item ids, `not_finished[].reason`
  and `removing` items (a checked Workflow id is at most 64 characters and a reason is
  a short code such as `pr_not_merged:CLOSED`). A string at the limit is valid,
  one over it is not.
* **Integer range 0 to 2**63 - 1** for every integer the report carries
  (`ttl_days`, `keep_recent`, `tracked_files`, `bytes`, and the four `totals`):
  the largest signed 64-bit value, which bounds any file size or count the
  engine can read (`st_size` is a signed 64-bit `off_t`), is far above any
  real value, and renders in 19 digits. A bool stays refused as before.
* **The fallback is the existing one.** An invalid report raises `_Invalid`,
  which `fetch` turns into the case-six note: `retention: not available: the
  script's report is malformed: <what>` and `  next: run `python3 -I
  scripts/workflow_retention.py report` in the repository`, two lines, the
  command's exit code unchanged (`--retention` never changes one). No new exit
  code, no new cause row. The reason names the field and the rule (`<field>
  contains a control character`, `<field> is longer than N characters`,
  `<field> is out of range (0 to 2**63 - 1)`) and **never the value**.
* **A value echoed in a refusal is shown by `_shown(value)`**: `repr(value)`
  (which escapes every control and non-printing character, so it cannot reach a
  terminal raw), cut to its first 40 characters, followed (outside the 40) by the visible
  marker `... (N characters)` where N is the length of the whole `repr`. A
  `repr` of 40 characters or fewer is unchanged, so `kind 'x'` and `schema_version 2` print byte for byte as today.
  It is used for `kind` and `schema_version` only: they are the only places
  `fetch` echoes a report value. A `RecursionError` while taking the `repr` of
  an absurdly nested value shows `<value>`.
* **`_size` is left as it is.** Its beyond-float branch is now unreachable from
  a validated report but costs nothing and keeps its own test.
* **Docs unchanged.** `docs/retention.md` already lists the malformed-report
  and the kind/schema_version rows; both stay true. No docs page changes.

## 3. Tests (`tests/test_retention_status.py`)

All through the existing `Scratch` stub engine (the stub prints a JSON file), so
no `gh`, no network; each end-to-end case runs `status --retention` **and**
`doctor --retention` and goes through `both()` (same exit code as without
`--retention`, no traceback).

* **Control characters, both commands, end to end**: `repository` with `\n`
  (a forged line), and `read_errors[].error` with `\x1b[31m` (report made
  incomplete): the output is the two-line case-six note, names the field, holds
  neither the forged text nor `\x1b`; the tree is unchanged (no-write proof,
  `tree_hash`, no `__pycache__`).
* **Control characters, every field, at the validator**: `_validate` over each
  string field (`repository`, `archive_dir`, `read_errors[].path`/`.error`, the
  ids of `finished`, `kept_recent` and `not_finished`, `reason`, a `removing`
  item) with each of `\n \r \t \x00 \x1b \x7f \x85 \u2028 \u2029`: `_Invalid`
  naming the field; the clean fixture still passes. `\u2028` and `\u2029` are
  separate cases, so dropping that clause alone fails.
* **Range, both commands, end to end**: `finished_folder_bytes` = `-1` and
  `10**400` (this replaces the existing huge-byte-count case, which pinned the
  465-character line): two-line fallback.
* **Range, every integer field at the validator**: each of the eight fields
  with `-1`, `2**63` and `10**400` refused, and `0` accepted. The upper bound
  `2**63 - 1` is accepted for seven fields through `_validate`; for
  `totals.finished`, which `_validate` also requires to equal `len(finished)`
  (`retention.py:218`) and so cannot reach `2**63 - 1` with a practical fixture,
  the acceptance is tested through `_need` directly, and `_validate` keeps its
  own tests for matching and mismatched counts.
* **Length, both commands, end to end**: a 4097-character `repository` falls
  back; the same field at 4096 characters prints.
* **Length, every string field at the validator**: each field at its limit
  accepted and at limit + 1 refused.
* **Echo**: `kind` = `"x" * 5000` and `schema_version` = `10**400` give one
  note whose cause is exactly the text the arithmetic gives, so at most 140
  characters: `the script's report has kind 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx... (5002 characters), not 'retention-report'`
  (114) and `the script's report has schema_version 1000000000000000000000000000000000000000... (401 characters); this workflow-manager reads 1`
  (130); the test asserts each whole text, then `len <= 140`;
  `kind` = `"a\x1b[31m\u2028b"` shows the escaped `repr`, no raw `\x1b` and no
  U+2028; `kind` `'x'` and `schema_version` 2 keep today's text (existing
  `"schema 2"` case). Both commands.
* **An unprintable `invalid_id` id is not refused, both commands, end to end**:
  a report whose `not_finished` holds an entry with the reason `invalid_id` and
  a `work_item_id` of 300 characters, and another with `"a\nb"`, prints the
  section exactly as the same report with the id `x` does; the same two ids
  under the reason `no_pull_request` fall back (the two-line note naming
  `not_finished[].work_item_id`). At the validator, the exemption does not
  cover `reason` (a control character in the reason of an `invalid_id` entry is
  refused) and a lone surrogate id is still refused.
* **Valid reports unchanged**: `TestRendering`, `TestArchiveCoverage`,
  `TestNextStep`, `TestIncomplete`, `TestCapabilityEndToEnd`, the fixture checks
  in `TestRealScript` and `TestNoWrites` stay unedited and green; they compare
  exact lines of the section for valid reports. The only existing test edited
  is the 10**400 one named above.

**Failure-only mutations** (a scratch clone, never the repository; each passes
on the real code and must fail as stated, the named test class listing the
failing cases):

| Mutation | Must fail |
| --- | --- |
| the control-character scan removed | the end-to-end `\n` and `\x1b` cases and the every-field case |
| only the U+2028/U+2029 clause removed | the two separator cases |
| `\x85` (C1) no longer refused (scan limited to C0) | the `\x85` case |
| the length check removed | both length cases |
| the length limit off by one (`<` for `<=`) | the at-the-limit case |
| the lower bound removed | the `-1` cases |
| the upper bound removed | the `2**63` and `10**400` cases |
| the range applied to `bytes` only | the every-integer-field case |
| `removing` items skipped by the scan | the `removing` case |
| the `invalid_id` exemption removed (every id checked) | the `invalid_id` end-to-end cases |
| the exemption widened to every `not_finished` id | the `no_pull_request` fall-back case |
| `kind` echoed untruncated | the echo case |
| `schema_version` echoed untruncated | the echo case |
| `_shown` returns the raw string instead of `repr` | the escaped-`repr` case |

Evidence at implementation: `python3 tests/run_all.py --select
test_retention_status.py` green, each mutation failing the case named, then the
full gate `python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The stricter validation and its tests | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the validation and its tests

**Files:** `src/workflow_manager/retention.py`, `tests/test_retention_status.py`.

Section 2 and section 3: constants for the limits, the integer check and the
`_printable` extension in `_need`/`_validate`, `_shown` for the `kind` and
`schema_version` refusals, and the tests.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 23 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance, and `docs/ACTIVE_MILESTONE.md` records the milestone and the
mutation results. No version is edited: the `fix:` title releases Manager
1.14.3. Both files stay excluded at both stages; the acceptance step writes
them.
<!-- /CP2 -->

## 5. Not in this item

* Items 3 to 6 of #116 (rate-limit step, link and limit items, wording,
  checklist notes).
* **The script's own stderr** (`error:` and `next step:` lines on exit 2, and the
  first line of stderr for other failures) is passed through by design and is
  pinned by `test_the_script_refuses_and_its_cause_and_step_pass_through`; it is
  not part of the JSON report. Sanitising it is a second mechanism and a
  follow-up.
* Category `Cf` characters (bidirectional overrides) and the number of entries in
  a list (`removing` is listed whole; #116 item 4) are follow-ups.

## 6. Functional review

Every flow runs offline with python3 and git only, outside the repository, in a
**small** scratch (a few hundred kilobytes). Set up once: `S=$TMPDIR/fr; mkdir
-p $S/home $S/cand $S/base`; the candidate is `git archive HEAD | tar -x -C
$S/cand`, the base is `git archive e5fa61f | tar -x -C $S/base`, both from this
branch's repository; copy the release cache (`command cp -r
~/.cache/workflow-manager/releases $S/cache`; run `python3 tests/run_all.py
--list` first if it lacks 2.12.0). Define `wm_cand` and `wm_base` as shell functions, `wm_<name>() { env -i
R="$R" HOME=$S/home PATH=/usr/bin:/bin PYTHONPATH=$S/<name>/src
XDG_CACHE_HOME=$S/home/.cache XDG_CONFIG_HOME=$S/home/.config
XDG_DATA_HOME=$S/home/.local/share WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache
WORKFLOW_MANAGER_PINNED_ONLY=1 GIT_CONFIG_NOSYSTEM=1 python3 -m
workflow_manager "$@"; }`. `env -i` clears the environment, so the report
selector `R` is passed to it explicitly with `R="$R"`; a bare `R=<file>` in front
of a command that begins `env -i` would be discarded and the stub would raise
`KeyError` instead of printing JSON. Build the target: `git init -q $S/t`, one commit, `wm_cand
--release-version 2.12.0 bootstrap $S/t` (with `R` unset or empty; the bootstrap does not run the stub), then write the stub
`$S/t/scripts/workflow_retention.py`: `import os,sys;
sys.stdout.write(open(os.environ["R"]).read())`, and a valid report
`$S/ok.json` (copy `tests/fixtures/retention_report.json` and set `"complete":
true`, `"read_errors": []`). Because the stub makes `status` report `modified`
(exit 1), the exit-code baseline of every flow is the same repository and stub
**without** `--retention`. `R=<file> wm_<name> <command> --retention $S/t` below is run
for `status` and `doctor` and for `cand` and `base`. Before trusting a flow,
check once that the stub prints JSON through the function (`R=$S/ok.json
wm_cand status --retention $S/t` shows the retention section and no
`KeyError`). Make each crafted report
with python3 from `$S/ok.json` (`json.dump`). Clean up with `rm -rf $S`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `repository` = `"a\nretention: forged"` | candidate: the two-line note `retention: not available: the script's report is malformed: repository contains a control character`, no `forged`; base: prints the forged second line; exit codes equal |
| 2 | `read_errors` = one entry whose `error` is `"\u001b[31mred"`, `complete` false | candidate: the two-line note, no ESC byte in the output (`grep -c $'\e'` is 0); base prints the ESC |
| 3 | `repository` = `"a\u2028b"` and, separately, `"a\u2029b"` | candidate: the two-line note; base prints the separator |
| 4 | `totals.finished_folder_bytes` = `-1` | candidate: the note, `... is out of range (0 to 2**63 - 1)`; base prints `-1 B` |
| 5 | `totals.finished_folder_bytes` = `10**400` (write the number literally into the JSON) | candidate: the two-line note; base: one line of 465 characters |
| 6 | `repository` of 4097 `a`, then 4096 `a` | 4097: the note, `longer than 4096 characters`; 4096: the section prints; base prints both |
| 7 | `kind` = 5000 `x`; then `schema_version` = `10**400` | candidate: one note, cause exactly as in section 3 (114 and 130 characters, so at most 140), the echo ending `... (N characters)`; base echoes the whole value |
| 8 | A valid report (`$S/ok.json`) | first, each output contains the successful retention section and does **not** contain `retention: not available` (`grep -c 'retention: not available'` is 0) -- two identical failure notes would otherwise pass; then `cand` and `base` print byte-identical output and equal exit codes, `diff` empty, for both commands |
| 9 | In the clone, `python3 tests/run_all.py --select test_retention_status.py` (needs the full environment) | exit 0 |

## 7. Risks

* A real engine report outside a limit would now fall back. The limits are
  chosen above anything the engine can produce for a printed field (`PATH_MAX`,
  64-character ids that pass its pattern, signed 64-bit sizes); the one field it
  fills unvalidated, the id of an `invalid_id` entry, is exempt (section 2); the
  fallback is the safe, existing one and names the
  field and the rule.
* `status` already refuses an installation whose `workflow_version` is damaged
  before the section runs; this item does not change that.

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
