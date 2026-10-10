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

import shlex
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .compatibility import (  # noqa: F401  (re-exported: one home for the predicate)
    NOT_MANAGED_PROBLEM,
    PREDICATE_EXCLUDED,
    RECORD_UNREADABLE_TITLE,
    DataFile,
    git_command,
    git_init_command,
    manager_command,
    render_command,
    rerun_phrase,
    writes_withheld,
)
from .install import (
    AlreadyManagedError,
    CollisionError,
    DriftError,
    NotAGitRepositoryError,
    NotManagedError,
    TargetNotFoundError,
    UnknownProfileError,
)
from .installation import (
    CorruptInstallationError,
    NotInstalledError,
    UnsupportedInstallationSchemaError,
)
from .release import STATE_TEMPLATES

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
    #: Whether the target holds Workflow data (`compatibility.holds_data`).
    holds_data: bool = False
    #: The Workflow data files the findings name, with what is wrong with each.
    data_files: tuple = ()
    #: Whether the installation record's source is a local, unpublished release.
    installed_local: bool = False

    @property
    def withheld(self) -> bool:
        """Whether a command that writes Workflow data may not be printed."""
        return writes_withheld(self.data_findings, self.missing_templates, self.holds_data)

    @property
    def target(self) -> str:
        return str(getattr(self.args, "target", "") or "")


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


PAGE_DATA = ("common-problems.md", "repair-workflow-data-by-hand")
PAGE_PARTIAL = ("common-problems.md", "an-install-stopped-part-way")
PAGE_UPDATE_MANAGER = ("update.md", "update-the-manager")

_OPERATOR = object()


def _url(spec) -> str:
    return page(*spec)


def _quote(text) -> str:
    return shlex.quote(str(text))


def writes_repository(args) -> bool:
    """True for the commands that write the repository: `bootstrap`, and
    `update` without `--dry-run`. One helper, so a read-only flag added to a
    write command later joins the read-only text by changing this."""
    command = getattr(args, "command", None)
    return command == "bootstrap" or (
        command == "update" and not getattr(args, "dry_run", False))


def _options(context: Context, version) -> tuple[tuple, str | None]:
    """The global options a printed command carries, and a note when
    `--release-dir` had to be left out. `--release-source` and `--release-cache`
    say where releases come from, not which one, so they are always carried.
    `--release-dir D` is carried only when D holds the version the command
    uses (any version, when the command names none)."""
    args = context.args
    options = []
    if getattr(args, "release_source", None):
        options.append(("--release-source", args.release_source))
    if getattr(args, "release_cache", None):
        options.append(("--release-cache", args.release_cache))
    note = None
    directory = getattr(args, "release_dir", None)
    held = context.release_dir_version
    if directory is not None:
        if version is None or held is None or held == version:
            options.append(("--release-dir", directory))
        else:
            note = (f"--release-dir {directory} holds {held}, so it is left out; the installed "
                    f"release {version} comes from the cache or --release-source")
    return tuple(options), note


def _command(context: Context, *args: str, target=True, version=_OPERATOR):
    """(rendered command or None, note). None means the command writes and the
    Workflow data is incomplete: the caller prints `data_step` instead."""
    if version is _OPERATOR:
        version = getattr(context.args, "release_version", None)
    options, note = _options(context, version)
    flags = list(args)
    profile = getattr(context.args, "profile", None)
    if flags and flags[0] in ("bootstrap", "update") and profile not in (None, "full"):
        flags.insert(1, f"--profile={profile}")
    built = manager_command(*flags, release_version=version, withheld=context.withheld,
                            target=context.target if target is True else target, options=options)
    return (built.render() if built is not None else None), note


def _history(context: Context, path: str) -> tuple[str, str]:
    """The two vetted history readers for `path`: `log` lists revisions and
    `show` prints a stored blob (no filter, no textconv, no pager)."""
    repo = context.target
    log = git_command(repo, "--no-pager", "log", "--oneline", "--no-show-signature",
                      "--", path).render()
    show = git_command(repo, "--no-pager", "show", "--no-textconv", f"HEAD:{path}").render()
    return log, show


