#!/usr/bin/env python3
"""Fetch any icon named in sources.toml that is not in icons/ yet.

This is the only thing here that goes looking for an icon, and it runs when
somebody adds one rather than on every build. Everything afterwards works from
the files in icons/, so the repository holds the icons rather than a list of
places to go and get them.

An icon already in icons/ is left alone. Refetching one that has changed
upstream is deliberate: pass --refetch and say which.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import pathlib
import sys
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.toml"
ICONS = ROOT / "icons"

TIMEOUT = 30
AGENT = "aeris-metadata (https://github.com/pkgforge/aeris-metadata)"

# What aeris can draw, in the order it prefers them.
EXTENSIONS = ("svg", "png")


# What a file is, read from its first bytes rather than from what it is called.
SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "png"),)


def formatted(body: bytes) -> str | None:
    for signature, extension in SIGNATURES:
        if body.startswith(signature):
            return extension

    # SVG is text, and may open with a declaration, a comment, or the tag.
    head = body[:512].lstrip()
    if head.startswith((b"<?xml", b"<svg", b"<!--")) and b"<svg" in body[:2048]:
        return "svg"
    return None


def fetch(job: tuple[str, str]) -> tuple[str, str]:
    package, source = job

    if not source.startswith(("http://", "https://")):
        return package, f"not a URL, expected {source} to be committed already"

    request = urllib.request.Request(source, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                return package, f"HTTP {response.status}"
            body = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return package, str(e)

    extension = formatted(body)
    if extension is None:
        return package, "what came back is neither a PNG nor an SVG"

    # A package given one format and then the other should not end up with
    # both, so anything already here under another name goes.
    for other in EXTENSIONS:
        if other != extension:
            (ICONS / f"{package}.{other}").unlink(missing_ok=True)

    (ICONS / f"{package}.{extension}").write_bytes(body)
    return package, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refetch",
        metavar="PACKAGE",
        nargs="*",
        help="fetch these again even though they are already here",
    )
    parser.add_argument("--jobs", type=int, default=12)
    args = parser.parse_args()

    ICONS.mkdir(exist_ok=True)
    sources: dict[str, str] = tomllib.loads(SOURCES.read_text())["icons"]

    again = set(args.refetch or ())
    unknown = again - set(sources)
    if unknown:
        print(f"not named in sources.toml: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    missing = {
        package: source
        for package, source in sources.items()
        if package in again or not any((ICONS / f"{package}.{e}").is_file() for e in EXTENSIONS)
    }

    if not missing:
        print(f"all {len(sources)} icons are already here", file=sys.stderr)
        return 0

    print(f"fetching {len(missing)} of {len(sources)}", file=sys.stderr)
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for package, why in pool.map(fetch, sorted(missing.items())):
            if why:
                failed.append((package, why))

    for package, why in failed:
        print(f"  {package}: {why}", file=sys.stderr)

    got = len(missing) - len(failed)
    print(f"fetched {got}, {len(failed)} failed", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
