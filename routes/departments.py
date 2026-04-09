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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_current_user, get_db, require_role, add_flash_message, get_flash_messages
from models.audit_log import AuditLog
from models.department import Department
from models.project import Project
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/departments")
async def list_departments(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead", "developer", "qa_tester", "viewer"]))],
):
    result = await db.execute(
        select(Department)
        .options(
            selectinload(Department.head),
            selectinload(Department.members),
            selectinload(Department.projects),
        )
        .order_by(Department.name)
    )
    departments = result.scalars().all()

    departments_with_counts = []
    for dept in departments:
        dept.member_count = len(dept.members) if dept.members else 0
        dept.project_count = len(dept.projects) if dept.projects else 0
        departments_with_counts.append(dept)

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = users_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "departments/list.html",
        context={
            "departments": departments_with_counts,
            "users": users,
            "current_user": current_user,
            "flash_messages": flash_messages,
        },
    )


@router.post("/departments")
async def create_department(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    name: str = Form(...),
    code: str = Form(...),
    description: str = Form(""),
    head_id: str = Form(""),
):
    name = name.strip()
    code = code.strip().upper()

    if not name:
        add_flash_message(request, "Department name is required.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    if not code:
        add_flash_message(request, "Department code is required.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    existing_name = await db.execute(
        select(Department).where(func.lower(Department.name) == name.lower())
    )
    if existing_name.scalars().first() is not None:
        add_flash_message(request, f"A department with the name '{name}' already exists.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    existing_code = await db.execute(
        select(Department).where(func.lower(Department.code) == code.lower())
    )
    if existing_code.scalars().first() is not None:
        add_flash_message(request, f"A department with the code '{code}' already exists.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    now = datetime.now(timezone.utc)
    department_id = str(uuid.uuid4())

    resolved_head_id: Optional[str] = None
    if head_id and head_id.strip():
        head_result = await db.execute(
            select(User).where(User.id == head_id.strip(), User.is_active == True)
        )
        head_user = head_result.scalars().first()
        if head_user:
            resolved_head_id = head_user.id

    department = Department(
        id=department_id,
        name=name,
        code=code,
        description=description if description.strip() else None,
        head_id=resolved_head_id,
        created_at=now,
        updated_at=now,
    )
    db.add(department)
    await db.flush()

    audit_log = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="department",
        entity_id=department_id,
        action="create",
        user_id=current_user.id,
        details=f"Created department '{name}' with code '{code}'",
        timestamp=now,
    )
    db.add(audit_log)

    logger.info("Department '%s' (code=%s) created by user '%s'.", name, code, current_user.username)
    add_flash_message(request, f"Department '{name}' created successfully.", "success")
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/departments/{department_id}/edit")
async def edit_department_form(
    request: Request,
    department_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(selectinload(Department.head))
    )
    department = result.scalars().first()

    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = users_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "departments/list.html",
        context={
            "departments": [],
            "users": users,
            "current_user": current_user,
            "edit_department": department,
            "flash_messages": flash_messages,
        },
    )


@router.post("/departments/{department_id}/edit")
async def update_department(
    request: Request,
    department_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
    name: str = Form(...),
    code: str = Form(...),
    description: str = Form(""),
    head_id: str = Form(""),
):
    result = await db.execute(
        select(Department).where(Department.id == department_id)
    )
    department = result.scalars().first()

    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    name = name.strip()
    code = code.strip().upper()

    if not name:
        add_flash_message(request, "Department name is required.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    if not code:
        add_flash_message(request, "Department code is required.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    existing_name = await db.execute(
        select(Department).where(
            func.lower(Department.name) == name.lower(),
            Department.id != department_id,
        )
    )
    if existing_name.scalars().first() is not None:
        add_flash_message(request, f"A department with the name '{name}' already exists.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    existing_code = await db.execute(
        select(Department).where(
            func.lower(Department.code) == code.lower(),
            Department.id != department_id,
        )
    )
    if existing_code.scalars().first() is not None:
        add_flash_message(request, f"A department with the code '{code}' already exists.", "error")
        return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

    now = datetime.now(timezone.utc)
    changes = []

    if department.name != name:
        changes.append(f"name: '{department.name}' -> '{name}'")
        department.name = name

    if department.code != code:
        changes.append(f"code: '{department.code}' -> '{code}'")
        department.code = code

    new_description = description.strip() if description.strip() else None
    if department.description != new_description:
        changes.append("description updated")
        department.description = new_description

    resolved_head_id: Optional[str] = None
    if head_id and head_id.strip():
        head_result = await db.execute(
            select(User).where(User.id == head_id.strip(), User.is_active == True)
        )
        head_user = head_result.scalars().first()
        if head_user:
            resolved_head_id = head_user.id

    if department.head_id != resolved_head_id:
        changes.append(f"head_id: '{department.head_id}' -> '{resolved_head_id}'")
        department.head_id = resolved_head_id

    department.updated_at = now

    if changes:
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            entity_type="department",
            entity_id=department_id,
            action="update",
            user_id=current_user.id,
            details=f"Updated department '{name}': {'; '.join(changes)}",
            timestamp=now,
        )
        db.add(audit_log)

    logger.info("Department '%s' updated by user '%s'.", name, current_user.username)
    add_flash_message(request, f"Department '{name}' updated successfully.", "success")
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/departments/{department_id}/delete")
async def delete_department(
    request: Request,
    department_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.members),
            selectinload(Department.projects),
        )
    )
    department = result.scalars().first()

    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    department_name = department.name
    now = datetime.now(timezone.utc)

    if department.members:
        for member in department.members:
            member.department_id = None

    if department.projects:
        for project in department.projects:
            project.department_id = None

    await db.flush()

    audit_log = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="department",
        entity_id=department_id,
        action="delete",
        user_id=current_user.id,
        details=f"Deleted department '{department_name}' (code: {department.code})",
        timestamp=now,
    )
    db.add(audit_log)

    await db.delete(department)

    logger.info("Department '%s' deleted by user '%s'.", department_name, current_user.username)
    add_flash_message(request, f"Department '{department_name}' deleted successfully.", "success")
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)