def data_step(context: Context) -> str:
    """P1: the one step for Workflow data that is missing, unreadable or
    malformed, whatever Git holds. It never prints a command that writes the
    file (no restore, checkout, update or bootstrap): the operator, not the
    Manager, decides which copy is the good one."""
    repo = context.target
    page_url = _url(PAGE_DATA)
    if not context.data_files:
        check = git_command(repo, "rev-parse", "--git-dir").render()
        return (f"the Workflow data in {repo} could not be inspected completely: make sure "
                f"`{check}` works here, or review the parts the report names by hand; this "
                f"Manager prints no command that writes Workflow data, and an update is not a "
                f"repair for it ({page_url})")
    clauses = []
    for item in context.data_files:
        full = f"{repo}/{item.path}"
        if item.state == "malformed" and item.backup:
            copy = render_command(["cp", "-p", "--", full, f"{repo}/{item.backup}"])
            clauses.append(f"save a copy of {item.path} first: `{copy}`")
        elif item.state == "unreadable":
            clauses.append(f"check the permissions and owner of {item.path}: "
                           f"`{render_command(['ls', '-ld', '--', full])}`")
        log, show = _history(context, item.path)
        clauses.append(f"see where a good copy of {item.path} is with `{log}` and `{show}`")
    names = ", ".join(item.path for item in context.data_files)
    return (f"Workflow data is missing or damaged ({names}): " + "; ".join(clauses)
            + f"; this Manager prints no command that writes it, and an update is not a repair "
              f"for it, so decide which copy is good and put it back yourself ({page_url})")


def _no_bootstrap(context: Context) -> str:
    return (f"{data_step(context)}; No bootstrap command is offered until the Workflow data "
            f"named above is back in place ({_url(PAGE_DATA)})")


def _again(context: Context, command: str | None, *, write: bool = True) -> str:
    """"run `command` again", or the withheld phrase while a write is withheld."""
    if command is None:
        return rerun_phrase(True, write, _url(PAGE_DATA))
    return f"run `{command}` again"


def _caveat(context: Context) -> str:
    """The release-version caveat of a bootstrap over existing Workflow data."""
    if not context.holds_data or getattr(context.args, "release_version", None):
        return ""
    versioned, _ = _command(context, "bootstrap", version="V")
    log, _ = _history(context, "docs/ai-workflow/WORKFLOW_STATE.json")
    return (f"; a bootstrap with no --release-version installs the newest release over state "
            f"an older release wrote: to stay on the release the repository was on, run "
            f"`{versioned}` with V that release (`{log}` lists the history)")


def _bootstrap_step(context: Context, lead: str, tail: str = "") -> str:
    if context.withheld:
        return _no_bootstrap(context)
    command, note = _command(context, "bootstrap")
    text = f"{lead} `{command}`{tail}{_caveat(context)}"
    return text + (f". {note}" if note else "")


def _not_a_directory_tail(error: CollisionError) -> bool:
    return any(d.detail in ("a directory is in the way", "it is a file, not a directory")
               for d in error.collisions)


# -- rows ---------------------------------------------------------------------

def _target_not_found(error, context):
    init = git_init_command(context.target).render()
    command, _ = _command(context, "bootstrap")
    return f"create the repository first with `{init}`, then {_again(context, command)}"


def _not_a_repository(error, context):
    init = git_init_command(context.target).render()
    command, _ = _command(context, "bootstrap")
    return (f"run `{init}` (or give the repository's top directory, the one holding .git), "
            f"then {_again(context, command)}")


def _already_managed(error, context):
    doctor, _ = _command(context, "doctor")
    update, note = _command(context, "update")
    if update is None:
        return f"{data_step(context)}; `{doctor}` shows what an update would do"
    text = (f"to move it to another release run `{update}`; `{doctor}` shows what that would "
            f"do first")
    return text + (f". {note}" if note else "")


def _not_managed(error, context):
    return _bootstrap_step(context, "to install the Workflow there run")


