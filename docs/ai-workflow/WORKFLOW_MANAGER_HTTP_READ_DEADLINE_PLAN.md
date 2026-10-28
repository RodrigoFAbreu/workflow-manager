# Workflow Manager: `_http_read` Releases Its Thread and Socket at the Deadline (Revision 7)

`work_item_id: http-read-deadline` -- `governing_workflow_version: "2.2"`

**Deliverable:** when the shared discovery deadline passes, `_http_read` stops
because the connection itself stops: no worker thread is started, and the
socket is closed before `DiscoveryFailure(expired=True)` reaches the caller.
Nothing is abandoned, so a long-lived caller (a test process) accumulates
nothing. Every caller sees the failure behaviour it saw before, proxy `CONNECT` and TLS
included, with one documented exception: a resolver that stalls in `getaddrinfo` delays the
`expired=True` failure until it returns (section 2, "What (b) leaves").

**Work item type:** `process`. **Base commit:** `0314658` (tip of `main`;
Workflow 2.25.0 installed, automatic gates). **Branch:**
`milestone/http-read-deadline`. **Scope source:** `docs/ROADMAP.md` row 15
(issue #50). A `fix:` pull request title: it releases a Manager patch (a
`src/` change). **Not in this milestone:** the cache fetch `ReleaseSource.fetch`
(its own 60-second per-operation timeout, no deadline, no thread), any change
to the error kinds, the cap, the redirect rules or `Deadline`, and any
user-visible output.

## 1. The defect, as it is today

