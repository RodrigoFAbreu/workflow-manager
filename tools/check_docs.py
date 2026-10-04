#!/usr/bin/env python3
"""Offline documentation checks (standard library only).

Run ``python3 tools/check_docs.py [--root DIR]``: exit 0 when clean, 1 with
one line per problem. ``tests/test_docs.py`` runs it on the repository and
exercises every rule on synthetic trees. Nothing here touches the network or
runs the Manager.

Rules:

1. Links and anchors: every relative Markdown link and ``#anchor`` in the
   scoped pages resolves to a file and, for Markdown targets, to a heading
   slug (GitHub's ``github-slugger`` rule). Links into the sibling
   repositories must be well formed (never fetched); other hosts must be
   allow-listed.
2. Commands and flags: every ``workflow-manager`` line in a fenced code block
   of a command page parses under ``workflow_manager.cli.build_parser()``
   (never run), with every terminating action (``--version``, ``--help``)
   replaced by a recording no-op.
3. Page header and internal ids on the user pages.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shlex
import sys
import typing
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The user pages: header and internal-id rules.
USER_PAGES: tuple[str, ...] = (
    "README.md",
    "docs/README.md",
    "docs/install.md",
    "docs/update.md",
    "docs/verify.md",
    "docs/troubleshooting.md",
    "docs/glossary.md",
    "docs/development.md",
    "docs/releases/README.md",
)

#: The pages whose fenced code blocks are command-checked.
COMMAND_PAGES: tuple[str, ...] = (
    "README.md",
    "docs/install.md",
    "docs/update.md",
    "docs/verify.md",
    "docs/troubleshooting.md",
    "docs/development.md",
)

#: Pages the link check skips: Workflow commands rewrite the first, the others
#: are records (see docs/README.md). docs/ai-workflow/, docs/milestones/ and
#: docs/defects/ are not matched by LINK_GLOBS at all.
LINK_EXCLUDED = ("docs/ROADMAP.md", "docs/ACTIVE_MILESTONE.md")
LINK_GLOBS = ("README.md", "docs/*.md", "docs/releases/*.md")

#: External hosts allowed besides github.com repository links.
ALLOWED_HOSTS = frozenset({"pipx.pypa.io", "cli.github.com", "img.shields.io"})
GITHUB_OWNER = "RodrigoFAbreu"
GITHUB_REPOS = frozenset({"workflow-controller", "workflow-manager", "workflow"})

HEADER_RE = re.compile(r"^> For: .+\. Last checked with: .+\.$")
INTERNAL_ID_RES = (re.compile(r"\bCP\d+\b"), re.compile(r"\b[A-Z]{2,5}-R\d+-\d+\b"),
                   re.compile(r"\b[MW]\d+[a-z]?\b"))


# ---------------------------------------------------------------------------
# Markdown reading.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


def split_fences(text: str) -> list[tuple[str, str, list[str]]]:
    """``[(kind, info, lines)]`` with ``kind`` ``"text"`` or ``"fence"``;
    ``info`` is a fence's info string. A fence closes on a line of the same
    character, at least as long, with nothing after it."""
    out: list[tuple[str, str, list[str]]] = []
    current: list[str] = []
    fence: tuple[str, int, str] | None = None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                if current:
                    out.append(("text", "", current))
                current = []
                fence = (m.group(1)[0], len(m.group(1)), m.group(2).strip())
            else:
                current.append(line)
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
                out.append(("fence", fence[2], current))
                current = []
                fence = None
            else:
                current.append(line)
    if fence is not None:
        out.append(("fence", fence[2], current))
    elif current:
        out.append(("text", "", current))
    return out


def prose(text: str) -> str:
    """The text outside code fences."""
    return "\n".join("\n".join(lines) for kind, _, lines in split_fences(text) if kind == "text")


_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def headings(text: str) -> list[tuple[int, str]]:
    """``[(level, heading text)]`` for every ATX heading outside fences."""
    found = []
    for line in prose(text).split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            found.append((len(m.group(1)), m.group(2)))
    return found


def slug_base(heading: str) -> str:
    """``github-slugger``: link markup reduced to its text, inline-code
    backticks removed but the code text kept, lowercased, every character
    but letters, digits, underscores, hyphens and spaces removed, spaces
    become hyphens."""
    text = _LINK_TEXT_RE.sub(r"\1", heading).replace("`", "")
    text = text.lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> list[str]:
    """Every anchor of a page, in heading order. A slug already taken gets
    the first ``-N`` (N from 1) that is itself not taken."""
    used: set[str] = set()
    result = []
    for _, heading in headings(text):
        base = slug_base(heading)
        slug = base
        n = 0
        while slug in used:
            n += 1
            slug = f"{base}-{n}"
        used.add(slug)
        result.append(slug)
    return result


_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1", re.S)
# One scanner for CommonMark's inline-link grammar (spec 0.31.2, 6.3 "Links")
# and link-reference-definition grammar (4.7). Both forms share one
# destination and one title sub-grammar, so they cannot drift apart:
#   destination: ``<...>`` (no line break, spaces allowed) or a non-empty run
#                of non-space characters with balanced parentheses;
#   title:       ``"..."``, ``'...'`` or ``(...)``.
# Link text may contain balanced brackets. Backslash escapes the next character.
_DEFINITION_START_RE = re.compile(r"^(?:[ \t]{0,3}>)*[ \t]{0,3}\[(?!\^)([^\]\n]+)\]:", re.M)
_BLOCK_QUOTE_PREFIX_RE = re.compile(r"(?:[ \t]{0,3}>)*[ \t]*")
_SPACE_RE = re.compile(r"\s*")
_BLANKS_RE = re.compile(r"[ \t]*")


class LinkSpan(typing.NamedTuple):
    kind: str  # "inline" or "definition"
    label: str  # the definition's label; "" for an inline link
    target: str
    target_span: tuple[int, int]
    span: tuple[int, int]  # the whole link, from ``[`` to the closing ``)``/title


def _parse_destination(s: str, i: int) -> tuple[str, int, int] | None:
    """``(destination, start, end)`` of the destination at ``i``, or ``None``."""
    n = len(s)
    if i < n and s[i] == "<":
        j = i + 1
        while j < n and s[j] not in "<>\n":
            j += 2 if s[j] == "\\" else 1
        if j < n and s[j] == ">" and j > i + 1:
            return s[i + 1:j], i + 1, j + 1
        return None
    j, depth = i, 0
    while j < n and not s[j].isspace():
        c = s[j]
        if c == "\\" and j + 1 < n:
            j += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                break
            depth -= 1
        j += 1
    if j == i or depth != 0:
        return None
    return s[i:j], i, j


def _parse_title(s: str, i: int) -> int | None:
    """The end of the title starting at ``i``, or ``None``."""
    n = len(s)
    if i >= n or s[i] not in "\"'(":
        return None
    close = ")" if s[i] == "(" else s[i]
    j = i + 1
    while j < n and s[j] != close:
        if s[j] == "\\":
            j += 1
        elif s[i] == "(" and s[j] == "(":
            return None
        j += 1
    return j + 1 if j < n else None


def _matching_bracket(s: str, i: int) -> int | None:
    """The index of the ``]`` closing the ``[`` at ``i`` (brackets balance)."""
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 1
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return None


def _inline_link(s: str, i: int) -> tuple[int, str, int, int] | None:
    """``(close, destination, start, stop)`` for the inline link opening at
    ``s[i] == "["`` (``stop`` is the index after ``)``)."""
    close = _matching_bracket(s, i)
    if close is None or close + 1 >= len(s) or s[close + 1] != "(":
        return None
    j = _SPACE_RE.match(s, close + 2).end()
    dest = _parse_destination(s, j)
    if dest is None:
        return None
    target, start, j = dest
    k = _SPACE_RE.match(s, j).end()
    if k > j:
        title_end = _parse_title(s, k)
        if title_end is not None:
            k = _SPACE_RE.match(s, title_end).end()
    if k < len(s) and s[k] == ")":
        return close, target, start, k + 1
    return None


def _scan_inline(s: str, lo: int, hi: int) -> list[tuple[int, int, int, int, str, bool]]:
    """Inline links opening in ``s[lo:hi]``: ``(open, start, stop, tstart,
    target, image)``. A link may not contain another link, so an outer link
    holding an inner (non-image) link is dropped."""
    found = []
    i = lo
    while i < hi:
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "[":
            m = _inline_link(s, i)
            if m is not None:
                close, target, tstart, stop = m
                image = i > 0 and s[i - 1] == "!"
                inner = _scan_inline(s, i + 1, close)
                found.extend(inner)
                if image or not any(not x[5] for x in inner):
                    found.append((i, i, stop, tstart, target, image))
                i = stop
                continue
        i += 1
    return found


def _scan_definitions(s: str) -> list[LinkSpan]:
    found = []
    for m in _DEFINITION_START_RE.finditer(s):
        j = m.end()
        k = _BLANKS_RE.match(s, j).end()
        if k < len(s) and s[k] == "\n":
            k = _BLOCK_QUOTE_PREFIX_RE.match(s, k + 1).end()
        dest = _parse_destination(s, k)
        if dest is None:
            continue
        target, start, end = dest
        stop = None
        for candidate in (_title_on_line(s, end), end):
            if candidate is None:
                continue
            rest = _BLANKS_RE.match(s, candidate).end()
            if rest >= len(s) or s[rest] == "\n":
                stop = rest
                break
        if stop is not None:
            found.append(LinkSpan("definition", m.group(1), target, (start, end), (m.start(), stop)))
    return found


def _title_on_line(s: str, end: int) -> int | None:
    k = _BLANKS_RE.match(s, end).end()
    return _parse_title(s, k) if k > end else None


def scan_links(text: str) -> list[LinkSpan]:
    """Every inline link (in order) then every link-reference definition (in
    order) of ``text``."""
    inline = [LinkSpan("inline", "", target, (tstart, tstart + len(target)), (o, stop))
              for o, _, stop, tstart, target, _ in sorted(_scan_inline(text, 0, len(text)))]
    return inline + _scan_definitions(text)


# A label starting with ``^`` is a GitHub footnote, not a link.
# ``a[i][j]`` (a word character right before the ``[``) is prose, not a
# reference link; put such text in a code span.
_REFERENCE_RE = re.compile(r"(?<![\w\]])\[(?!\^)((?:[^\]\n]|\n)+?)\]\[([^\]\n]*)\]")
_AUTOLINK_RE = re.compile(r"<([a-z][a-z0-9+.-]*:[^<>\s]+)>", re.I)
# GFM extended autolinks: a bare ``http(s)://`` or ``www.`` URL in prose.
_BARE_URL_RE = re.compile(r"(?<![\w/@.=-])((?:https?://|www\.)[^\s<]+)", re.I)


def _body(text: str) -> str:
    """Prose with inline code blanked out."""
    return _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), prose(text))


def _label(label: str) -> str:
    return " ".join(label.lower().split())


def _blank(match: re.Match) -> str:
    return " " * len(match.group(0))


def _trim_bare_url(url: str) -> str:
    """GFM: drop trailing punctuation and an unbalanced closing ``)``."""
    while url:
        last = url[-1]
        if last in "?!.,:*_~;'\"":
            url = url[:-1]
        elif last == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def bare_urls(text: str) -> list[str]:
    """Bare URLs of ``text`` (already free of inline links, definitions,
    reference links and ``<...>`` autolinks, which are blanked first)."""
    for link in reversed(sorted(scan_links(text), key=lambda x: x.span)):
        text = text[:link.span[0]] + " " * (link.span[1] - link.span[0]) + text[link.span[1]:]
    for pattern in (_REFERENCE_RE, _AUTOLINK_RE):
        text = pattern.sub(_blank, text)
    found = []
    for m in _BARE_URL_RE.finditer(text):
        url = _trim_bare_url(m.group(1))
        found.append("https://" + url if url.lower().startswith("www.") else url)
    return found


def links(text: str) -> list[str]:
    """The target of every link form outside code fences and inline code:
    inline links, reference-link definitions, ``<...>`` autolinks and bare
    URLs."""
    body = _body(text)
    found = [link.target for link in scan_links(body)]
    found += [m.group(1) for m in _AUTOLINK_RE.finditer(body)]
    found += bare_urls(body)
    return found


def blank_link_targets(text: str) -> str:
    """``text`` with every link target (all forms of :func:`links`) removed,
    so a target is never scanned as prose."""
    for link in sorted(scan_links(text), key=lambda x: x.target_span, reverse=True):
        text = text[:link.target_span[0]] + text[link.target_span[1]:]
    text = _AUTOLINK_RE.sub(lambda m: m.group(0).replace(m.group(1), ""), text)
    return _BARE_URL_RE.sub(lambda m: m.group(0).replace(_trim_bare_url(m.group(1)), ""), text)


def undefined_references(text: str) -> list[str]:
    """Labels used by ``[text][label]`` / ``[label][]`` with no definition."""
    body = _body(text)
    defined = {_label(link.label) for link in scan_links(body) if link.kind == "definition"}
    missing = []
    for m in _REFERENCE_RE.finditer(body):
        label = _label(m.group(2) or m.group(1))
        if label not in defined:
            missing.append(label)
    return missing


# ---------------------------------------------------------------------------
# Rule 1: links and anchors.
# ---------------------------------------------------------------------------


def link_pages(root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in LINK_GLOBS:
        found.update(p for p in root.glob(pattern) if p.is_file())
    excluded = {root / e for e in LINK_EXCLUDED}
    return sorted(p for p in found if p not in excluded)


def external_link_problem(target: str) -> str | None:
    """``None`` when the external link is acceptable."""
    m = re.match(r"^https?://([^/?#]+)(/[^?#]*)?(?:[?#].*)?$", target)
    if not m:
        return "malformed URL"
    host = m.group(1).lower()
    path = (m.group(2) or "").strip("/")
    if host in ALLOWED_HOSTS:
        return None
    if host != "github.com":
        return f"host {host!r} is not allow-listed"
    parts = path.split("/") if path else []
    if len(parts) < 2 or parts[0] != GITHUB_OWNER:
        return f"github.com link must name {GITHUB_OWNER}/<repository>"
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    if repo not in GITHUB_REPOS:
        return f"unknown repository {repo!r} (known: {', '.join(sorted(GITHUB_REPOS))})"
    rest = parts[2:]
    if not rest:
        return None
    kind = rest[0]
    if kind in ("blob", "tree"):
        need = 3 if kind == "blob" else 2
        if len(rest) >= need:
            return None
        return f"{kind} link needs a ref" + (" and a file path" if kind == "blob" else "")
    if kind in ("releases", "actions"):
        return None
    if kind in ("issues", "pull"):
        return None if len(rest) == 2 and rest[1].isdigit() else f"{kind} link needs a number"
    return f"unsupported github.com path form {kind!r}"


def check_links(root: Path) -> list[str]:
    problems: list[str] = []
    cache: dict[Path, list[str]] = {}

    def page_anchors(path: Path) -> list[str]:
        if path not in cache:
            cache[path] = anchors(path.read_text(encoding="utf-8"))
        return cache[path]

    for page in link_pages(root):
        rel = page.relative_to(root).as_posix()
        page_text = page.read_text(encoding="utf-8")
        for label in undefined_references(page_text):
            problems.append(f"{rel}: reference link [{label}] has no definition")
        for target in links(page_text):
            if target.startswith("mailto:"):
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I):
                problem = external_link_problem(target)
                if problem:
                    problems.append(f"{rel}: external link {target!r}: {problem}")
                continue
            path_part, _, fragment = target.partition("#")
            path_part = unquote(path_part)
            dest = page if path_part == "" else (page.parent / path_part).resolve()
            if not dest.exists():
                problems.append(f"{rel}: link {target!r} points at a missing file")
                continue
            if fragment and dest.is_file() and dest.suffix == ".md":
                if fragment not in page_anchors(dest):
                    problems.append(f"{rel}: link {target!r} points at a missing heading")
    return problems


# ---------------------------------------------------------------------------
# Rule 2: commands and flags.
# ---------------------------------------------------------------------------

_NUMERIC_PLACEHOLDERS = frozenset({"n", "count", "seconds", "number", "max-steps", "steps"})
_PLACEHOLDER_RE = re.compile(r"<([^<>\s]+)>")
_VARIABLE_RE = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*[^}]*\}|[A-Za-z_][A-Za-z0-9_]*)")


def command_lines(text: str, *, checked_info=lambda info: info.strip().split(" ")[0] != "text") -> list[str]:
    """Every Manager invocation in the fenced blocks of ``text``: the
    line (continuations joined, an optional ``$ `` and comments removed)
    starts ``workflow-manager``, carries no ``[``/``]`` (a synopsis) and is
    cut at the first shell operator.
    A block whose info string is ``text`` is not checked."""
    found = []
    for kind, info, lines in split_fences(text):
        if kind != "fence" or not checked_info(info):
            continue
        joined: list[str] = []
        pending = ""
        for raw in lines:
            if raw.rstrip().endswith("\\"):
                pending += raw.rstrip()[:-1] + " "
                continue
            joined.append(pending + raw)
            pending = ""
        if pending:
            joined.append(pending)
        for line in joined:
            line = line.strip()
            if line.startswith("$ "):
                line = line[2:].strip()
            if not line.startswith("workflow-manager"):
                continue
            if "[" in line or "]" in line:
                continue  # a usage synopsis, not a runnable line
            found.append(line)
    return found


def argv_for(line: str) -> list[str]:
    """The argument vector of an invocation line: ``<placeholders>`` and
    shell variables replaced by fixed words, comments dropped, cut at the
    first shell operator."""
    def placeholder(m: re.Match) -> str:
        return "1" if m.group(1).lower() in _NUMERIC_PLACEHOLDERS else "placeholder"

    line = _PLACEHOLDER_RE.sub(placeholder, line)
    line = _VARIABLE_RE.sub("placeholder", line)
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    tokens: list[str] = []
    for token in lexer:
        if token and all(c in lexer.punctuation_chars for c in token):
            break
        tokens.append(token)
    return tokens[1:] if tokens and tokens[0] == "workflow-manager" else tokens


class _Recorder(argparse.Action):
    """Stands in for a terminating action (``--version``, ``--help``): the
    flag parses and is recorded; nothing is printed, nothing exits, no
    runtime is resolved."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None, sink=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)
        self.sink = sink

    def __call__(self, parser, namespace, values, option_string=None):
        self.sink.append(option_string)


