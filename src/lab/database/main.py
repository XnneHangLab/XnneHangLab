from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from lab.database.routes.product_review import router
from lab.database.setup import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)


app.include_router(router, tags=["Product Reviews"], prefix="/reviews")


@app.get("/", tags=["Root"])
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to your beanie powered app!"}
