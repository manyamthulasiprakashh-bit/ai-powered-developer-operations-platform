import asyncio

import httpx
import pytest

from app.core.cache import AsyncTTLCache
from app.core.config import Settings, get_settings
from app.core.exceptions import GitHubServiceError, GitHubTimeoutError
from app.integrations.github.client import GitHubClient
from app.services.github_service import GitHubService


class AsyncRepositoryClient:
    def __init__(self):
        self.calls = 0

    async def aget_repository(self, owner, repo):
        self.calls += 1
        await asyncio.sleep(0)
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
            "private": False,
            "default_branch": "main",
            "html_url": f"https://github.com/{owner}/{repo}",
        }


class StubAsyncHttpClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def request(self, **kwargs):
        if self.error:
            raise self.error
        return self.response

    async def aclose(self):
        pass


@pytest.mark.anyio
async def test_async_github_client_returns_successful_response():
    client = GitHubClient(base_url="https://github.example")
    client._async_client = StubAsyncHttpClient(response=httpx.Response(200, json={"name": "repo"}))

    assert await client.aget_repository("owner", "repo") == {"name": "repo"}


@pytest.mark.anyio
async def test_async_github_client_maps_upstream_failure():
    client = GitHubClient(base_url="https://github.example")
    client._async_client = StubAsyncHttpClient(response=httpx.Response(503))

    with pytest.raises(GitHubServiceError, match="GitHub API error: 503"):
        await client.aget_repository("owner", "repo")


@pytest.mark.anyio
async def test_async_github_client_maps_timeout():
    client = GitHubClient(base_url="https://github.example")
    client._async_client = StubAsyncHttpClient(error=httpx.ReadTimeout("timeout"))

    with pytest.raises(GitHubTimeoutError):
        await client.aget_repository("owner", "repo")


@pytest.mark.anyio
async def test_async_github_client_maps_malformed_response():
    response = httpx.Response(200, content=b"not-json")
    client = GitHubClient(base_url="https://github.example")
    client._async_client = StubAsyncHttpClient(response=response)

    with pytest.raises(GitHubServiceError, match="malformed data"):
        await client.aget_repository("owner", "repo")


@pytest.mark.anyio
async def test_service_cache_hit_avoids_duplicate_async_github_request():
    client = AsyncRepositoryClient()
    service = GitHubService(client=client)

    first = await service.get_repository_async("owner", "repo")
    second = await service.get_repository_async("owner", "repo")

    assert first.full_name == second.full_name == "owner/repo"
    assert client.calls == 1


@pytest.mark.anyio
async def test_service_single_flight_deduplicates_concurrent_requests():
    client = AsyncRepositoryClient()
    service = GitHubService(client=client)

    results = await asyncio.gather(*[service.get_repository_async("owner", "repo") for _ in range(10)])

    assert len(results) == 10
    assert client.calls == 1


@pytest.mark.anyio
async def test_cache_ttl_and_max_entries(monkeypatch):
    current_time = 100.0
    monkeypatch.setattr("app.core.cache.time.monotonic", lambda: current_time)
    cache = AsyncTTLCache(ttl_seconds=10, max_entries=1)
    loads = 0

    async def loader():
        nonlocal loads
        loads += 1
        return loads

    assert await cache.get_or_set("a", loader) == 1
    assert await cache.get_or_set("a", loader) == 1
    await cache.set("b", 2)
    assert await cache.get("a") is None
    current_time = 111.0
    assert await cache.get_or_set("b", loader) == 2
    assert loads == 2


@pytest.mark.anyio
async def test_cache_disabled_does_not_store_values():
    cache = AsyncTTLCache(enabled=False)
    loads = 0

    async def loader():
        nonlocal loads
        loads += 1
        return loads

    assert await cache.get_or_set("a", loader) == 1
    assert await cache.get_or_set("a", loader) == 2


@pytest.mark.anyio
async def test_cache_does_not_store_errors():
    cache = AsyncTTLCache()
    calls = 0

    async def failing_loader():
        nonlocal calls
        calls += 1
        raise GitHubServiceError("upstream failed")

    with pytest.raises(GitHubServiceError):
        await cache.get_or_set("a", failing_loader)
    with pytest.raises(GitHubServiceError):
        await cache.get_or_set("a", failing_loader)
    assert calls == 2


def test_github_client_uses_configured_connection_limits_and_timeouts(monkeypatch):
    monkeypatch.setenv("GITHUB_CONNECT_TIMEOUT", "2.5")
    monkeypatch.setenv("GITHUB_READ_TIMEOUT", "12.5")
    monkeypatch.setenv("GITHUB_MAX_CONNECTIONS", "40")
    monkeypatch.setenv("GITHUB_MAX_KEEPALIVE_CONNECTIONS", "8")

    get_settings.cache_clear()
    settings = Settings()
    client = GitHubClient()

    assert settings.github_connect_timeout == 2.5
    assert settings.github_read_timeout == 12.5
    assert client.timeout.connect == 2.5
    assert client.timeout.read == 12.5
    assert client.limits.max_connections == 40
    assert client.limits.max_keepalive_connections == 8


def test_scalability_settings_have_bounded_defaults():
    settings = Settings()

    assert settings.github_max_per_page == 100
    assert settings.cache_enabled is True
    assert settings.cache_ttl_seconds == 60
    assert settings.cache_max_entries == 500
