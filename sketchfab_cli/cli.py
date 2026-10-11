import json
import os
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table

from sketchfab_cli import config
from sketchfab_cli.client import SketchfabClient

console = Console()

SORT_CHOICES = ["-likeCount", "-viewCount", "-publishedAt", "-createdAt", "likeCount", "viewCount", "publishedAt"]


def get_client() -> SketchfabClient:
    token = os.environ.get("SKETCHFAB_TOKEN") or config.get_token()
    return SketchfabClient(token)


def _dump(data: Any) -> None:
    console.print_json(json.dumps(data, default=str))


def _results(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("results", [])  # type: ignore[no-any-return]
    return data  # type: ignore[no-any-return]


def _user_name(m: dict[str, Any]) -> str:
    user = m.get("user") or {}
    return str(user.get("displayName") or user.get("username") or "")


def _models_table(title: str, models: list[dict[str, Any]]) -> None:
    table = Table(title=title)
    table.add_column("UID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Author", style="dim")
    table.add_column("Likes", justify="right", style="yellow")
    table.add_column("Views", justify="right")
    table.add_column("Faces", justify="right", style="dim")
    table.add_column("DL", justify="center")
    table.add_column("License", style="dim")
    for m in models:
        lic = m.get("license") or {}
        table.add_row(
            str(m.get("uid", "")),
            str(m.get("name", ""))[:45],
            _user_name(m)[:20],
            str(m.get("likeCount", "")),
            str(m.get("viewCount", "")),
            str(m.get("faceCount", "")),
            "[green]yes[/green]" if m.get("isDownloadable") else "",
            str(lic.get("label", lic.get("slug", "")) if isinstance(lic, dict) else lic)[:30],
        )
    console.print(table)


def _show_models(title: str, data: Any, json_output: bool, empty: str = "No models found") -> None:
    if json_output:
        _dump(data)
        return
    models = _results(data)
    if not models:
        console.print(f"[dim]{empty}[/dim]")
        return
    _models_table(title, models)
    if isinstance(data, dict) and data.get("next"):
        console.print("[dim]More results available - raise --limit[/dim]")


class _Group(click.Group):
    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except httpx.HTTPStatusError as e:
            r = e.response
            hint = " (not logged in? try `sketchfab login`)" if r.status_code in (401, 403) else ""
            console.print(f"[red]API error {r.status_code} for {r.request.url.path}{hint}[/red]")
            raise SystemExit(1)


@click.group(cls=_Group)
def main() -> None:
    """Sketchfab CLI - Search, download and manage 3D models on Sketchfab."""


# === Authentication ===


@main.command()
@click.option("--token", "-t", help="API token (https://sketchfab.com/settings/password)")
def login(token: str | None) -> None:
    """Save your Sketchfab API token.

    \b
    Find your token at https://sketchfab.com/settings/password
    Examples:
      sketchfab login -t <api-token>
      sketchfab login               # prompts for token
    """
    if not token:
        token = click.prompt("API token", hide_input=True)
    assert token
    try:
        with SketchfabClient(token) as client:
            user = client.get_me()
    except httpx.HTTPStatusError:
        console.print("[red]Token rejected by Sketchfab - not saved.[/red]")
        raise SystemExit(1)
    config.set_token(token)
    console.print(f"[green]Logged in as[/green] [bold]{user.get('displayName') or user.get('username')}[/bold]")
    console.print(f"Config saved to {config.CONFIG_FILE}")


@main.command()
def logout() -> None:
    """Clear saved credentials."""
    config.clear_config()
    console.print("[green]Logged out - credentials cleared[/green]")


@main.command("config-show")
def config_show() -> None:
    """Show current configuration."""
    console.print(f"[bold]Config file:[/bold] {config.CONFIG_FILE}")
    token = os.environ.get("SKETCHFAB_TOKEN") or config.get_token()
    console.print(f"[bold]Token:[/bold] {token[:6] + '...' if token else '[dim]not set[/dim]'}")


@main.command("whoami")
def whoami() -> None:
    """Show current user info."""
    with get_client() as client:
        user = client.get_me()
        for key, val in user.items():
            if val and not isinstance(val, (dict, list)):
                console.print(f"[bold]{key}:[/bold] {val}")
        account = (client.get_account() or {}).get("plan", {})
        if account:
            console.print(f"[bold]plan:[/bold] {account.get('label', account.get('name', ''))}")


# === Models ===


@main.command()
@click.argument("query", required=False)
@click.option("--limit", "-l", default=24, help="Number of results (max 24 per page)")
@click.option("--sort", "-s", type=click.Choice(SORT_CHOICES), help="Sort order")
@click.option("--downloadable", "-d", is_flag=True, help="Only downloadable models")
@click.option("--animated", is_flag=True, help="Only animated models")
@click.option("--staffpicked", is_flag=True, help="Only staff picks")
@click.option("--category", "-c", help="Category slug (see `categories`)")
@click.option("--tag", help="Tag")
@click.option("--user", "-u", help="Restrict to a username")
@click.option("--license", "license_", help="License slug (see `licenses`)")
@click.option("--max-faces", type=int, help="Maximum face count")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def search(
    query: str | None,
    limit: int,
    sort: str | None,
    downloadable: bool,
    animated: bool,
    staffpicked: bool,
    category: str | None,
    tag: str | None,
    user: str | None,
    license_: str | None,
    max_faces: int | None,
    json_output: bool,
) -> None:
    """Search for models."""
    with get_client() as client:
        result = client.search_models(
            q=query,
            count=min(limit, 24),
            sort_by=sort,
            downloadable=True if downloadable else None,
            animated=True if animated else None,
            staffpicked=True if staffpicked else None,
            categories=category,
            tags=tag,
            user=user,
            license=license_,
            max_face_count=max_faces,
        )
        # Follow pagination until we have `limit` results
        collected = list(result.get("results", []))
        while len(collected) < limit and result.get("next"):
            result = client.next_page(result["next"])
            collected.extend(result.get("results", []))
        result["results"] = collected[:limit]
        if len(collected) <= limit:
            result["next"] = None
        _show_models(f"Models matching '{query or ''}'", result, json_output)


@main.command("model")
@click.argument("uid")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def model_show(uid: str, json_output: bool) -> None:
    """Show model details by UID (or viewer URL)."""
    uid = uid.rstrip("/").split("-")[-1]
    with get_client() as client:
        m = client.get_model(uid)
        if json_output:
            _dump(m)
            return
        lic = m.get("license") or {}
        console.print(f"[bold cyan]{m.get('name', '')}[/bold cyan]  [dim]{m.get('uid')}[/dim]")
        console.print(f"[bold]Author:[/bold] {_user_name(m)}")
        console.print(f"[bold]URL:[/bold] {m.get('viewerUrl')}")
        console.print(f"[bold]License:[/bold] {lic.get('label', '-')}")
        console.print(
            f"[bold]Likes:[/bold] {m.get('likeCount')}  [bold]Views:[/bold] {m.get('viewCount')}  "
            f"[bold]Comments:[/bold] {m.get('commentCount')}"
        )
        console.print(
            f"[bold]Faces:[/bold] {m.get('faceCount')}  [bold]Vertices:[/bold] {m.get('vertexCount')}  "
            f"[bold]Animations:[/bold] {m.get('animationCount')}"
        )
        console.print(f"[bold]Downloadable:[/bold] {'yes' if m.get('isDownloadable') else 'no'}")
        console.print(f"[bold]Categories:[/bold] {', '.join(c.get('name', '') for c in m.get('categories', []))}")
        console.print(f"[bold]Tags:[/bold] {', '.join(t.get('name', '') for t in m.get('tags', []))}")
        if m.get("description"):
            console.print(f"\n{m['description']}")
        archives = m.get("archives") or {}
        for fmt, a in archives.items():
            if a and a.get("size"):
                console.print(f"[dim]{fmt}: {a['size'] / 1_000_000:.1f} MB, {a.get('faceCount')} faces[/dim]")


@main.command()
@click.argument("uid")
@click.option("--format", "-f", "fmt", type=click.Choice(["glb", "gltf", "usdz", "source"]), default="glb")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Save to this file or directory")
@click.option("--url-only", is_flag=True, help="Print the temporary download URL instead of downloading")
@click.option("--json-output", "-j", is_flag=True, help="Output all download links as JSON")
def download(uid: str, fmt: str, output: Path | None, url_only: bool, json_output: bool) -> None:
    """Download a model (auth required, model must be downloadable)."""
    uid = uid.rstrip("/").split("-")[-1]
    with get_client() as client:
        try:
            links = client.get_download(uid)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            hint = {401: "not logged in", 403: "model is not downloadable"}.get(code, "")
            console.print(f"[red]Download failed ({code}){': ' + hint if hint else ''}[/red]")
            raise SystemExit(1)
        if json_output:
            _dump(links)
            return
        entry = links.get(fmt)
        if not entry:
            console.print(f"[red]Format '{fmt}' not available.[/red] Available: {', '.join(links)}")
            raise SystemExit(1)
        if url_only:
            click.echo(entry["url"])
            return
        ext = {"glb": "glb", "gltf": "zip", "usdz": "usdz", "source": "zip"}[fmt]
        dest = Path(f"{uid}.{ext}") if output is None else output
        if dest.is_dir():
            dest = dest / f"{uid}.{ext}"
        client.download_file(entry["url"], dest)
        console.print(f"[green]Saved[/green] {dest} ({dest.stat().st_size / 1_000_000:.1f} MB)")


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", "-n", help="Model name")
@click.option("--description", "-d", help="Model description")
@click.option("--tags", "-t", help="Space-separated tags")
@click.option("--private", is_flag=True, help="Make the model private (paid plans)")
@click.option("--draft", is_flag=True, help="Upload as draft (don't publish)")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def upload(
    file: Path,
    name: str | None,
    description: str | None,
    tags: str | None,
    private: bool,
    draft: bool,
    json_output: bool,
) -> None:
    """Upload a model file (zip, glb, gltf, obj, fbx, ...)."""
    with get_client() as client:
        result = client.upload_model(
            file,
            {
                "name": name or file.stem,
                "description": description,
                "tags": tags,
                "private": "true" if private else None,
                "isPublished": "false" if draft else None,
            },
        )
        if json_output:
            _dump(result)
            return
        uid = result.get("uid")
        console.print(f"[green]Uploaded[/green] uid={uid}")
        console.print(f"https://sketchfab.com/3d-models/{uid} [dim](processing may take a few minutes)[/dim]")


@main.command("delete-model")
@click.argument("uid")
@click.confirmation_option(prompt="Permanently delete this model?")
def delete_model(uid: str) -> None:
    """Delete one of your models."""
    with get_client() as client:
        client.delete_model(uid)
        console.print("[green]Deleted[/green]")


@main.command("my-models")
@click.option("--downloadable", "-d", is_flag=True, help="Only downloadable models")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def my_models(downloadable: bool, json_output: bool) -> None:
    """List your own models (auth required)."""
    with get_client() as client:
        _show_models("My models", client.get_my_models(downloadable=True if downloadable else None), json_output)


# === Taxonomy ===


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def categories(json_output: bool) -> None:
    """List model categories."""
    with get_client() as client:
        data = client.get_categories()
        if json_output:
            _dump(data)
            return
        table = Table(title="Categories")
        table.add_column("Slug", style="cyan")
        table.add_column("Name", style="green")
        for c in _results(data):
            table.add_row(str(c.get("slug", "")), str(c.get("name", "")))
        console.print(table)


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def licenses(json_output: bool) -> None:
    """List licenses."""
    with get_client() as client:
        data = client.get_licenses()
        if json_output:
            _dump(data)
            return
        table = Table(title="Licenses")
        table.add_column("Slug", style="cyan")
        table.add_column("Name", style="green")
        for lic in _results(data):
            table.add_row(str(lic.get("slug", "")), str(lic.get("fullName", lic.get("label", ""))))
        console.print(table)


# === Users ===


@main.command("user")
@click.argument("username_or_uid")
@click.option("--models", "-m", is_flag=True, help="List the user's models")
@click.option("--limit", "-l", default=24, help="Number of models")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def user_show(username_or_uid: str, models: bool, limit: int, json_output: bool) -> None:
    """Show a user (by UID) or search users by name; --models lists their models."""
    with get_client() as client:
        found = client.search_users(q=username_or_uid, count=1).get("results", [])
        if not found:
            console.print("[red]User not found[/red]")
            raise SystemExit(1)
        u = found[0]
        if models:
            _show_models(
                f"Models by {u.get('username')}", client.get_user_models(u["uid"], count=min(limit, 24)), json_output
            )
            return
        if json_output:
            _dump(u)
            return
        for key, val in u.items():
            if val and not isinstance(val, (dict, list)):
                console.print(f"[bold]{key}:[/bold] {val}")


# === Likes ===


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def likes(json_output: bool) -> None:
    """List models you've liked (auth required)."""
    with get_client() as client:
        _show_models("Liked models", client.get_likes(), json_output, "No liked models")


@main.command()
@click.argument("uid")
def like(uid: str) -> None:
    """Like a model (auth required)."""
    with get_client() as client:
        client.like(uid)
        console.print("[green]Liked[/green]")


@main.command()
@click.argument("uid")
def unlike(uid: str) -> None:
    """Remove your like from a model (auth required)."""
    with get_client() as client:
        client.unlike(uid)
        console.print("[green]Unliked[/green]")


# === Collections ===


@main.command()
@click.argument("uid", required=False)
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def collections(uid: str | None, json_output: bool) -> None:
    """List your collections, or the models in collection UID (auth required for your own)."""
    with get_client() as client:
        if uid:
            _show_models("Collection", client.get_collection_models(uid), json_output)
            return
        data = client.get_my_collections()
        if json_output:
            _dump(data)
            return
        table = Table(title="My collections")
        table.add_column("UID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Models", justify="right")
        for c in _results(data):
            table.add_row(str(c.get("uid", "")), str(c.get("name", "")), str(c.get("modelCount", "")))
        console.print(table)


# === Comments ===


@main.command()
@click.argument("uid")
@click.option("--post", "-p", "body", help="Post a comment instead of listing (auth required)")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def comments(uid: str, body: str | None, json_output: bool) -> None:
    """List comments on a model, or post one with --post."""
    with get_client() as client:
        if body:
            client.post_comment(uid, body)
            console.print("[green]Comment posted[/green]")
            return
        data = client.get_comments(uid)
        if json_output:
            _dump(data)
            return
        items = _results(data)
        if not items:
            console.print("[dim]No comments[/dim]")
            return
        for c in items:
            console.print(
                f"[bold]{(c.get('user') or {}).get('username', '?')}[/bold] [dim]{c.get('createdAt', '')}[/dim]"
            )
            console.print(f"  {c.get('body', '')}")
