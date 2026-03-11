from __future__ import annotations

from .screen_shot import ScreenShotPlugin
from .web_fetch import WebFetchPlugin
from .web_search_duckduckgo import WebSearchDuckDuckGoPlugin
from .web_search_searxng import WebSearchSearxngPlugin

__all__ = [
    "ScreenShotPlugin",
    "WebFetchPlugin",
    "WebSearchDuckDuckGoPlugin",
    "WebSearchSearxngPlugin",
]