def _is_terminating(action: argparse.Action) -> bool:
    return (isinstance(action, argparse._HelpAction) or isinstance(action, argparse._VersionAction)
            or type(action).__name__ == "_VersionAction")


def _walk(parser: argparse.ArgumentParser):
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                yield from _walk(sub)


def neutralise(parser: argparse.ArgumentParser, sink: list, *, relax: bool) -> argparse.ArgumentParser:
    """Replace every terminating action in ``parser`` and its subparsers
    with a recorder writing to ``sink``; with ``relax``, also clear every
    ``required`` flag (positionals, required options, the subparsers action
    and every mutually exclusive group)."""
    for p in _walk(parser):
        for i, action in enumerate(p._actions):
            if _is_terminating(action):
                recorder = _Recorder(action.option_strings, help=action.help, sink=sink)
                p._actions[i] = recorder
                for option in action.option_strings:
                    p._option_string_actions[option] = recorder
        if relax:
            for action in p._actions:
                action.required = False
            for group in p._mutually_exclusive_groups:
                group.required = False
    return parser


class CommandChecker:
    """Validates invocation lines against freshly built parsers."""

    def __init__(self, build_parser) -> None:
        self.sink: list = []
        self.relaxed = neutralise(build_parser(), self.sink, relax=True)
        self.strict = neutralise(build_parser(), self.sink, relax=False)

    def _parse(self, parser, argv) -> str | None:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
                parser.parse_args(argv)
        except SystemExit:
            return buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else "usage error"
        return None

    def problem(self, line: str) -> str | None:
        """``None`` when ``line`` would be accepted by the real CLI up to
        its first terminating action."""
        argv = argv_for(line)
        self.sink.clear()
        error = self._parse(self.relaxed, argv)
        if error is not None:
            return error
        if self.sink:
            return None
        return self._parse(self.strict, argv)


