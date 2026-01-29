from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Callable

import httpx

from lab.mcp._typing import WebSearchResultItem


def _strip_tags(raw_html: str) -> str:
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return s.strip()


def _build_item(title: str | None, url: str | None, snippet: str | None) -> WebSearchResultItem | None:
    if not url:
        return None
    try:
        return WebSearchResultItem(
            title=title or url,
            url=url,
            snippet=snippet or None,
        )
    except Exception:
        return None


class SearchProvider:
    name: str

    async def search(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        raise NotImplementedError


def _ddg_extract_results(html_text: str, max_results: int) -> list[WebSearchResultItem]:
    results: list[WebSearchResultItem] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</', re.DOTALL)

    for match in pattern.finditer(html_text):
        url = html.unescape(match.group("url"))
        title = _strip_tags(match.group("title"))
        chunk = html_text[match.end() : match.end() + 1200]
        snippet_match = snippet_pattern.search(chunk)
        snippet = _strip_tags(snippet_match.group("snippet")) if snippet_match else None
        item = _build_item(title, url, snippet)
        if item:
            results.append(item)
        if len(results) >= max_results:
            break
    return results


class DuckDuckGoHtmlProvider(SearchProvider):
    name = "duckduckgo"

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or "https://duckduckgo.com/html/").rstrip("/") + "/"

    async def search(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        params = {"q": query}
        headers = {"User-Agent": "XnneHangLab-MCP/1.0"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(self._base_url, params=params, headers=headers)
        resp.raise_for_status()
        return _ddg_extract_results(resp.text, max_results)


class SearxNGProvider(SearchProvider):
    name = "searxng"

    def __init__(self, base_url: str, lang: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._lang = lang

    async def search(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        params = {"q": query, "format": "json"}
        if self._lang:
            params["language"] = self._lang
        headers = {"User-Agent": "XnneHangLab-MCP/1.0"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(f"{self._base_url}/search", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        items: list[WebSearchResultItem] = []
        for row in data.get("results", []):
            item = _build_item(row.get("title"), row.get("url"), row.get("content"))
            if item:
                items.append(item)
            if len(items) >= max_results:
                break
        return items


class BraveSearchProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "XnneHangLab-MCP/1.0",
            "X-Subscription-Token": self._api_key,
        }
        params = {"q": query, "count": max_results}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.search.brave.com/res/v1/web/search", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        items: list[WebSearchResultItem] = []
        for row in data.get("web", {}).get("results", []):
            item = _build_item(row.get("title"), row.get("url"), row.get("description"))
            if item:
                items.append(item)
            if len(items) >= max_results:
                break
        return items


class SerperProvider(SearchProvider):
    name = "serper"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": self._api_key,
            "User-Agent": "XnneHangLab-MCP/1.0",
        }
        payload = {"q": query, "num": max_results}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://google.serper.dev/search", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        items: list[WebSearchResultItem] = []
        for row in data.get("organic", []):
            item = _build_item(row.get("title"), row.get("link"), row.get("snippet"))
            if item:
                items.append(item)
            if len(items) >= max_results:
                break
        return items


@dataclass(frozen=True)
class ProviderFactory:
    name: str
    factory: Callable[[], SearchProvider | None]


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def build_search_providers() -> list[SearchProvider]:
    ddg_url = _env("XNNE_DDG_HTML_URL")
    searx_url = _env("XNNE_SEARXNG_URL") or _env("SEARXNG_BASE_URL")
    searx_lang = _env("SEARXNG_LANGUAGE") or None
    brave_key = _env("BRAVE_SEARCH_API_KEY")
    serper_key = _env("SERPER_API_KEY")

    registry = {
        "searxng": ProviderFactory("searxng", lambda: SearxNGProvider(searx_url, searx_lang) if searx_url else None),
        "brave": ProviderFactory("brave", lambda: BraveSearchProvider(brave_key) if brave_key else None),
        "serper": ProviderFactory("serper", lambda: SerperProvider(serper_key) if serper_key else None),
        "duckduckgo": ProviderFactory("duckduckgo", lambda: DuckDuckGoHtmlProvider(ddg_url or None)),
        "ddg": ProviderFactory("duckduckgo", lambda: DuckDuckGoHtmlProvider(ddg_url or None)),
    }

    order_raw = _env("XNNE_WEBSEARCH_PROVIDERS")
    if order_raw:
        order = [x.strip().lower() for x in order_raw.split(",") if x.strip()]
    else:
        order = ["searxng", "brave", "serper", "duckduckgo"]

    providers: list[SearchProvider] = []
    for name in order:
        factory = registry.get(name)
        if not factory:
            continue
        provider = factory.factory()
        if provider:
            providers.append(provider)

    if not providers:
        providers.append(DuckDuckGoHtmlProvider(ddg_url or None))

    return providers


async def search_with_fallback(query: str, max_results: int) -> list[WebSearchResultItem]:
    last_items: list[WebSearchResultItem] = []
    for provider in build_search_providers():
        try:
            items = await provider.search(query, max_results)
        except Exception:
            continue
        last_items = items
        if items:
            return items
    return last_items
