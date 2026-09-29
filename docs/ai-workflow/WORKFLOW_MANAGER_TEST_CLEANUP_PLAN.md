# Workflow Manager: Test Cleanup, No Orphaned Git Processes (Revision 5)

`work_item_id: workflow-manager-test-cleanup` -- `governing_workflow_version: "2.2"`

**Deliverable:** this repository's tests stop orphaning Git's detached
background maintenance, at the source, and the test runner fails any run
whose tests leave orphaned processes behind. Two layers switch Git's
automatic maintenance off in every throwaway repository a test creates:
the runner's chunk environment (its `GIT_CONFIG_*` entries, plus a template
directory that writes the settings into every repository a chunk creates),
and a shared per-repository setup. A
per-chunk subreaper wrapper then adopts, records and reaps every orphan a
chunk produces, and the run fails with a named fault when an undeclared
orphan appears.
**Governing workflow version:** `2.2` (the config default at creation).
**Work item type:** `process` (test infrastructure; no Workflow release, no
Manager behaviour change).
**Base commit:** `7dabd2e99b69f59a776bfe81831a06f2c508d5fc` (tip of `main`,
after M1's squash merge `59158c6` and its docs follow-up; installed Workflow
`2.6.0`, protocol `2.2` active).
**Branch:** `milestone/workflow-manager-test-cleanup`, created from the base.
The milestone reaches `main` through one pull request, opened and merged by
the user.
**Scope source:** `docs/ROADMAP.md` "At a glance" step **M1b** and section
**10.1b**, and the cross-lane order the user agreed on 2026-09-29 (the
Manager lane does this small milestone while the Controller lane fixes its
zombie reaping; a Controller release is installed only between Manager
milestones).

**M1b creates no Workflow release, and `distribution/`, `migration/`,
`scripts/` and `.claude/commands/` stay byte-identical to the base
(INV-1).**

## 1. Goal

### 1.1 Fixed inputs (from the roadmap and the user's lane decision)

1. **Throwaway test repositories turn off Git's automatic maintenance**:
   `maintenance.auto=false` and `gc.auto=0`, set by the shared test setup
   (the fixture builder and the test infrastructure).
2. **A leak check**: a test run, or the CI job, fails when the suite leaves
   orphaned background processes behind.
3. **Kept small.** The big test reduction stays in M2.
4. **Full matrix.** It changes the fixture builder and the test
   infrastructure, so M1's stopgap rule 1 runs its pull request on the full
   matrix (`tools/ci/pr_profile_paths.json` already maps `src/`,
   `tests/support.py`, `tests/frozen_runs.py`, `tests/run_all.py` and
   `tests/parallel/` to `full`).

### 1.2 What "done" means

- A full `python3 tests/run_all.py` at the milestone head, with the leak
  check on, is green with **zero undeclared orphans**, and its report lists
  every declared (tolerated) orphan by chunk.
- The same full run, wrapped in an outer subreaper probe (the one used in
  section 3), hands the probe **zero** orphans of any kind: everything a test
  orphans is adopted and reaped inside the run, so none can accumulate
  under a Workflow Controller that runs the suite.
- No Git process is among the orphans the leak check records, judged on
  each entry's recorded label (its command line, or `[<comm>]` when the
  command line was empty; 5.4 step 2).
- A synthetic chunk that daemonizes a process makes the run exit `2` with an
  `OrphanProcessError` naming the chunk and the orphan's command line, in
  local, `--run-shard` and `--aggregate` modes alike.
- A Linux chunk whose check is unavailable makes the run exit `2` with an
  `OrphanCheckUnavailableError`, in the same three modes. It never passes
  unchecked.
- The CI pull-request run for this milestone (the full matrix, by rule 1)
  is green and its report says the orphan check is on.

## 2. Non-goals

- **No Workflow release and no change to `distribution/`, `migration/`,
  `scripts/`, `.claude/commands/`, the managed
  `.github/workflows/workflow-conformance.yml`, or the managed part of
  `CLAUDE.md`** (INV-1, INV-3). The frozen suites' own `git init` sites
  cannot be edited; the environment layer (5.2) reaches them instead.
- **Not the Controller fix.** Reaping every finished child in the
  Controller belongs to the Controller lane. This milestone makes this
  repository's suite hand no orphans to whatever runs it; it does not change
  how the Controller reaps.
