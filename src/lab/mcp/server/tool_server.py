from __future__ import annotations

import html
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastmcp import FastMCP

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import ReadFileResult, WebFetchResult, WebSearchResult, WebSearchResultItem

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class AppContext:
    root_dir: Path


@asynccontextmanager
async def app_lifespan(server: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
    root_dir = Path.cwd().resolve()
    try:
        yield AppContext(root_dir=root_dir)
    finally:
        pass


mcp = FastMCP("tool", lifespan=app_lifespan)

# 预编译正则（性能更好，也更清晰）
_RE_BLOCK_TAGS = re.compile(r"(?is)<(script|style|noscript|svg|iframe|template)[^>]*>.*?</\1>")
_RE_COMMENTS = re.compile(r"(?s)<!--.*?-->")
_RE_ANY_TAG = re.compile(r"(?is)<[^>]+>")
_RE_BASE64 = re.compile(r"(?is)data:image/[^;]+;base64,[A-Za-z0-9+/=\s]{200,}")


def _extract_main_html(raw_html: str) -> str:
    """
    尽量只取正文区域（如果页面有 article/main），避免导航/脚本污染。
    """
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", raw_html)
    if m:
        return m.group(1)

    m = re.search(r"(?is)<main[^>]*>(.*?)</main>", raw_html)
    if m:
        return m.group(1)

    # 兜底：整页
    return raw_html


def _strip_tags(raw_html: str) -> str:
    """
    把 HTML 变成可读纯文本：
    - 删除 script/style 等块内容（关键！）
    - 删除注释
    - 去掉所有 tag
    - unescape 实体 & 压缩空白
    """
    s = raw_html

    # 1) 先删掉 script/style 等，否则会把一堆 JS/CSS 留下来
    s = _RE_BLOCK_TAGS.sub(" ", s)

    # 2) 删 HTML 注释
    s = _RE_COMMENTS.sub(" ", s)

    # 3) 可选：干掉超长 base64（一般来自内嵌图片/CSS）
    s = _RE_BASE64.sub(" ", s)

    # 4) 去掉所有剩余标签
    s = _RE_ANY_TAG.sub(" ", s)

    # 5) HTML 实体解码 + 压缩空白
    s = html.unescape(s)
    s = " ".join(s.split())
    return s


def _extract_ddg_results(html_text: str, max_results: int) -> list[WebSearchResultItem]:
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
        try:
            results.append(WebSearchResultItem(title=title, url=url, snippet=snippet)) # type: ignore
        except Exception:
            continue
        if len(results) >= max_results:
            break
    return results


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> WebSearchResult:
    """
    使用 DuckDuckGo HTML 页面做 Web Search。
    """
    params = {"q": query}
    headers = {"User-Agent": "XnneHangLab-MCP/1.0"}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get("https://duckduckgo.com/html/", params=params, headers=headers)
    resp.raise_for_status()
    results = _extract_ddg_results(resp.text, max_results)
    return WebSearchResult(query=query, results=results)


@mcp.tool()
async def web_fetch(url: str, max_chars: int = 20000, timeout_s: float = 10.0) -> WebFetchResult:
    """
    抓取网页内容，并尽量返回可读文本。
    """
    headers = {
        "User-Agent": "XnneHangLab-MCP/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)

    content_type = resp.headers.get("content-type")
    text = resp.text

    if content_type and "text/html" in content_type.lower():
        # 先尽量抽正文区域，再做 strip，效果比直接全页 strip 干净很多
        main_html = _extract_main_html(text)
        text = _strip_tags(main_html)

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return WebFetchResult(
        url=url, # type: ignore
        status_code=resp.status_code,
        content_type=content_type,
        text=text,
        truncated=truncated,
    )


@mcp.tool()
def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_chars: int = 8000,
) -> ReadFileResult:
    """
    读取本地文本文件内容。
    """
    root = Path.cwd().resolve()
    target = Path(path).expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside root: {target}") from exc

    content = target.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total_lines = len(lines)
    start = start_line or 1
    end = end_line or total_lines
    start = max(1, start)
    end = min(end, total_lines)

    selected = lines[start - 1 : end]
    text = "\n".join(selected)
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return ReadFileResult(
        path=str(target),
        text=text,
        truncated=truncated,
        start_line=start,
        end_line=end,
        total_lines=total_lines,
    )


def run_mcp():
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    mcp.run(
        transport=lab_settings.mcp.tool.transport,
        host=lab_settings.mcp.tool.host,
        port=lab_settings.mcp.tool.port,
        path=lab_settings.mcp.tool.path,
        log_level=lab_settings.mcp.tool.log_level,
    )


if __name__ == "__main__":
    run_mcp()
