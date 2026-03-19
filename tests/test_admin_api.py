from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lab.api.routes.admin import router

if TYPE_CHECKING:
    import pytest


def _make_app(tmp_path: Path, *, enable_tool: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/admin")
    app.state.default_context_cache = SimpleNamespace(
        lab_setting=SimpleNamespace(
            root=SimpleNamespace(root_dir=str(tmp_path)),
            agent=SimpleNamespace(enable_tool=enable_tool),
        ),
        character_config=SimpleNamespace(tts_preprocessor_config="tts-config"),
        live2d_model="live2d-model",
        agent_engine=None,
        _mcp_connected=False,
    )
    return app


def test_list_plugins_returns_stable_plugin_structure(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "src" / "lab" / "plugins"
    (plugins_dir / "z_plugin").mkdir(parents=True)
    (plugins_dir / "a_plugin").mkdir(parents=True)
    (plugins_dir / "skip_me").mkdir(parents=True)

    (plugins_dir / "a_plugin" / "plugin.toml").write_text(
        """
[plugin]
id = "plugin-a"
name = "Plugin A"

[config]
enabled = true

[config_schema.enabled]
type = "bool"
""".strip(),
        encoding="utf-8",
    )
    (plugins_dir / "z_plugin" / "plugin.toml").write_text(
        """
[plugin]
name = "Plugin Z"
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(_make_app(tmp_path))
    response = client.get("/admin/api/plugins")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "plugin-a",
            "path": "src/lab/plugins/a_plugin",
            "plugin": {"id": "plugin-a", "name": "Plugin A"},
            "config": {"enabled": True},
            "config_schema": {"enabled": {"type": "bool"}},
        },
        {
            "id": "z_plugin",
            "path": "src/lab/plugins/z_plugin",
            "plugin": {"name": "Plugin Z"},
            "config": {},
            "config_schema": {},
        },
    ]


def test_profiles_list_get_and_put(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "b.toml").write_text('[profile]\nname = "b"\n', encoding="utf-8")
    (profiles_dir / "a.toml").write_text('[profile]\nname = "a"\n', encoding="utf-8")
    (profiles_dir / "ignore.txt").write_text("x", encoding="utf-8")

    client = TestClient(_make_app(tmp_path))

    list_response = client.get("/admin/api/profiles")
    assert list_response.status_code == 200
    assert list_response.json() == ["a.toml", "b.toml"]

    get_response = client.get("/admin/api/profiles/a.toml")
    assert get_response.status_code == 200
    assert get_response.json() == {"profile": {"name": "a"}}

    put_response = client.put(
        "/admin/api/profiles/a.toml",
        json={
            "profile": {"name": "updated", "agent_name": "updated"},
            "plugins": {"enabled": ["memory"], "memory": {"search_limit": 3}},
        },
    )
    assert put_response.status_code == 200
    assert put_response.json() == {"status": "ok", "name": "a.toml"}

    with (profiles_dir / "a.toml").open("rb") as file:
        assert tomllib.load(file) == {
            "profile": {"name": "updated", "agent_name": "updated"},
            "plugins": {"enabled": ["memory"], "memory": {"search_limit": 3}},
        }


def test_profile_endpoints_reject_invalid_profile_names(tmp_path: Path) -> None:
    client = TestClient(_make_app(tmp_path))

    response = client.get("/admin/api/profiles/not-toml.txt")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid profile name"


def test_reload_default_agent_rebuilds_shared_context_in_place(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _make_app(tmp_path, enable_tool=True)
    shared_ctx = app.state.default_context_cache
    reload_calls: list[Any] = []

    async def fake_reload() -> None:
        reload_calls.append(shared_ctx)
        shared_ctx.agent_engine = "reloaded-agent"
        shared_ctx.character_config = SimpleNamespace(tts_preprocessor_config="reloaded-tts")

    monkeypatch.setattr(shared_ctx, "reload_runtime_from_current_settings", fake_reload, raising=False)

    client = TestClient(app)
    response = client.post("/admin/api/agent/reload")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert app.state.default_context_cache is shared_ctx
    assert app.state.default_context_cache.agent_engine == "reloaded-agent"
    assert reload_calls == [shared_ctx]


def test_service_context_reload_runtime_refreshes_template_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from lab.service_context import ServiceContext

    close_calls: list[str] = []

    class OldAgent:
        async def close(self) -> None:
            close_calls.append("old")

    class NewAgent:
        async def close(self) -> None:
            close_calls.append("new")

    ctx: Any = object.__new__(ServiceContext)
    ctx.lab_setting = SimpleNamespace(model_copy=lambda deep=True: "settings-copy")
    ctx.server_config = SimpleNamespace(model_copy=lambda deep=True: "server-copy")
    ctx.character_config = SimpleNamespace(model_copy=lambda deep=True: "character-copy")
    ctx.live2d_model = "old-live2d"
    ctx.agent_engine = OldAgent()
    ctx.translate_engine = None
    ctx.history_uid = "history-1"
    ctx.chat_system_prompt = "old-chat"
    ctx.vision_system_prompt = "old-vision"
    ctx.live2d_startup_expression_applied = True
    ctx._mcp_connected = False

    reloaded = SimpleNamespace(
        lab_setting="new-settings",
        server_config="new-server",
        character_config="new-character",
        live2d_model="new-live2d",
        agent_engine=NewAgent(),
        _mcp_connected=True,
        chat_system_prompt="new-chat",
        vision_system_prompt="new-vision",
        live2d_startup_expression_applied=False,
    )
    load_calls: list[Any] = []
    ensure_calls: list[Any] = []
    cache_calls: list[dict[str, Any]] = []

    async def fake_load_from_config(config: Any) -> None:
        load_calls.append(config)

    async def fake_ensure_mcp_connected() -> None:
        ensure_calls.append(reloaded.agent_engine)

    def fake_load_cache(*, lab_setting: Any, server_config: Any, character_config: Any, live2d_model: Any, agent_engine: Any) -> None:
        cache_calls.append(
            {
                "lab_setting": lab_setting,
                "server_config": server_config,
                "character_config": character_config,
                "live2d_model": live2d_model,
                "agent_engine": agent_engine,
            }
        )
        ctx.lab_setting = lab_setting
        ctx.server_config = server_config
        ctx.character_config = character_config
        ctx.live2d_model = live2d_model
        ctx.agent_engine = agent_engine

    monkeypatch.setattr("lab.service_context.ServiceContext", lambda: reloaded)
    monkeypatch.setattr(reloaded, "load_from_config", fake_load_from_config, raising=False)
    monkeypatch.setattr(reloaded, "ensure_mcp_connected", fake_ensure_mcp_connected, raising=False)
    monkeypatch.setattr(ctx, "load_cache", fake_load_cache)

    asyncio.run(ServiceContext.reload_runtime_from_current_settings(ctx))

    assert load_calls == ["settings-copy"]
    assert ensure_calls == [reloaded.agent_engine]
    assert cache_calls == [
        {
            "lab_setting": "settings-copy",
            "server_config": "new-server",
            "character_config": "new-character",
            "live2d_model": "new-live2d",
            "agent_engine": reloaded.agent_engine,
        }
    ]
    assert ctx._mcp_connected is True
    assert ctx.chat_system_prompt == "new-chat"
    assert ctx.vision_system_prompt == "new-vision"
    assert ctx.history_uid == ""
    assert ctx.live2d_startup_expression_applied is False
    assert close_calls == ["old"]


def test_server_registers_admin_router() -> None:
    server_source = Path("src/lab/server.py").read_text(encoding="utf-8")

    assert 'import_module("lab.api.routes.admin").router' in server_source
    assert 'prefix="/admin"' in server_source
