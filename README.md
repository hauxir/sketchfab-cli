# sketchfab-cli

A command-line tool for [Sketchfab](https://sketchfab.com): search, inspect and download 3D models, and manage your own.
Built on the [Data API v3](https://docs.sketchfab.com/data-api/v3/index.html).

## Installation

Requires Python 3.12+.

```bash
pip install .
# or
uv pip install .
```

## Authentication

Search and model info work anonymously. Downloading and anything personal needs an API token from
<https://sketchfab.com/settings/password>.

```bash
sketchfab login -t <api-token>   # validated, then saved
sketchfab whoami
sketchfab logout
```

Or set `SKETCHFAB_TOKEN`. Config is stored in `~/.config/sketchfab/config.json` (mode 600).

## Commands

```bash
sketchfab search "cat" -d -l 10 -s -likeCount   # downloadable, top liked
sketchfab search --category animals-pets --license cc0
sketchfab model <uid>                            # details (viewer URLs also accepted)
sketchfab download <uid> -f glb -o models/       # glb | gltf | usdz | source
sketchfab download <uid> --url-only              # temporary signed URL
sketchfab categories | licenses
sketchfab user <name> [-m]                       # profile / their models
sketchfab comments <uid> [-p "nice!"]
sketchfab my-models | likes | like <uid> | unlike <uid>
sketchfab collections [<uid>]
sketchfab upload model.glb -n "Name" -t "tag1 tag2" [--private] [--draft]
sketchfab delete-model <uid>
```

Every listing command supports `-j` / `--json-output`.

## Development

```bash
pip install -e ".[dev]"
ruff check sketchfab_cli/
basedpyright
```

## License

MIT
