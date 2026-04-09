import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
from typing import Annotated, AsyncGenerator, Callable, Optional

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database import async_session_factory
from models.project_member import ProjectMember
from models.user import User

logger = logging.getLogger(__name__)

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

SESSION_COOKIE_NAME = "session"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def create_session(response: Response, user_id: str) -> None:
    token = serializer.dumps(user_id, salt="user-session")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.TOKEN_EXPIRY_SECONDS,
        path="/",
    )


def decode_session(token: str) -> Optional[str]:
    try:
        user_id: str = serializer.loads(
            token,
            salt="user-session",
            max_age=settings.TOKEN_EXPIRY_SECONDS,
        )
        return user_id
    except SignatureExpired:
        logger.warning("Session token expired.")
        return None
    except BadSignature:
        logger.warning("Invalid session token signature.")
        return None
    except Exception:
        logger.exception("Unexpected error decoding session token.")
        return None


async def get_current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    user_id = decode_session(token)
    if not user_id:
        return None

    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.is_active == True)
        .options(
            selectinload(User.department),
            selectinload(User.project_memberships),
        )
    )
    user = result.scalars().first()
    return user


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def require_role(allowed_roles: list[str]) -> Callable:
    async def role_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not authorized. Required: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_dependency


def require_project_role(allowed_project_roles: list[str]) -> Callable:
    async def project_role_dependency(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if current_user.role == "super_admin":
            return current_user

        project_id = request.path_params.get("project_id")
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project ID is required in the URL path.",
            )

        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
        membership = result.scalars().first()

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project.",
            )

        if membership.role not in allowed_project_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Project role '{membership.role}' is not authorized. Required: {', '.join(allowed_project_roles)}",
            )

        return current_user

    return project_role_dependency


def add_flash_message(request: Request, message: str, category: str = "info") -> None:
    if not hasattr(request.state, "flash_messages"):
        request.state.flash_messages = []
    request.state.flash_messages.append({"text": message, "category": category})


def get_flash_messages(request: Request) -> list[dict]:
    if hasattr(request.state, "flash_messages"):
        messages = request.state.flash_messages
        request.state.flash_messages = []
        return messages
    return []