def _not_installed(error, context):
    status, _ = _command(context, "status", version=None)
    return (f"there is nothing to uninstall; check the path, or run `{status}` to see whether "
            f"the Manager manages it")


def _record_unreadable(error, context):
    """T8, T20 and T9 (any value but an integer above 1)."""
    repo = context.target
    folder = _quote(f"{repo}/.workflow-manager")
    if context.withheld:
        return f"delete {folder}; {_no_bootstrap(context)}"
    command, note = _command(context, "bootstrap", version="V")
    log, _ = _history(context, ".workflow-manager/installation.json")
    show = git_command(repo, "--no-pager", "show", "--no-textconv",
                       "REV:.workflow-manager/installation.json").render()
    text = (f"delete {folder}, then run `{command}`, with V the release the repository was on "
            f"(`{log}` lists the revisions and `{show}` shows its workflow_version); a "
            f"bootstrap with no version installs the newest release. Repository-local state is "
            f"not stored there and is not affected. If bootstrap lists files in the way, they "
            f"are files you edited or files of a different release than V; keep a copy of any "
            f"edit, then add --force")
    return text + (f". {note}" if note else "")


def _newer_record(error, context):
    return f"upgrade the Manager: {_url(PAGE_UPDATE_MANAGER)}"


def _unknown_profile(error, context):
    return (f"the installation record names a profile this Manager does not know: if a newer "
            f"Manager wrote it, upgrade the Manager ({_url(PAGE_UPDATE_MANAGER)}); otherwise "
            f"the record is damaged, so take this step: {_record_unreadable(error, context)}")


def _drift(error, context):
    dry, _ = _command(context, "update", "--dry-run")
    force, note = _command(context, "update", "--force")
    if force is None:
        return f"{data_step(context)}; `{dry}` previews what an update would do"
    text = (f"keep a copy of any file a `modified:` line above names, then run `{force}` to "
            f"replace those files with the release's; `{dry}` previews it first")
    return text + (f". {note}" if note else "")


def _collision(error, context):
    name = getattr(context.args, "command", "bootstrap")
    page_url = _url(PAGE_DATA)
    if _not_a_directory_tail(error):
        plain, note = _command(context, name)
        if plain is None:
            text = f"{data_step(context)}; {rerun_phrase(True, True, page_url)}"
        else:
            text = ("move or remove that directory, or that file where a directory goes (--force "
                    f"cannot replace either), then run `{plain}` again")
    else:
        force, note = _command(context, name, "--force")
        if force is None:
            text = f"{data_step(context)}; {rerun_phrase(True, True, page_url)}"
        else:
            text = (f"move your own files away and run the same command again, or add --force "
                    f"to replace them with the release's: `{force}`")
    return text + (f". {note}" if note else "")


def _os_error(error, context):
    page_url = _url(PAGE_PARTIAL)
    command = getattr(context.args, "command", None)
    if writes_repository(context.args):
        if context.withheld:
            return (f"fix the cause named above; {data_step(context)}; "
                    f"{rerun_phrase(True, True, _url(PAGE_DATA))}")
        return ("fix the cause named above, then run the same command again; if it then lists "
                "a file as modified or in the way that you did not edit, it is a partial write "
                f"from this run, and adding --force replaces it ({page_url})")
    if command == "uninstall":
        return ("fix the cause named above, then run the same command again (it removes only "
                "what is left)")
    return ("fix the cause named above (often a permission), then run the same command again; "
            "this command writes nothing in the repository")


# -- verify and status (T15) --------------------------------------------------

def _problem_path(line: str, kind: str) -> str | None:
    prefix = kind + ": "
    if not line.startswith(prefix):
        return None
    return line[len(prefix):].split(" (", 1)[0]


