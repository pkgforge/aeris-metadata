#!/usr/bin/env python3
"""Take the candidates still in candidates/ into the set that ships.

Whatever survived a look through candidates/ is moved into icons/, recorded in
sources.toml, and written into index.toml. Anything deleted from candidates/ is
simply not taken, which is how a wrong guess is rejected: delete the file.

Nothing here touches the network.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.toml"
CANDIDATES = ROOT / "needs-review.toml"
STAGED = ROOT / "candidates"
ICONS = ROOT / "icons"

# A suffix says how a package was built, not what it is, and aeris drops these
# itself when it looks an icon up. Carrying one in a file name would store the
# same drawing once per way it happens to be packaged.
PACKAGING_SUFFIXES = ("-bin", "-deb", "-app", "-appimage", "-static", "-git", "-stable")


def plainly(name: str) -> str:
    for suffix in PACKAGING_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def split_at(text: str, table: str) -> tuple[str, str]:
    """The comment above a table, and everything from the table onwards.

    Anchored to the start of a line: the prose above a table can mention it by
    name, and splitting on the first mention would throw away the header and
    the table with it.
    """
    at = re.search(r"^" + re.escape(table) + r"\s*$", text, re.M)
    return (text[: at.start()], text[at.start() :]) if at else (text, "")


def write_sources(path: pathlib.Path, icons: dict[str, str]) -> None:
    """Rewrite sources.toml whole, in one order and one shape.

    Appending would be less work and would leave the file in two halves, each
    sorted and neither sorted against the other.
    """
    header, _ = split_at(path.read_text(), "[icons]")
    width = max((len(name) + 2 for name in icons), default=0)
    body = "\n".join(
        f'{(chr(34) + name + chr(34)).ljust(width)} = "{where}"'
        for name, where in sorted(icons.items())
    )
    path.write_text(header + "[icons]\n" + body + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="say what would be taken, take nothing"
    )
    args = parser.parse_args()

    if not STAGED.is_dir():
        print(f"nothing staged in {STAGED.name}/", file=sys.stderr)
        return 0

    proposed = tomllib.loads(CANDIDATES.read_text())["icons"] if CANDIDATES.is_file() else {}
    staged = {p.stem: p for p in sorted(STAGED.iterdir()) if p.suffix in (".png", ".svg")}
    if not staged:
        print(f"{STAGED.name}/ is empty; nothing to take", file=sys.stderr)
        return 0

    unproposed = sorted(set(staged) - set(proposed))
    for package in unproposed:
        print(f"  {package} is staged but not in {CANDIDATES.name}", file=sys.stderr)

    if args.dry_run:
        print(f"{len(staged)} would be taken", file=sys.stderr)
        return 0

    icons = dict(tomllib.loads(SOURCES.read_text())["icons"])
    for package, path in staged.items():
        under = plainly(package)
        if under != package and (
            under in icons or any((ICONS / f"{under}{e}").is_file() for e in (".png", ".svg"))
        ):
            # The program is already here under its plain name.
            print(f"  {package} is {under}, which is already here", file=sys.stderr)
            path.unlink()
            continue

        # Whichever format was staged is the one that ships, so an earlier
        # answer in the other format goes.
        for extension in (".png", ".svg"):
            (ICONS / f"{under}{extension}").unlink(missing_ok=True)
        shutil.move(str(path), ICONS / f"{under}{path.suffix}")
        icons[under] = proposed.get(package, "staged by hand")

    added = staged
    write_sources(SOURCES, icons)
    shutil.rmtree(STAGED)
    CANDIDATES.unlink(missing_ok=True)

    subprocess.run([sys.executable, str(ROOT / "tools" / "index.py")], check=True)
    print(f"took {len(added)} icons", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
