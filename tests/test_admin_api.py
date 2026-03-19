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


def test_profile_endpoints_block_path_traversal(tmp_path: Path) -> None:
    client = TestClient(_make_app(tmp_path))

    response = client.get("/admin/api/profiles/..%5Csecret.toml")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid profile name"


def test_reload_default_agent_replaces_cached_agent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _make_app(tmp_path, enable_tool=True)
    close_calls: list[str] = []
    create_calls: list[dict[str, object]] = []

    class OldAgent:
        async def close(self) -> None:
            close_calls.append("old")

    class NewAgent:
        def __init__(self) -> None:
            self.connected = False

        async def connect_mcp_servers(self) -> None:
            self.connected = True

        async def close(self) -> None:
            close_calls.append("new")

    async def fake_create_agent(
        *,
        lab_setting: Any,
        live2d_model: Any,
        tts_preprocessor_config: Any,
        workspace_root: Any,
    ) -> NewAgent:
        create_calls.append(
            {
                "lab_setting": lab_setting,
                "live2d_model": live2d_model,
                "tts_preprocessor_config": tts_preprocessor_config,
                "workspace_root": workspace_root,
            }
        )
        return NewAgent()

    app.state.default_context_cache.agent_engine = OldAgent()
    monkeypatch.setattr("lab.api.routes.admin.AgentFactory.create_agent", fake_create_agent)

    client = TestClient(app)
    response = client.post("/admin/api/agent/reload")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert isinstance(app.state.default_context_cache.agent_engine, NewAgent)
    assert app.state.default_context_cache.agent_engine.connected is True
    assert app.state.default_context_cache._mcp_connected is True
    assert close_calls == ["old"]
    assert create_calls == [
        {
            "lab_setting": app.state.default_context_cache.lab_setting,
            "live2d_model": "live2d-model",
            "tts_preprocessor_config": "tts-config",
            "workspace_root": tmp_path.resolve(),
        }
    ]


def test_server_registers_admin_router() -> None:
    server_source = Path("src/lab/server.py").read_text(encoding="utf-8")

    assert 'import_module("lab.api.routes.admin").router' in server_source
    assert 'prefix="/admin"' in server_source