def problem_step(context: Context, problems: list[str]) -> str | None:
    """T15: the one next step for the problem lines `verify` and `status` print."""
    if not problems:
        return None
    installed = context.installed_version or getattr(context.args, "release_version", None)
    missing_data = [DataFile(path, "missing") for line in problems
                    if (path := _problem_path(line, "missing")) in STATE_TEMPLATES]
    if missing_data:
        return data_step(replace(context, data_files=tuple(missing_data)))
    for line in problems:
        path = _problem_path(line, "unexpected")
        if path is not None:
            return (f"move {path} away or delete it if it is not yours; an update refuses to "
                    f"run over it unless it already holds the release's bytes, or you add "
                    f"--force (--force cannot replace a directory)")
    if any(line.startswith("release: ") for line in problems):
        return ("the release package failed its own check, so the comparison is unreliable: run "
                "the command again (a cache entry that fails its pin is discarded and "
                "downloaded afresh)")
    if any(line.startswith("version: ") for line in problems):
        update, _ = _command(context, "update", version=getattr(context.args, "release_version", None))
        step = ("you compared with a release other than the installed one: leave out "
                f"--release-version and --release-dir to compare with workflow {installed}")
        if update is None:
            return f"{step}; {data_step(context)}"
        return f"{step}, or run `{update}` to move the repository"
    return _repair_step(context, installed)


def _repair_step(context: Context, installed: str | None) -> str:
    if context.installed_local and context.release_dir_version != installed:
        return (f"a release directory holding {installed} is needed: run the command again "
                f"with --release-dir DIR")
    update, note = _command(context, "update", version=installed)
    dry, _ = _command(context, "update", "--dry-run", version=installed)
    if update is None:
        return f"{data_step(context)}; `{dry}` previews what an update would do"
    text = (f"to put the release's files back run `{update}` (add --force if a line says "
            f"\"modified: PATH\" for a release file: that replaces your edit, so keep a copy "
            f"first); `{dry}` previews it")
    return text + (f". {note}" if note else "")


def success_step(context: Context) -> str:
    """T17: after a successful `bootstrap` or `update`."""
    options, _ = _options(context, context.installed_version)
    verify = manager_command("verify", target=context.target, options=options,
                             withheld=False).render()
    status = git_command(context.target, "status", inspection=False).render()
    return f"run `{verify}`, then review and commit what changed (`{status}`)"


def unmanaged_status_step(context: Context) -> str:
    """T7: stdout of `status` for a target that is not managed."""
    return _bootstrap_step(context, "run", " to install the Workflow")


#: The table: exception class -> function(error, context) -> step. Entries for
#: runtime errors are added by the checkpoints that own them. A row that prints
#: a command that writes goes through the predicate, so its context needs the
#: Workflow data facts (`needs_data`).
_TABLE: dict[type, Callable[[BaseException, Context], str | None]] = {}
_PREDICATE_ROWS: set[type] = set()


def _row(cls: type, function, *, predicate: bool = False) -> None:
    _TABLE[cls] = function
    if predicate:
        _PREDICATE_ROWS.add(cls)


_row(TargetNotFoundError, _target_not_found)
_row(NotAGitRepositoryError, _not_a_repository, predicate=True)
_row(AlreadyManagedError, _already_managed, predicate=True)
_row(NotManagedError, _not_managed, predicate=True)
_row(NotInstalledError, _not_installed)
_row(CorruptInstallationError, _record_unreadable, predicate=True)
_row(UnsupportedInstallationSchemaError,
     lambda error, context: _newer_record(error, context) if error.newer
     else _record_unreadable(error, context), predicate=True)
_row(UnknownProfileError, _unknown_profile, predicate=True)
_row(DriftError, _drift, predicate=True)
_row(CollisionError, _collision, predicate=True)
_row(OSError, _os_error)


def needs_data(error: BaseException, args) -> bool:
    """Whether `error`'s step goes through the withholding predicate, so the
    caller must compute the Workflow data facts for it."""
    if isinstance(error, OSError):
        return writes_repository(args)
    return any(isinstance(error, cls) for cls in _PREDICATE_ROWS)


def next_step(error: BaseException, context: Context) -> str | None:
    """The `next:` text for `error`, or None when the table has no entry."""
    for cls in type(error).__mro__:
        entry = _TABLE.get(cls)
        if entry is not None:
            return entry(error, context)
    return None
