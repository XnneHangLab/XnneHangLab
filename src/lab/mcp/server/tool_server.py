from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import logging
import time
import urllib.parse
import urllib.robotparser
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pydantic
from bs4 import BeautifulSoup  # ✅ 强依赖：只用这一种“最常用/最实用”的解析方式
from fastmcp import FastMCP

from lab.config_manager.config import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import ReadFileResult, WebFetchResult, WebSearchResult, WebSearchResultItem

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from pydantic import BaseModel


def _dump_json(model: BaseModel) -> dict[str, Any]:
    """
    Force pydantic to serialize in JSON mode.
    Key point: AnyHttpUrl -> "https://..." (string), not {"_url": Url(...)}.
    """
    return model.model_dump(exclude_none=True, mode="json")


DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
DEFAULT_ACCEPT_LANG = "zh-CN,zh;q=0.9,en;q=0.8"

lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)


def _ua() -> str:
    """
    User-Agent used for all outbound HTTP requests.

    Reads:
        lab_settings.mcp.tools.user_agent
    """
    return lab_settings.mcp.tools.user_agent


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """
    Build common HTTP headers for outbound requests.
    """
    h = {
        "User-Agent": _ua(),
        "Accept": DEFAULT_ACCEPT,
        "Accept-Language": DEFAULT_ACCEPT_LANG,
    }
    if extra:
        h.update(extra)
    return h


def _clamp_int(v: int, lo: int, hi: int) -> int:
    """
    Clamp an integer into [lo, hi]. On conversion failure returns lo.
    """
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, iv))


# =============================================================================
# MCP app context
# =============================================================================


@dataclass
class AppContext:
    root_dir: Path


@asynccontextmanager
async def app_lifespan(server: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
    """
    FastMCP lifespan: provides project root_dir as context.

    Reads:
        lab_settings.root.root_dir
    """
    root = Path(lab_settings.root.root_dir).expanduser().resolve()
    yield AppContext(root_dir=root)


mcp = FastMCP("tool", lifespan=app_lifespan)

# =============================================================================
# HTTP helpers (stable, minimal)
# =============================================================================


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 2,
    backoff_s: float = 0.6,
) -> httpx.Response:
    """
    Perform GET with a small retry + exponential backoff.

    Why it exists:
        - Real-world web requests often fail transiently (timeouts, resets).
        - This keeps behavior stable without adding multiple parsing fallbacks.
    """
    last_exc: Exception | None = None
    for i in range(retries + 1):
        try:
            return await client.get(url, params=params, headers=headers)
        except httpx.RequestError as e:
            # Retry on likely-transient httpx network errors (timeouts, DNS, connect, etc.).
            last_exc = e
            if i >= retries:
                logging.getLogger(__name__).warning(
                    "HTTP GET to %s failed after %d retries; last error: %s: %s",
                    url,
                    retries,
                    type(e).__name__,
                    str(e),
                )
                break
            await asyncio.sleep(backoff_s * (2**i))
        except Exception as e:
            # Non-httpx exceptions are treated as non-retryable and re-raised immediately.
            logging.getLogger(__name__).error(
                "Non-retryable error during HTTP GET to %s: %s: %s",
                url,
                type(e).__name__,
                str(e),
            )
            raise
    assert last_exc is not None
    raise last_exc


# =============================================================================
# Safety: refuse private/localhost URLs (SSRF guard)
# =============================================================================


def _is_probably_private_host(host: str) -> bool:
    """
    Return True if host is likely private/loopback.

    This protects web_fetch from being abused to access:
        - localhost services
        - internal network services (192.168.x.x / 10.x.x.x / etc.)
    """
    if not host:
        return True
    h = host.lower().strip()
    if h in {"localhost"}:
        return True
    if h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except Exception:
        return False


def _validate_public_http_url(url: str) -> None:
    """
    Validate that a URL is public and uses http/https.

    Raises:
        ValueError: if URL is not allowed.
    """
    p = urllib.parse.urlparse(url)
    if p.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if not p.netloc:
        raise ValueError("URL missing host")
    if _is_probably_private_host(p.hostname or ""):
        raise ValueError("Refuse to fetch localhost/private network URL")


# =============================================================================
# robots.txt
# =============================================================================

