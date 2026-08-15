#!/usr/bin/env python3
"""Write index.toml, which says which packages have an icon and as what.

Aeris reads this once and then asks for an icon only when it draws one, so it
needs to know what is here without asking for a listing. That is all this file
is: the contents of icons/, written down.

Nothing here touches the network. Run it after adding or removing an icon, and
commit the result alongside.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons"
INDEX = ROOT / "index.toml"

# What aeris can draw, in the order it prefers them.
EXTENSIONS = ("svg", "png")

# Where the icons are served from. Written into the index rather than built
# into aeris, so moving them is a change here and not a release of aeris.
DEFAULT_BASE = "https://raw.githubusercontent.com/pkgforge/aeris-metadata/main/icons"


def read() -> dict[str, str]:
    """Every icon in icons/, as package name to extension.

    Where a package has both, the one that scales wins, and the other is
    reported: carrying two of the same thing is a mistake rather than a choice.
    """
    found: dict[str, str] = {}
    for extension in reversed(EXTENSIONS):
        for path in sorted(ICONS.glob(f"*.{extension}")):
            if path.stem in found:
                print(
                    f"  {path.stem} has both a .{found[path.stem]} and a .{extension};"
                    f" the .{EXTENSIONS[0]} is what ships",
                    file=sys.stderr,
                )
            found[path.stem] = extension
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", help=f"where the icons are served from (default {DEFAULT_BASE})"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if index.toml does not already say what icons/ holds",
    )
    args = parser.parse_args()

    base = args.base
    if base is None and INDEX.is_file():
        base = tomllib.loads(INDEX.read_text()).get("base")
    base = base or DEFAULT_BASE

    icons = read()
    width = max((len(name) + 2 for name in icons), default=0)
    written = (
        "# Which packages have an icon, and what kind. Written by tools/index.py\n"
        "# from the contents of icons/; do not edit it by hand.\n"
        "#\n"
        "# Aeris reads this once, then asks for an icon only when it draws one.\n"
        "\n"
        f'base = "{base}"\n'
        "\n"
        "[icons]\n"
        + "\n".join(
            f'{(chr(34) + name + chr(34)).ljust(width)} = "{extension}"'
            for name, extension in sorted(icons.items())
        )
        + "\n"
    )

    if args.check:
        current = INDEX.read_text() if INDEX.is_file() else ""
        if current == written:
            print(f"index.toml is what icons/ holds ({len(icons)})", file=sys.stderr)
            return 0
        print("index.toml is out of date; run tools/index.py", file=sys.stderr)
        return 1

    INDEX.write_text(written)
    print(f"{len(icons)} icons written to {INDEX.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
