import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from database import create_all_tables
from dependencies import get_current_user_optional, get_db
from routes import all_routers
from seed import seed_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ProjectForge application...")
    await create_all_tables()
    logger.info("Database tables created.")
    try:
        await seed_database()
        logger.info("Database seeding completed.")
    except Exception as e:
        logger.error("Database seeding encountered an error: %s", str(e))
    yield
    logger.info("Shutting down ProjectForge application...")


app = FastAPI(
    title="ProjectForge",
    description="A comprehensive project management platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

for router in all_routers:
    app.include_router(router)


@app.get("/")
async def landing_page(request: Request) -> Response:
    from dependencies import get_current_user_optional, async_session_factory
    from sqlalchemy import select
    from models.user import User
    from sqlalchemy.orm import selectinload

    current_user = None
    token = request.cookies.get("session")
    if token:
        from dependencies import decode_session
        user_id = decode_session(token)
        if user_id:
            async with async_session_factory() as session:
                try:
                    result = await session.execute(
                        select(User)
                        .where(User.id == user_id, User.is_active == True)
                        .options(
                            selectinload(User.department),
                            selectinload(User.project_memberships),
                        )
                    )
                    current_user = result.scalars().first()
                except Exception:
                    logger.exception("Error fetching current user for landing page.")

    return templates.TemplateResponse(
        request,
        "landing.html",
        context={
            "current_user": current_user,
            "flash_messages": [],
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "application": "ProjectForge"}


@app.get("/admin")
async def admin_redirect(request: Request) -> Response:
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/users", status_code=302)


@app.get("/profile")
async def profile_page(request: Request) -> Response:
    from fastapi.responses import RedirectResponse
    from dependencies import decode_session, async_session_factory
    from sqlalchemy import select
    from models.user import User
    from sqlalchemy.orm import selectinload

    current_user = None
    token = request.cookies.get("session")
    if token:
        user_id = decode_session(token)
        if user_id:
            async with async_session_factory() as session:
                try:
                    result = await session.execute(
                        select(User)
                        .where(User.id == user_id, User.is_active == True)
                        .options(
                            selectinload(User.department),
                            selectinload(User.project_memberships),
                        )
                    )
                    current_user = result.scalars().first()
                except Exception:
                    logger.exception("Error fetching current user for profile page.")

    if current_user is None:
        return RedirectResponse(url="/auth/login", status_code=302)

    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/reports")
async def reports_redirect(request: Request) -> Response:
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard", status_code=302)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == 404:
        current_user = None
        token = request.cookies.get("session")
        if token:
            from dependencies import decode_session, async_session_factory
            from sqlalchemy import select
            from models.user import User
            from sqlalchemy.orm import selectinload

            user_id = decode_session(token)
            if user_id:
                try:
                    async with async_session_factory() as session:
                        result = await session.execute(
                            select(User)
                            .where(User.id == user_id, User.is_active == True)
                            .options(
                                selectinload(User.department),
                                selectinload(User.project_memberships),
                            )
                        )
                        current_user = result.scalars().first()
                except Exception:
                    logger.exception("Error fetching user in 404 handler.")

        return templates.TemplateResponse(
            request,
            "errors/404.html",
            context={
                "current_user": current_user,
                "flash_messages": [],
            },
            status_code=404,
        )

    if exc.status_code == 401:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/auth/login", status_code=302)

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )