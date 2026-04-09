import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import math
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_current_user, get_db, require_role
from models.audit_log import AuditLog
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
from jinja2 import Environment, FileSystemLoader

from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory=templates_dir)

ENTITY_TYPES = [
    "user",
    "project",
    "sprint",
    "ticket",
    "comment",
    "label",
    "time_entry",
    "department",
    "project_member",
]

ACTIONS = [
    "create",
    "update",
    "delete",
]

PER_PAGE = 25


@router.get("/audit")
async def list_audit_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
) -> Response:
    stmt = select(AuditLog).options(selectinload(AuditLog.user))

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            stmt = stmt.where(AuditLog.timestamp >= dt_from)
        except ValueError:
            logger.warning("Invalid date_from format: %s", date_from)
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            stmt = stmt.where(AuditLog.timestamp <= dt_to)
        except ValueError:
            logger.warning("Invalid date_to format: %s", date_to)

    count_stmt = select(func.count()).select_from(AuditLog)
    if entity_type:
        count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)
    if action:
        count_stmt = count_stmt.where(AuditLog.action == action)
    if user_id:
        count_stmt = count_stmt.where(AuditLog.user_id == user_id)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            count_stmt = count_stmt.where(AuditLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            count_stmt = count_stmt.where(AuditLog.timestamp <= dt_to)
        except ValueError:
            pass

    count_result = await db.execute(count_stmt)
    total_entries = count_result.scalar() or 0
    total_pages = max(1, math.ceil(total_entries / PER_PAGE))

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * PER_PAGE
    stmt = stmt.order_by(AuditLog.timestamp.desc()).offset(offset).limit(PER_PAGE)

    result = await db.execute(stmt)
    audit_logs = result.scalars().all()

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = users_result.scalars().all()

    filters = {
        "entity_type": entity_type or "",
        "action": action or "",
        "user_id": user_id or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
    }

    return templates.TemplateResponse(
        request,
        "audit/list.html",
        context={
            "current_user": current_user,
            "audit_logs": audit_logs,
            "entity_types": ENTITY_TYPES,
            "actions": ACTIONS,
            "users": users,
            "filters": filters,
            "total_entries": total_entries,
            "total_pages": total_pages,
            "current_page": page,
            "per_page": PER_PAGE,
        },
    )