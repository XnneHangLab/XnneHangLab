#!/usr/bin/env python3
"""Chat CLI — interactive terminal client for the Memory Chat Server.

A lightweight REPL that sends messages to a running Chat Server via HTTP,
making it easy to test memory augmentation without curl or a full frontend.

Usage::

    # Start the server first:
    just memory-chat-server

    # Then in another terminal:
    uv run memory_bench/server/chat_cli.py

    # Or with options:
    uv run memory_bench/server/chat_cli.py --base-url http://localhost:9090 --no-persona
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx  # type: ignore[reportUnknownVariableType]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DOTENV_BENCHMARK_PATH = _REPO_ROOT / "memory_bench" / ".env.benchmark"
_PERSONA_PATH = _REPO_ROOT / "memory_bench" / "docs" / "22_PERSONA_CANON.md"

_DEFAULT_BASE_URL = "http://localhost:8080"
_DEFAULT_ENDPOINT = "openai"  # Choices: "openai" or "memory"
_USER_PROMPT = "xnne"
_ASSISTANT_PROMPT = "congyin"

# Endpoint mapping
_ENDPOINT_MAP = {
    "openai": "/v1/chat/completions",
    "memory": "/memory/chat",
}


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load memory_bench/.env.benchmark if present."""
    try:
        from dotenv import load_dotenv  # type: ignore[reportMissingImports,reportUnknownVariableType]
    except ImportError:
        return
    if _DOTENV_BENCHMARK_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_BENCHMARK_PATH, override=True)  # type: ignore[reportUnknownArgumentType]


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "")
    return value if value.strip() else default


# ---------------------------------------------------------------------------
# Persona loader
# ---------------------------------------------------------------------------


def _load_persona() -> str:
    """Read 22_PERSONA_CANON.md and return its content as a system prompt."""
    if not _PERSONA_PATH.exists():
        print(f"\u26a0\ufe0f Persona file not found: {_PERSONA_PATH}")
        return ""
    return _PERSONA_PATH.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


def _send_chat(
    base_url: str,
    endpoint: str,
    messages: list[dict[str, str]],
    api_key: str | None,
) -> str:
    """POST to chat endpoint and return assistant content.

    Supports two endpoints:
    - /v1/chat/completions: OpenAI-compatible standard endpoint
    - /memory/chat: Memory Chat Server endpoint (with session management)

    Creates a new client for each request to avoid keep-alive issues on Windows.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Build payload based on endpoint
    if endpoint == "/memory/chat":
        # Memory Chat Server expects: {"message": "...", "session_id": "...", "model": "..."}
        # Extract the last user message
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break
        
        payload = {
            "message": last_user_message,
            "stream": False,
        }
    else:  # /v1/chat/completions
        # OpenAI-compatible format
        payload = {
            "messages": messages,
            "stream": False,
        }

    # Create new client per request to avoid keep-alive issues.
    # Use trust_env=False to completely ignore HTTP_PROXY/HTTPS_PROXY
    # environment variables, ensuring localhost traffic bypasses tun/Clash.
    with httpx.Client(http2=False, trust_env=False) as client:  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
        try:
            resp = client.post(  # type: ignore[reportUnknownMemberType]
                f"{base_url.rstrip('/')}{endpoint}",
                json=payload,
                headers=headers,
                timeout=120.0,
            )
        except httpx.ConnectError as exc:  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
            raise httpx.ConnectError(f"Cannot connect to {base_url}: {exc}") from exc  # type: ignore[reportUnknownMemberType]

        resp.raise_for_status()  # type: ignore[reportUnknownMemberType]
        data = resp.json()  # type: ignore[reportUnknownMemberType]

        # Handle different response formats
        if endpoint == "/memory/chat":
            # Memory Chat Server returns: {"session_id": "...", "content": "...", "model": "...", "created": ...}
            return data.get("content", "(no content)")
        else:
            # OpenAI-compatible returns: {"choices": [{"message": {"content": "..."}}]}
            choices = data.get("choices", [])
            if not choices:
                return "(empty response)"
            return choices[0].get("message", {}).get("content", "(no content)")


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def _run_repl(
    base_url: str,
    endpoint: str,
    system_prompt: str,
    api_key: str | None,
) -> None:
    """Interactive read-eval-print loop."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    print(f"\n\u2728 Chat CLI — connected to {base_url}{endpoint}")
    print("   Type 'quit' or 'exit' to leave, Ctrl+C / Ctrl+D also works.\n")

    while True:
        try:
            user_input = input(f"{_USER_PROMPT}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\U0001f44b Bye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("\U0001f44b Bye!")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            reply = _send_chat(base_url, endpoint, messages, api_key)
        except httpx.HTTPStatusError as exc:  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
            print(f"\u274c HTTP {exc.response.status_code}: {exc.response.text}")  # type: ignore[reportUnknownMemberType]
            messages.pop()  # remove failed user message
            continue
        except httpx.ConnectError:  # type: ignore[reportUnknownMemberType]
            print(
                f"\u274c Cannot connect to {base_url} — is the server running?"
                "\n   Start it with: just memory-chat-server"
            )
            messages.pop()
            continue
        except Exception as exc:
            print(f"\u274c Error: {exc}")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})
        print(f"{_ASSISTANT_PROMPT}> {reply}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chat CLI — interactive terminal client for the Memory Chat Server",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help=f"Server base URL (default: {_DEFAULT_BASE_URL})",
    )
    p.add_argument(
        "--endpoint",
        choices=["openai", "memory"],
        default=None,
        help=f"Chat endpoint: 'openai' for /v1/chat/completions, 'memory' for /memory/chat (default: {_DEFAULT_ENDPOINT})",
    )
    p.add_argument(
        "--system",
        default=None,
        help="Extra system prompt (appended after persona)",
    )
    p.add_argument(
        "--no-persona",
        action="store_true",
        help="Skip loading 22_PERSONA_CANON.md as system prompt",
    )
    p.add_argument(
        "--api-key",
        default=None,
        help="Server API key (env: CHAT_SERVER_API_KEY)",
    )
    return p


def main() -> None:
    _load_dotenv()
    args = _build_parser().parse_args()

    base_url = args.base_url or _get_env("CHAT_CLI_BASE_URL", _DEFAULT_BASE_URL) or _DEFAULT_BASE_URL
    endpoint_name = args.endpoint or _get_env("CHAT_CLI_ENDPOINT", _DEFAULT_ENDPOINT) or _DEFAULT_ENDPOINT
    api_key = args.api_key or _get_env("CHAT_SERVER_API_KEY")

    # Map endpoint name to actual path
    endpoint = _ENDPOINT_MAP.get(endpoint_name, endpoint_name)

    # Build system prompt
    parts: list[str] = []
    if not args.no_persona:
        persona = _load_persona()
        if persona:
            parts.append(persona)
            print(f"\u2705 Persona loaded: {_PERSONA_PATH.name}")
    if args.system:
        parts.append(args.system)

    system_prompt = "\n\n".join(parts)

    _run_repl(base_url=base_url, endpoint=endpoint, system_prompt=system_prompt, api_key=api_key)


if __name__ == "__main__":
    main()
