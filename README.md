# aeris-metadata

Icons for packages that are not installed yet.

[aeris](https://github.com/pkgforge/aeris) draws a real icon for anything it
has one for, and a drawing of a package for everything else. Once a package is
installed its manager writes a desktop entry and aeris reads the icon from
there; before that, there is nothing on the machine to read. This repository is
what fills that gap.

## What ships

| | |
|---|---|
| `icons/` | every icon, each named after the package it belongs to |
| `index.toml` | which packages have one, what kind, and where they are served from |
| `icons.toml` | the exceptions, and only the exceptions |

Aeris reads `index.toml` once, then asks for `krita.png` the first time it
draws `krita` and keeps it. A session touches a handful of icons rather than
all of them, and adding one costs everybody a single small request rather than
a fresh copy of the set.

Nothing is built or published. The icons are served straight out of the
repository, at whatever `base` in `index.toml` says, so moving them somewhere
else is a change here and not a release of aeris.

## Adding an icon

Record where it comes from in `sources.toml`, keyed by the package name as the
manager reports it, then fetch it:

```toml
[icons]
"inkscape" = "https://example.org/inkscape/icon.png"
```

```sh
python3 tools/fetch.py            # brings in anything named but not yet here
python3 tools/index.py            # writes index.toml from what icons/ holds
```

That writes `icons/inkscape.png`, and **the icon is what you commit**, along
with the `sources.toml` line recording where it came from and the updated
`index.toml`.

For an icon nobody publishes, put the file at `icons/<package>.png` yourself
and say where it came from:

```toml
"my-tool" = "drawn by hand"
```

Either a PNG or an SVG, 128×128 if raster. CI checks that `index.toml` says
what `icons/` actually holds and fails if they have drifted.

## The exceptions file

`icons.toml` exists for the two cases a name alone cannot express.

**One package wants another's icon.** Saves carrying the same picture twice:

```toml
[default]
"krita-devel" = "krita"
```

A suffix saying how something was *built* rather than what it *is* needs no
entry at all: `-bin`, `-deb`, `-app`, `-appimage`, `-static` and `-git` are
dropped when nothing matches, so `krita-bin` finds `krita` on its own. Saying
it of a name says it of the built forms too, so the line above also covers
`krita-devel-bin`.

What is left alone is a channel a project brands separately, such as `-esr`,
`-beta` or `-nightly`. Firefox draws a different fox for each of those, so they
get their own icons rather than the release one.

**Two managers mean different things by one name.** A manager's own table wins
over `[default]`, and `[default]` wins over the package's own name:

```toml
[am]
"some-editor" = "some-editor-nightly"
```

Only the manager that means something different needs saying. Anything the
other managers offer under that name keeps being drawn with its own icon.

Everything else needs no entry at all. A package called `krita` is drawn with
the icon called `krita` because that is what it is called.

## Finding new icons

```sh
python3 tools/propose.py                 # ~25s, 22 MB for the Arch catalogue
python3 tools/propose.py --without-arch  # Flathub only, no large download
```

It fetches what every manager offers, drops anything already covered, and looks
the rest up in what Flathub and Arch publish. Each candidate's icon is staged
in `candidates/` and recorded in `needs-review.toml`. Nothing is read off the
machine it runs on, so it proposes the same thing anywhere.

Flathub is asked first and Arch second, but every answer is kept and tried in
turn: a catalogue that names an icon it no longer serves does not stop a later
one that still has it.

Then look through `candidates/`, **delete every icon that is wrong**, and take
what is left:

```sh
python3 tools/accept.py           # moves candidates/ into icons/, updates both files
python3 tools/accept.py --dry-run # says what it would take
```

Rejecting is deleting the file. That is the whole review: the icon aeris would
draw is sitting in front of you.

Adding a manager is one line in `CATALOGUES`:

```python
CATALOGUES = {
    "am": lambda: from_listing(
        "https://raw.githubusercontent.com/ivan-hc/AM/main/programs/x86_64-apps",
        r"^◆\s+(\S+)\s*:",
    ),
    "soarpkgs": lambda: from_git_tree("pkgforge/soarpkgs", "main"),
    "pacstall": lambda: from_git_tree("pacstall/pacstall-programs", "master"),
}
```

`from_listing` reads a text file that names one package per line;
`from_git_tree` reads a repository laid out one directory per package. Those
are shapes rather than managers, so a new one picks whichever fits.

A name is also tried without a suffix that says how it was built rather than
what it is, so `86box-app` finds what `86box` finds. Suffixes marking a
different build, such as `-git` or `-nightly`, are left alone: those are a
different program often enough to be worth deciding by hand.

**Every candidate needs a person before it moves into `sources.toml`.** It
matches on names, and names collide. A wrong icon is worse than no icon: a
missing one reads as "this is a command line tool", a wrong one reads as a
different program.

## Licensing

The tools and the lists are MIT, the same as aeris.

Each icon belongs to the project that drew it and is redistributed here on the
same terms, the way a distribution ships an icon cache beside its package
listing. `sources.toml` records where every one of them came from. If you
maintain a project and would rather your icon were not carried here, open an
issue and it will be removed.
