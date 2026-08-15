#!/usr/bin/env python3
"""Carry each icon once, and point the rest at it.

Several packages are the same application under different names: a `-bin`, a
`-deb`, an `-app`. Each arrives with its own copy of the same picture, and the
set ends up storing one image several times.

This keeps one file per distinct image and writes the others into icons.toml as
exceptions, which is what that file is for. Aeris resolves the exception before
it looks anything up, so nothing changes about what is drawn.

Nothing here touches the network.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.toml"
EXCEPTIONS = ROOT / "icons.toml"
ICONS = ROOT / "icons"


# How much of a name several packages must share before they are taken for
# the same program. Two unrelated programs can ship the same picture: a pair of
# system monitors both using a stock chart, or a game and its sequel.
SHARED_ENOUGH = 4

# Aeris drops these itself when it cannot find a package's own icon, so saying
# so here would be saying what it already knows.
PACKAGING_SUFFIXES = ("-bin", "-deb", "-app", "-appimage", "-static", "-git", "-stable")


def worked_out(name: str, keep: str) -> bool:
    """Whether aeris would land on `keep` for `name` without being told."""
    return any(name.removesuffix(s) == keep for s in PACKAGING_SUFFIXES)


def canonical(names: list[str]) -> str | None:
    """Which of several names for one picture the file is kept under.

    Nothing, where the names have too little in common to call them the same
    program. Otherwise the shortest, which is reliably the one without a suffix
    saying how it was packaged: `86box` rather than `86box-app`.
    """
    shared = os.path.commonprefix(names).rstrip("-")
    if len(shared) < SHARED_ENOUGH:
        return None

    return shared if shared in names else sorted(names, key=lambda n: (len(n), n))[0]


def split_at(text: str, table: str) -> tuple[str, str]:
    """The comment above a table, and everything from the table onwards.

    Anchored to the start of a line: the prose above a table can mention it by
    name, and splitting on the first mention would throw away the header and
    the table with it.
    """
    at = re.search(r"^" + re.escape(table) + r"\s*$", text, re.M)
    return (text[: at.start()], text[at.start() :]) if at else (text, "")


def write_sources(icons: dict[str, str]) -> None:
    header, _ = split_at(SOURCES.read_text(), "[icons]")
    width = max((len(name) + 2 for name in icons), default=0)
    body = "\n".join(
        f'{(chr(34) + name + chr(34)).ljust(width)} = "{where}"'
        for name, where in sorted(icons.items())
    )
    SOURCES.write_text(header + "[icons]\n" + body + "\n")


def write_exceptions(aliases: dict[str, str], per_adapter: str) -> None:
    header, _ = split_at(EXCEPTIONS.read_text(), "[default]")
    width = max((len(name) + 2 for name in aliases), default=0)
    body = "\n".join(
        f'{(chr(34) + name + chr(34)).ljust(width)} = "{icon}"'
        for name, icon in sorted(aliases.items())
    )
    EXCEPTIONS.write_text(header + "[default]\n" + body + "\n" + per_adapter)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="say what would go, change nothing"
    )
    args = parser.parse_args()

    files = [p for p in sorted(ICONS.glob("*.*")) if p.suffix in (".png", ".svg")]
    same: dict[str, list[pathlib.Path]] = collections.defaultdict(list)
    for path in files:
        same[hashlib.sha256(path.read_bytes()).hexdigest()].append(path)

    shared = {digest: paths for digest, paths in same.items() if len(paths) > 1}
    if not shared:
        print(f"every one of the {len(files)} icons is already distinct", file=sys.stderr)
        return 0

    existing = tomllib.loads(EXCEPTIONS.read_text())
    aliases = dict(existing.get("default", {}))
    # Anything under a manager's own table is somebody's deliberate choice and
    # is left exactly as it is.
    # Everything from the first line that is not an entry: a manager's own
    # table, or a note somebody left. Rewriting the entries should not eat it.
    after = split_at(EXCEPTIONS.read_text(), "[default]")[1]
    kept = [i for i in (after.find("\n["), after.find("\n#")) if i != -1]
    per_adapter = after[min(kept) :] if kept else ""

    freed = 0
    going: list[tuple[str, str]] = []
    left = 0
    for paths in shared.values():
        names = [p.stem for p in paths]
        keep = canonical(names)
        if keep is None:
            left += len(names) - 1
            print(f"  leaving {', '.join(names)}: too little in common", file=sys.stderr)
            continue
        for path in paths:
            if path.stem == keep:
                continue
            going.append((path.stem, keep))
            freed += path.stat().st_size

    for name, keep in going:
        how = "dropped" if worked_out(name, keep) else "exception"
        print(f"  {name} -> {keep} ({how})", file=sys.stderr)

    if args.dry_run:
        print(
            f"{len(going)} would become exceptions, {freed / 1024:.0f} KB freed"
            f" ({left} left alone)",
            file=sys.stderr,
        )
        return 0

    sources = dict(tomllib.loads(SOURCES.read_text())["icons"])
    for name, keep in going:
        for extension in (".png", ".svg"):
            (ICONS / f"{name}{extension}").unlink(missing_ok=True)
        # The record of where it came from goes with the file; what is left is
        # the alias saying which picture it shares.
        sources.pop(name, None)
        if not worked_out(name, keep):
            aliases[name] = keep

    write_sources(sources)
    write_exceptions(aliases, per_adapter)
    spelled = sum(1 for name, keep in going if not worked_out(name, keep))
    print(
        f"{len(going)} duplicate icons gone, {freed / 1024:.0f} KB freed;"
        f" {spelled} needed saying, the rest aeris works out."
        f" Run tools/index.py",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
