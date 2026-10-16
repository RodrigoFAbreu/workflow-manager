"""Gathering the release data a report needs beyond the built-in tables (3.4).

`compatibility.py` decides what a report says from a `ReleaseMetadata`; this
module reads one, the only place a report reaches for the network. It looks at
the releases the update or downgrade crosses that have no built-in data (above
`BUILTIN_THROUGH`): the target (already resolved), the installed release, and
every release the source says lies between them. Each one's `manager` block
comes from the cache entry's manifest, else from a checksum-verified manifest
asset (in memory, under one deadline). What cannot be read is recorded with
its cause, never skipped: a missing assessment is a finding, not a clean bill.
"""

from __future__ import annotations

from .compatibility import BUILTIN_THROUGH, ReleaseMetadata, has_builtin_data, in_range, \
    is_comparable, version_key
from .release import Release, ReleaseIntegrityError, parse_manifest_manager
from .source import (
    Deadline,
    DiscoveryFailure,
    ReleaseCache,
    ReleaseUnavailableError,
    is_strict_version,
)

#: Errors that mean "this version's manifest could not be had", not a bug.
_UNREADABLE = (DiscoveryFailure, ReleaseUnavailableError, ReleaseIntegrityError, OSError, ValueError)


def _cause(exc: Exception) -> str:
    return getattr(exc, "reason", None) or str(exc)


def gather_metadata(cache: ReleaseCache, installed, target: Release, *,
                    deadline: Deadline | None = None) -> ReleaseMetadata:
    """The metadata for a report on `installed` -> `target`; empty (and no
    network) when both lie within the built-in data."""
    if not is_comparable(installed) or not is_comparable(target.version):
        return ReleaseMetadata()
    top = max(installed, target.version, key=version_key)
    if version_key(top) <= version_key(BUILTIN_THROUGH):
        return ReleaseMetadata()
    deadline = deadline or Deadline()
    metadata = ReleaseMetadata()
    candidates = {installed, target.version}
    candidates |= {v for v in cache.known_local() if is_strict_version(v)}
    source = cache.source if cache.discover else None
    if source is None:
        metadata.catalog_incomplete = "discovery is off (--pinned-only), so no listing was read"
    else:
        try:
            listing = source.listing(cache.pins.repository, deadline)
        except (DiscoveryFailure, ReleaseUnavailableError, OSError) as exc:
            metadata.catalog_incomplete = f"the listing could not be read: {_cause(exc)}"
            listing = None
        else:
            if listing is None:
                metadata.catalog_incomplete = (
                    "the source is a URL template and has no listing; name a directory mirror, "
                    "or leave --release-source unset")
            else:
                candidates |= set(listing.versions)
                for version, why in listing.rejected.items():
                    candidates.add(version)
                    metadata.unreadable[version] = why
                if not listing.complete:
                    metadata.catalog_incomplete = "the listing may be truncated"
    wanted = sorted((v for v in candidates
                     if is_comparable(v) and not has_builtin_data(v)
                     and in_range(v, installed, target.version)), key=version_key)
    metadata.versions = tuple(wanted)
    for version in wanted:
        if version in metadata.unreadable:
            continue
        try:
            if version == target.version:
                metadata.blocks[version] = target.manager
                continue
            manifest = cache.cached_manifest(version)
            if manifest is None:
                if source is None:
                    raise ReleaseUnavailableError(
                        f"release {version} is not cached and discovery is off (--pinned-only)")
                manifest = source.inspect(version, deadline).manifest
            metadata.blocks[version] = parse_manifest_manager(manifest)
        except _UNREADABLE as exc:
            metadata.unreadable[version] = _cause(exc)
    return metadata
