from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://api.sketchfab.com/v3"


class SketchfabClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self._client.request(method, url, headers=self._headers(), **kwargs)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self._request("GET", path, params=clean)

    def _post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=data or {})

    def _delete(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", path, json=data) if data else self._request("DELETE", path)

    def next_page(self, url: str) -> Any:
        """Fetch a `next` cursor URL returned by a listing."""
        return self._request("GET", url)

    # === Search & models ===

    def search_models(self, **params: Any) -> Any:
        """Search models (q, tags, categories, downloadable, sort_by, count, ...)."""
        return self._get("/search", {"type": "models", **params})

    def search_users(self, **params: Any) -> Any:
        return self._get("/search", {"type": "users", **params})

    def search_collections(self, **params: Any) -> Any:
        return self._get("/search", {"type": "collections", **params})

    def get_model(self, uid: str) -> Any:
        return self._get(f"/models/{uid}")

    def get_download(self, uid: str) -> Any:
        """Get temporary download URLs (gltf, glb, usdz, source). Auth required."""
        return self._get(f"/models/{uid}/download")

    def delete_model(self, uid: str) -> None:
        self._delete(f"/models/{uid}")

    def upload_model(self, path: Path, fields: dict[str, Any]) -> Any:
        with open(path, "rb") as f:
            return self._request(
                "POST",
                "/models",
                data={k: v for k, v in fields.items() if v is not None},
                files={"modelFile": (path.name, f)},
                timeout=600.0,
            )

    def download_file(self, url: str, dest: Path) -> None:
        with self._client.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)

    # === Taxonomy ===

    def get_categories(self) -> Any:
        return self._get("/categories")

    def get_licenses(self) -> Any:
        return self._get("/licenses")

    def get_tags(self) -> Any:
        return self._get("/tags")

    # === Users ===

    def get_me(self) -> dict[str, Any]:
        return self._get("/me")  # type: ignore[no-any-return]

    def get_account(self) -> Any:
        return self._get("/me/account")

    def get_user(self, uid: str) -> Any:
        return self._get(f"/users/{uid}")

    def get_my_models(self, **params: Any) -> Any:
        return self._get("/me/models", params)

    def get_user_models(self, user: str, **params: Any) -> Any:
        return self._get("/models", {"user": user, **params})

    # === Likes ===

    def get_likes(self) -> Any:
        return self._get("/me/likes")

    def like(self, model: str) -> Any:
        return self._post("/me/likes", {"model": model})

    def unlike(self, model: str) -> None:
        self._delete(f"/me/likes/{model}")

    # === Collections ===

    def get_my_collections(self) -> Any:
        return self._get("/me/collections")

    def get_collection(self, uid: str) -> Any:
        return self._get(f"/collections/{uid}")

    def get_collection_models(self, uid: str) -> Any:
        return self._get(f"/collections/{uid}/models")

    # === Comments ===

    def get_comments(self, model: str) -> Any:
        return self._get("/comments", {"model": model})

    def post_comment(self, model: str, body: str) -> Any:
        return self._post("/comments", {"model": model, "body": body})

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SketchfabClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
