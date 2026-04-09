import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_db, get_current_user, require_role, add_flash_message, get_flash_messages
from models.user import User
from models.department import Department
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
except Exception:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def _create_audit_log(
    db: AsyncSession,
    user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    details: Optional[str] = None,
) -> None:
    audit_log = AuditLog(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        details=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(audit_log)
    await db.flush()


@router.get("/admin/users")
async def list_users(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    search: Optional[str] = None,
):
    query = select(User).options(
        selectinload(User.department),
        selectinload(User.project_memberships),
    ).order_by(User.created_at.desc())

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.where(
            (User.username.ilike(search_term)) | (User.email.ilike(search_term))
        )

    result = await db.execute(query)
    users = result.scalars().all()

    dept_result = await db.execute(
        select(Department).order_by(Department.name)
    )
    departments = dept_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "users/list.html",
        context={
            "current_user": current_user,
            "users": users,
            "departments": departments,
            "search": search or "",
            "flash_messages": flash_messages,
        },
    )


@router.post("/admin/users/create")
async def create_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("developer"),
    department_id: str = Form(""),
):
    valid_roles = ["super_admin", "project_manager", "team_lead", "developer", "qa_tester", "viewer"]
    if role not in valid_roles:
        add_flash_message(request, f"Invalid role: {role}", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    existing_result = await db.execute(
        select(User).where((User.username == username) | (User.email == email))
    )
    existing_user = existing_result.scalars().first()
    if existing_user:
        if existing_user.username == username:
            add_flash_message(request, f"Username '{username}' already exists.", "error")
        else:
            add_flash_message(request, f"Email '{email}' already exists.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    if len(password) < 6:
        add_flash_message(request, "Password must be at least 6 characters.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    now = datetime.now(timezone.utc)
    hashed = hash_password(password)

    new_user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        hashed_password=hashed,
        role=role,
        department_id=department_id if department_id else None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(new_user)
    await db.flush()

    await _create_audit_log(
        db=db,
        user_id=current_user.id,
        entity_type="user",
        entity_id=new_user.id,
        action="create",
        details=f"Created user '{username}' with role '{role}'",
    )

    logger.info("User '%s' created by '%s'.", username, current_user.username)
    add_flash_message(request, f"User '{username}' created successfully.", "success")
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/toggle-active")
async def toggle_user_active(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        add_flash_message(request, "User not found.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    if user.id == current_user.id:
        add_flash_message(request, "You cannot deactivate your own account.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    previous_status = user.is_active
    user.is_active = not user.is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    new_status = "active" if user.is_active else "inactive"
    old_status = "active" if previous_status else "inactive"

    await _create_audit_log(
        db=db,
        user_id=current_user.id,
        entity_type="user",
        entity_id=user.id,
        action="update",
        details=f"Toggled user '{user.username}' status from '{old_status}' to '{new_status}'",
    )

    logger.info(
        "User '%s' status changed to '%s' by '%s'.",
        user.username, new_status, current_user.username,
    )
    add_flash_message(
        request,
        f"User '{user.username}' is now {new_status}.",
        "success",
    )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/role")
async def update_user_role(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    role: str = Form(...),
):
    valid_roles = ["super_admin", "project_manager", "team_lead", "developer", "qa_tester", "viewer"]
    if role not in valid_roles:
        add_flash_message(request, f"Invalid role: {role}", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        add_flash_message(request, "User not found.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    old_role = user.role
    if old_role == role:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    user.role = role
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _create_audit_log(
        db=db,
        user_id=current_user.id,
        entity_type="user",
        entity_id=user.id,
        action="update",
        details=f"Changed role of user '{user.username}' from '{old_role}' to '{role}'",
    )

    logger.info(
        "User '%s' role changed from '%s' to '%s' by '%s'.",
        user.username, old_role, role, current_user.username,
    )
    add_flash_message(
        request,
        f"Role for '{user.username}' updated to '{role.replace('_', ' ').title()}'.",
        "success",
    )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/department")
async def update_user_department(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    department_id: str = Form(""),
):
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.department))
    )
    user = result.scalars().first()

    if not user:
        add_flash_message(request, "User not found.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    new_department_id = department_id if department_id else None

    if new_department_id:
        dept_result = await db.execute(
            select(Department).where(Department.id == new_department_id)
        )
        department = dept_result.scalars().first()
        if not department:
            add_flash_message(request, "Department not found.", "error")
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    old_department_id = user.department_id
    old_department_name = user.department.name if user.department else "None"

    if old_department_id == new_department_id:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    user.department_id = new_department_id
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    if new_department_id:
        dept_result = await db.execute(
            select(Department).where(Department.id == new_department_id)
        )
        new_dept = dept_result.scalars().first()
        new_department_name = new_dept.name if new_dept else "None"
    else:
        new_department_name = "None"

    await _create_audit_log(
        db=db,
        user_id=current_user.id,
        entity_type="user",
        entity_id=user.id,
        action="update",
        details=f"Changed department of user '{user.username}' from '{old_department_name}' to '{new_department_name}'",
    )

    logger.info(
        "User '%s' department changed from '%s' to '%s' by '%s'.",
        user.username, old_department_name, new_department_name, current_user.username,
    )
    add_flash_message(
        request,
        f"Department for '{user.username}' updated to '{new_department_name}'.",
        "success",
    )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/users/{user_id}")
async def view_user(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.department),
            selectinload(User.project_memberships),
            selectinload(User.assigned_tickets),
            selectinload(User.time_entries),
        )
    )
    user = result.scalars().first()

    if not user:
        add_flash_message(request, "User not found.", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    dept_result = await db.execute(
        select(Department).order_by(Department.name)
    )
    departments = dept_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "users/list.html",
        context={
            "current_user": current_user,
            "users": [user],
            "departments": departments,
            "search": "",
            "flash_messages": flash_messages,
        },
    )