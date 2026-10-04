# Glossary

> For: anyone reading the Manager's pages who meets an unfamiliar word. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Workflow words (work item, approval gate, milestone, checkpoint and the rest) are defined once, in the shared [Workflow glossary](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/glossary.md). This page covers only the Manager's own words.

## Bootstrap

The first install of the Workflow into a repository: `workflow-manager bootstrap <repo>`. It copies the release's files, writes clean state files from templates, adds the Workflow's section to `.gitignore` and `CLAUDE.md`, and writes the [installation record](#installation-record). It refuses if the repository already has its own file where a release file goes, unless you pass `--force`.

## Drift

A difference between an installed file and the release it came from, for example a file someone edited. `verify` reports drift; `update` refuses to overwrite it without `--force`.

## Installation record

The file `.workflow-manager/installation.json` inside a managed repository. It names the installed Workflow release and profile, where the release came from, and the digest of every file installed. It is how the Manager recognises a repository, finds drift and updates safely.

## Managed file

A file the release owns: the Workflow's commands in `.claude/commands/`, its scripts, its documents in `docs/ai-workflow/` and its conformance workflow. An update replaces managed files and refuses to overwrite edited ones.

## Manager release and Workflow release

Two different things with two different version numbers. A *Manager release* (1.4.0) is the tool itself. A *Workflow release* (2.8.0) is the process the tool installs. A Manager release carries no Workflow release. It only knows the digests of the ones it pins, and downloads them when needed.

## Package

A Workflow release as published: an archive (`workflow-<version>.tar.gz`), its manifest, and a `SHA256SUMS` file. Packages are built and published in the Workflow repository, never by the Manager.

## Pin

The record, inside the Manager, of one published Workflow release: its archive name and the digests the download must match. A release that is not pinned cannot be installed from the published source. A pin is added once and never changed.

## Profile

How much of a release is installed. `full` (the default) installs the Workflow and its own conformance checks. `runtime` installs only what the Workflow needs to operate. `update` keeps the profile the repository already has unless you pass `--profile`.

## Release cache

The local folder where verified Workflow releases are kept after their first download, by default `~/.cache/workflow-manager/releases`. Every command works offline once the release is cached. Change it with `--release-cache` or the `WORKFLOW_MANAGER_RELEASE_CACHE` environment variable.

## Release source

Where the Manager downloads Workflow releases from. By default, the Workflow repository's published releases. A mirror folder or URL can replace it with `--release-source` or `WORKFLOW_MANAGER_RELEASE_SOURCE`. The pins still decide what is accepted.

## State files

The repository's own record of its work: `docs/ai-workflow/WORKFLOW_STATE.json`, `docs/ai-workflow/WORKFLOW_CONFIG.json`, `docs/ACTIVE_MILESTONE.md` and `.ai-review/`. The Manager creates the first three once, from clean templates, and never changes them afterwards.

## Status, update, verify

- `status` summarises a repository: managed or not, release, profile, and whether it is clean.
- `update` moves a managed repository to another release, replacing managed files and keeping state files.
- `verify` compares every installed file with its release and lists the differences.

`status` and `verify` use the release the repository's record names. `bootstrap` and `update` use the newest pinned release unless you choose one with `--release-version`.

## Uninstall

`workflow-manager uninstall <repo>` removes the managed files. State files stay.
