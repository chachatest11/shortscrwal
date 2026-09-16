"""ChannelBoard FastAPI 앱"""
import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .routers import ALL_ROUTERS
from .services.legacy_import import maybe_import_on_startup
from .services.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        maybe_import_on_startup(config.LEGACY_DB_PATH)
    except Exception as exc:  # 가져오기 실패가 서버 기동을 막지 않도록
        print(f"[ChannelBoard] 이전 버전 데이터 가져오기 실패: {exc}")

    stop_event = asyncio.Event()
    task = None
    if config.SCHEDULER_ENABLED:
        task = asyncio.create_task(scheduler_loop(stop_event))
    print(f"[ChannelBoard] v{config.VERSION} 시작 · DB: {config.DB_PATH}")
    try:
        yield
    finally:
        stop_event.set()
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title=config.APP_NAME, version=config.VERSION, lifespan=lifespan)

for router in ALL_ROUTERS:
    app.include_router(router)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(config.STATIC_DIR / "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"status": "ok", "app": config.APP_NAME, "version": config.VERSION}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"서버 오류: {exc.__class__.__name__}: {exc}"})


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
