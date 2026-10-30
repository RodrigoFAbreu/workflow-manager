# Active Milestone

## Milestone

`http-read-test-strength` -- complete (accepted by policy; `governing_workflow_version: "2.2"`, `process`, plan revision 1, base `19b2ffc`, branch `milestone/http-read-test-strength`): roadmap row 20 (#128, items 1 and 2). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_HTTP_READ_TEST_STRENGTH_PLAN.md`.

Two test-strength gaps of the bounded discovery read (row 15) are closed in `tests/test_discovery.py`: the descriptor-leak assertions skip, with a reason that names the platform, where the process's descriptor directory cannot show socket links (instead of comparing empty with empty), and a case now fails when `_Bounded._decref_socketios` stops counting readers. Nothing under `src/` changes.

Not in this milestone: items 3 to 5 of #128 (message wording, the priming test's tree), and any `src/` change.

### CP1: the probe, the reader cases and their mutations -- complete

- `_FD_DIRECTORIES`, `_socket_links(directories=None)` and `_require_socket_links(directories=None)`: the probe opens a `socket.socketpair()` and raises `unittest.SkipTest` unless both new links show. Both leak-checking classes take their baseline from it in `setUp`.
- New class `TestTheDescriptorProbe` (links are read; three stand-ins that cannot expose links skip with their reason; a positive control; both classes honour the probe) and two reader cases in `TestTheBoundedPieces` (a fake socket and a real socket pair, two readers each).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 20 was Current and is Done at acceptance (by policy). No version is edited.

### Mutation results (scratch clone of `974a797`, `python3 tests/run_all.py --select test_discovery.py`)

The candidate passes: 19 of 19 units, 108 tests, exit 0, nothing skipped on this Linux host. Each mutation exits 1 and fails exactly the cases the plan names:

| Mutation | Failed |
| --- | --- |
| `_decref_socketios` calls `_real_close()` | `test_a_second_reader_keeps_the_fake_socket_open`, `test_a_second_reader_still_reads_after_the_first_closes` (the other cases stay green) |
| `_require_socket_links` never raises | the stand-in skip case (all three sub-tests) and `test_both_leak_checking_classes_skip_when_sockets_cannot_be_listed` |
| `_require_socket_links` always raises `SkipTest` | `test_the_helper_sees_a_socket_it_just_opened` (a failure, not a skip) |
| `_socket_links` always returns an empty set | `test_links_are_read` and `test_the_helper_sees_a_socket_it_just_opened` |
| a class's `setUp` takes its baseline with `_socket_links()` | `test_both_leak_checking_classes_skip_when_sockets_cannot_be_listed` |

The scratch clone is deleted; the repository was never mutated.

## Functional review

Flows F1 to F5 from the checklist passed on the candidate (`44b005b`, independent executor, `claude-sonnet-5-5`, round 1): F1 the 18 new or changed tests pass with nothing skipped, F2 to F5 each mutation fails the cases the plan names. The milestone was accepted by policy; the Optional findings are dispositioned in `docs/ai-workflow/registry/http-read-test-strength-dispositions.json` (4 fixed, 4 follow-ups on RodrigoFAbreu/workflow-manager#131) and recorded in `docs/milestones/completed/http-read-test-strength-findings.md`.

## Next action

Roadmap row 20 is Done. The pull request (#132, a `test:` title, nothing released) merges after the acceptance commit. Open follow-ups: issue #131 (the four test-strength items from this milestone's review) and issue #128 (items 3 to 5). Then `/milestone-plan` when one is chosen.
