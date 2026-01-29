from __future__ import annotations

import html
import json
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


def _extract_next_data_text(raw_html: str) -> str | None:
    m = re.search(r'(?is)<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw_html)
    if not m:
        return None
    try:
        data = json.loads(html.unescape(m.group(1)))
    except Exception:
        return None

    # 粗暴但泛用：递归找“很长的字符串”，拼起来
    chunks: list[str] = []

    def walk(x):  # type: ignore
        if isinstance(x, dict):
            for v in x.values():  # type: ignore
                walk(v)  # type: ignore
        elif isinstance(x, list):
            for v in x:  # type: ignore
                walk(v)  # type: ignore
        elif isinstance(x, str):
            s = x.strip()
            # 过滤太短/明显不是正文的
            if len(s) >= 200 and (" " in s or "。" in s or "." in s):
                chunks.append(s)

    walk(data)

    if not chunks:
        return None

    # 取前几段，避免把整站配置也塞进来
    out = "\n\n".join(chunks[:10])
    return out if len(out) >= 400 else None


_RE_BLOCK_TAGS = re.compile(r"(?is)<(script|style|noscript|svg|iframe|template)[^>]*>.*?</\1>")
_RE_COMMENTS = re.compile(r"(?s)<!--.*?-->")
_RE_BASE64 = re.compile(r"(?is)data:image/[^;]+;base64,[A-Za-z0-9+/=\s]{200,}")
_RE_ANY_TAG = re.compile(r"(?is)<[^>]+>")

# 这些标签出现时，通常意味着段落/结构
_RE_BREAKS = re.compile(
    r"(?is)</?(p|div|section|article|main|header|footer|h[1-6]|li|ul|ol|br|hr|blockquote|pre|table|tr|td)\b[^>]*>"
)


def _strip_tags(raw_html: str) -> str:
    s = raw_html
    s = _RE_BLOCK_TAGS.sub(" ", s)
    s = _RE_COMMENTS.sub(" ", s)
    s = _RE_BASE64.sub(" ", s)

    # 先把结构性标签替换成换行，避免“一坨一行”
    s = _RE_BREAKS.sub("\n", s)

    s = _RE_ANY_TAG.sub(" ", s)
    s = html.unescape(s)

    # 清理多余空白：保留换行
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _looks_bad(text: str) -> bool:
    t = text.strip()
    if len(t) < 400:  # 太短通常没抽到正文
        return True
    # JS/CSS 味太重（可按你站点调整）
    bad_markers = ["self.__next_s", "__NEXT_DATA__", "window.__ENV", "function(", "var ", "{", "};"]
    hits = sum(1 for m in bad_markers if m in t)
    if hits >= 3:
        return True
    return False


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
            results.append(WebSearchResultItem(title=title, url=url, snippet=snippet))  # type: ignore
        except Exception:
            continue
        if len(results) >= max_results:
            break
    return results


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> WebSearchResult:
    """
    使用 DuckDuckGo HTML 页面做 Web Search。
    args:
    query: 搜索关键词。
    max_results: 返回结果数量，最多 5 条。
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
    args:
    url: 目标网页 URL。
    max_chars: 返回文本最大字符数，超出截断。
    """
    headers = {
        "User-Agent": "XnneHangLab-MCP/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)

    content_type = resp.headers.get("content-type")
    raw = resp.text
    text = raw

    if content_type and "text/html" in content_type.lower():
        # 1) 优先 article/main
        main_html = _extract_main_html(raw)
        text1 = _strip_tags(main_html)

        # 2) 如果看起来不对，退回全页 strip
        if _looks_bad(text1):
            text2 = _strip_tags(raw)
        else:
            text2 = text1

        # 3) 仍然不对，再试 Next.js __NEXT_DATA__
        if _looks_bad(text2):
            nd = _extract_next_data_text(raw)
            if nd:
                text2 = nd

        text = text2

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return WebFetchResult(
        url=url,  # type: ignore
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
    max_chars: int = 20000,
) -> ReadFileResult:
    """
    读取本地文本文件内容，相对路径的根目录为项目根目录。
    如果用户让你读取一个相对路径或者绝对路径的文件，调用这个工具。如果没有特殊说明的话，默认读取整个文件内容。
    args:
    path: 文件路径（相对或绝对）。
    start_line: 起始行号（从 1 开始），默认从头开始
    end_line: 结束行号（从 1 开始），默认读到结尾
    """
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    root = lab_settings.root.root_dir
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