_ROBOTS_CACHE: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}
_ROBOTS_TTL_S = 6 * 3600


async def _allowed_by_robots(url: str) -> bool:
    """
    Check robots.txt allowance for the given URL.

    Reads:
        lab_settings.mcp.tools.web_fetch.respect_robots
        lab_settings.mcp.tools.web_fetch.robots_fail_closed
        lab_settings.mcp.tools.web_fetch.timeout_s

    Behavior:
        - If respect_robots is False -> always allow
        - If robots cannot be fetched/parsed:
            - robots_fail_closed = False -> allow
            - robots_fail_closed = True  -> deny
    """
    s = lab_settings.mcp.tools.web_fetch
    if not s.respect_robots:
        return True

    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    now = time.time()

    cached = _ROBOTS_CACHE.get(base)
    if cached and (now - cached[0]) < _ROBOTS_TTL_S:
        rp = cached[1]
        return rp.can_fetch(_ua(), url)

    robots_url = urllib.parse.urljoin(base, "/robots.txt")
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)

    timeout_s = float(s.timeout_s)
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        try:
            r = await _get_with_retries(client, robots_url, headers=_headers())
            if r.status_code >= 400:
                _ROBOTS_CACHE[base] = (now, rp)
                return False if s.robots_fail_closed else True
            rp.parse(r.text.splitlines())
            _ROBOTS_CACHE[base] = (now, rp)
            return rp.can_fetch(_ua(), url)
        except Exception:
            return False if s.robots_fail_closed else True


# =============================================================================
# HTML -> readable text (single, maintainable method)
# =============================================================================


def _clean_soup(soup: BeautifulSoup) -> None:
    """
    Remove non-content tags that usually pollute text extraction.
    """
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()


def _pick_main_container(soup: BeautifulSoup):
    """
    Choose the most likely 'main content' container.
    Priority: <article> -> <main> -> <body> -> document root
    """
    return soup.find("article") or soup.find("main") or soup.body or soup


def _html_to_text(raw_html: str) -> str:
    """
    Convert HTML to readable plain text using BeautifulSoup only.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    _clean_soup(soup)
    container = _pick_main_container(soup)

    # separator keeps some structure (paragraph-ish), strip trims edges
    text = container.get_text(separator="\n", strip=True)

    # normalize excessive blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


def _extract_next_data_text(raw_html: str) -> str | None:
    """
    Extract readable text from Next.js __NEXT_DATA__ if present.

    Why:
        Some sites render content client-side; __NEXT_DATA__ can contain the real text.

    Implementation:
        - Find <script id="__NEXT_DATA__"> via BeautifulSoup (no regex)
        - Parse JSON, walk recursively, collect longer text chunks
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None

    try:
        data = json.loads(html.unescape(script.string))
    except Exception:
        return None

    chunks: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():  # type: ignore
                walk(v)
        elif isinstance(x, list):
            for v in x:  # type: ignore
                walk(v)
        elif isinstance(x, str):
            s = x.strip()
            # heuristic: longer strings with natural language markers
            if len(s) >= 200 and (" " in s or "。" in s or "." in s):
                chunks.append(s)

    walk(data)

    if not chunks:
        return None

    out = "\n\n".join(chunks[:12])
    return out if len(out) >= 400 else None


def _looks_unusable(text: str) -> bool:
    """
    Heuristic: whether extracted text is likely not real content.
    """
    t = text.strip()
    if len(t) < 400:
        return True
    bad_markers = ["__NEXT_DATA__", "window.__ENV", "function(", "var ", "{", "};"]
    return sum(1 for m in bad_markers if m in t) >= 3


# =============================================================================
# Web Search providers (one parsing strategy each)
# =============================================================================


def _is_http_url(u: str) -> bool:
    try:
        p = urllib.parse.urlparse(u)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except ValueError:
        return False


def _dedup_keep_order(items: Iterable[WebSearchResultItem]) -> list[WebSearchResultItem]:
    seen: set[str] = set()
    out: list[WebSearchResultItem] = []
    for it in items:
        u = str(it.url)
        if u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out