def check_commands(root: Path, build_parser) -> list[str]:
    problems = []
    checker = CommandChecker(build_parser)
    for rel in COMMAND_PAGES:
        page = root / rel
        if not page.is_file():
            problems.append(f"{rel}: command page is missing")
            continue
        for line in command_lines(page.read_text(encoding="utf-8")):
            error = checker.problem(line)
            if error:
                problems.append(f"{rel}: command {line!r} does not parse: {error}")
    return problems


# ---------------------------------------------------------------------------
# Rule 3: page header and internal ids.
# ---------------------------------------------------------------------------


def work_item_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    state = root / "docs/ai-workflow/WORKFLOW_STATE.json"
    if state.is_file():
        try:
            ids.update(json.loads(state.read_text(encoding="utf-8")).get("work_items", {}))
        except (ValueError, AttributeError):
            pass
    completed = root / "docs/milestones/completed"
    if completed.is_dir():
        ids.update(p.stem for p in completed.glob("*.md"))
    return ids


def header_problem(text: str) -> str | None:
    lines = prose(text).split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^# \S", line):
            for following in lines[i + 1:]:
                if following.strip():
                    return None if HEADER_RE.match(following.strip()) else (
                        "the first line after the title must be '> For: <reader>. Last checked with: <versions>.'")
            return "no header after the title"
    return "no H1 title"