`_http_read` runs `_http_fetch` in a daemon thread and `join`s it for the time
left on the `Deadline`. When the join times out the caller raises
`DiscoveryFailure(expired=True)` and walks away: the thread stays blocked in
`recv` holding its socket, until the server lets go or the per-request timeout
fires. In the one-shot CLI the process exits; in a test process each expired
read leaves a thread and a file descriptor behind. The first attempt at this
row (three review rounds, recorded on #50) tried to cancel the thread from
outside and found that a thread, a socket and a DNS lookup cannot be cancelled
from outside.

## 2. The mechanism: the connection bounds itself (option b)

**Chosen: every blocking operation on the connection is clamped to the time
left, checked before each one, so no single operation can outlast the
deadline and the caller never needs to give up on anything.** One mechanism,
three small pieces in `src/workflow_manager/source.py`:

1. `_Bounded`, a wrapper around the connected socket that `http.client` uses
   in its place. Before every `sendall` and `recv_into` it calls
   `deadline.timeout()` (which raises `DiscoveryFailure(expired=True)` once
   nothing remains) and sets the socket timeout to what that returns, the
   smaller of the per-request bound and the time left. It also provides
   `makefile`, with the reference counting `socket.socket` does, so
   `urllib`'s `h.close()` after the response headers does not close a socket
   the body still reads from. `HTTPResponse` reads through
   `sock.makefile("rb")`, so `_Bounded.makefile` builds its `SocketIO` over
   the wrapper, never over the real socket (delegating `makefile` to the real
   socket would bypass the `recv_into` clamp entirely); the wrapper therefore
   provides the `recv_into`, `fileno` and `_decref_socketios` that `SocketIO`
   and the reference counting need. A trickling server that returns one byte at a
   time is stopped at the next byte, not after it stops: this is what the old
   test `test_trickling_response_headers_reach_the_deadline` needed a thread
   for.
2. `_bounded_connector(deadline)`, installed as the connection's
   `_create_connection` (a private, undocumented instance attribute that
   `HTTPConnection.__init__` sets, so the subclass assigns it after
   `super().__init__()`): a loop over
   `getaddrinfo` results that sets each connect attempt's timeout from
   `deadline.timeout()`, so several addresses cannot multiply the per-request
   bound past the deadline, and closes every socket it does not return.
3. `_BoundedHTTPConnection` and `_BoundedHTTPSConnection` (subclasses of the
   `http.client` classes: install the connector and **own `connect()`** rather
   than wrapping the base one, because the base `connect()` reads a proxy's
   `CONNECT` reply and runs the TLS handshake before any wrapper could exist).
   What each owned `connect()` keeps from the base: the `http.client.connect`
   audit event (`sys.audit("http.client.connect", self, host, port)`, raised
   first, as the base does, so audit hooks see the same event), `TCP_NODELAY`,
   and, for the TLS server name, the base's rule: `server_hostname` is
   `_tunnel_host` when tunnelling and `host` otherwise (load-bearing for
   certificate checking through a proxy; never `host` alone). The order, in
   both classes: the audit event; the connector's raw socket, wrapped in
   `_Bounded` at once and stored in `self.sock`; `TCP_NODELAY` as the base does; then, when
   `_tunnel_host` is set, the base `_tunnel()`, whose `sendall` and
   status/header reads therefore go through the clamp, so a proxy that trickles
   its `CONNECT` reply is stopped at the deadline with the socket closed. The
   HTTPS class then, **immediately before the handshake**, takes the real socket
   back out of the wrapper, sets its timeout to `deadline.timeout()` (the time
   left *now*, after the TCP connect and any tunnel work, not the budget at
   connect time), runs `self._context.wrap_socket(raw, server_hostname=...)`
   with the name chosen as above, and wraps the resulting TLS socket in a
   fresh `_Bounded`. **The connection cleans up after itself:** everything
   after the first assignment to `self.sock` runs inside a `try` whose
   `except BaseException` closes `self.sock` **only when it is not `None`** and
   sets it to `None` before re-raising (`self.sock` always holds the one
   object to close: the wrapper, then, from the moment the HTTPS class takes
   the real socket back out of it, that raw socket; `wrap_socket` itself
   detaches the raw socket on success and closes the TLS socket on a failed
   handshake). The guard is load-bearing: the base `_tunnel()` answers a
   non-200 `CONNECT` reply (a 407 or 403 from a refusing proxy) by calling
   `self.close()`, which sets `self.sock` to `None`, and then raises
   `OSError("Tunnel connection failed: ...")`; an unguarded `self.sock.close()`
   would raise `AttributeError` from inside the handler and replace that
   `OSError`, which `urllib` would not wrap in `URLError` and `_http_fetch`
   would not catch, so a refusing proxy must still surface as
   `ReleaseUnavailableError(kind="fetch-url")` as at `0314658`. So a trickled
   `CONNECT` reply that hits the deadline, or a `deadline.timeout()` that
   raises before the handshake, leaves nothing open whether or not the caller
   (`urllib`'s `do_open`, or a test driving `connect()` directly) closes the
   connection afterwards. CPython applies the
   socket timeout to the handshake as a whole, so the handshake cannot outlast
   the time left. This reimplementation leans on `_tunnel_host`, `_tunnel()` and
   `_context`, private `http.client` names (section 9), plus two `urllib` handlers that build them. The
   handlers subclass `urllib.request.HTTPHandler` and `HTTPSHandler` and are
   passed to `build_opener` as instances carrying the deadline, beside
   `_RedirectHandler`: `build_opener` drops a default handler only when an
   argument is a subclass or instance of it, so a handler that is not would
   register next to the default `http_open`/`https_open` and could lose to it.
   The HTTPS handler keeps `HTTPSHandler()`'s default SSL context, so
   certificate checking is unchanged. A redirect opens its connection
   through the same handler, so one deadline covers the whole chain.

`_http_fetch` then, when a deadline exists, converts any `OSError` that surfaces
after the deadline has run out (a connect, handshake or read that hit the
clamped timeout) into `DiscoveryFailure("the discovery time limit passed",
expired=True)`, exactly what the thread version raised; before the deadline an
`OSError` is the same `ReleaseUnavailableError(kind="fetch-url")` as today.
`_http_read` loses its thread and calls `_http_fetch` directly. With no
deadline (`ReleaseSource.read(..., deadline=None)`) the plain default handlers
and the 60-second timeout stay as they are.

**Why not the subprocess child (option a).** It would also stop a blocked DNS
lookup (kill the child), which (b) cannot. But it costs an interpreter start
for each of the (up to) four reads of a choosing walk, needs the result, the
cap error and the error kinds carried across a pipe and rebuilt, puts the
`urllib` call out of reach of every in-process test seam, and adds a process
whose reaping the Manager's orphan rule then governs on every error path. That is
more machinery, with a bigger review surface, to cover one pathological case,
and the thread-free in-process path is provable with the same test. Out.

**What (b) leaves, documented rather than hidden.**

* **A blocking DNS lookup.** `getaddrinfo` cannot be interrupted. A resolver
  that stalls delays the failure until it returns (the resolver's own
  timeout); then the connector's next `deadline.timeout()` raises
  `expired=True` and no socket was opened. Nothing is left behind afterwards,
  but the deadline can be overshot by that long, on a network whose resolver is
  broken. (The thread version returned at the deadline in that case, and left a
  thread until the resolver returned.) An IP literal or `localhost` is not
  affected. Stated in `docs/ARCHITECTURE.md`.
* **A TLS handshake and a proxy's `CONNECT` reply are bounded, not
  residual.** The `CONNECT` request and reply go through the wrapper, so each
  operation is clamped to the time left; the handshake runs under a socket
  timeout refreshed to the time left immediately before it, after the TCP
  connect and the tunnel (item 3 above), and CPython applies that timeout to
  the handshake as a whole. What is **not** hermetically provable is a real
  handshake (no certificate on loopback): CP1 proves the refresh with a fake
  clock and a context stub that records the socket timeout it is handed, and
  the real handshake is argued from CPython's whole-call timeout. The
  `CONNECT` path *is* proven on loopback: a plain-HTTP connection with
  `set_tunnel` against a server that trickles the reply (section 3).

## 3. The proof (all in `tests/test_discovery.py`; failing ones first)

A class `TestAnExpiredReadLeavesNothingBehind`. A loopback server runs in the
one thread the test owns and accepts connections sequentially in it (no
per-connection threads, which would also appear in the thread-set difference);
a case with a redirect uses one accepted connection per hop, and the stalled
redirect cases wait for the second hop's `closed` event. It has these
behaviours: `silent` (reads the request, says nothing), `header` (a partial
status line, then nothing), `body` (headers with `Content-Length: 100`, three
bytes, then nothing), `trickle-header` (one header byte at a time),
`trickle-body` (full headers, then one body byte at a time), `late-body-stall`
(full headers sent only after a 1.5 s hold, then the body stalls; run with
`Deadline(2.0)`, the hold a fixture parameter), `redirect-stall`
(a 302 to a path that behaves as `silent`, same server) and `slow-redirect-stall`
(the same, but the server holds the 302 back for 0.6 s of the 1.0 s deadline
before sending it; the delay is a fixture parameter, not an assertion bound),
plus `ok`, `big`
(a body over the cap) and `redirect-ok` for the behaviour that must not change.
A second small fixture, `trickle-connect`, is the same server used as a
proxy: it reads the `CONNECT` request, then sends the reply one byte at a time.
A third mode, `refuse-connect`, replies `HTTP/1.1 407 Proxy Authentication
Required` and the blank line at once.

For each stalled behaviour, with `Deadline(1.0)`:

* `DiscoveryFailure` with `expired=True`, and the wall time under the deadline
  plus a generous 10 seconds (no tuned bound).
* **The client socket is gone:** the server's handler blocks in `recv`/`send`
  until the peer closes and sets a `closed` event; the test waits for it with a
  10-second backstop. No sleep.
* **No thread is left:** the set of live threads, minus the ones that existed
  after the server started, is empty right after the call returns.
* **No descriptor is left:** the set of socket links under `/proc/self/fd`
  (`/dev/fd` where that is absent; the test is skipped where neither lists
  sockets) after the server and listener are closed is a subset of the set
  before the test began. Comparing sets, not counts, keeps the check immune to
  unrelated fds opening and closing.

Behaviour that must not change: `ok` returns the body (and the thread and
socket sets are clean); `big` raises `ReleaseUnavailableError(kind=
"source-response")` and leaves nothing; `redirect-ok` is followed and the 6th
redirect still refuses; a redirect that drops https still refuses (existing
tests, untouched); a refused connection is `ReleaseUnavailableError(kind=
"fetch-url")` before the deadline. The existing trickle test, which called
`_http_read` directly, stays and is now the thread-free proof's twin.

The proxy case drives `_BoundedHTTPConnection` with `set_tunnel` directly
(`_tunnel` is shared by both classes, so no TLS is needed) and calls
**`connect()` alone**, inside `assertRaises((OSError, DiscoveryFailure))`,
never sending a request and never closing the connection itself (`connect()`
converts nothing: the `OSError`-to-`expired` conversion lives only in
`_http_fetch`, so on the last read before the deadline the clamped socket
timeout fires first and `connect()` raises the socket's own `TimeoutError`; a
read that *starts* after the deadline would raise `DiscoveryFailure` from
`deadline.timeout()`, so the case accepts either and requires neither): the `closed` event and the
descriptor-set check therefore prove the cleanup is the connection's own.
The `trickle-connect` fixture sends the reply one byte every 0.2 s and **never
completes it**: it keeps trickling until the peer closes or until a **fixture
end of 5.0 s** (a fixture parameter, well beyond the asserted bound), then
closes its side, so the only way the call ends before 5.0 s is the client
giving up, and no run can hang. Checks, under `Deadline(1.0)`:
the exception is a `TimeoutError`/`OSError`, or a `DiscoveryFailure` with
`expired=True`, and `deadline.remaining() <= 0` afterwards; wall time under the deadline plus a fixture-derived margin of
five trickle intervals (1.0 s), which a mutant that finishes the tunnel late
cannot meet, because the fixture never finishes the reply; the `closed` event within the
10-second backstop; and the thread-set and descriptor-set checks as for the
stalled behaviours. Running the tunnel before the wrapper is installed (the raw
socket keeping its connect-time timeout of about 1.0 s, which a byte every
0.2 s never trips) makes `connect()` run until the fixture's 5.0 s end, where it
ends at the fixture's 5.0 s close having read a partial but parseable
`HTTP/1.1 200 Connectio` status line, so `_tunnel()` accepts it and
`connect()` returns normally: the expected exception is not raised and the
wall time is about 5 s, over the 2.0 s bound, so the case fails on both:
deterministic, and terminating. The case is not a
fail-first claim at `0314658`, where the thread version gave up at the join.

The refusing proxy is a separate case on the same direct-`connect()` footing:
with `refuse-connect`, `connect()` raises `OSError` (not `AttributeError`, and
not `DiscoveryFailure`), `sock` is `None`, the `closed` event is set within the
backstop and the descriptor-set check passes, with the test never closing the
connection. The same refusal driven end to end through `_http_read` gives
`ReleaseUnavailableError(kind="fetch-url")`, and a `trickle-connect` twin
through `_http_read` gives `DiscoveryFailure(expired=True)` with the thread and
descriptor sets clean: this is where `expired=True` for the proxy path is
asserted, because `_http_fetch`'s conversion applies there. Both end-to-end
cases reach the fixture by one seam: `_http_read` and `_http_fetch` take no
handler argument, `build_opener`'s default `ProxyHandler` reads `https_proxy`
and `proxy_bypass` honours `no_proxy`, so the cases patch the environment
(`https_proxy` set to the fixture, `no_proxy` and `NO_PROXY` cleared, with
`mock.patch.dict(os.environ, ...)`) and use a host the bypass list cannot match
(`https://example.invalid/...`, never `localhost` or `127.0.0.1`), so a
developer's own `no_proxy` cannot route the case around the fixture.

Unit cases for the pieces: the connector tries the next address after an
`OSError` and re-raises the last; a connect that runs past a fake-clock
deadline stops before the second address (`expired=True`); a resolver that
advances a fake clock past the deadline then returns opens no socket (the DNS
residual, bounded as stated); `_BoundedHTTPSConnection.connect` hands
`wrap_socket` a socket whose timeout is the time left *after* the connect: with
a connector stub that advances a fake clock by 1.5 s of a 2.0 s deadline, and a
context stub whose `wrap_socket` records `gettimeout()` and returns a fake TLS
socket, the recorded value is the remaining 0.5 s (never 2.0), and the final
`sock` is a `_Bounded` around the stub's result. The same case with a tunnel
host confirms the refresh happens after `_tunnel()`. An exhausted deadline
between connect and handshake raises `expired=True` without calling
`wrap_socket`, **and the stub socket the connector returned is closed and
`sock` is `None` afterwards, with the test never closing the connection** (the
connection's own cleanup, item 3). The same cleanup is shown for
`wrap_socket` itself raising (the stub socket the connector returned is closed
and `sock` is `None`), and for the HTTP class when `_tunnel()` raises.
The `server_hostname` rule: the context stub records it, and it is the tunnel
host when `set_tunnel` was called and the connection host otherwise; the
`http.client.connect` audit event is raised once per `connect()` (a
`sys.addaudithook` recorder, installed only for that case). `_Bounded`'s
reference counting: the real socket stays open while a `makefile` reader is
open after `close()`, and closes when the reader does.

**Which cases are regression proof.** The old `_http_read` computes
`deadline.timeout()` once and gives that value to the worker, so for `silent`,
`header`, `body` and `redirect-stall` the worker's own socket timeout fires a
few milliseconds after `join` gives up and it closes its socket by itself: the
old code passes the `closed` assertion on those, and fails the "no thread right
after return" check only by that margin, which a loaded parallel gate can
reverse. `trickle-body` is no better: `_read_capped` already checks the
deadline after every chunk, so the old worker raises `expired=True` at the first
body byte after the deadline and closes its socket, outliving `join` by at most
one trickle interval. Those five are behaviour checks of the new code, not
regression proof (`trickle-body` is the twin of the existing
`test_a_trickling_body_reaches_the_deadline`). Three cases deterministically
show the defect on the old code, and are the fail-first and
thread-version-mutation evidence:

* `trickle-header`: header parsing in `http.client` has no deadline check and
  the per-operation timeout never fires, so the worker lives as long as the
  server trickles.
* `slow-redirect-stall`: the second hop's socket gets a fresh full timeout
  after 0.6 s are spent, so the worker and its socket outlive the deadline by
  about 0.6 s: the thread check fails first, by a wide margin; the `closed`
  assertion alone does not discriminate there, since the worker closes at about
  1.6 s, inside the 10-second backstop.
* `late-body-stall`: the headers arrive after 1.5 s of the 2.0 s deadline, and
  the old worker's body `recv` then gets a fresh full timeout, so the worker
  and socket outlive the deadline by about 1.5 s (thread check). It is also the
  case that shows the pre-`recv_into` clamp matters for the body: with the
  clamp removed, the body `recv` keeps the timeout set at connect and the call
  returns about 1.5 s after the deadline. This case alone asserts a wall time,
  under the deadline plus half the hold (0.75 s), the margin being the fixture
  hold and not a tuned bound.

**Fail first, and mutate.** Written and run first against `0314658`:
`trickle-header`, `slow-redirect-stall` and `late-body-stall` fail on the
thread check (the worker is alive and holds the socket); no claim is made about
the others, which may pass or fail it by a narrow scheduling margin (above).
After
the change: green. Failure-only mutations, each run once and recorded:
restoring the thread version fails those three (and is not claimed to fail the
other stalled cases); removing the pre-`recv_into` clamp fails
`trickle-header` and `late-body-stall` (`silent`, `header`, `body`,
`trickle-body` and `slow-redirect-stall` pass it, because the connect-time
clamp already set the socket timeout to about the time left); removing the
`OSError`-to-`expired` conversion fails the `silent` case (the clamped timeout
surfaces as `fetch-url`); making `_Bounded.close()` ignore its readers fails
`body` alone (the next `recv_into` meets a closed socket and surfaces as
`fetch-url` before the deadline; `ok` and `big` are not claimed to fail it,
since a short response, or a body that crosses the cap within the first
buffered read, never needs another socket read); running the tunnel before the
wrapper is installed fails both `trickle-connect` cases (the direct one by wall
time and the missing exception, the end-to-end twin by `expired` and wall time); skipping the timeout
refresh before `wrap_socket` fails the fake-clock TLS case (it records 2.0, not
0.5); removing the connection's own close-on-exception from `connect()` fails
the direct `trickle-connect` case (the `closed` event waits out its backstop) and the
pre-handshake unit case (the stub socket stays open and `sock` is not `None`);
dropping the `is not None` guard fails the `refuse-connect` case (`AttributeError`
instead of `OSError`). Every mutation terminates: the `trickle-connect` mutants
by the fixture's 5.0 s end, the others by the 10-second backstops.
Nothing in these paths writes a file, so the "no write" proof is the
thread/socket sets above plus the existing test that discovery leaves the tree
byte-identical.

## 4. Docs

`docs/ARCHITECTURE.md`, the source paragraph that says "the choosing walk is
in memory, size-capped and under one 20-second deadline": it gains the
mechanism in two sentences (every read and write on the connection, a proxy's
`CONNECT` exchange included, is clamped to the time left, the TLS handshake gets
the time left as of just before it, and the socket is closed at the deadline, so
no thread is used) and the one residual (a resolver that stalls delays the failure until it
returns). No page names a milestone. `docs/ROADMAP.md` row 15 is marked
Current in CP1 (its "Later: low priority ..." text replaced) and Done at
acceptance.

<!-- Registry table generated by workflow_state.render_registry_markdown. -->

## 8. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The bounded connection, its proof and the architecture note | - | 3 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the bounded connection, its proof and the architecture note

**Files:** `src/workflow_manager/source.py`, `tests/test_discovery.py`, `docs/ARCHITECTURE.md`.

Order: the section 3 tests first, recorded failing at `0314658`; then
`_Bounded`, the connector, the two connection classes (each owning `connect()`)
and handlers, and the
simplified `_http_read`/`_http_fetch` (the `threading` import goes if nothing
else uses it); then the two architecture sentences. Row 15 of
`docs/ROADMAP.md` is marked Current here.

Evidence: the new tests fail first and are green after; the eight mutations of
section 3 each fail the named test; `python3 tests/run_all.py --select
test_discovery.py`, `--select test_docs.py` and `--select test_release_source.py`
green; a scratch run against a loopback server that stalls, with `lsof`-free
before/after counts of threads and sockets printed; the full gate green, run
last. A `check-title` of `fix: release the worker thread and socket of an
expired discovery read` passes.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** docs/ROADMAP.md and docs/ACTIVE_MILESTONE.md, written by the acceptance step.

Row 15 Done at acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone.
Both stay excluded at both stages, as in every item. No version is edited: the
`fix:` title releases a patch when it merges and `main` is green.
<!-- /CP2 -->

## 9. Risks

* **Size.** About 70 new lines of source (down 25 for the thread), one test
  class of about 150 lines, two doc sentences: under the 400-line guard, one
  mechanism. If the review wants the DNS residual closed, that is the subprocess
  child, a second mechanism: it would split into its own item, not grow this
  one.
* **`http.client` internals.** `_create_connection` is a private, undocumented, stable
  attribute (public in effect since Python 3.2, used the same way by other
  libraries); `connect()` is reimplemented using the private `_tunnel_host`,
  `_tunnel()` and `_context`, also unchanged in the parts used since 3.2 (the
  tests exercise each on 3.14, and fail loudly if a name disappears); the wrapper relies on `HTTPResponse` calling only `makefile`, and
  `HTTPConnection` only `sendall`, `close`, `setsockopt` and `makefile`, all
  covered by the tests on Python 3.14 (the project's floor is 3.11; the
  attribute and the calls are unchanged there).
* **A cap error inside the body** closes the stream through the existing `with`;
  the `big` case proves no socket remains.
* **Overshoot on a broken resolver** (section 2): documented, tested as far as
  a fake clock can, and a deliberate trade for removing the thread.

## 10. Open decisions

None: nothing here finalises a row of `docs/TECHNICAL_DECISIONS.md` (the file
does not exist in this repository). The DNS residual is a stated trade for the
reviewer to confirm or send to a split.