def _decode_ddg_redirect(u: str) -> str:
    """
    DuckDuckGo HTML results sometimes link to /l/?uddg=<encoded>.
    Decode to the real URL.
    """
    try:
        p = urllib.parse.urlparse(u)
        if "duckduckgo.com/l/" in u or p.path.startswith("/l/"):
            qs = urllib.parse.parse_qs(p.query)
            uddg = qs.get("uddg", [None])[0]
            if uddg:
                return urllib.parse.unquote(uddg)
    except Exception:
        pass
    return u


def _parse_ddg_html_results(html_text: str, max_results: int) -> list[WebSearchResultItem]:
    """
    Parse DuckDuckGo HTML result page using BeautifulSoup only.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[WebSearchResultItem] = []

    # a.result__a is the standard title link in DDG HTML
    for a in soup.select("a.result__a"):
        title = a.get_text(" ", strip=True) or "No title"
        href = a.get("href") or ""
        href = html.unescape(href)  # type: ignore
        href = _decode_ddg_redirect(href)  # type: ignore

        if href.startswith("//"):
            href = "https:" + href

        if not _is_http_url(href):
            continue

        # snippet: typically in the same result block
        snippet = None
        block = a.find_parent(class_="result")
        if block:
            sn = block.select_one(".result__snippet")
            if sn:
                snippet = sn.get_text(" ", strip=True) or None

        try:
            items.append(WebSearchResultItem(title=title, url=href, snippet=snippet))  # type: ignore
        except pydantic.ValidationError:
            # AnyHttpUrl validation fails -> skip
            continue

        if len(items) >= max_results:
            break

    return _dedup_keep_order(items)


def _parse_searxng_html_results(html_text: str, base_url: str, max_results: int) -> list[WebSearchResultItem]:
    """
    Parse SearXNG HTML results using BeautifulSoup only.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[WebSearchResultItem] = []

    for article in soup.select("article.result"):
        h3 = article.find("h3")
        title = h3.get_text(" ", strip=True) if h3 else "No title"

        a = article.select_one("a.url_header") or (h3.find("a") if h3 else None)
        href = a.get("href") if a else None
        if not href:
            continue

        href = html.unescape(href)  # type: ignore
        if href.startswith("//"):  # type: ignore
            href = "https:" + href  # type: ignore
        elif href.startswith("/"):  # type: ignore
            href = urllib.parse.urljoin(base_url.rstrip("/") + "/", href)  # type: ignore

        if not _is_http_url(href):  # type: ignore
            continue

        snippet = None
        p = article.select_one("p.content")
        if p:
            snippet = p.get_text(" ", strip=True) or None

        try:
            items.append(WebSearchResultItem(title=title, url=href, snippet=snippet))  # type: ignore
        except Exception:
            continue

        if len(items) >= max_results:
            break

    return _dedup_keep_order(items)


async def _search_duckduckgo(query: str, max_results: int) -> list[WebSearchResultItem]:
    """
    DuckDuckGo HTML search.
    No extra dependencies beyond httpx + bs4.
    """
    s = lab_settings.mcp.tools.web_search
    timeout_s = float(s.timeout_s)
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await _get_with_retries(
            client,
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers=_headers(),
        )
    resp.raise_for_status()
    return _parse_ddg_html_results(resp.text, max_results)


async def _search_searxng(query: str, max_results: int) -> list[WebSearchResultItem]:
    """
    SearXNG search via your self-hosted instance.
    Recommended for stability and control.
    """
    s = lab_settings.mcp.tools.web_search
    base = s.searxng_url.rstrip("/")
    timeout_s = float(s.timeout_s)

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await _get_with_retries(
            client,
            f"{base}/search",
            params={"q": query, "categories": "general", "count": max_results},
            headers=_headers(),
        )
    resp.raise_for_status()
    return _parse_searxng_html_results(resp.text, base_url=base, max_results=max_results)


async def _run_search(provider: str, query: str, max_results: int) -> list[WebSearchResultItem]:
    """
    Dispatch search based on provider name.
    Provider is validated by your Pydantic/Literal on the caller side.
    """
    p = (provider or "").strip().lower()
    if p == "searxng":
        return await _search_searxng(query, max_results)
    # default / fallback provider choice is still "duckduckgo"
    return await _search_duckduckgo(query, max_results)


# =============================================================================
# Jina fallback (optional)
# =============================================================================


