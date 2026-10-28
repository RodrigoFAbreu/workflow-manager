# Active Milestone

## Milestone

`http-read-deadline` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 7, base `0314658`, branch `milestone/http-read-deadline`): roadmap row 15 (#50). A `fix:` pull request title (releases a patch when it merges and `main` is green). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_HTTP_READ_DEADLINE_PLAN.md`.

`_http_read` (`src/workflow_manager/source.py`) no longer runs a worker thread: the connection itself is bounded, so every send and receive on it, a proxy's `CONNECT` exchange included, is clamped to the time left and the socket is closed at the deadline.

Not in this milestone: closing the DNS-resolution residual (a second mechanism, its own item if the review asks for it).

### CP1: the bounded connection, its proof and the architecture note -- complete

- `src/workflow_manager/source.py`: `_Bounded`, the connector, the two connection classes and handlers, the simplified `_http_read`/`_http_fetch`.
- `tests/test_discovery.py`: the new test class and the mutation-proof cases.
- `docs/ARCHITECTURE.md`: the two sentences; `docs/ROADMAP.md` row 15 Current.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 15 is marked Done at acceptance. No version is edited.

### Self-review -- complete

- `src/workflow_manager/source.py`: the owned `connect()` tolerates an `ENOPROTOOPT` from `TCP_NODELAY`, as the base `connect()` does; `tests/test_discovery.py`: a case for it, and the audit-hook case records only during itself.
- Evidence: the fail-first run at `0314658` and the eight mutations of the plan's section 3, each failing the cases the plan names; the full gate (`python3 tests/run_all.py`) exited 0 at head `95228d1` (2320 of 2320 units, 15347 tests, orphan check on).

### Post-fix verification -- complete

- The post-fix implementation review (round 2) approved; the fix is `340622c`, which closes an HTTP error's response and the bounded socket on every failed connect.
- The full gate (`python3 tests/run_all.py`) exited 0 at head `766f368` (2320 of 2320 units, 15349 tests, orphan check on), run after the fix, for the functional review.

## Functional review checklist

The discovery read's connection is now bounded. At the CLI the behaviour must be **unchanged**: the same stderr text, exit codes and timing as before (flows A to C below, each observed on 2026-10-28 with this tree and with the base `0314658`, and identical on both). The one difference, that no thread or socket is left behind, is proven by the automated tests and cannot be seen from a one-shot CLI.

### Setup

Work outside the clone. Nothing may be written into it.

```sh
CLONE=<the milestone/http-read-deadline checkout>
SCR=$(mktemp -d)                                   # outside the clone
mkdir -p "$SCR/home" "$SCR/xdg/config" "$SCR/xdg/cache" "$SCR/xdg/data" "$SCR/tmp" "$SCR/cache" "$SCR/base"
git -C "$CLONE" archive 0314658 src | tar -x -C "$SCR/base"    # the base commit, read-only
wm() {  # wm <src-dir> <command...>: global options go before the command
  env -i HOME="$SCR/home" XDG_CONFIG_HOME="$SCR/xdg/config" XDG_CACHE_HOME="$SCR/xdg/cache" \
    XDG_DATA_HOME="$SCR/xdg/data" TMPDIR="$SCR/tmp" PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
    HTTPS_PROXY="$PROXY" PYTHONPATH="$1" python3 -B -m workflow_manager --release-cache "$SCR/cache" "${@:2}"
}
```

A stall proxy for flows B and C, saved as `$SCR/stall_proxy.py`. It takes a port and `silent` or `trickle`:

```python
import socket, sys, time
port, mode = int(sys.argv[1]), sys.argv[2]
srv = socket.create_server(("127.0.0.1", port))
print("listening", flush=True)
conn, _ = srv.accept()
print("accepted", flush=True)
conn.recv(65536)                      # the CONNECT request; never answered in full
start = time.monotonic()
try:
    while True:
        if mode == "trickle":
            conn.sendall(b"H")        # one byte of a reply that never ends
            time.sleep(1)
        elif not conn.recv(4096):     # silent: b"" once the client hangs up
            break
except OSError:
    pass
print(f"client closed after {time.monotonic() - start:.1f}s", flush=True)
```

No test data is needed. Every flow uses the pins in `published_releases.json` and a fresh `$SCR/cache`.

### Flow A: offline, no network (runs in the sandbox)

1. `PROXY=http://127.0.0.1:9 wm "$CLONE/src" releases`. Port 9 refuses at once, as a stand-in for "no network".
   - Expected: 13 pinned lines, `2.3.1` to `2.12.0`, each `[not cached]`; stderr first: `workflow-manager: could not look for newer releases: cannot fetch https://api.github.com/repos/RodrigoFAbreu/workflow/releases?per_page=100: <urlopen error [Errno 111] Connection refused>`; exit 0; returns at once, not after 20 seconds. (A sandbox with no network gives a different cause after `cannot fetch`; the rest must match.)
2. `PROXY=http://127.0.0.1:9 wm "$SCR/base/src" releases`. Output identical to step 1.

### Flow B: a proxy that trickles, so the 20-second discovery deadline fires (needs a loopback listener)

1. Terminal 1: `python3 -B "$SCR/stall_proxy.py" 18899 trickle`.
2. Terminal 2: `time PROXY=http://127.0.0.1:18899 wm "$CLONE/src" releases`.
   - Expected: terminal 1 prints `listening`, then `accepted`. Stderr: `workflow-manager: could not look for newer releases: the discovery time limit passed`. About 20 seconds (`real` about 20.1 s). Exit 0. Terminal 1 reports `client closed after` about 21 s, one write after the deadline. Nothing is left running once the command returns.
3. Repeat with `wm "$SCR/base/src" releases`. Identical result.

### Flow C: a silent proxy, so the 8-second per-request bound fires first (needs a loopback listener)

1. Terminal 1: `python3 -B "$SCR/stall_proxy.py" 18899 silent`.
2. Terminal 2: `time PROXY=http://127.0.0.1:18899 wm "$CLONE/src" releases`.
   - Expected: stderr `workflow-manager: could not look for newer releases: cannot fetch https://api.github.com/repos/RodrigoFAbreu/workflow/releases?per_page=100: <urlopen error timed out>` after about 8 seconds, not 20. Exit 0. Terminal 1 reports `client closed after` about 8 s.
3. Repeat with the base tree. Identical result.

### Sandbox note

Flow A needs no loopback. Flows B and C need a loopback listener. If a sandbox refuses loopback connections, record B and C as `environment`, a sandbox limit, not a `defect`.

### Known limitations (not defects)

- **A stalled resolver.** A DNS lookup that stalls in `getaddrinfo` cannot be interrupted, so the expired failure waits for the resolver to return. The flows above use a literal loopback address and never resolve a name, so they do not reach this. Documented in the plan's section 2 and `docs/ARCHITECTURE.md`.
- **Other fetches are unchanged.** `ReleaseSource.fetch` (the cache fetch) keeps its own 60-second timeout and has no deadline. A read with no deadline keeps the 60-second timeout and the default handlers.
- **Thread and descriptor residue** is proven by `TestAnExpiredReadLeavesNothingBehind` in `tests/test_discovery.py`, not by these flows.
- **Unchanged:** the error kinds, the size caps, the redirect rules, user-visible text and exit codes.

### Automated evidence (current)

`python3 tests/run_all.py` exited 0 at head `766f368` (2320 of 2320 units, 15349 tests, orphan check on). This includes the loopback tests, which the implementation reviewers' sandbox could not run.

## Next action

No active milestone. The next incomplete roadmap item is the first one in `docs/ROADMAP.md` that is not Done and is not already in flight on another work item (rows 16 to 18 each have their own work item), ready for `/milestone-plan`.
