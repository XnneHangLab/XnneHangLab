from __future__ import annotations

import html
import json
import urllib.parse
from typing import Any

import httpx
import pydantic
from bs4 import BeautifulSoup
from loguru import logger

from lab.plugins.web_fetch import clamp_int, get_with_retries
from lab.plugins.web_search_ddg import WebSearchArgs, WebSearchResult, WebSearchResultItem
from lab.tools.base import BuiltinTool
from lab.tools.plugin import ToolPlugin
from lab.tools.types import AgentContext, ToolResult

DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
DEFAULT_ACCEPT_LANG = "zh-CN,zh;q=0.9,en;q=0.8"


def _headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": DEFAULT_ACCEPT,
        "Accept-Language": DEFAULT_ACCEPT_LANG,
    }


def _is_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_searxng_html_results(html_text: str, base_url: str, max_results: int) -> list[WebSearchResultItem]:
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[WebSearchResultItem] = []

    for article in soup.select("article.result"):
        h3 = article.find("h3")
        title = h3.get_text(" ", strip=True) if h3 else "No title"
        anchor = article.select_one("a.url_header") or (h3.find("a") if h3 else None)
        href = anchor.get("href") if anchor else None
        if not href:
            continue

        href = html.unescape(str(href))  # type: ignore[arg-type]
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urllib.parse.urljoin(base_url.rstrip("/") + "/", href)

        if not _is_http_url(href):
            continue

        snippet = None
        snippet_node = article.select_one("p.content")
        if snippet_node:
            snippet = snippet_node.get_text(" ", strip=True) or None

        try:
            items.append(WebSearchResultItem(title=title, url=href, snippet=snippet))  # type: ignore[arg-type]
        except pydantic.ValidationError:
            continue

        if len(items) >= max_results:
            break

    seen: set[str] = set()
    deduped: list[WebSearchResultItem] = []
    for item in items:
        url = str(item.url)
        if url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


class _WebSearchTool(BuiltinTool):
    name = "web_search"
    description = "Search the web through a SearXNG instance and return title, URL and snippet."
    usage_hint = "当需要通过自建 SearXNG 搜索网页结果时调用此工具。"

    def __init__(self, plugin: WebSearchSearxngPlugin) -> None:
        self._plugin = plugin

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords or natural language query."},
                        "max_results": {"type": "integer", "description": "Number of results to return (1-10)."},
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        try:
            parsed = WebSearchArgs.model_validate(args)
        except pydantic.ValidationError as exc:
            return ToolResult(ok=False, text="", error=str(exc))

        result = await self._plugin.search(query=parsed.query, max_results=parsed.max_results)
        content = json.dumps(
            [item.model_dump(exclude_none=True, mode="json") for item in result.results],
            ensure_ascii=False,
        )
        return ToolResult(ok=True, text=content, data=result.model_dump(exclude_none=True, mode="json"))


class WebSearchSearxngPlugin(ToolPlugin):
    name = "web_search"
    description = "Search the web using a SearXNG instance."

    def __init__(
        self,
        *,
        searxng_url: str,
        user_agent: str = "XnneHangLab-ToolPlugin/1.0",
        timeout_s: float = 10.0,
    ) -> None:
        self.searxng_url = searxng_url
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self._tool = _WebSearchTool(self)

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]

    async def on_register(self, ctx: AgentContext) -> bool:
        if not self.searxng_url.strip():
            logger.info("Skip WebSearchSearxngPlugin registration because searxng_url is empty")
            return False
        return True

    async def search(self, *, query: str, max_results: int) -> WebSearchResult:
        max_results = clamp_int(max_results, 1, 10)
        base = self.searxng_url.rstrip("/")
        async with httpx.AsyncClient(timeout=float(self.timeout_s), follow_redirects=True) as client:
            response = await get_with_retries(
                client,
                f"{base}/search",
                params={"q": query, "categories": "general", "count": max_results},
                headers=_headers(self.user_agent),
            )
        response.raise_for_status()
        return WebSearchResult(
            query=query,
            results=_parse_searxng_html_results(response.text, base_url=base, max_results=max_results),
        )
