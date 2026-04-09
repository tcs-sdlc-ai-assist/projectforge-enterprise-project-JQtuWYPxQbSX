import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import (
    SESSION_COOKIE_NAME,
    create_session,
    get_current_user_optional,
    get_db,
)
from models.user import User

logger = logging.getLogger(__name__)

try:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

except Exception:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


from jinja2 import Environment, FileSystemLoader

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login_page(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)],
):
    if current_user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request,
        "auth/login.html",
        context={
            "current_user": None,
            "error": None,
            "username": "",
            "flash_messages": [],
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    username: str = Form(...),
    password: str = Form(...),
):
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalars().first()

    if user is None or not verify_password(password, user.hashed_password):
        logger.warning("Failed login attempt for username: %s", username)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            context={
                "current_user": None,
                "error": "Invalid username or password.",
                "username": username,
                "flash_messages": [],
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        logger.warning("Login attempt for deactivated user: %s", username)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            context={
                "current_user": None,
                "error": "Your account has been deactivated. Please contact an administrator.",
                "username": username,
                "flash_messages": [],
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    create_session(response, user.id)
    logger.info("User '%s' logged in successfully.", username)
    return response


@router.get("/register")
async def register_page(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)],
):
    if current_user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request,
        "auth/register.html",
        context={
            "current_user": None,
            "error": None,
            "form_data": None,
            "flash_messages": [],
        },
    )


@router.post("/register")
async def register_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    full_name: str = Form(""),
):
    form_data = {
        "username": username,
        "email": email,
        "full_name": full_name,
    }

    errors: list[str] = []

    if not username or len(username.strip()) < 3:
        errors.append("Username must be at least 3 characters long.")

    if len(username) > 150:
        errors.append("Username must be at most 150 characters long.")

    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters long.")

    if password != confirm_password:
        errors.append("Passwords do not match.")

    if not email or "@" not in email:
        errors.append("A valid email address is required.")

    if errors:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            context={
                "current_user": None,
                "error": " ".join(errors),
                "form_data": form_data,
                "flash_messages": [],
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    result = await db.execute(
        select(User).where(User.username == username.strip())
    )
    existing_user = result.scalars().first()

    if existing_user is not None:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            context={
                "current_user": None,
                "error": "Username already exists. Please choose a different one.",
                "form_data": form_data,
                "flash_messages": [],
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    result = await db.execute(
        select(User).where(User.email == email.strip())
    )
    existing_email = result.scalars().first()

    if existing_email is not None:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            context={
                "current_user": None,
                "error": "An account with this email already exists.",
                "form_data": form_data,
                "flash_messages": [],
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    hashed = hash_password(password)
    now = datetime.now(timezone.utc)

    new_user = User(
        id=str(uuid.uuid4()),
        username=username.strip(),
        hashed_password=hashed,
        email=email.strip(),
        full_name=full_name.strip() if full_name else None,
        role="viewer",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    db.add(new_user)
    await db.flush()

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    create_session(response, new_user.id)
    logger.info("New user '%s' registered successfully.", username)
    return response


@router.post("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    logger.info("User logged out.")
    return response


@router.get("/logout")
async def logout_get(request: Request):
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    logger.info("User logged out via GET.")
    return response