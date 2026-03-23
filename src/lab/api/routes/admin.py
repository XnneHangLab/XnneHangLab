from __future__ import annotations

from fastapi import APIRouter

from lab.api.routes.admin_config import router as config_router
from lab.api.routes.admin_plugins import router as plugins_router
from lab.api.routes.admin_profiles import router as profiles_router
from lab.api.routes.admin_reload import router as reload_router

router = APIRouter(tags=["admin"])
router.include_router(plugins_router)
router.include_router(profiles_router)
router.include_router(config_router)
router.include_router(reload_router)
