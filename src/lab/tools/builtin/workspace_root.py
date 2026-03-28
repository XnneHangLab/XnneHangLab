from __future__ import annotations

import os
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

    # On Windows, treat "/foo" and "\foo" as workspace-root-relative paths instead of
    # drive-rooted paths so prompt-authored paths like "/data/agent/diary" stay inside
    # the project. On POSIX, "/foo" must remain an absolute filesystem path.
    is_root_anchored_without_drive = (
        os.name == "nt"
        and
        bool(raw)
        and raw[0] in {"/", "\\"}
        and path.drive == ""
        and not raw.startswith(("\\\\", "//"))
    )
    if is_root_anchored_without_drive:
        path = Path(raw.lstrip("/\\"))

    return (root / path).resolve() if not path.is_absolute() else path.resolve()
