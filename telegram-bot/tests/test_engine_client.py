"""Tests for the engine HTTP client — retry logic and API-key forwarding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    """Build a minimal httpx.Response for mocking."""
    import json as json_lib
    content = json_lib.dumps(json_body or {}).encode()
    request = httpx.Request("POST", "http://engine:8000/moderate_text")
    return httpx.Response(status_code=status_code, content=content, request=request)


_ALLOW_RESULT = {
    "verdict": "allow",
    "reasons": [],
    "scores": {"violence": 0.0, "sexual_violence": 0.0, "nsfw": 0.0, "deepfake_suspect": 0.0},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModerateText:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        ok_resp = _make_response(200, _ALLOW_RESULT)
        with patch("engine_client._get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=ok_resp)
            mock_get.return_value = mock_client

            import engine_client
            result = await engine_client.moderate_text("hello")

        assert result["verdict"] == "allow"
        mock_client.post.assert_called_once_with(
            "/moderate_text", json={"text": "hello", "platform": "telegram"}
        )

    @pytest.mark.asyncio
    async def test_retries_on_transport_error(self):
        ok_resp = _make_response(200, _ALLOW_RESULT)
        call_count = 0

        async def flaky_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("connection refused")
            return ok_resp

        with (
            patch("engine_client._get_client") as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),  # skip real waits
        ):
            mock_client = MagicMock()
            mock_client.post = flaky_post
            mock_get.return_value = mock_client

            import engine_client
            result = await engine_client.moderate_text("hello")

        assert result["verdict"] == "allow"
        assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        with (
            patch("engine_client._get_client") as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client = MagicMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
            mock_get.return_value = mock_client

            import engine_client
            with pytest.raises(httpx.ConnectError):
                await engine_client.moderate_text("hello")

        # 1 initial + 3 retries = 4 total calls
        assert mock_client.post.call_count == 4

    @pytest.mark.asyncio
    async def test_retries_on_5xx(self):
        ok_resp = _make_response(200, _ALLOW_RESULT)
        server_error = _make_response(503, {"detail": "unavailable"})

        responses = [server_error, ok_resp]

        async def post_sequence(*args, **kwargs):
            return responses.pop(0)

        with (
            patch("engine_client._get_client") as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client = MagicMock()
            mock_client.post = post_sequence
            mock_get.return_value = mock_client

            import engine_client
            result = await engine_client.moderate_text("hello")

        assert result["verdict"] == "allow"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 401, 403, 422])
    async def test_does_not_retry_client_errors(self, status):
        with (
            patch("engine_client._get_client") as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=_make_response(status, {"detail": "x"}))
            mock_get.return_value = mock_client

            import engine_client
            with pytest.raises(httpx.HTTPStatusError):
                await engine_client.moderate_text("hello")

        assert mock_client.post.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_retry_read_timeout(self):
        """A read timeout means the engine is busy — re-sending only adds load."""
        with (
            patch("engine_client._get_client") as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client = MagicMock()
            mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
            mock_get.return_value = mock_client

            import engine_client
            with pytest.raises(httpx.ReadTimeout):
                await engine_client.moderate_video(b"\x00\x01")

        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_payload_carries_audit_context(self):
        ok_resp = _make_response(200, _ALLOW_RESULT)
        with patch("engine_client._get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=ok_resp)
            mock_get.return_value = mock_client

            import engine_client
            await engine_client.moderate_image(b"img", user_id="1", group_id="-100")

        path, = mock_client.post.call_args.args
        payload = mock_client.post.call_args.kwargs["json"]
        assert path == "/moderate_image"
        assert payload["image_base64"] == "aW1n"
        assert payload["user_id"] == "1"
        assert payload["group_id"] == "-100"
        assert payload["platform"] == "telegram"


class TestApiKeyHeader:
    def test_client_includes_api_key_when_configured(self, monkeypatch):
        monkeypatch.setenv("ENGINE_API_KEY", "my-secret")

        # Force client to be rebuilt
        import engine_client
        engine_client._client = None

        import config as config_module
        config_module.settings.engine_api_key = "my-secret"

        client = engine_client._get_client()
        assert client.headers.get("x-api-key") == "my-secret"

        # Cleanup
        engine_client._client = None
        config_module.settings.engine_api_key = ""

    def test_client_uses_configured_timeout(self):
        import config as config_module
        import engine_client
        engine_client._client = None
        original = config_module.settings.engine_timeout_seconds
        config_module.settings.engine_timeout_seconds = 12.5
        try:
            client = engine_client._get_client()
            assert client.timeout.read == 12.5
        finally:
            engine_client._client = None
            config_module.settings.engine_timeout_seconds = original

    def test_client_omits_header_when_no_key(self, monkeypatch):
        import engine_client
        engine_client._client = None

        import config as config_module
        config_module.settings.engine_api_key = ""

        client = engine_client._get_client()
        assert "x-api-key" not in client.headers

        engine_client._client = None