- **No change to the operator's lane scripts.** The watchdog's own
  `GIT_CONFIG_*` exports and its `--max-steps 1` stay until the fixed
  Controller is installed between milestones (the roadmap's "After it").
  They live outside this repository.
- **Not M2.** No test is removed, and the selection only grows by this
  milestone's own new test module.
- **No change to the user's machine.** Nothing writes the global or system
  Git config.
- **No push, pull request, merge or settings change by an agent**
  (the managed `CLAUDE.md`'s Git restrictions). The CI evidence in 1.2 comes
  from the pull request the user opens.

## 3. Investigation findings (measured at the base commit)

### 3.1 The roadmap's premise, checked

`docs/ROADMAP.md` 10.1b says environment settings are "not enough: tests
start Git with their own clean environment". For **this** repository that
is mostly not true, and the plan relies on the difference:

- The runner starts every chunk with `isolation.chunk_env`
  (`tests/parallel/isolation.py:272`): the parent environment minus
  `PYTHONPATH`/`FORCE_COLOR`, plus a private `TMPDIR`. HOME,
  `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM` and `XDG_CONFIG_HOME` are not
  touched.
- The frozen suites run through `support.run_suite` (`tests/support.py:59`),
  which copies the environment and sets `GIT_CONFIG_GLOBAL` and
  `GIT_CONFIG_SYSTEM` to `/dev/null`. `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`
  survive that.
- Every frozen suite's Git helper, in all five releases, either passes no
  `env=` or copies `os.environ`. The only callers that build an environment
  from scratch (`env={"PATH": ...}`) are the frozen engine's three isolated
  evidence drivers per release (for example `workflow_state.py:11099`,
  `:11802` and `:12176` in `2.6.0`). One of them,
  `_load_and_run_named_test` (`:11064`), runs an arbitrary named unittest,
  so what it runs cannot be bounded by reading it. Its pinned-commit twin,
  `_run_named_test_in_scratch` (`:11770`, environment at `:11802`), runs
  the named test inside a scratch **clone** made by
  `_materialize_pinned_worktree_at_commit` (`:11653`, the clone at
  `:11734`). A clone does not inherit its source's local config, and the
  named test's Git sees no environment keys, so the environment entries
  alone leave maintenance on there. 3.4's measurement found no Git orphan
  on that path, but a measurement does not meet the requirement. The
  template layer (5.2) closes the gap from the test side. The clone runs in
  the frozen engine's own process, which inherits the chunk environment, so
  the clone is created with the four keys in its own local config, and a
  `PATH`-only Git inside it still reads them. The leak check (5.4) remains
  the backstop for a repository that code creates from inside a
  from-scratch environment (5.6).
- The frozen suites create their **own** repositories (`git init` in
  `workflow_test_harness.py`, `workflow_fingerprint_test.py`,
  `workflow_integration_test.py`, `workflow_state_test.py`,
  `workflow_state_completion_obligations_test.py` and
  `workflow_acceptance_matrix_test.py`, one or two per suite, plus `clone`
  and `worktree add`). No fixture builder touches those repositories, so
  per-repository config written by this repository's helpers cannot reach
  them. Only the environment does: its `GIT_CONFIG_*` entries, and its
  template directory, which Git itself applies at each `init` and `clone`
  (5.2). No suite, frozen or host, passes `--template` or sets
  `GIT_TEMPLATE_DIR` or `init.templateDir` (searched at the base).
- The Controller lane's suite leaked orphans even with the environment
  exports (per the shared lane record); that is its own suite's behaviour,
  not this one's.

### 3.2 Where this repository creates repositories

There are eleven `git init` sites outside the frozen code, in ten places, each with its own
local helper. There is no shared helper. Each one sets `user.email`,
`user.name` and `commit.gpgsign` itself:

- `src/workflow_manager/fixture.py:63` (`init_git_repo`, used by
  `build_conformance_repo`, `build_target_repo` and the driver);
- `tests/frozen_runs.py:86` (`empty_repo`, the same steps as
  `init_git_repo` with a different commit identity, `e2e@example.invalid`/
  `E2E` against `fixture@example.invalid`/`Workflow Fixture`; re-exported to
  `test_bootstrap_e2e.py`);
- `tests/test_release_versioning.py:56`;
- `tests/test_manager_version.py:60`;
- `tests/test_amendment_update_path.py:112` and `:502`;
- `tests/test_squash_merge_compat.py:106`;
- `tests/test_bootstrap.py:58`;
- `tests/test_implementation_review_two_stage_disposable_repo.py:78`;
- `tests/test_workflow_2_6_0_hardening_disposable_repo.py:232`;
- `tests/test_parallel_runner.py:77` (`_git_repo`, also used by
  `test_stopgap_profile.py`).

There are two clone sites, `test_squash_merge_compat.py:152` and
`test_parallel_runner.py:2646`. A clone does not inherit its source's
config.

`src/workflow_manager/fixture.py` ships in the wheel, but nothing in the
product (`cli.py`, `install.py`, `installation.py`, `release.py`) imports
it. It is test support in practice.

No test compares a fixture repository's `.git/config` byte for byte.
`frozen_runs.full_state` records `git config --local --list` only to
compare before and after on the same repository, so a constant extra key
is harmless. Disabling auto-gc also removes a source of unclassified gitdir
residue (`gc.pid`, `gc.log`).

### 3.3 Why the runner's existing descendant kill does not catch them

`isolation.run_chunk` starts each chunk in its own session, and kills the
chunk's whole process group once the chunk exits
(`test_a_normal_exit_leaves_no_descendant_behind`). Git's detached
maintenance daemonizes: it calls `setsid()` and leaves the group, so it
escapes that kill. It is re-parented to the nearest subreaper, which under
Workflow Controller `1.3.0` is the Controller. The Controller collects only
the orphans it saw alive, so the rest stay zombies until it exits. On
2026-09-29 they filled the per-user process limit (125,849) twice.

The runner never calls `waitpid(-1)`. It waits for chunks with
`waitid(P_PID, pid, WNOWAIT)` and `Popen.wait`, and it also runs its own Git
subprocesses. A reaper inside the runner process would race with all of
these, and `Popen` turns `ECHILD` into return code 0, which would hide a
failure. The leak check therefore lives in a separate process (5.4).

### 3.4 Measurements

Each run below is a full `python3 tests/run_all.py` (4088/4088 units,
8 workers, head `7dabd2e`), started under an outer subreaper
probe that records and reaps every orphan re-parented to it. The probe is
`orphan-probe.py`, the operator's script from the zombie investigation,
outside this repository. CP3 repeats the measurement with this plan's own
wrapper (5.4), which does the same job.

| run | verdict | orphans reaching the probe | Git among them | wall |
| --- | --- | --- | --- | --- |
| default Git config | exit 2 (see below) | 42,158 | 31,731 seen as Git, plus 10,391 that exited before the probe could read them | 380 s |
| the four keys of 5.1, exported for the whole run | exit 0 | 36 | 0 | 370 s |

The default-config run's `exit 2` was the author's doing, not Git's: this
plan file was being written during the run. The integrity guard reported
that as an `IntegrityError`. The changed tree digest also made phase B's 15
matrix classes refuse their merge context (`FrozenMergeError`), which is why
that run counted 25,544 tests instead of 25,624. Every phase-A chunk ran,
and the only failed units were the documented portability exceptions, so
the orphan count stands. The wall times are one run each and include the
probe's own polling; they are not a speed claim.

The 36 non-Git orphans are all Python processes (19 already exited when
seen, 15 `python3 -B -c import ...`, one `python3 -c import time; ...`, one
`python3 -B -m parallel.unit`). Targeted probes attribute them in part:

- `--select test_parallel_runner.py` (55 units): 6. This module's
  `TestRunChunk` deliberately starts grandchildren and kills the chunk's
  group; a grandchild whose parent dies first is re-parented.
- every other host module except `test_conformance_suite.py` (1418 units):
  10;
- `frozen:2.6.0/target/workflow_state_test.py` (149 units, including its
  lifecycle-worker tests): 0.

The rest, about 20, are not attributed at plan time. CP2 attributes every
one by chunk with the leak check itself (5.4). The counts vary from run to
run, because each depends on which of two dying processes the kernel
re-parents first.

## 4. Invariants (normative for every checkpoint)

- **INV-1** `git diff 7dabd2e -- distribution migration scripts
  .claude/commands .github/workflows/workflow-conformance.yml` is empty, and
  `workflow-manager verify .` is clean.
- **INV-2** No test is removed, skipped or weakened. The full selection only
  gains this milestone's own new test units. No frozen pin and no
  portability exception changes.
- **INV-3** The managed part of `CLAUDE.md` stays byte-identical.
- **INV-4** The runner's exit contract is extended, not changed: `0`/`1`/`2`
  keep their meanings, and an orphan is one more named exit-`2` fault.
- **INV-5** The leak check never reaps a process the runner itself waits
  for. It reaps only descendants that were re-parented to its own wrapper,
  inside one chunk's session.
- **INV-6** Nothing writes Git config outside a throwaway repository, the
  runner's own chunk environment, or the run's template directory under
  `<run_dir>` (outside the checkout).

## 5. Design

### 5.1 `D-Quiet-Git`: the settings

One constant, `THROWAWAY_GIT_CONFIG`, is defined once in
`src/workflow_manager/fixture.py` and imported everywhere else:

| key | value | why |
| --- | --- | --- |
| `maintenance.auto` | `false` | `git commit` and friends skip `git maintenance run --auto` (the roadmap's key) |
| `gc.auto` | `0` | commands that run `git gc --auto` skip it (the roadmap's key) |
| `maintenance.autoDetach` | `false` | defence in depth: an auto run that still happens stays in the foreground |
| `gc.autoDetach` | `false` | the same, for `gc` |

The two `autoDetach` keys are the ones the operator's measurement proved on
2026-09-29 (13,978 orphans down to 10 on a 1315-unit selection). The two
`auto` keys do the work the roadmap asks for, and they save the time the
maintenance would take. Together, no auto maintenance runs, and any that a
future Git or test turns back on cannot detach.

### 5.2 `D-Quiet-Git-Env`: the runner's layer

`isolation.chunk_env` appends the four pairs to the chunk's environment as
`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`:

- **Preserving.** Entries the parent already exports (the operator's
  watchdog exports two) are kept, and the new pairs are numbered after
  them.
- **Decided by each key's last value.** All four keys are single-valued,
  and Git uses the **last** value a key is given (checked on 2.55.0:
  `maintenance.auto=false` then `maintenance.auto=true` reads `true`). So
  for each of the four keys, `chunk_env` finds the last parent entry for
  that key, matching the key case-insensitively as Git does
  (`Maintenance.AutoDetach` is `maintenance.autodetach`). It appends our
  pair unless that last value is already ours, as the same string. An
  earlier matching pair followed by a different value therefore does not
  count: `false`, then `true` gets our `false` appended, and Git reads
  `false`. A parent's `gc.autoDetach=true` is kept, and ours follows it.
  An equivalent spelling (`no` for `false`) gets ours appended too, which
  is harmless.
- **Idempotent.** When every key's last value is already ours, nothing is
  appended. Nested runners (`test_parallel_runner.py`'s scratch checkouts
  run the runner inside a chunk) therefore do not grow the list.
- **Nothing outranks it.** Git reads `GIT_CONFIG_PARAMETERS` (what `git -c`
  exports to its children) after every `GIT_CONFIG_COUNT` entry, so a key
  set there beats ours (checked on 2.55.0). A parent
  `GIT_CONFIG_PARAMETERS` that sets any of the four keys, or that cannot be
  parsed, is a usage error. A parent that does not set it is the normal
  case.
- **Fail-closed.** A parent `GIT_CONFIG_COUNT` that is not a non-negative
  integer, or that names a missing key, is a usage error. Git itself would
  refuse every command under it. Every usage error here is exit `2`,
  raised before any chunk starts.
- **The template directory.** The environment also sets
  `GIT_TEMPLATE_DIR` to `<run_dir>/git-template/`. The executor builds that
  directory once per run, before any chunk starts, and passes it to
  `run_chunk` (`executor.py:218`) and to its other `chunk_env` call
  (`prepare_merge`, `executor.py:318`). `chunk_env` and `run_chunk` take
  it as an optional keyword argument, `git_template`, defaulting to
  `None`. The default serves direct callers that build no template, such as
  `TestRunChunk`'s `run_chunk(self.tmp, ...)` (`test_parallel_runner.py:2776`).
  With `None`, `chunk_env` **removes** `GIT_TEMPLATE_DIR` from the chunk's
  environment and appends the `GIT_CONFIG_*` pairs as usual, so an
  operator's exported template never reaches a chunk. It is
  Git's own default template plus a `config` file holding the four keys.
  To get the default, the executor runs `git init` in a scratch directory
  with `GIT_TEMPLATE_DIR` unset, `GIT_CONFIG_GLOBAL=/dev/null` and
  `GIT_CONFIG_NOSYSTEM=1`, so no user or system `init.templateDir` applies.
  It then copies every entry of that `.git` except `HEAD`, `config`,
  `objects` and `refs`. Git copies a template's `config` into every
  repository that `git init` or `git clone` creates, before writing its own
  `core` and `remote` keys, so every repository any process in the chunk
  creates starts with the four keys in its **local** config. That includes
  the frozen suites' repositories and the frozen evidence clone (3.1).
  Measured on 2.55.0, a clone made that way, read by a Git whose
  environment is only `PATH`, reports `local false` for `maintenance.auto`
  and `local 0` for `gc.auto`. The default hooks and `info/` files are
  unchanged. A parent `GIT_TEMPLATE_DIR` is always replaced, by the run's
  template or, when none is given, by nothing. Every chunk the executor
  starts therefore runs on the runner's template. A direct `run_chunk`
  call without one gets Git's own template resolution, as today, minus
  any inherited `GIT_TEMPLATE_DIR`.

This layer reaches every Git process a chunk starts, and every repository
a chunk creates, including the frozen suites' own repositories (3.1). Its
`GIT_CONFIG_*` entries are what stopped the orphans in the measured run.

### 5.3 `D-Quiet-Git-Repo`: the per-repository layer

`fixture.py` gains `configure_throwaway_repo(root)`, which writes the four
keys into the repository's local config. `init_git_repo` calls it. Every
site in 3.2 goes through `init_git_repo`, or through
`configure_throwaway_repo` right after its own `clone`. `frozen_runs.empty_repo`
becomes a call to `init_git_repo`, removing the duplicate. Test-specific
extras (`tag.gpgsign` in two modules) stay where they are.

This layer covers what the environment layer cannot: a test module run
directly (`python3 -m unittest tests/test_x.py`) outside the runner, with
no chunk environment and no template.

A static test (`T-QG-4`) parses `tests/*.py`, `tests/parallel/*.py` and
`src/workflow_manager/*.py` with `ast`, skipping `fixture.py` (the helper
itself). Its detection rule, exactly:

- **A site** is one of three node shapes, each matching the exact string
  constant `"init"` or `"clone"` (the *verb*):
  1. an `ast.Call` whose callee's name (`Name.id` or `Attribute.attr`) ends
     in `git` (`_git`, `git`, `run_git`) and whose positional arguments
     include the verb as a constant (`_git(root, "init", ...)`);
  2. an `ast.List` or `ast.Tuple` literal holding the constant `"git"` with
     the verb as a later element (`["git", "init", ...]`,
     `test_implementation_review_two_stage_disposable_repo.py:78`;
     `["git", "clone", ...]`, `test_parallel_runner.py:2646`);
  3. an `ast.List` or `ast.Tuple` literal whose first element is the verb
     (`["init", "-q", "-b", "main"]`, spliced into `["git", "-C", root,
     *args]` by a loop, `test_bootstrap.py:57-63`).
- **Not a site, by construction:** a verb inside a longer string. The only
  such text today is the CI-YAML assertion `'git init -q "$upstream"'` at
  `test_parallel_runner.py:4744`, which checks a workflow file and invokes
  nothing. Shell-string invocations (`shell=True`) are also out of scope;
  there are none.
- **Out of scope:** `git worktree add`. A worktree shares its repository's
  local config, so it inherits whatever that repository has.
- **The site's destination**, the repository it creates, is an expression
  read from the site itself:
  - the last argument after the verb that is **not a string constant**.
    Every option and every option value written as a constant is skipped
    this way, wherever it stands (`"-q"`, `"-b", "main"`, `"--origin",
    "up"`). So `_git(tmp, "clone", "-q", "--no-local", str(root),
    str(cls.clone))` gives `str(cls.clone)`; `["git", "clone", "-q",
    str(scratch), str(path)]` gives `str(path)`; and `_git(tmp, "clone",
    str(src), str(dest), "--origin", "up")` gives `str(dest)`;
  - for an `init` with no such argument, the repository it runs in: shape
    1's first positional argument (`_git(root, "init", "-q", "-b", "main")`
    gives `root`: `"-q"`, `"-b"` and `"main"` are all constants), or shape
    2's `-C` value;
  - otherwise it is **unresolved**. Shape 3 is always unresolved: its list
    names no repository.
  Two consequences fail closed, never open. A destination written as a
  string literal is unresolved. An option value that is not a constant
  (`"-b", branch`) is read as the destination, so the site fails unless it
  is configured on that same expression. Neither shape exists today.
  Applied with `ast` to the 13 sites listed below, the rule gives every
  shape-1 `init` its own first argument (`root`, `self.target`, `path`,
  ...), and the two clones `str(path)` and `str(cls.clone)`. The shape-2
  `init` (`:78`, no `-C`) and the shape-3 list are unresolved, and both
  become `init_git_repo` calls in CP1.
  Destinations are compared as `ast.dump` text after unwrapping one-argument
  `str(...)`, `os.fspath(...)` and `Path(...)` calls, so `str(cls.clone)`
  matches `cls.clone`.
- **The check** binds the configuration to that destination, not just to
  the function. A site passes only when a call to
  `configure_throwaway_repo(D)`, with `D` equal to the site's destination,
  comes after it in the same enclosing function (or, at module level, the
  module). An unresolved destination always fails. For `init` the fix is
  to call `init_git_repo`, which is not a site: it lives in the skipped
  `fixture.py`. For `clone` the fix is `configure_throwaway_repo(<the
  clone's destination>)`. So `test_squash_merge_compat.py`'s `_build`
  (`:104-155`), which holds an `init` (`:106`) and a `clone` (`:152`),
  passes only with `configure_throwaway_repo(cls.clone)` after the clone.
  Configuring `root` there, or calling `init_git_repo(root)`, leaves the
  clone site failing. The failure names the file, line, shape, verb and
  destination (or `unresolved`), and the helper to use.
  Applied literally at the base, the three shapes find 13 sites: 11 `init`
  (including `fixture.py:63`, which the check skips) and 2 `clone`. After
  CP1, the 10 host `init` sites are `init_git_repo` calls, and the 2 clones
  are followed by `configure_throwaway_repo` on their destinations.
- **What it still does not prove.** It reads source; it does not watch Git.
  A helper that takes the verb from a variable escapes it. The runtime
  layers (5.2) and the leak check (5.4) do not depend on it.
- **Exemptions** are an explicit list in the test, each with a reason. It is
  empty at plan time; a false positive CP1 finds goes there, never into a
  looser rule.

### 5.4 `D-Orphan-Check`: the leak check

**The wrapper.** `tests/parallel/reaper.py` is a small, stdlib-only
program, and each chunk runs under it:

```text
python3 -I -S -B tests/parallel/reaper.py --report <run_dir>/orphans/<chunk>.json [--pass-fd <lock fd>] -- <chunk argv>
```

1. It makes itself a child subreaper (`prctl(PR_SET_CHILD_SUBREAPER, 1)`
   through `ctypes`), then starts the chunk command as its only child. The
   environment is unchanged. The run lock's file descriptor is passed on,
   so the lock stays held while any chunk process lives, exactly as today.
   Standard streams are inherited.
2. **Recording.** Until the chunk has exited, it polls every 10 ms. Each
   poll first lists its children (`/proc/self/task/*/children`) and records
   every new pid other than the chunk's. It then drains exited children one
   at a time: `waitid(P_ALL, WEXITED | WNOHANG | WNOWAIT)` names an exited
   child without reaping it; the wrapper records or completes its entry,
   and only then does `waitpid(pid)` reap it.
   - **The label.** An entry's `cmdline` is `/proc/<pid>/cmdline`, joined
     with spaces. Whenever that is empty or unreadable, at listing time or
     at reap time, the label is `[<comm>]` from `/proc/<pid>/comm`, which
     an exiting process and a zombie still have, or `[unknown]` if even
     that is gone. An entry recorded at listing with an empty command line
     is upgraded, from `cmdline` or `comm`, just before it is reaped. This
     matters for Git: a detached maintenance orphan is already exiting when
     it is adopted, so its command line reads empty even while it shows
     state `R` (measured on Git 2.55.0, 3 of 3 commits in a default-config
     repository), and every Git orphan is therefore labelled `[git]`.
   - **One entry per process lifetime.** The "already recorded" set is
     keyed by pid and a pid leaves it when `waitpid` reaps it, so a pid the
     kernel reuses later is recorded again, never merged into the earlier
     entry.
   - **Every pid a wait returns, other than the chunk's, is an orphan and
     is recorded**, whether or not a listing ever saw it alive, so an
     orphan that is adopted and exits between two listings still counts.

   Every child the wrapper has is
   either the chunk or an adopted orphan, so reaping all of them is safe
   here (INV-5), unlike in the runner (3.3).
3. **Termination.** Every live descendant of the chunk is in the wrapper's
   subtree: an orphan is re-parented to the wrapper, and its own children
   follow it when it dies. So `ECHILD` from a wait proves that nothing is
   left. Once the chunk has exited:
   - the wrapper keeps recording and reaping for a grace period of at most
     5 s, so an orphan still finishing can exit on its own, and **ends the
     grace period at once on `ECHILD`**. A chunk that leaves nothing behind,
     the normal case, pays no grace period at all;
   - after the grace period, it kills and reaps **in a loop until
     `ECHILD`**: each pass lists its children, sends `SIGKILL` to every one
     by pid, marks it `killed`, and drains as in step 2. A descendant that
     an adopted orphan forks just before its kill is re-parented to the
     wrapper and caught by the next pass. The loop never ends on a single
     pass.
4. **Report and exit.** It writes the report atomically (temporary file
   plus `rename`): `{"schema_version": 1, "chunk_id": ..., "platform":
   <sys.platform>, "supported": true, "unsupported_reason": null,
   "chunk_status": <the chunk's wait status: exit code or signal>,
   "orphans": [{"pid", "cmdline", "fate": "exited"|"killed"}]}`. It then
   exits with the chunk's status. A chunk killed by signal *n* is
   reproduced by re-raising *n* on the wrapper, so `run_chunk`'s
   classification is unchanged. Python starts with `SIGPIPE` ignored and a
   handler on `SIGINT`, so before re-raising the wrapper resets *n* to
   `SIG_DFL`, unblocks it and sets `RLIMIT_CORE` to 0 (so a re-raised
   `SIGSEGV` dumps no core of the wrapper). If it survives the re-raise
   anyway, it calls `os._exit(128 + n)`, never falling through to exit 0.
5. **Its own faults.** Any exception inside the wrapper's own logic is
   caught at the top: the wrapper still waits for or kills the chunk, then
   runs step 3's kill-and-reap loop until `ECHILD` as a best effort, so
   orphans it already adopted are not handed up. It writes no report,
   prints the error to standard error and exits `125`. It never writes a
   report it cannot stand behind. If that loop itself fails, what it had
   adopted goes to the next subreaper up (5.6).
6. **Unsupported hosts.** Where `prctl` is unavailable or fails, or it
   succeeds but `/proc/self/task/<tid>/children` does not exist (a kernel
   without `CONFIG_PROC_CHILDREN`), it runs the chunk unchanged and writes
   `"supported": false` with `unsupported_reason` (`no-prctl`,
   `prctl-failed` or `no-children-file`). It never runs the check with an
   empty listing. The wrapper only reports this; the runner decides what it
   means (below). **On Linux it is a fault**, whatever the reason: CI and
   the operator's machines are Linux, and a Linux run that silently loses
   its leak check must not pass. Only a non-Linux platform gets OD-4's
   notice.

The executor's timeout and interrupt paths are unchanged. They kill the
chunk's process group, and the wrapper and the chunk are in it. The wrapper
then writes no report. Timeout and interruption are already exit-`2`
faults. Orphans adopted by a wrapper that was killed go to the next
subreaper up; that residual is stated in 5.6.

**The runner.**

- `isolation.run_chunk` launches the wrapper around `argv`. The wrapper is
  located from the runner's own code (`Path(__file__).with_name
  ("reaper.py")` in `isolation.py`), never from the `repo_root` argument:
  `TestRunChunk` calls `run_chunk(self.tmp, ...)`, and nested runners run
  from scratch checkouts.
- Before starting, `run_chunk` deletes any report left by an earlier run,
  as it already does for the record (`isolation.py:389`).
- After an ordinary exit (not the timeout or interrupt paths), the report
  must exist, parse, carry this `chunk_id`, and have a `chunk_status` that
  matches the wrapper's own exit. Anything else (missing, including after
  the wrapper's own `125`; unreadable; malformed; another chunk's) is a new
  infrastructure outcome, `bad_orphan_report`, in
  `INFRASTRUCTURE_OUTCOMES`. Its fault names the chunk and the report path.
  It is never read as "no orphans". A wrapper crash that exits `1` without
  a report is caught by the same rule, so it cannot pass for a chunk's test
  failure.
- `ChunkRun`/`ChunkResult` gain `orphans` (the recorded entries) next to
  `tmp_residue`.
- `ChunkResult.to_json`/`from_json` carry `orphans`, so a CI shard's
  orphans reach `--aggregate`.
- `verdict_of` gains the declarations (`orphan_sources=`) and adds one
  fault per chunk with undeclared orphans:
  `("OrphanProcessError", "<chunk>: <n> orphaned process(es): <count x
  cmdline, most frequent first>")`. It applies in `local_run`, `run_shard`
  and `aggregate`, because all three go through `verdict_of`.
- `ChunkResult` also carries the report's `platform`, `supported` and
  `unsupported_reason`, through the same JSON round trip. `verdict_of`
  adds `("OrphanCheckUnavailableError", "<chunk>: orphan check unavailable
  on <platform>: <reason>")`, an exit-`2` fault, for every chunk whose
  report says `supported: false` on a `platform` starting with `linux`. The
  decision uses the report's own `platform`, so a Linux shard's missing
  check still fails `--aggregate`, wherever the aggregate runs.
- The report prints one check line: `orphan check: on` when every chunk
  was checked, or `orphan check: unavailable on this platform` when the
  only unchecked chunks are non-Linux (OD-4). A Linux chunk without the
  check has already failed the run by the rule above. It also prints a
  `tolerated orphans` section that lists declared orphans by chunk, so they
  are never silent.
- The `evidence:` line and the identity digests do not change. The check
  is a verdict input, not part of the selection's identity.

**Declared sources.** Some tests orphan processes on purpose. The runner's
own `TestRunChunk` exists to kill process groups, and frozen code cannot be
edited. `tests/parallel/resources.json` gains an `orphan_sources` map:

```json
"orphan_sources": {
  "host:test_parallel_runner.py::TestRunChunk": {
    "reason": "kills a chunk's process group on purpose; a grandchild whose parent dies first is re-parented"
  }
}
```

- The `orphan_sources` key is optional; `schema_version` stays `1`.
  `resources.parse` changes from "exactly `{schema_version, resources,
  exclusive}`" to "those three, plus optionally `orphan_sources`, and
  nothing else". An older runner reading the new file refuses it, which is
  fail-closed.
- A key is an exact unit id from the inventory, host or frozen, and
  `reason` must not be empty. An unknown unit is a schema error, as for
  `exclusive`. `resources.load` therefore gains a keyword,
  `orphan_unit_ids`, the ids `orphan_sources` keys are validated against;
  `exclusive` keeps validating against host ids only. When the keyword is
  omitted, `orphan_sources` keys are validated against the host ids, so a
  frozen declaration read by a caller that forgot it is refused, never
  silently accepted. **Every `load` caller in `tests/parallel/` passes
  `orphan_unit_ids=inv.unit_ids()`**: the three in `executor.py` (`:618`,
  `:736`, `:840`) and `planner.plan_checkout` (`planner.py:366`, reached
  from `local_run` and the plan step). The three `executor.py` callers
  pass the declarations to `verdict_of`. The direct calls in
  `test_parallel_runner.py` that load the real `resources.json` (`:290`,
  `:3489`) pass it too; the ones on synthetic files (`:311`, `:2198`,
  `:2622`) need not.
- A chunk's orphans are tolerated only when the chunk contains a declared
  unit. A host chunk is one unit, so a host declaration is exact. A frozen
  chunk normally holds several classes of one suite, so
  `planner.make_chunks` puts every frozen class that has an
  `orphan_sources` entry into a chunk of its own. The rest of its group is
  chunked as before, in `whole_groups` mode too. A frozen declaration is
  then as exact as a host one, and it cannot hide a new orphan from another
  class. With no frozen declaration, no chunk changes, so today's plans and
  their digests are unchanged. `verdict_of` also adds an exit-`2`
  `OrphanDeclarationError` fault for a chunk that holds a declared frozen
  unit alongside any other unit, so a stale or hand-made plan cannot widen
  a declaration. The measured frozen sources are zero, so none is expected.
- **Policy:** an orphan from code this repository owns is fixed at the
  source. The test waits for, or kills and reaps, what it started. It is
  declared only when orphaning is the test's subject. An orphan from frozen
  code is declared, with the frozen class named. CP2 applies this to every
  orphan the check finds. The final inventory, with each source's
  attribution and disposition, goes into the implementation bundle's
  `TEST_RESULTS.md` and `IMPLEMENTATION_SUMMARY.md`, which the
  implementation review is bound to; `docs/ACTIVE_MILESTONE.md` keeps the
  working log.
- The example above is illustrative. Once CP2 wraps `TestRunChunk`'s own
  synthetic chunks in their own inner wrappers, its orphans may shrink to
  the timeout and interrupt tests, or vanish. CP2's inventory decides
  whether it is declared. The report lists a declaration that tolerated
  nothing in the run as `unused`, for information, so a stale one is
  visible.

**Whole-run use.** The wrapper is also the outer probe: `python3 -I -S -B
tests/parallel/reaper.py --report <file> -- python3 tests/run_all.py` runs
the whole suite under one subreaper and reports every orphan that escaped
the per-chunk wrappers. CP3 measures with it.

### 5.5 Tests

A new module, `tests/test_orphan_processes.py`, gets its own exact `full`
rule in `tools/ci/pr_profile_paths.json` (rule 1; `test_stopgap_profile.py`
requires one). All its tests run on Linux; the platform-unavailable case is
tested by forcing `supported: false` through a test seam.

Each test is listed under the checkpoint that can run it.

**CP1** (no wrapper yet):

- **T-QG-1** `chunk_env`: the four pairs are added; a parent's two
  `autoDetach` pairs are kept and not duplicated; a parent pair for one of
  the four keys with a **different** value is kept, ours is appended after
  it, and `git config --get` in a repository under that environment
  returns ours; **the mixed sequence** `maintenance.auto=false` then
  `maintenance.auto=true` gets ours appended, and `git config --get`
  returns `false`; a differently cased last entry
  (`Maintenance.AutoDetach=true`) counts as the same key and gets ours
  appended; a nested call is a no-op; a malformed parent
  `GIT_CONFIG_COUNT` is refused; a parent `GIT_CONFIG_PARAMETERS` setting
  one of the four keys, and an unparsable one, are refused, while one
  setting an unrelated key is kept.
- **T-QG-2** A repository from `init_git_repo`, and a clone configured by
  `configure_throwaway_repo`, report the four values from
  `git config --local`. Under a chunk environment with the run's template
  directory, a plain `git init` and a plain `git clone` (neither helper
  called) report them too, and the new repository's `hooks/` and `info/`
  match a default-template repository's. A direct `run_chunk` call with no
  template, under a parent environment that exports `GIT_TEMPLATE_DIR`,
  runs a chunk whose environment has no `GIT_TEMPLATE_DIR` and still
  carries the four `GIT_CONFIG_*` pairs.
- **T-QG-5** The frozen isolated-test path. Under a chunk environment with
  the run's template directory, the test calls the frozen `2.6.0` engine's
  own `_materialize_pinned_worktree_at_commit` (imported read-only from
  `distribution/workflow/2.6.0/payload/scripts/`; nothing is copied or
  changed). Then, in the scratch clone it returns, a Git whose environment
  is exactly `{"PATH": ...}`, as `_run_named_test_in_scratch` builds it,
  reports `local` scope for all four keys from `git config --show-scope
  --get`. The same clone made without the template reports none of them,
  so the test proves the template is what covers the path.
  **The "without" environment.** The frozen function passes `env=None`
  (`_run`, `:1551`), so it inherits `os.environ`, and inside a gate that
  already carries the chunk's `GIT_TEMPLATE_DIR`. The "without" arm
  therefore makes its call under `unittest.mock.patch.dict(os.environ)`,
  with `GIT_TEMPLATE_DIR` removed, `GIT_CONFIG_GLOBAL=/dev/null` and
  `GIT_CONFIG_NOSYSTEM=1` set, which neutralises an operator's own
  `init.templateDir`. `GIT_CONFIG_COUNT`, every `GIT_CONFIG_KEY_*`/
  `GIT_CONFIG_VALUE_*` and `GIT_CONFIG_PARAMETERS` are removed too. The
  "with" arm sets the same three variables, except that `GIT_TEMPLATE_DIR`
  is the run's template, so the two arms differ only in the template.
- **T-QG-4** The static routing check of 5.3 over the real tree, plus its
  rule on synthetic sources: a positive case for each of the three shapes
  (`_git(root, "init", ...)`, `["git", "clone", ...]`, and a first-element
  `["init", ...]` spliced by a loop); a clone site followed by
  `configure_throwaway_repo` on its destination passes, including through
  `str(...)` unwrapping; **a clone configured only through a call on
  another repository is flagged**: the `_build` shape, a function that
  runs `init`, then `clone` into `cls.clone`, and then calls
  `configure_throwaway_repo(root)` or `init_git_repo(root)`; a
  `configure_throwaway_repo(dest)` that comes before its clone is flagged;
  an `init` site written exactly as `_git(root, "init", "-q", "-b",
  "main")` and followed by `configure_throwaway_repo(root)` passes, so the
  `-b main` value is not read as its destination; a clone with a trailing
  value-taking option, `_git(tmp, "clone", str(src), str(dest), "--origin",
  "up")`, followed by `configure_throwaway_repo(dest)` passes; a clone
  whose destination is a string literal is flagged as `unresolved`; and
  shape 3 is always flagged as `unresolved`; the `:4744` shape,
  a verb inside a longer string, is not flagged; `git worktree add` is not
  flagged.

**CP2** (the wrapper exists):

- **T-QG-3** The environment layer wins where it must. A repository from
  `init_git_repo` has its four local keys unset with `git config --local
  --unset-all` (whether the helper or the run's template wrote them),
  leaving Git's defaults (auto maintenance on, detached). On Git
  2.55.0, the version installed here, that alone is deterministic: every
  `git commit` in such a repository adopted one detached orphan (3 of 3 in
  this round's measurement, 5 of 5 in round 2's review), recorded in
  `TEST_RESULTS.md`. So that an older Git, whose `gc --auto` detaches only
  past a threshold, triggers as well, the control also sets
  `gc.autoPackLimit=1` locally and makes two packs first (a commit, `git
  repack`, a commit, `git repack`), then makes the measured commit. The
  preparation runs in the control's stripped environment below, plus
  `-c maintenance.auto=false -c gc.auto=0` on each of those four commands,
  so that no preparatory command can detach and only the measured commit
  is observed.
  `gc.auto=1` is not used: it counts loose objects in `objects/17/` only,
  so it is not deterministic. CP2 verifies this arrangement on 2.55.0. The
  test prints the Git version it ran on. Before the pull request, CP2
  records the Git version the `ubuntu-latest` runner image documents; if
  it is older than 2.55.0, CP2 also verifies the arrangement on that
  version (a local build or container) rather than learning it from a red
  required check.
  - **The control** makes a commit under the wrapper, in a **stripped**
    environment: `os.environ` minus `GIT_CONFIG_COUNT`, every
    `GIT_CONFIG_KEY_*`/`GIT_CONFIG_VALUE_*` and `GIT_CONFIG_PARAMETERS`,
    with `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` set to `/dev/null`.
    It must record at least one orphan, or the test fails rather than
    skips, because then the test could not see an orphan at all. Stripping
    is what lets the control detach inside a gate, whose own chunk
    environment (and the operator's watchdog exports) already carry the
    keys.
  - **The treatment** makes the same commit from `chunk_env(base=<that
    stripped environment>)`, so the two runs differ only in the layer under
    test. The wrapper records no orphan, and no `gc.pid` or `gc.log`
    appears. Environment-supplied config has command scope, which outranks
    local config (checked with `git config --show-scope`).
  - **The frozen path** (T-QG-5 under the wrapper): a commit in the frozen
    engine's scratch clone, made by a Git whose environment is exactly
    `{"PATH": ...}` plus `-c user.email=... -c user.name=...`, records no
    orphan when the clone came from the template, and at least one when
    the same clone came without it. The second half is this path's own
    control, and its clone is made in T-QG-5's "without" environment.
- **T-OC-1** The wrapper, driven directly:
  - a clean chunk yields `orphans: []` and its exit status (0, 1, 3, and a
    signal death), and **returns well under the 5 s grace period** (it
    ends on `ECHILD`);
  - a chunk killed by `SIGPIPE`, and one killed by `SIGINT`, make the
    wrapper die of that same signal, not exit 0;
  - a chunk that double-forks a `setsid` sleeper yields one `killed` orphan
    with its command line;
  - an orphan whose `cmdline` reads empty while it is listed (a daemon that
    exits at once, and a real `git commit` in a default-config repository)
    is recorded as `[<comm>]`, never `""`; the Git case records `[git]`;
  - an adopted orphan that forks a child right before the final kill: the
    child is still killed and reaped, and the wrapper leaves no process
    behind;
  - a short-lived daemon yields one `exited` orphan;
  - many short-lived daemons, each exiting at once: the recorded count
    equals the number started, including those reaped without ever being
    listed;
  - the wrapper leaves no zombie child behind;
  - the passed lock fd is open in the chunk;
  - forcing each unsupported path through a test seam (no `prctl`, a
    failing `prctl`, and no `children` file) yields `"supported": false`,
    its `unsupported_reason`, the host's `platform` and the chunk's
    status.
- **T-OC-2** `run_chunk` plus `verdict_of`, through the executor:
  - an orphaning synthetic chunk makes the verdict `2` with
    `OrphanProcessError` naming the chunk, in local mode, and in shard mode
    followed by aggregate (through the JSON round trip);
  - a declared unit's orphans are tolerated and listed, and an unused
    declaration is listed as `unused`;
  - an undeclared one in the same run is not;
  - a missing report, a stale report left before the run (deleted, so
    still missing), a malformed one, another chunk's, and a wrapper exit
    `125` each give `bad_orphan_report`, an exit-`2` fault naming the chunk
    and the report path;
  - **a Linux `supported: false`**: a chunk whose wrapper is forced
    unsupported on this Linux host makes the verdict `2` with
    `OrphanCheckUnavailableError` naming the chunk and the reason, in local
    mode, and in shard mode followed by aggregate; the report never prints
    `orphan check: on` for that run;
  - the same report with its `platform` set to `darwin` (through the
    seam) is not a fault: the run is green and prints `orphan check:
    unavailable on this platform` (OD-4);
  - a chunk holding a declared frozen unit and another unit gives
    `OrphanDeclarationError`.
- **T-OC-3** `resources.json` schema: an unknown unit and an empty reason
  are refused; a frozen unit id is accepted for `orphan_sources` and still
  refused for `exclusive`; a frozen `orphan_sources` key loads through
  `planner.plan_checkout` as well as through the three `executor.py`
  paths, and is refused by a `load` call without `orphan_unit_ids`; a file
  without `orphan_sources` still loads; an unknown top-level key is still
  refused; `make_chunks` gives a declared frozen class a chunk of its own,
  in `whole_groups` mode too, and leaves the rest of its group chunked as
  without the declaration; with no frozen declaration, `make_chunks`
  returns exactly the chunks it returned before the change, for the same
  inputs.
- **T-OC-4** The timeout and interrupt paths: the wrapper and the chunk
  die together, the run is `2` for the existing reason, and there is no
  spurious `OrphanProcessError` or `bad_orphan_report`.

Existing tests that assert on the chunk process itself are adapted, not
weakened: its session and group, the passed fd, and the no-descendant
guarantee. `test_parallel_runner.py`'s environment test gains the four
pairs.

### 5.6 Residuals, stated

- **A killed run's orphans.** On timeout, interrupt or `SIGKILL`, the
  wrappers die with their chunks. The same holds for a wrapper whose own
  fault path (5.4 step 5) cannot finish its best-effort kill loop. Orphans adopted afterwards go to the next
  subreaper up, the Controller when one runs the suite. This is bounded by
  the environment layer, which stops Git's maintenance orphans at the
  source.
- **Processes outside chunks.** The runner's own Git calls, the plan step
  and `prepare_merge` do not run under a wrapper. They start no detached
  work, and the outer-probe measurement in CP3 would show it if they did.
- **Non-Linux.** The check is off, and the report says so. On Linux an
  unavailable check is a fault (5.4 step 6), and CI runs on
  `ubuntu-latest`, so every pull request and `main` run enforces it.
- **A repository created inside a from-scratch environment.** Code that
  runs `git init` or `git clone` under an environment it builds itself
  (`{"PATH": ...}`) gets neither the template nor the `GIT_CONFIG_*`
  entries. No such site exists in this repository's code (5.3 routes every
  site through the helpers). A frozen named test could do it inside the
  evidence drivers (3.1); none measured does, and the leak check fails the
  run if one ever orphans.
- **The managed `workflow-conformance.yml`** runs the installed
  `scripts/*_test.py` directly, outside the runner. It is managed (INV-1),
  runs only in CI, and its job's processes end with the job.

## 6. Open decisions (recommendations, for the reviewers and the user)

- **OD-1: the pull-request title's type.** Recommended:
  `test: throwaway test repositories leave no orphaned Git processes`,
  which releases nothing. The only file under `src/` that changes,
  `fixture.py`, ships in the wheel but no product command reaches it
  (3.2). The alternative, `fix:`, would publish a patch release with no
  user-visible change.
- **OD-2: the fault's exit code.** Recommended: `2`, an infrastructure
  fault, like a repository-integrity violation. An orphan is a hygiene
  failure of the run, not a failed assertion. The alternative, `1`, would
  mix it with test failures and their reproduction lines.
- **OD-3: declared sources by unit, not by count or pattern.** Recommended,
  because counts vary run to run (3.4), and an already-exited orphan has no
  command line to match. The declaration is reviewed data with a reason,
  and the report lists every tolerated orphan.
- **OD-4: non-Linux runs.** Recommended: a printed notice, not a refusal.
  CI enforces the check, and local development on macOS keeps working.

No row of a `docs/TECHNICAL_DECISIONS.md` applies: this repository has no
such file. The decisions above are the ones this plan would otherwise
finalize silently.

## 7. Checkpoint registry

Every checkpoint ends with:

- its own targeted tests: `python3 tests/run_all.py --select <modules>`;
- INV-1 and INV-3: the `git diff` of INV-1 is empty, and
  `workflow-manager verify .` is clean;
- the full gate: `python3 tests/run_all.py`, green.

<!-- registry-table:begin -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Git maintenance off at the source: THROWAWAY_GIT_CONFIG, the chunk-environment layer, the shared per-repository setup for every init/clone site, and the static routing check | - | 2 | 1 |
| CP2 | The leak check: the per-chunk subreaper wrapper, OrphanProcessError in every runner mode, declared orphan_sources, and every orphan source fixed or declared | CP1 | 4 | 1 |
| CP3 | Measurement under the whole-run wrapper, ARCHITECTURE.md and CLAUDE.md, and the milestone's evidence | CP1, CP2 | 2 | 1 |
<!-- registry-table:end -->

### CP1: Git maintenance off at the source

- **Files:** `src/workflow_manager/fixture.py` (`THROWAWAY_GIT_CONFIG`,
  `configure_throwaway_repo`, `init_git_repo`);
  `tests/parallel/isolation.py` (`chunk_env`, including
  `GIT_TEMPLATE_DIR`, and `run_chunk` passing the template, both through
  the optional `git_template` argument; the usage
  errors surfaced by `tests/parallel/cli.py`); `tests/parallel/executor.py`
  (building `<run_dir>/git-template/` once per run, and `prepare_merge`'s
  `chunk_env` call); `tests/frozen_runs.py` (`empty_repo`); the host sites
  of 3.2; `tests/test_orphan_processes.py` (new: T-QG-1, T-QG-2, T-QG-4 and
  T-QG-5; T-QG-3 needs the wrapper and lands in CP2);
  `tests/test_parallel_runner.py` (its environment test gains the pairs and
  the template); `tools/ci/pr_profile_paths.json` (its exact rule).
- **Exit:** the targeted modules and the full gate are green.

### CP2: the leak check, and every orphan source fixed or declared

- **Files:** `tests/parallel/reaper.py` (new); `tests/parallel/isolation.py`
  (`run_chunk`, `ChunkRun`, the `bad_orphan_report` outcome);
  `tests/parallel/executor.py` (`ChunkResult` with `platform`/`supported`,
  `verdict_of` with `OrphanProcessError`, `OrphanCheckUnavailableError` and
  `OrphanDeclarationError`, the JSON round trip, the three `resources.load`
  callers); `tests/parallel/planner.py` (`plan_checkout`'s
  `resources.load` call, and `make_chunks`' own chunk for a declared
  frozen class); `tests/parallel/report.py` (the check line and the
  tolerated section); `tests/parallel/resources.py` and `resources.json`
  (`orphan_sources`, schema); `tests/test_orphan_processes.py` (T-QG-3
  with the frozen-path case, T-OC-1 to T-OC-4);
  `tests/test_parallel_runner.py` (adapted assertions); whichever host
  tests turn out to orphan incidentally.
- **Work:** once the mechanism's targeted tests pass, run the full selection
  with the check on. Classify every orphan by chunk under 5.4's policy. Fix
  the incidental sources in this repository's own tests, and declare the
  inherent ones in `orphan_sources`, each with a reason.
- **Log:** the complete orphan inventory (chunk, count, label and
  disposition) goes into `docs/ACTIVE_MILESTONE.md` as the working log, and
  into the implementation bundle's `TEST_RESULTS.md` and
  `IMPLEMENTATION_SUMMARY.md`, which the review is bound to (5.4).
- **Exit:** the full gate is green with zero undeclared orphans, in two
  consecutive runs, because the counts are timing-dependent.

### CP3: measurement, documentation and the milestone's evidence

- **Measure:** repeat 3.4's run at the checkpoint head under the wrapper's
  whole-run use (5.4). Expected: zero orphans reach the outer wrapper, and
  the run's own report has no Git orphan, judged on each entry's label
  (`cmdline`, or `[<comm>]`; 5.4 step 2), so no entry names `git` or
  `[git]`. Record the wall time against
  3.4's rows, for information; it is not a target.
- **Files:**
  - `docs/ARCHITECTURE.md`, "Verification execution": the two settings
    layers, the leak check and its whole-run use, `OrphanProcessError` in
    the exit-`2` list, `orphan_sources`, and 5.6's residuals;
  - the non-managed part of `CLAUDE.md`: one line saying that a run fails
    on orphaned processes and where they are declared.
- **Exit:** the full gate is green. INV-1 to INV-3 hold over the whole
  milestone diff.

## 8. Requirements traceability

| requirement | checkpoints |
| --- | --- |
| REQ-1 throwaway repositories created by this repository's test setup set `maintenance.auto=false` and `gc.auto=0` (plus the two `autoDetach` keys), through one shared helper | CP1 |
| REQ-2 the runner's chunk environment carries the same settings, preserving the parent's `GIT_CONFIG_*` entries and deciding by each key's last value, plus a template directory that writes them into every repository a chunk creates, so the frozen suites' own repositories and the frozen evidence clone are covered; proved to outrank local config under the wrapper | CP1, CP2 |
| REQ-3 a static check keeps every new `git init`/`clone` site on the shared setup, bound to the repository the site creates | CP1 |
| REQ-4 the leak check: a per-chunk subreaper wrapper adopts, records and reaps orphans, and an undeclared orphan, or an unavailable check on Linux, fails the run (exit 2) in local, shard and aggregate modes | CP2 |
| REQ-5 declared orphan sources are reviewed data with a reason, validated against the inventory, exact to one unit (a declared frozen class runs in its own chunk), and always reported | CP2 |
| REQ-6 every orphan the full selection produces is attributed, then fixed at the source or declared; zero undeclared orphans in two consecutive full gates | CP2 |
| REQ-7 before and after measurements with an outer subreaper: zero orphans escape the run, and no Git orphan at all | CP3 |
| REQ-8 no Workflow release; `distribution/`, `migration/`, `scripts/`, `.claude/commands/` and managed content unchanged; no test removed or weakened | CP3 |
| REQ-9 the design recorded in `docs/ARCHITECTURE.md` and the non-managed `CLAUDE.md` | CP3 |

## 9. This milestone's own review logistics

- Governing version `2.2`: two-stage plan review (local, then manual
  external) and two-stage implementation review. The item carries
  `feedback_layout: "scoped"`, so feedback lands in
  `.ai-review/workflow-manager-test-cleanup/feedback/`.
- **The artifacts declaration** is generated from the `process` template and
  fitted to this footprint.
  - **Implementation deliverables, protected at the implementation stage:**
    `tests/`, `src/`, `tools/` (only `tools/ci/pr_profile_paths.json` is
    expected to change), `docs/ARCHITECTURE.md`, `CLAUDE.md`.
  - **Must not change, protected so that any change is reviewed:**
    `distribution/`, `migration/`, `scripts/`, `.claude/commands/`,
    `.github/workflows/workflow-conformance.yml`, `pyproject.toml`,
    `README.md`, `docs/RELEASING.md`, `docs/MIGRATION.md`, and the other
    `.github/` files M1 protected by exact path.
- Running the Controller for this milestone is the user's call, as before.
  Until the fixed Controller is installed between milestones, any run uses
  the operator's one-step workaround.
- The pull request, its CI run (the full matrix, by rule 1) and the merge
  are the user's actions. They belong to the functional review, never to a
  checkpoint's exit.

## 10. `SELF_REVIEWING_PLAN`

- **Coverage.** No test is removed. The leak check is a stricter verdict,
  and 5.4's policy prefers fixing a source to declaring it. A declaration
  tolerates exactly one unit, host or frozen, since a declared frozen class
  runs in its own chunk (5.4), and no frozen declaration is expected: the
  frozen suite measured so far produced none.
- **The roadmap's premise.** It said environment settings were not enough.
  The environment layer is kept anyway, because for this repository it is
  the only layer that reaches the frozen suites' repositories (3.1). The
  per-repository layer the roadmap asks for is kept too, for direct runs
  and scratch environments.
- **Correctness of the reaper.** Reaping lives in a process whose only
  non-adopted child is the chunk, so it cannot steal an exit status the
  runner waits for (INV-5). Signal deaths are re-raised, so the existing
  outcome classification and its tests stand.
- **Unnecessary complexity, removed during self-review:**
  - a reaper thread inside the runner (it races `Popen.wait`; 3.3);
  - an orphan count budget per unit (counts are timing-dependent; OD-3);
  - a CI workflow change (the runner carries the check, so every CI mode
    has it already);
  - a second probe tool (the wrapper's whole-run use measures);
  - a separate checkpoint for attributing orphans (a checkpoint must end on
    a green full gate, and the check is red until its sources are handled,
    so attribution belongs to the checkpoint that adds the check).
- **Performance.** A full plan at the base has 290 phase-A chunks over 8
  shards (`--plan-only` at `7dabd2e`). A clean chunk pays one Python start
  (`-I -S`, stdlib only, tens of milliseconds) and no grace period, since
  the wrapper ends on `ECHILD` (5.4 step 3): about 290 x 0.05 s / 8, around
  2 s over a run of about 370 s. Only a chunk that still has a live adopted
  orphan when it exits pays up to 5 s, and after CP2 that is only a declared
  source. The run's template directory is built once, before any chunk,
  by one `git init` and a copy. An unconditional grace period would have cost about
  290 x 5 s / 8, around 180 s, which is why it is not one. Against that,
  thousands of Git maintenance runs are saved. CP3 records the wall time.
- **Migration risk:** none to Workflow state. Fixture repositories gain four
  local config keys, which no test reads.

## 11. Review dispositions

### Round 1, `LOCAL_MODEL_PLAN_REVIEW` (revision 1, content `fa1d2691`): REVISE

Every finding was checked against the repository before it was applied.

- **IMP-1 accepted.** Confirmed: `--plan-only` at `7dabd2e` reports 290
  phase-A chunks over 8 shards. 5.4 step 3 now states the termination rule
  (`ECHILD` proves nothing is left), ends the grace period on `ECHILD`, and
  kills and reaps in a loop until `ECHILD`. Section 10's performance claim
  is restated against the 290 chunks. T-OC-1 gains the fast-return and
  fork-before-kill cases.
- **IMP-2 accepted.** 5.4 step 2 now peeks with `waitid(..., WNOWAIT)`,
  records any unlisted pid from `/proc/<pid>/comm` (or `[unknown]`) before
  reaping it, and counts every pid a wait returns other than the chunk's.
  T-OC-1 gains the many-short-lived-daemons count case.
- **IMP-3 accepted, all four parts.** (a) `run_chunk` deletes a stale
  report first (as for the record, `isolation.py:386`), and a missing,
  unreadable, malformed or mismatched report after an ordinary exit is the
  new `bad_orphan_report` infrastructure outcome. (b) The wrapper's own
  faults exit `125` with no report, and the missing-report rule catches a
  crash that exits `1`. (c) The re-raise resets the disposition to
  `SIG_DFL`, unblocks the signal, and falls back to `os._exit(128 + n)`.
  (d) The wrapper is located from `isolation.py`'s own `__file__`
  (confirmed: `TestRunChunk` calls `run_chunk(self.tmp, ...)`,
  `test_parallel_runner.py:2776`).
- **IMP-4 accepted.** T-QG-3 moves to CP2, where the wrapper exists, and
  REQ-2's traceability gains CP2. Its control runs in a stripped
  environment, and the treatment is `chunk_env(base=<the same stripped
  environment>)`; `chunk_env` already takes `base=`
  (`isolation.py:272`). The Git version (2.55.0 here) is stated and
  printed by the test.
- **IMP-5 accepted.** 5.3 now defines the rule by AST node shape, covering
  the three shapes named (confirmed at `test_bootstrap.py:57-63`,
  `test_implementation_review_two_stage_disposable_repo.py:78`,
  `test_parallel_runner.py:2646`). The `:4744` CI-YAML literal is out of
  scope by construction, since it is one longer string; `git worktree add`
  is out of scope, and exemptions are an explicit list with reasons.
- **OPT-1 accepted.** Confirmed: `resources.parse` requires exactly three
  top-level keys (`resources.py:89`), and `load` gets host ids only
  (`executor.py:618`, `:736`, `:840`). 5.4 now says that `orphan_sources`
  is optional, `schema_version` stays `1`, the callers pass
  `inv.unit_ids()`, and `verdict_of` gains the declarations in all three
  modes.
- **OPT-2 accepted.** 3.2 states the identity difference. Routing
  `frozen_runs.empty_repo` (and `test_bootstrap.py`'s own `empty_repo`)
  through `init_git_repo` changes their commit identity; no test asserts
  either identity.
- **OPT-3 accepted.** 3.1 now rests on 3.4's measurement and the leak check,
  and names `_load_and_run_named_test` (`2.6.0` `workflow_state.py:11064`).
- **OPT-4 accepted.** 5.2 states that a different parent value is kept and
  ours wins as the last value; T-QG-1 covers it.
- **OPT-5 accepted.** 5.4 step 6: a missing `children` file means
  `"supported": false`, never an empty listing; T-OC-1 forces it.
- **OPT-6 accepted.** The example declaration is marked illustrative, CP2's
  inventory decides, and the report lists an unused declaration.
- **Missing tests:** each is now in 5.5, under the checkpoint that can run
  it.

### Round 2, `LOCAL_MODEL_PLAN_REVIEW` (revision 2, content `9be3dc14`): REVISE

Every finding was checked against the repository before it was applied.

- **IMP-1 accepted.** Reproduced here on Git 2.55.0: under a subreaper
  listing its children every 2 ms, 3 of 3 commits in a default-config
  repository each adopted one Git orphan, and all three read an empty
  `/proc/<pid>/cmdline` with `comm` `git`. 5.4 step 2 now labels any entry
  with an empty or unreadable command line as `[<comm>]` (or `[unknown]`),
  at listing and at reap time, upgrades a listed empty entry before
  reaping, and keys the recorded set per process lifetime. 1.2's and CP3's
  "no Git orphan" are judged on that label. T-OC-1 gains the empty-cmdline
  case, with a real `git commit` recording `[git]`.
- **IMP-2 accepted.** Confirmed: `_build` in `test_squash_merge_compat.py`
  holds `_git(root, "init", ...)` and `_git(tmp, "clone", ...)` in one
  function. 5.3's check is now per verb: a `clone` site passes only on
  `configure_throwaway_repo`. T-QG-4 gains the `init_git_repo`-plus-clone
  negative.
- **OPT-1 accepted.** Confirmed: `planner.plan_checkout` calls
  `resources_mod.load(repo_root, list(inv.host))` (`planner.py:366`).
  `load` gains `orphan_unit_ids`, every caller in `tests/parallel/` passes
  it, a caller that omits it refuses a frozen declaration, and
  `planner.py` joins CP2's files. T-OC-3 covers the planner path.
- **OPT-2 accepted.** T-QG-3's control now names its settings and actions:
  the four local keys unset, plus `gc.autoPackLimit=1` and two packs for an
  older Git. The measured detach rate on 2.55.0 is in `TEST_RESULTS.md`.
  CP2 checks the runner image's Git version before the pull request.
- **OPT-3 accepted.** The orphan inventory also goes into the
  implementation bundle's `TEST_RESULTS.md` and
  `IMPLEMENTATION_SUMMARY.md` (5.4, CP2).
- **OPT-4 accepted.** Confirmed: `test_amendment_update_path.py` has two
  `init` sites (`:112`, `:502`). 3.2 now says eleven sites in ten places,
  and 5.3 states the literal count at the base: 13 sites, 11 `init` and 2
  `clone`, including `fixture.py:63`.
- **OPT-5 accepted.** The wrapper's fault path still runs the
  kill-until-`ECHILD` loop as a best effort before exiting `125`, and 5.6
  names the case where that loop itself fails.
- **Missing tests:** each is now in 5.5, under CP1 (T-QG-4) or CP2 (T-OC-1,
  T-OC-3). Pid reuse is not a test; the per-lifetime keying is stated in
  5.4 step 2.

### Round 3, `LOCAL_MODEL_PLAN_REVIEW` (revision 3, content `abc6f71f`): APPROVE

The approval carried two optional findings. They were not applied then,
since an `APPROVE` round edits nothing. Revision 4 applies both:

- **OPT-1 accepted.** T-QG-3's preparatory commits and repacks now name
  their environment: the control's stripped environment plus `-c
  maintenance.auto=false -c gc.auto=0`, so that only the measured commit
  can detach.
- **OPT-2 accepted.** 5.4 step 2's "every pid a wait returns" paragraph
  was mis-indented and read as a stray line. It is now its own bullet of
  step 2.

### Round 3, `MANUAL_EXTERNAL_PLAN_REVIEW` (revision 3, content `abc6f71f`): REVISE

Every finding was checked against the repository before it was applied.

- **IMP-1 accepted.** Confirmed in the frozen `2.6.0` payload:
  `_materialize_pinned_worktree_at_commit` clones at `workflow_state.py:11734`,
  and `_run_named_test_in_scratch` runs the named test with `env={"PATH":
  ...}` (`:11802`). The clone gets no local keys, and that Git sees no
  environment keys. The fix is test-side, and the payload is unchanged:
  the chunk environment now sets `GIT_TEMPLATE_DIR` to a per-run template
  (Git's default template plus a `config` holding the four keys), so every
  repository any chunk process creates, the frozen clone included, starts
  with the keys in its local config (5.2). This was checked on Git 2.55.0
  before it went into the plan. Under such a template, `git init` and
  `git clone` both wrote the four keys; a `PATH`-only Git in the clone
  read `local false` and `local 0`; the hooks and `info/` files matched a
  default repository's. No suite sets a template (searched: no
  `--template`, `GIT_TEMPLATE_DIR` or `init.templateDir` anywhere under
  `distribution/`, `tests/`, `src/` or `tools/`). The new test is T-QG-5,
  in CP1. It calls the real frozen function and passes only with the
  template. T-QG-3 gains the frozen path's orphan case in CP2. 3.1 and 5.6
  state what remains: a repository created inside a from-scratch
  environment.
- **IMP-2 accepted.** Confirmed on 2.55.0. `maintenance.auto=false` then
  `=true` in `GIT_CONFIG_*` reads `true`. Keys match case-insensitively.
  `GIT_CONFIG_PARAMETERS` outranks every `GIT_CONFIG_COUNT` entry. 5.2 now
  decides by each key's last inherited value, matched case-insensitively,
  and refuses a parent `GIT_CONFIG_PARAMETERS` that sets one of the four
  keys, which nothing appended could outrank. T-QG-1 gains the mixed
  sequence, the case variant and the `GIT_CONFIG_PARAMETERS` cases.
- **IMP-3 accepted.** The report now carries `platform` and
  `unsupported_reason`, and `ChunkResult` carries both through the JSON
  round trip. `verdict_of` makes a Linux `supported: false` an exit-`2`
  `OrphanCheckUnavailableError` in all three modes (5.4 step 6 and "The
  runner"). OD-4's non-Linux notice is unchanged. T-OC-1 and T-OC-2 gain
  the cases, and 1.2 states the fault.
- **IMP-4 accepted.** Confirmed: `_build` (`test_squash_merge_compat.py:104-155`)
  holds both `_git(root, "init", ...)` and `_git(tmp, "clone", ..., str(cls.clone))`,
  so function-level presence let a `root` configuration satisfy the
  clone. 5.3 now reads each site's destination from its own arguments and
  passes the site only on a later `configure_throwaway_repo` call with the
  same destination. An unresolved destination always fails, and
  `init_git_repo` no longer passes a raw `init` site: it replaces the site.
  T-QG-4 gains the configured-on-another-repository case and the
  configured-before-the-clone case.
- **OPT-1 accepted.** 5.4 now gives a declared frozen class its own chunk
  (`planner.make_chunks`, in `whole_groups` mode too), so a frozen
  declaration tolerates one class, exactly as a host one does.
  `verdict_of` refuses a chunk that mixes a declared frozen unit with
  others (`OrphanDeclarationError`). With no frozen declaration, no chunk
  changes. This reverses the self-review's removal of that planner change
  (section 10), which counted only the measured sources and not the
  hiding risk. T-OC-3 and T-OC-2 cover it.
- **Missing tests:** each is now in 5.5: the mixed inherited sequence
  (T-QG-1), the Linux `supported: false` verdict (T-OC-2), a clone
  configured through a call on another repository (T-QG-4), and Git in the
  frozen isolated-test path (T-QG-5, and T-QG-3's frozen-path case).
- **Required acceptance criteria:** the full matrix, the verdicts in
  local, shard and aggregate modes, zero orphans at the outer probe, and
  unchanged frozen payload bytes are 1.2's, CP3's and INV-1's already.

### Round 4, `LOCAL_MODEL_PLAN_REVIEW` (revision 4, content `78db7a2c`): REVISE

Each finding was checked against the repository first. Revision 5 applies
all four.

- **IMP-1 accepted.** Confirmed: under revision 4's rule,
  `_git(root, "init", "-q", "-b", "main")` resolves to the constant
  `"main"`, since `"main"` is a constant that does not start with `-`.
  That contradicts 5.3's own example and T-QG-4. 5.3 now takes the last
  argument after the verb that is **not a string constant**. Every
  constant option and option value is skipped, wherever it stands. This
  round applied the revised rule with `ast` to the real tree. It finds the
  same 13 sites, gives each shape-1 `init` its own repository argument,
  and gives `str(path)` (`test_parallel_runner.py:2646`) and
  `str(cls.clone)` (`test_squash_merge_compat.py:152`) for the clones.
  Two edge cases fail closed, and 5.3 states them: a string-literal
  destination is unresolved, and a non-constant option value is read as
  the destination. T-QG-4 gains the exact `-b main` `init` shape, a clone
  with a trailing `--origin up`, and a string-literal clone destination.
- **OPT-1 accepted.** Confirmed: `paths.record.unlink(missing_ok=True)` is
  at `isolation.py:389`. The citation in 5.4 is corrected. Round 1's
  disposition keeps its original text as a record of that round.
- **OPT-2 accepted.** Confirmed: `TestRunChunk` calls `run_chunk(self.tmp,
  ...)` directly (`test_parallel_runner.py:2776`). 5.2 now makes the
  template an optional `git_template` argument on `chunk_env` and
  `run_chunk`. When it is omitted, `GIT_TEMPLATE_DIR` is removed and the
  `GIT_CONFIG_*` pairs still apply. Removal was chosen over a refusal so
  that the existing direct callers keep working unchanged. T-QG-2 gains
  the direct call.
- **OPT-3 accepted.** Confirmed: the frozen `_run` passes `env=None`
  (`2.6.0` `workflow_state.py:1551`). T-QG-5 now states both arms'
  environments: `patch.dict(os.environ)` with `GIT_CONFIG_GLOBAL=/dev/null`,
  `GIT_CONFIG_NOSYSTEM=1` and the `GIT_CONFIG_*` entries removed, and
  `GIT_TEMPLATE_DIR` either removed or set to the run's template. T-QG-3's
  frozen-path control uses the "without" arm.
- **Missing tests:** both are in 5.5, the destination shapes in T-QG-4 and
  the direct `run_chunk` call in T-QG-2.