async def _fetch_via_jina(original_url: str, timeout_s: float) -> str | None:
    """
    Fetch via Jina reader endpoint:
        https://r.jina.ai/<original_url>

    Notes:
        - If jina_api_key is empty, request is made without auth.
        - Returned content is typically readable markdown/text.
    """
    s = lab_settings.mcp.tools.web_fetch
    headers = _headers()
    if s.jina_api_key:
        headers["Authorization"] = f"Bearer {s.jina_api_key}"

    url = f"https://r.jina.ai/{original_url}"
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await _get_with_retries(client, url, headers=headers)
    if resp.status_code >= 400:
        return None
    t = resp.text.strip()
    return t or None


def _render_non_html(content_type: str | None, raw_text: str) -> str:
    """
    Render non-HTML response into readable text.
    - JSON -> pretty print
    - other -> raw text
    """
    if not content_type:
        return raw_text
    ct = content_type.lower()
    if "application/json" in ct or ct.endswith("+json"):
        try:
            return json.dumps(json.loads(raw_text), ensure_ascii=False, indent=2)
        except Exception:
            return raw_text
    return raw_text


# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool()
async def web_search(query: str, max_results: int = 5, provider: str | None = None) -> WebSearchResult:
    """
    Search the web and return a small list of results (title + url + snippet).

    When to use:
        - The user asks for information that may be online (docs, articles, news, explanations).
        - You need multiple sources quickly (compare viewpoints or pick an authoritative source).
        - You want URLs you can later pass into `web_fetch()` for full-page reading.

    Args:
        query:
            Search keywords or a natural-language query.
            Example: "FastMCP streamable-http tutorial"
        max_results:
            Number of results to return. Clamped to [1, 10].
        provider:
            Optional provider override.
            If omitted, uses `lab_settings.mcp.tools.web_search.provider`.
            Allowed values (your Literal): "duckduckgo" / "searxng"

    Returns:
        WebSearchResult:
            {
              "query": "<query>",
              "results": [
                {"title": "...", "url": "https://...", "snippet": "..."},
                ...
              ]
            }

    Examples:
        - Minimal:
            web_search(query="FastMCP tutorial")
        - Override provider:
            web_search(query="OpenAI o1 vs gpt-4.1-mini", provider="searxng", max_results=5)

    Notes for tool-model behavior:
        - Prefer `provider="searxng"` in config for stability (self-hosted + predictable HTML).
        - URLs are validated as http/https; invalid URLs are dropped.
    """
    max_results = _clamp_int(max_results, 1, 10)

    s = lab_settings.mcp.tools.web_search
    provider = provider or s.provider

    try:
        results = await _run_search(provider, query, max_results)
    except Exception:
        logging.getLogger(__name__).exception("web_search failed: provider=%s query=%s", provider, query)
        results = []
    result_model = WebSearchResult(query=query, results=results)
    return _dump_json(result_model)  # type: ignore[return-value]


