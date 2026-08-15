#!/usr/bin/env python3
"""Suggest icon sources for packages that have none yet.

Reads the catalogues of every manager aeris can drive, looks each name up in
what Flathub and Arch publish, and writes what it finds to needs-review.toml
with the icon itself staged in candidates/.

Every catalogue is fetched rather than read off this machine, so what it
proposes does not depend on which managers happen to be installed here or which
repositories they happen to have enabled. Adding a manager is one line.

Nothing this writes is trustworthy on its own. It matches on names, and names
collide: a package called `builder` is not necessarily GNOME Builder. Every
candidate needs a person to look at it before it moves into sources.toml, which
is why it writes to a separate file and never touches sources.toml itself.

The icon is staged so it can be looked at: flip through candidates/, delete the
wrong ones, and run tools/accept.py to take the rest.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.toml"
CANDIDATES = ROOT / "needs-review.toml"
STAGED = ROOT / "candidates"

FLATHUB_CATALOGUE = "https://dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz"
FLATHUB_ICONS = "https://dl.flathub.org/repo/appstream/x86_64/icons/128x128"

# Arch ships its catalogue and its icons together as a package, so the icons
# are files rather than somewhere to link to.
ARCH_PACKAGE = "https://archlinux.org/packages/extra/any/archlinux-appstream-data/json/"
ARCH_MIRROR = "https://geo.mirror.pkgbuild.com/extra/os/x86_64"
# Suffixes that say how a package was built rather than what it is, so a name
# carrying one is also tried without it. Building from a repository rather than
# a release does not change what a program is called. What is left out is
# anything a project brands separately, such as -nightly or -beta.
PACKAGING_SUFFIXES = ("-bin", "-deb", "-app", "-appimage", "-static", "-git", "-stable")
AGENT = "aeris-metadata propose (https://github.com/pkgforge/aeris-metadata)"

# Names too common to match on. Several applications are plausibly "Music",
# and the last piece of a reverse-domain id is a common word often enough that
# matching one is a coin toss. Everything below was proposed once, looked at,
# and turned out to be a different program than the package.
AMBIGUOUS = {
    "builder", "music", "text", "files", "notes", "calculator", "clock",
    "weather", "maps", "photos", "videos", "camera", "contacts", "calendar",
    "console", "terminal", "editor", "browser", "player", "viewer", "reader",
    "mail", "chat", "paint", "draw", "game", "games", "shell", "monitor",
    "recorder", "screenshot", "commit", "health", "money",
    "launcher", "play", "delta", "elastic", "station", "quicknote",
}


def get(url: str) -> bytes:
    headers = {"User-Agent": AGENT}
    # The tree listings are two requests, which is well inside what GitHub
    # allows unauthenticated. A token only matters when something else on the
    # same address has been busy.
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def keyed(components) -> dict[str, dict[str, str]]:
    """Three ways to name the same application, each to where its icon is.

    A name, a command it says it provides, and the last piece of its id. They
    are tried in that order, loosest last.
    """
    by_name: dict[str, str] = {}
    by_binary: dict[str, str] = {}
    by_tail: dict[str, str] = {}

    for component, icon in components:
        published = component.findtext("id") or ""
        if not published:
            continue

        name = (component.findtext("name") or "").strip().lower()
        if name:
            by_name.setdefault(name, icon)
        for provided in component.findall("provides/binary"):
            binary = (provided.text or "").strip().lower()
            if binary:
                by_binary.setdefault(binary, icon)
        tail = published.removesuffix(".desktop").split(".")[-1].lower()
        if tail:
            by_tail.setdefault(tail, icon)

    return {"name": by_name, "binary": by_binary, "tail": by_tail}


def flathub() -> dict[str, dict[str, str]]:
    """What Flathub publishes, each icon named by where to fetch it."""
    root = ET.parse(io.BytesIO(gzip.decompress(get(FLATHUB_CATALOGUE)))).getroot()
    found = []
    for component in root.findall("component"):
        icon = next(
            (
                (i.text or "").strip()
                for i in component.findall("icon")
                if i.get("type") in ("cached", "remote")
            ),
            "",
        )
        if icon.endswith(".png"):
            found.append((component, f"{FLATHUB_ICONS}/{icon}"))
    return keyed(found)


# What the Arch catalogue was, once it has been read. A temporary directory is
# no use as a record of where an icon came from.
ARCH_RELEASE = "archlinux-appstream-data"


def arch(into: pathlib.Path) -> dict[str, dict[str, str]]:
    """What Arch publishes, each icon named by where it landed on disk.

    Arch ships the catalogue and the icons in one package, so this unpacks it
    rather than linking to anything. `bsdtar` and `zstd` do the unpacking; both
    come with a working Arch or a GitHub runner.
    """
    global ARCH_RELEASE
    listed = json.loads(get(ARCH_PACKAGE))
    ARCH_RELEASE = f"archlinux-appstream-data {listed['pkgver']}-{listed['pkgrel']}"
    url = f"{ARCH_MIRROR}/{listed['filename']}"
    print(f"  fetching {listed['filename']}", file=sys.stderr)

    archive = into / "arch.pkg.tar.zst"
    archive.write_bytes(get(url))
    subprocess.run(
        ["tar", "-I", "zstd", "-xf", str(archive), "-C", str(into)],
        check=True,
        capture_output=True,
    )

    catalogue = into / "usr/share/swcatalog"
    found = []
    for xml in sorted((catalogue / "xml").glob("*.xml.gz")):
        origin = f"archlinux-arch-{xml.name.removesuffix('.xml.gz')}"
        for component in ET.parse(gzip.open(xml)).getroot().findall("component"):
            icon = next(
                (
                    (i.text or "").strip()
                    for i in component.findall("icon")
                    if i.get("type") == "cached"
                ),
                "",
            )
            if not icon:
                continue
            # Largest first: an icon drawn small cannot be made bigger.
            for size in ("128x128", "64x64", "48x48"):
                path = catalogue / "icons" / origin / size / icon
                if path.is_file():
                    found.append((component, str(path)))
                    break
    return keyed(found)


def from_listing(url: str, pattern: str) -> set[str]:
    """Every name a plain text listing names, one per line."""
    listing = get(url).decode("utf-8", "replace")
    return set(re.findall(pattern, listing, re.MULTILINE))


def from_git_tree(repository: str, branch: str, under: str = "packages") -> set[str]:
    """Every directory in `under`, which is how several package collections are
    laid out: one directory per package, named for the package.

    Only that one directory is asked for, rather than the whole repository, so
    what comes back is the listing itself and not a tree the size of the
    project around it.
    """
    tree = json.loads(
        get(f"https://api.github.com/repos/{repository}/git/trees/{branch}:{under}")
    )
    if tree.get("truncated"):
        print(f"  {repository}: listing was truncated", file=sys.stderr)

    return {
        entry["path"]
        for entry in tree.get("tree", ())
        if entry.get("type") == "tree" and entry.get("path")
    }


# What each manager offers. A manager aeris gains is a line here, and no
# manager is written into this file anywhere else.
CATALOGUES = {
    "am": lambda: from_listing(
        "https://raw.githubusercontent.com/ivan-hc/AM/main/programs/x86_64-apps",
        r"^◆\s+(\S+)\s*:",
    ),
    "soarpkgs": lambda: from_git_tree("pkgforge/soarpkgs", "main"),
    "pacstall": lambda: from_git_tree("pacstall/pacstall-programs", "master"),
}


def packages() -> set[str]:
    """Every package name aeris might be asked to draw."""
    names: set[str] = set()
    for manager, read in CATALOGUES.items():
        try:
            offered = read()
        except Exception as e:
            print(f"  {manager}: {e}", file=sys.stderr)
            continue
        print(f"  {manager}: {len(offered)}", file=sys.stderr)
        names |= offered
    return names


def lookup_keys(package: str) -> list[str]:
    """The names to try for a package, most exact first."""
    keys = [package.lower()]
    for suffix in PACKAGING_SUFFIXES:
        trimmed = keys[0].removesuffix(suffix)
        if trimmed != keys[0] and trimmed:
            keys.append(trimmed)
    return keys


def resolves(icon: str) -> bool:
    request = urllib.request.Request(
        f"{FLATHUB_ICONS}/{icon}", headers={"User-Agent": AGENT}, method="HEAD"
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except Exception:
        return False


def stage(package: str, where: str) -> str | None:
    """Put a candidate's icon in candidates/ so it can be looked at.

    Returns what it was called, or nothing if it could not be had. A URL is
    fetched; anything else is a file already unpacked.
    """
    try:
        if where.startswith(("http://", "https://")):
            body = get(where)
        else:
            body = pathlib.Path(where).read_bytes()
    except Exception:
        # Reported only if every answer for this package fails, since the
        # next one along may well have it.
        return None

    if not body:
        return None

    extension = "svg" if body[:512].lstrip().startswith((b"<?xml", b"<svg")) else "png"
    (STAGED / f"{package}.{extension}").write_bytes(body)
    return f"{package}.{extension}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-ambiguous",
        action="store_true",
        help="also suggest matches for names like 'music', which are usually wrong",
    )
    parser.add_argument(
        "--without-arch",
        action="store_true",
        help="skip the Arch catalogue, which is a 22 MB download",
    )
    args = parser.parse_args()

    covered = set(tomllib.loads(SOURCES.read_text())["icons"])

    with tempfile.TemporaryDirectory() as scratch:
        catalogues = [("flathub", flathub())]
        if not args.without_arch:
            catalogues.append(("arch", arch(pathlib.Path(scratch))))

        print("reading what each manager offers", file=sys.stderr)
        wanted = sorted(packages() - covered)
        print(f"{len(wanted)} packages without an icon", file=sys.stderr)

        # Every answer, surest first, rather than only the first one: a
        # catalogue that names an icon it no longer serves should not stop a
        # later catalogue that still has it.
        found: dict[str, list[tuple[str, str, str]]] = {}
        for package in wanted:
            keys = lookup_keys(package)
            if keys[0] in AMBIGUOUS and not args.include_ambiguous:
                continue
            for key in keys:
                for origin, tables in catalogues:
                    for how in ("name", "binary", "tail"):
                        where = tables[how].get(key)
                        if where:
                            trimmed = "" if key == keys[0] else ", trimmed"
                            found.setdefault(package, []).append(
                                (where, origin, how + trimmed)
                            )

        print(f"{len(found)} candidates, staging each one", file=sys.stderr)
        if STAGED.exists():
            shutil.rmtree(STAGED)
        STAGED.mkdir()

        kept: dict[str, tuple[str, str, str]] = {}
        for package, answers in sorted(found.items()):
            for entry in answers:
                if stage(package, entry[0]):
                    kept[package] = entry
                    break

    dropped = len(found) - len(kept)
    if not kept:
        print("nothing new to propose", file=sys.stderr)
        return 0

    width = max(len(p) + 2 for p in kept)

    def recorded(where: str, origin: str) -> str:
        # An icon fetched is recorded by where it came from; one unpacked from
        # a package is recorded by the package, since the path it was unpacked
        # to was temporary.
        return where if origin != "arch" else ARCH_RELEASE

    lines = "\n".join(
        f'{chr(34) + package + chr(34):<{width}} = "{recorded(where, origin)}"'
        f"  # {origin}, matched on {how}"
        for package, (where, origin, how) in sorted(kept.items())
    )
    CANDIDATES.write_text(
        "# Suggested by tools/propose.py. Nothing here is trusted yet.\n"
        "#\n"
        "# These were matched by name, which is a guess. The icon each would draw\n"
        "# is staged in candidates/: flip through it, delete the wrong ones, then\n"
        "# run tools/accept.py to take what is left. A wrong icon is worse than\n"
        "# none, so anything you are unsure of should go.\n\n"
        "[icons]\n" + lines + "\n"
    )
    print(
        f"{len(kept)} staged in {STAGED.name}/ and written to {CANDIDATES.name}"
        f" ({dropped} could not be had)",
        file=sys.stderr,
    )
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
