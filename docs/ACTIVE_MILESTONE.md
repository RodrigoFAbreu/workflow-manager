# Active Milestone

## Milestone

`discovery-test-cleanup` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `fd423fa`, branch `milestone/discovery-test-cleanup`): roadmap row 31 (#131, items 1 to 3). A `test:` pull request title (releases nothing).

The bounded-read tests of `tests/test_discovery.py` identify the sockets they count, by the descriptor probe's own rules. The positive control decides "this host can list sockets" from what the first existing descriptor directory of `_FD_DIRECTORIES` shows (`_lists_links`) and skips with the probe's one wording (`_blind_reason`). The probe and the control look for the socket pair's own links (`socket:[<inode>]` from `os.fstat` of each end, `_own_links`) instead of counting two new links in a before/after difference, so a descriptor another thread opens or closes between two listings disturbs neither. Four lines of dead setup (`recv_into`, `fileno` on the fake socket, in two tests) are deleted. Item 4 of the issue was already fixed on main. Test code only: no `src/` change, no printed text, no Workflow change.

### CP1: the probe and its control identify what they count -- complete

- `tests/test_discovery.py` only (commit `392ffe1`): `_blind_reason`, `_own_links`, `_lists_links`; the probe and the control rewritten; the growing-listing test and the coupling test added (`TestTheDescriptorProbe` has 6 tests); the four dead lines removed.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 31 is Current (Done at acceptance); this record.

### Failure-only mutations

Plan section 3, run in a scratch copy of `392ffe1` made with `git archive` (not a repository; the offline `run` of plan section 5: empty scratch lock, empty release cache, `python3 -I -B`). The unmutated copy passes the 6 probe tests; each mutation fails exactly what the plan names:

| # | Mutation | Result |
| --- | --- | --- |
| M1 | control decides with the literal `/proc/self/fd` | `test_the_control_skips_exactly_where_the_probe_does`, both cases |
| M2 | control words its own skip | the same test, both cases |
| M3 | control decides by existence only (`return True`) | the same test, `regular files` case only |
| M4 | control leaves one end open | `test_the_helper_sees_a_socket_it_just_opened` |
| M5 | `_own_links` names the wrong inodes | `test_the_helper_sees_a_socket_it_just_opened` |
| M6 | the probe never skips | `test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason` (three subtests), plus the leak classes' skip test, the coupling test and the growing-listing test (13 s on all of `TestTheDescriptorProbe`: the leak classes then run for real) |
| M7 | a bounded read leaks one socket (`src/workflow_manager/source.py`, scratch copy only) | the leak checks of `TestAnExpiredReadLeavesNothingBehind` fail (needs loopback sockets) |
| M8 | the directory list is blind (a missing path, and a directory of one regular file) | comparison: on `fd423fa`'s file the control **fails** in both variants; on the change it **skips** with the probe's reason in both |
| M9 | the probe counts again | `test_the_probe_names_the_pairs_own_links_not_new_ones` |
| M10 | the control counts again | `test_the_helper_sees_a_socket_it_just_opened` (the bystander makes four new links) |

### Self-review

Pending (step 2).
