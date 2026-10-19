"""SSRF hardening for ``image_url`` / ``video_url`` fetching (routes.py)."""
from __future__ import annotations

import base64
import io
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

_PUBLIC_IP = "93.184.216.34"


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color=(0, 255, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _fake_resolver(mapping: dict[str, list[str]]):
    """Return an async stand-in for routes._resolve_host."""

    async def _resolve(host: str, port: int) -> list[str]:  # noqa: ARG001
        if host in mapping:
            return mapping[host]
        # IP literals resolve to themselves, like getaddrinfo does
        return [host]

    return _resolve


@pytest.fixture()
def no_legacy_fetch():
    """Fail loudly if the unguarded sync httpx.get path is ever used."""
    with patch("httpx.get", side_effect=AssertionError("unguarded httpx.get used")) as m:
        yield m


class TestBlockedUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:11434/api/tags",  # loopback (e.g. local Ollama)
            "http://localhost/secret.png",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://10.0.0.5/internal.png",
            "http://192.168.1.1/router.png",
            "http://[::1]/x.png",
            "http://[::ffff:127.0.0.1]/x.png",  # IPv4-mapped loopback
            "http://0.0.0.0/x.png",
            "file:///etc/passwd",
            "ftp://example.com/x.png",
            "http://internal.example/x.png",  # resolves to a private address
        ],
    )
    def test_private_or_non_http_image_url_rejected(self, client, no_legacy_fetch, url):
        resolver = _fake_resolver(
            {"localhost": ["127.0.0.1"], "internal.example": ["10.1.2.3"]}
        )
        with patch("routes._resolve_host", side_effect=resolver):
            resp = client.post("/moderate_image", json={"image_url": url})
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]
        no_legacy_fetch.assert_not_called()

    def test_private_video_url_rejected(self, client):
        with patch("httpx.get", side_effect=AssertionError("unguarded fetch")) as m:
            resp = client.post(
                "/moderate_video", json={"video_url": "http://169.254.169.254/v.mp4"}
            )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]
        m.assert_not_called()

    def test_redirect_to_private_address_rejected(self, client):
        """A public URL must not be able to bounce the engine onto an internal host."""
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})

        with (
            patch("routes._resolve_host", side_effect=_fake_resolver({"cdn.example": [_PUBLIC_IP]})),
            patch("routes._media_transport", httpx.MockTransport(handler)),
        ):
            resp = client.post("/moderate_image", json={"image_url": "http://cdn.example/a.png"})
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]
        assert seen == ["http://cdn.example/a.png"]  # the internal hop was never requested


class TestAllowedUrls:
    def test_public_image_url_is_fetched_and_moderated(self, client):
        png = _png_bytes()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=png, headers={"Content-Type": "image/png"})

        with (
            patch("routes._resolve_host", side_effect=_fake_resolver({"cdn.example": [_PUBLIC_IP]})),
            patch("routes._media_transport", httpx.MockTransport(handler)),
        ):
            resp = client.post("/moderate_image", json={"image_url": "https://cdn.example/a.png"})
        assert resp.status_code == 200
        assert resp.json()["verdict"] in ("allow", "flag", "delete")

    def test_public_redirect_is_followed(self, client):
        png = _png_bytes()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/old.png":
                return httpx.Response(301, headers={"Location": "/new.png"})
            return httpx.Response(200, content=png)

        with (
            patch("routes._resolve_host", side_effect=_fake_resolver({"cdn.example": [_PUBLIC_IP]})),
            patch("routes._media_transport", httpx.MockTransport(handler)),
        ):
            resp = client.post("/moderate_image", json={"image_url": "https://cdn.example/old.png"})
        assert resp.status_code == 200

    def test_oversized_download_rejected(self, client):
        import config

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"\0" * 2048)

        with (
            patch("routes._resolve_host", side_effect=_fake_resolver({"cdn.example": [_PUBLIC_IP]})),
            patch("routes._media_transport", httpx.MockTransport(handler)),
            patch.object(config.settings, "max_media_bytes", 1024),
        ):
            resp = client.post("/moderate_image", json={"image_url": "https://cdn.example/big.png"})
        assert resp.status_code == 413

    def test_base64_still_takes_precedence_over_url(self, client):
        b64 = base64.b64encode(_png_bytes()).decode()
        resp = client.post(
            "/moderate_image",
            json={"image_base64": b64, "image_url": "http://127.0.0.1/ignored.png"},
        )
        assert resp.status_code == 200

    def test_private_urls_allowed_when_opted_in(self, client):
        import config

        png = _png_bytes()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=png)

        with (
            patch("routes._media_transport", httpx.MockTransport(handler)),
            patch.object(config.settings, "media_url_allow_private", True),
        ):
            resp = client.post("/moderate_image", json={"image_url": "http://10.0.0.5/a.png"})
        assert resp.status_code == 200
