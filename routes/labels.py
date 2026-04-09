import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_current_user, get_db, add_flash_message, get_flash_messages
from models.audit_log import AuditLog
from models.label import Label
from models.project import Project
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

from jinja2 import Environment as Jinja2Environment
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/projects/{project_id}/labels")
async def list_labels(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await db.execute(
        select(Label)
        .where(Label.project_id == project_id)
        .order_by(Label.name)
    )
    labels = result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "labels/list.html",
        context={
            "project": project,
            "labels": labels,
            "current_user": current_user,
            "flash_messages": flash_messages,
        },
    )


@router.post("/projects/{project_id}/labels")
async def create_label(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    name: str = Form(...),
    color: str = Form("#6366f1"),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    name = name.strip()
    if not name:
        add_flash_message(request, "Label name is required.", "error")
        return Response(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/projects/{project_id}/labels"},
        )

    result = await db.execute(
        select(Label).where(
            Label.project_id == project_id,
            Label.name == name,
        )
    )
    existing_label = result.scalars().first()
    if existing_label:
        add_flash_message(request, f"A label named '{name}' already exists in this project.", "error")
        return Response(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/projects/{project_id}/labels"},
        )

    color = color.strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        color = "#6366f1"

    label_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    label = Label(
        id=label_id,
        project_id=project_id,
        name=name,
        color=color,
        created_at=now,
    )
    db.add(label)
    await db.flush()

    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="label",
        entity_id=label_id,
        action="create",
        user_id=current_user.id,
        details=f'{{"name": "{name}", "color": "{color}", "project_id": "{project_id}"}}',
        timestamp=now,
    )
    db.add(audit_entry)
    await db.flush()

    logger.info(
        "Label '%s' created in project '%s' by user '%s'.",
        name,
        project_id,
        current_user.username,
    )

    add_flash_message(request, f"Label '{name}' created successfully.", "success")

    return Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": f"/projects/{project_id}/labels"},
    )


@router.post("/projects/{project_id}/labels/{label_id}/delete")
async def delete_label(
    request: Request,
    project_id: str,
    label_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await db.execute(
        select(Label).where(
            Label.id == label_id,
            Label.project_id == project_id,
        )
    )
    label = result.scalars().first()
    if not label:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")

    label_name = label.name
    now = datetime.now(timezone.utc)

    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="label",
        entity_id=label_id,
        action="delete",
        user_id=current_user.id,
        details=f'{{"name": "{label_name}", "project_id": "{project_id}"}}',
        timestamp=now,
    )
    db.add(audit_entry)
    await db.flush()

    await db.delete(label)
    await db.flush()

    logger.info(
        "Label '%s' (id=%s) deleted from project '%s' by user '%s'.",
        label_name,
        label_id,
        project_id,
        current_user.username,
    )

    add_flash_message(request, f"Label '{label_name}' deleted successfully.", "success")

    return Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": f"/projects/{project_id}/labels"},
    )