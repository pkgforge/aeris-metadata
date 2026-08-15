# Icons committed here

For an application nobody publishes an icon for, put the file here and name it
in `sources.toml` by its file name rather than a URL:

```toml
[icons]
"my-tool" = "my-tool.png"
```

`tools/mirror.py` reads these the same way it reads a URL, so an icon that
lives here is indistinguishable from one that was fetched once it is in the
archive.

A 128x128 PNG, please. Anything larger is carried at full size for every
person who installs aeris.