def internal_id_problems(text: str, ids: set[str]) -> list[str]:
    body = blank_link_targets(text)
    found = []
    for pattern in INTERNAL_ID_RES:
        found.extend(sorted({m.group(0) for m in pattern.finditer(body)}))
    for item in sorted(ids):
        if re.search(r"(?<![\w-])" + re.escape(item) + r"(?![\w-])", body):
            found.append(item)
    return found


def check_pages(root: Path) -> list[str]:
    problems = []
    ids = work_item_ids(root)
    for rel in USER_PAGES:
        page = root / rel
        if not page.is_file():
            problems.append(f"{rel}: user page is missing")
            continue
        text = page.read_text(encoding="utf-8")
        problem = header_problem(text)
        if problem:
            problems.append(f"{rel}: {problem}")
        for found in internal_id_problems(text, ids):
            problems.append(f"{rel}: internal id {found!r} on a user page")
    return problems


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def check_tree(root: Path, *, build_parser=None) -> list[str]:
    """Every problem in the tree at ``root``. ``build_parser`` defaults to the
    live Manager's."""
    if build_parser is None:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from workflow_manager import cli
        build_parser = cli.build_parser
    problems = check_links(root)
    problems += check_commands(root, build_parser)
    problems += check_pages(root)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline documentation checks.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root to check")
    args = parser.parse_args(argv)
    problems = check_tree(Path(args.root).resolve())
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