@mcp.tool()
async def web_fetch(url: str, max_chars: int = 8000, timeout_s: float = 10.0) -> WebFetchResult:
    """
    Fetch a web page and extract readable text.

    When to use:
        - You already have a URL (from the user or from `web_search`) and need page content.
        - You want to read an article / docs page and summarize it.
        - You need the authoritative text from the source page.

    Safety / compliance:
        - Refuses localhost/private-network URLs (SSRF guard).
        - Optionally respects robots.txt:
            controlled by `lab_settings.mcp.tools.web_fetch.respect_robots`.
        - If robots.txt disallows fetching, returns status_code=451 with an explanation.

    Extraction strategy (single maintainable path):
        1) If HTML: BeautifulSoup -> remove scripts/styles -> choose article/main/body -> get_text()
        2) If text seems unusable and `__NEXT_DATA__` exists: extract from Next.js data
        3) If still unusable and `use_jina_fallback=true`: use https://r.jina.ai/<url>
        4) If not HTML: return readable form (JSON pretty-print, otherwise raw)

    Args:
        url:
            Target page URL. Must be http/https and public.
        max_chars:
            Maximum characters to return (will be truncated). Clamped to [256, 20000].
        timeout_s:
            HTTP timeout seconds. Clamped to [1.0, 30.0].

    Returns:
        WebFetchResult:
            {
              "url": "https://...",
              "status_code": 200,
              "content_type": "text/html; charset=utf-8",
              "text": "<readable text>",
              "truncated": false
            }

    Examples:
        - Read a page:
            web_fetch(url="https://example.com/docs", max_chars=12000)
        - Respect config defaults (callers may omit max_chars/timeout_s):
            web_fetch(url="https://example.com")

    Notes for tool-model behavior:
        - If a page is heavy/dynamic, consider enabling `use_jina_fallback` in config.
        - For multi-page research: call `web_search()` first, then `web_fetch()` on selected URLs.
    """
    _validate_public_http_url(url)

    s = lab_settings.mcp.tools.web_fetch
    max_chars = _clamp_int(max_chars, 256, 20000)
    timeout_s = max(1.0, min(float(timeout_s), 30.0))

    if not await _allowed_by_robots(url):
        return WebFetchResult(
            url=url,  # type: ignore
            status_code=451,
            content_type="text/plain",
            text="Blocked by robots.txt (respect_robots=true).",
            truncated=False,
        )

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await _get_with_retries(client, url, headers=_headers())

    content_type = resp.headers.get("content-type")
    raw = resp.text

    if content_type and "text/html" in content_type.lower():
        text1 = _html_to_text(raw)

        if _looks_unusable(text1):
            nd = _extract_next_data_text(raw)
            if nd:
                text1 = nd

        if _looks_unusable(text1) and s.use_jina_fallback:
            try:
                jina_text = await _fetch_via_jina(url, timeout_s=min(20.0, timeout_s + 5.0))
                if jina_text and len(jina_text) >= 200:
                    text1 = jina_text
            except Exception:  # 忽略 Jina 失败
                pass

        text = text1
    else:
        text = _render_non_html(content_type, raw)

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    result_model = WebFetchResult(
        url=url,  # type: ignore
        status_code=resp.status_code,
        content_type=content_type,
        text=text,
        truncated=truncated,
    )
    return _dump_json(result_model)  # type: ignore[return-value]


@mcp.tool()
def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_chars: int = 8000,
) -> ReadFileResult:
    """
    Read a local text file from within project root.

    When to use:
        - The user asks to inspect local files (logs/config/code) inside the project directory.
        - You need to read snippets to answer questions about local code/config.

    Security model:
        - Resolves the target path and enforces it is inside `lab_settings.root.root_dir`.
        - This prevents reading arbitrary files outside the project.

    Args:
        path:
            File path (relative to root_dir or absolute).
        start_line:
            1-based start line (inclusive). If omitted, starts from 1.
        end_line:
            1-based end line (inclusive). If omitted, reads to end of file.
        max_chars:
            Maximum characters to return. Clamped to [256, 20000].

    Returns:
        ReadFileResult:
            {
              "path": "<absolute path>",
              "text": "<file content slice>",
              "truncated": false,
              "start_line": 1,
              "end_line": 200,
              "total_lines": 1234
            }

    Examples:
        - Read whole file:
            read_file(path="README.md")
        - Read a range:
            read_file(path="src/app.py", start_line=1, end_line=200)
    """
    root = Path(lab_settings.root.root_dir).expanduser().resolve()

    p = Path(path).expanduser()
    target = (root / p).resolve() if not p.is_absolute() else p.resolve()

    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside root: {target}") from exc

    content = target.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total_lines = len(lines)

    start = max(1, start_line or 1)
    end = min(total_lines, end_line or total_lines)
    if end < start:
        end = start

    selected = lines[start - 1 : end]
    text = "\n".join(selected)

    max_chars = _clamp_int(max_chars, 256, 20000)
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    result_model = ReadFileResult(
        path=str(target),
        text=text,
        truncated=truncated,
        start_line=start,
        end_line=end,
        total_lines=total_lines,
    )
    return _dump_json(result_model)  # type: ignore[return-value]


# =============================================================================
# Run server
# =============================================================================


def run_mcp() -> None:
    """
    Start the MCP tool server using lab_settings.mcp.servers.tool configuration.

    Reads:
        lab_settings.mcp.servers.tool.transport/host/port/path/log_level
    """
    tool = lab_settings.mcp.servers.tool

    mcp.run(
        transport=tool.transport,
        host=tool.host,
        port=tool.port,
        path=tool.path,
        log_level=tool.log_level,
    )


if __name__ == "__main__":
    run_mcp()
