from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.tools.types import AgentContext


def _load_configured_root() -> Path | None:
    try:
        from lab.config_manager import XnneHangLabSettings, load_settings_file

        settings = load_settings_file("lab.toml", XnneHangLabSettings)
        root_dir = settings.root.root_dir.strip()
        if not root_dir:
            return None
        return Path(root_dir).expanduser().resolve()
    except Exception:
        return None


def resolve_workspace_root(ctx: AgentContext) -> Path:
    raw_ctx_root = str(ctx.workspace_root).strip()
    ctx_root = ctx.workspace_root.expanduser().resolve()

    configured_root = _load_configured_root()
    if configured_root is None:
        return ctx_root

    if raw_ctx_root in {"", ".", "./", ".\\"}:
        return configured_root

    return ctx_root


def resolve_workspace_path(ctx: AgentContext, path_str: str) -> Path:
    root = resolve_workspace_root(ctx)
    raw = (path_str or "").strip()
    path = Path(raw).expanduser()

    # Treat the prompt-facing logical workspace prefix "/data" as project-root-relative
    # on every platform. Real absolute paths like "/tmp/..." or "D:\\..." keep their
    # filesystem meaning and will still be checked against the workspace boundary.
    normalized_raw = raw.replace("\\", "/")
    if normalized_raw == "/data" or normalized_raw.startswith("/data/"):
        path = Path(raw.lstrip("/\\"))

    return (root / path).resolve() if not path.is_absolute() else path.resolve()
