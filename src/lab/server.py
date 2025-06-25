from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from lab._dataclass import RootAbsDir
from lab.utils.config import load_settings_file

from .config_manager.utils import Config
from .routes import init_client_ws_route, init_webtool_routes
from .service_context import ServiceContext

RootSettings: RootAbsDir = load_settings_file("root.toml", RootAbsDir)
ROOT_DIR = Path(RootSettings.root_dir) / "static"


class CustomStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript"
        return response


class AvatarStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        allowed_extensions = (".jpg", ".jpeg", ".png", ".gif", ".svg")
        if not any(path.lower().endswith(ext) for ext in allowed_extensions):
            return Response("Forbidden file type", status_code=403)
        return await super().get_response(path, scope)


class WebSocketServer:
    def __init__(self, config: Config):
        # def __init__(self):
        self.app = FastAPI()

        # Add CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Load configurations and initialize the default context cache
        default_context_cache = ServiceContext()
        default_context_cache.load_from_config(config)

        # Include routes
        self.app.include_router(
            init_client_ws_route(default_context_cache=default_context_cache),
        )
        self.app.include_router(
            init_webtool_routes(default_context_cache=default_context_cache),
        )

        # Mount cache directory first (to ensure audio file access)
        # if not os.path.exists("cache"):
        # os.makedirs("cache")
        # self.app.mount(
        #     "/cache",
        #     StaticFiles(directory="cache"),
        #     name="cache",
        # )

        # Mount static files
        self.app.mount(
            "/live2d-models",
            StaticFiles(directory=(ROOT_DIR / "live2d-models")),
            name="live2d-models",
        )
        self.app.mount(
            "/bg",
            StaticFiles(directory=str(ROOT_DIR / "backgrounds")),
            name="backgrounds",
        )
        self.app.mount(
            "/avatars",
            AvatarStaticFiles(directory=str(ROOT_DIR / "avatars")),
            name="avatars",
        )

        # Mount web tool directory separately from frontend
        self.app.mount(
            "/web-tool",
            CustomStaticFiles(directory=str(ROOT_DIR / "web_tool"), html=True),
            name="web_tool",
        )

        # Mount main frontend last (as catch-all)
        # self.app.mount(
        #     "/",
        #     CustomStaticFiles(directory="frontend", html=True),
        #     name="frontend",
        # )

    def run(self):
        pass

    # @staticmethod
    # def clean_cache():
    #     """Clean the cache directory by removing and recreating it."""
    #     cache_dir = "cache"
    #     if os.path.exists(cache_dir):
    #         shutil.rmtree(cache_dir)
    #         os.makedirs(cache_dir)
