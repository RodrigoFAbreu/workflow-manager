"""The next step an error tells the operator to take.

`cli.main` prints an error's cause on stderr, then at most one `next:` line.
This module computes that line: `next_step(error, context)` looks the error up
in a table keyed by exception class (and, where one class has several causes,
by its `kind` attribute). It never reads the filesystem and never asks Git;
the facts it needs arrive in a `Context` that the caller computed.

A step names a command in backticks, a flag, or a page. Placeholders are
upper-case words (`TARGET`, `VERSION`), never `<angle brackets>`, so a pasted
command still parses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .compatibility import (  # noqa: F401  (re-exported: one home for the predicate)
    NOT_MANAGED_PROBLEM,
    PREDICATE_EXCLUDED,
    RECORD_UNREADABLE_TITLE,
    writes_withheld,
)

PROGRAM = "workflow-manager"

#: Pages are full URLs, because an installed wheel has no `docs/` folder.
DOCS_BASE = "https://github.com/RodrigoFAbreu/workflow-manager/blob/main/docs/"

#: The four options that go before the command, in the parser's order, each with
#: the placeholder its value gets in a printed pattern.
GLOBAL_OPTIONS = (
    ("--release-version", "VERSION"),
    ("--release-source", "SOURCE"),
    ("--release-cache", "DIR"),
    ("--release-dir", "DIR"),
)


def page(name: str, anchor: str | None = None) -> str:
    """The URL of docs page `name` (`exit-codes.md`), at `anchor` when given."""
    url = DOCS_BASE + name
    return f"{url}#{anchor}" if anchor else url


@dataclass(frozen=True)
class Context:
    """The facts an error's cause and `args` do not hold."""
    args: Any = None
    installed_version: str | None = None
    cache_dir: str | None = None
    release_dir_version: str | None = None
    missing_templates: tuple[str, ...] = ()
    data_findings: tuple = field(default_factory=tuple)


def misplaced_global_options(unrecognized: list[str]) -> list[str]:
    """The global options named among `unrecognized` arguments, in the parser's
    order. `--opt=value` counts as `--opt`."""
    named = {token.split("=", 1)[0] for token in unrecognized}
    return [option for option, _ in GLOBAL_OPTIONS if option in named]


def global_option_step(misplaced: list[str], command: str | None) -> str:
    """A1: the usage pattern for global options written after the command.

    It echoes only the option names and the command word the operator typed.
    Every value is a placeholder, so the pattern is not a command that could be
    pasted, and carries no `update` or `bootstrap` for a real target.
    """
    placeholders = dict(GLOBAL_OPTIONS)
    options = " ".join(f"[{option} {placeholders[option]}]" for option in misplaced)
    tail = {"releases": "", "package": " package SUBCOMMAND ARGS"}.get(
        command or "", f" {command} TARGET" if command else " COMMAND TARGET")
    words = f"{PROGRAM} {options}{tail}"
    return (f"global options go before the command, as in the pattern `{words}`; "
            f"see {page('exit-codes.md', 'global-options')}")


#: The table: exception class -> function(error, context) -> step. Entries for
#: runtime errors are added by the checkpoints that own them.
_TABLE: dict[type, Callable[[BaseException, Context], str | None]] = {}


def next_step(error: BaseException, context: Context) -> str | None:
    """The `next:` text for `error`, or None when the table has no entry."""
    for cls in type(error).__mro__:
        entry = _TABLE.get(cls)
        if entry is not None:
            return entry(error, context)
    return None
