import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_db, get_current_user, require_role, add_flash_message, get_flash_messages
from models.audit_log import AuditLog
from models.comment import Comment
from models.label import Label
from models.project import Project
from models.project_member import ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket, ticket_labels
from models.time_entry import TimeEntry
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

TICKET_TYPES = ["feature", "bug", "task", "improvement"]
TICKET_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "closed"]
TICKET_PRIORITIES = ["critical", "high", "medium", "low"]


async def _log_audit(
    db: AsyncSession,
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: Optional[str] = None,
) -> None:
    audit = AuditLog(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        details=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(audit)


# ─── Global ticket list (all tickets across projects) ───────────────────────

@router.get("/tickets")
async def list_all_tickets(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    sprint_id: Optional[str] = None,
    project_id: Optional[str] = None,
    page: int = 1,
):
    per_page = 25
    offset = (page - 1) * per_page

    query = select(Ticket).options(
        selectinload(Ticket.project),
        selectinload(Ticket.sprint),
        selectinload(Ticket.assignee),
        selectinload(Ticket.reporter),
        selectinload(Ticket.labels),
    )

    if project_id:
        query = query.where(Ticket.project_id == project_id)
    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if type_filter:
        query = query.where(Ticket.type == type_filter)
    if priority:
        query = query.where(Ticket.priority == priority)
    if assignee_id:
        query = query.where(Ticket.assignee_id == assignee_id)
    if sprint_id:
        query = query.where(Ticket.sprint_id == sprint_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    tickets = result.scalars().all()

    users_result = await db.execute(select(User).where(User.is_active == True))
    assignees = users_result.scalars().all()

    sprints_result = await db.execute(select(Sprint))
    sprints = sprints_result.scalars().all()

    project = None
    if project_id:
        proj_result = await db.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalars().first()

    filters = {
        "status": status_filter or "",
        "type": type_filter or "",
        "priority": priority or "",
        "assignee_id": assignee_id or "",
        "sprint_id": sprint_id or "",
    }

    total_pages = max(1, (total + per_page - 1) // per_page)

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "offset": offset,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/list.html",
        context={
            "current_user": current_user,
            "tickets": tickets,
            "project": project,
            "filters": filters,
            "assignees": assignees,
            "sprints": sprints,
            "pagination": pagination,
            "flash_messages": flash_messages,
        },
    )


# ─── Project-scoped ticket list ─────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets")
async def list_project_tickets(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    sprint_id: Optional[str] = None,
    page: int = 1,
):
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id).options(selectinload(Project.sprints))
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    per_page = 25
    offset = (page - 1) * per_page

    query = (
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .options(
            selectinload(Ticket.project),
            selectinload(Ticket.sprint),
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
            selectinload(Ticket.labels),
        )
    )

    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if type_filter:
        query = query.where(Ticket.type == type_filter)
    if priority:
        query = query.where(Ticket.priority == priority)
    if assignee_id:
        query = query.where(Ticket.assignee_id == assignee_id)
    if sprint_id:
        query = query.where(Ticket.sprint_id == sprint_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    tickets = result.scalars().all()

    users_result = await db.execute(select(User).where(User.is_active == True))
    assignees = users_result.scalars().all()

    sprints = project.sprints or []

    filters = {
        "status": status_filter or "",
        "type": type_filter or "",
        "priority": priority or "",
        "assignee_id": assignee_id or "",
        "sprint_id": sprint_id or "",
    }

    total_pages = max(1, (total + per_page - 1) // per_page)

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "offset": offset,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/list.html",
        context={
            "current_user": current_user,
            "tickets": tickets,
            "project": project,
            "filters": filters,
            "assignees": assignees,
            "sprints": sprints,
            "pagination": pagination,
            "flash_messages": flash_messages,
        },
    )


# ─── Create ticket form (GET) ───────────────────────────────────────────────

@router.get("/projects/{project_id}/tickets/new")
async def create_ticket_form(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    projects_result = await db.execute(select(Project))
    projects = projects_result.scalars().all()

    users_result = await db.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    sprints_result = await db.execute(
        select(Sprint).where(Sprint.project_id == project_id)
    )
    sprints = sprints_result.scalars().all()

    labels_result = await db.execute(
        select(Label).where(Label.project_id == project_id)
    )
    labels = labels_result.scalars().all()

    parent_tickets_result = await db.execute(
        select(Ticket).where(Ticket.project_id == project_id)
    )
    parent_tickets = parent_tickets_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "current_user": current_user,
            "ticket": None,
            "projects": projects,
            "users": users,
            "sprints": sprints,
            "labels": labels,
            "parent_tickets": parent_tickets,
            "ticket_types": TICKET_TYPES,
            "statuses": TICKET_STATUSES,
            "priorities": TICKET_PRIORITIES,
            "selected_project_id": project_id,
            "ticket_label_ids": [],
            "flash_messages": flash_messages,
        },
    )


# ─── Create ticket form (global GET) ────────────────────────────────────────

@router.get("/tickets/create")
async def create_ticket_form_global(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    project_id: Optional[str] = None,
):
    projects_result = await db.execute(select(Project))
    projects = projects_result.scalars().all()

    users_result = await db.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    sprints_result = await db.execute(select(Sprint))
    sprints = sprints_result.scalars().all()

    labels_result = await db.execute(select(Label))
    labels = labels_result.scalars().all()

    parent_tickets_result = await db.execute(select(Ticket))
    parent_tickets = parent_tickets_result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "current_user": current_user,
            "ticket": None,
            "projects": projects,
            "users": users,
            "sprints": sprints,
            "labels": labels,
            "parent_tickets": parent_tickets,
            "ticket_types": TICKET_TYPES,
            "statuses": TICKET_STATUSES,
            "priorities": TICKET_PRIORITIES,
            "selected_project_id": project_id or "",
            "ticket_label_ids": [],
            "flash_messages": flash_messages,
        },
    )


# ─── Create ticket (POST) ───────────────────────────────────────────────────

@router.post("/tickets/create")
async def create_ticket_post_global(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    title: str = Form(...),
    project_id: str = Form(...),
    type: str = Form(...),
    priority: str = Form(...),
    status_field: str = Form("backlog", alias="status"),
    description: str = Form(""),
    assignee_id: str = Form(""),
    reporter_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    estimated_hours: str = Form(""),
    label_ids: list[str] = Form([]),
):
    ticket_id = str(uuid.uuid4())

    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    key_prefix = project.key or project.name[:3].upper()
    count_result = await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.project_id == project_id)
    )
    ticket_count = (count_result.scalar() or 0) + 1
    ticket_key = f"{key_prefix}-{ticket_count}"

    est_hours = None
    if estimated_hours and estimated_hours.strip():
        try:
            est_hours = float(estimated_hours)
        except ValueError:
            est_hours = None

    now = datetime.now(timezone.utc)

    ticket = Ticket(
        id=ticket_id,
        project_id=project_id,
        sprint_id=sprint_id if sprint_id else None,
        parent_id=parent_id if parent_id else None,
        key=ticket_key,
        title=title,
        description=description if description else None,
        type=type,
        status=status_field,
        priority=priority,
        assignee_id=assignee_id if assignee_id else None,
        reporter_id=reporter_id if reporter_id else current_user.id,
        estimated_hours=est_hours,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    await db.flush()

    if label_ids:
        for lid in label_ids:
            if lid and lid.strip():
                await db.execute(
                    ticket_labels.insert().values(ticket_id=ticket_id, label_id=lid.strip())
                )

    await _log_audit(
        db,
        current_user.id,
        "create",
        "ticket",
        ticket_id,
        json.dumps({"title": title, "project_id": project_id, "type": type, "priority": priority}),
    )

    add_flash_message(request, f"Ticket '{title}' created successfully.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@router.post("/projects/{project_id}/tickets")
async def create_ticket_post_project(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    title: str = Form(...),
    type: str = Form(...),
    priority: str = Form(...),
    status_field: str = Form("backlog", alias="status"),
    description: str = Form(""),
    assignee_id: str = Form(""),
    reporter_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    estimated_hours: str = Form(""),
    label_ids: list[str] = Form([]),
):
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ticket_id = str(uuid.uuid4())

    key_prefix = project.key or project.name[:3].upper()
    count_result = await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.project_id == project_id)
    )
    ticket_count = (count_result.scalar() or 0) + 1
    ticket_key = f"{key_prefix}-{ticket_count}"

    est_hours = None
    if estimated_hours and estimated_hours.strip():
        try:
            est_hours = float(estimated_hours)
        except ValueError:
            est_hours = None

    now = datetime.now(timezone.utc)

    ticket = Ticket(
        id=ticket_id,
        project_id=project_id,
        sprint_id=sprint_id if sprint_id else None,
        parent_id=parent_id if parent_id else None,
        key=ticket_key,
        title=title,
        description=description if description else None,
        type=type,
        status=status_field,
        priority=priority,
        assignee_id=assignee_id if assignee_id else None,
        reporter_id=reporter_id if reporter_id else current_user.id,
        estimated_hours=est_hours,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    await db.flush()

    if label_ids:
        for lid in label_ids:
            if lid and lid.strip():
                await db.execute(
                    ticket_labels.insert().values(ticket_id=ticket_id, label_id=lid.strip())
                )

    await _log_audit(
        db,
        current_user.id,
        "create",
        "ticket",
        ticket_id,
        json.dumps({"title": title, "project_id": project_id, "type": type, "priority": priority}),
    )

    add_flash_message(request, f"Ticket '{title}' created successfully.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── Ticket detail ──────────────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}")
async def ticket_detail(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.project),
            selectinload(Ticket.sprint),
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
            selectinload(Ticket.labels),
            selectinload(Ticket.comments).selectinload(Comment.author),
            selectinload(Ticket.comments).selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Ticket.time_entries).selectinload(TimeEntry.user),
            selectinload(Ticket.subtasks),
        )
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    project = ticket.project

    top_level_comments = [c for c in (ticket.comments or []) if c.parent_id is None]

    time_entries = ticket.time_entries or []
    total_time = sum(e.hours for e in time_entries if e.hours)

    subtasks = ticket.subtasks or []

    labels = ticket.labels or []

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/detail.html",
        context={
            "current_user": current_user,
            "ticket": ticket,
            "project": project,
            "comments": top_level_comments,
            "time_entries": time_entries,
            "total_time": total_time,
            "subtasks": subtasks,
            "labels": labels,
            "flash_messages": flash_messages,
        },
    )


@router.get("/projects/{project_id}/tickets/{ticket_id}")
async def ticket_detail_project(
    request: Request,
    project_id: str,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── Edit ticket form (GET) ─────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/edit")
async def edit_ticket_form(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.project),
            selectinload(Ticket.labels),
            selectinload(Ticket.sprint),
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
        )
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    projects_result = await db.execute(select(Project))
    projects = projects_result.scalars().all()

    users_result = await db.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    sprints_result = await db.execute(
        select(Sprint).where(Sprint.project_id == ticket.project_id)
    )
    sprints = sprints_result.scalars().all()

    labels_result = await db.execute(
        select(Label).where(Label.project_id == ticket.project_id)
    )
    labels = labels_result.scalars().all()

    parent_tickets_result = await db.execute(
        select(Ticket).where(Ticket.project_id == ticket.project_id, Ticket.id != ticket_id)
    )
    parent_tickets = parent_tickets_result.scalars().all()

    ticket_label_ids = [l.id for l in (ticket.labels or [])]

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "tickets/form.html",
        context={
            "current_user": current_user,
            "ticket": ticket,
            "projects": projects,
            "users": users,
            "sprints": sprints,
            "labels": labels,
            "parent_tickets": parent_tickets,
            "ticket_types": TICKET_TYPES,
            "statuses": TICKET_STATUSES,
            "priorities": TICKET_PRIORITIES,
            "selected_project_id": ticket.project_id,
            "ticket_label_ids": ticket_label_ids,
            "flash_messages": flash_messages,
        },
    )


# ─── Edit ticket (POST) ─────────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/edit")
async def edit_ticket_post(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    title: str = Form(...),
    project_id: str = Form(...),
    type: str = Form(...),
    priority: str = Form(...),
    status_field: str = Form("backlog", alias="status"),
    description: str = Form(""),
    assignee_id: str = Form(""),
    reporter_id: str = Form(""),
    sprint_id: str = Form(""),
    parent_id: str = Form(""),
    estimated_hours: str = Form(""),
    label_ids: list[str] = Form([]),
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.labels))
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    old_values = {
        "title": ticket.title,
        "status": ticket.status,
        "type": ticket.type,
        "priority": ticket.priority,
        "assignee_id": ticket.assignee_id,
    }

    ticket.title = title
    ticket.description = description if description else None
    ticket.project_id = project_id
    ticket.type = type
    ticket.priority = priority
    ticket.status = status_field
    ticket.assignee_id = assignee_id if assignee_id else None
    ticket.reporter_id = reporter_id if reporter_id else ticket.reporter_id
    ticket.sprint_id = sprint_id if sprint_id else None
    ticket.parent_id = parent_id if parent_id else None
    ticket.updated_at = datetime.now(timezone.utc)

    est_hours = None
    if estimated_hours and estimated_hours.strip():
        try:
            est_hours = float(estimated_hours)
        except ValueError:
            est_hours = None
    ticket.estimated_hours = est_hours

    await db.execute(ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id))
    if label_ids:
        for lid in label_ids:
            if lid and lid.strip():
                await db.execute(
                    ticket_labels.insert().values(ticket_id=ticket_id, label_id=lid.strip())
                )

    new_values = {
        "title": ticket.title,
        "status": ticket.status,
        "type": ticket.type,
        "priority": ticket.priority,
        "assignee_id": ticket.assignee_id,
    }

    await _log_audit(
        db,
        current_user.id,
        "update",
        "ticket",
        ticket_id,
        json.dumps({"old": old_values, "new": new_values}),
    )

    add_flash_message(request, f"Ticket '{title}' updated successfully.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── Delete ticket (POST) ───────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/delete")
async def delete_ticket(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.project))
    )
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    project_id = ticket.project_id
    ticket_title = ticket.title

    await db.execute(ticket_labels.delete().where(ticket_labels.c.ticket_id == ticket_id))

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "ticket",
        ticket_id,
        json.dumps({"title": ticket_title, "project_id": project_id}),
    )

    await db.delete(ticket)

    add_flash_message(request, f"Ticket '{ticket_title}' deleted.", "success")
    return RedirectResponse(url=f"/projects/{project_id}/tickets", status_code=303)


# ─── Change ticket status (POST) ────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/status")
async def change_ticket_status(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status: str = Form(...),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    old_status = ticket.status
    ticket.status = status
    ticket.updated_at = datetime.now(timezone.utc)

    await _log_audit(
        db,
        current_user.id,
        "update",
        "ticket",
        ticket_id,
        json.dumps({"field": "status", "old": old_status, "new": status}),
    )

    add_flash_message(request, f"Ticket status changed to '{status.replace('_', ' ').title()}'.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── PATCH ticket status (API for Kanban drag-and-drop) ─────────────────────

@router.patch("/api/tickets/{ticket_id}/status")
async def api_change_ticket_status(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    body = await request.json()
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Status is required")

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    old_status = ticket.status
    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)

    await _log_audit(
        db,
        current_user.id,
        "update",
        "ticket",
        ticket_id,
        json.dumps({"field": "status", "old": old_status, "new": new_status}),
    )

    return {"ok": True, "ticket_id": ticket_id, "status": new_status}


# ─── Add comment (POST) ─────────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/comments")
async def add_comment(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    content: str = Form(...),
    parent_id: str = Form(""),
    is_internal: str = Form(""),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    comment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    internal = is_internal.lower() in ("true", "on", "1", "yes") if is_internal else False

    comment = Comment(
        id=comment_id,
        ticket_id=ticket_id,
        author_id=current_user.id,
        parent_id=parent_id if parent_id else None,
        content=content,
        is_internal=internal,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)

    await _log_audit(
        db,
        current_user.id,
        "create",
        "comment",
        comment_id,
        json.dumps({"ticket_id": ticket_id, "is_internal": internal}),
    )

    add_flash_message(request, "Comment added.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}#comment-{comment_id}", status_code=303)


# ─── Delete comment (POST) ──────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/comments/{comment_id}/delete")
async def delete_comment(
    request: Request,
    ticket_id: str,
    comment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.ticket_id == ticket_id)
    )
    comment = result.scalars().first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != current_user.id and current_user.role not in ("super_admin", "project_manager"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "comment",
        comment_id,
        json.dumps({"ticket_id": ticket_id}),
    )

    await db.delete(comment)

    add_flash_message(request, "Comment deleted.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── Add time entry (POST) ──────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/time-entries")
async def add_time_entry(
    request: Request,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    hours: str = Form(...),
    entry_date: str = Form(...),
    description: str = Form(""),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalars().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        hours_val = float(hours)
    except ValueError:
        add_flash_message(request, "Invalid hours value.", "error")
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)

    if hours_val <= 0:
        add_flash_message(request, "Hours must be a positive number.", "error")
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)

    try:
        parsed_date = date.fromisoformat(entry_date)
    except ValueError:
        add_flash_message(request, "Invalid date format.", "error")
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)

    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    time_entry = TimeEntry(
        id=entry_id,
        ticket_id=ticket_id,
        user_id=current_user.id,
        hours=hours_val,
        description=description if description else None,
        entry_date=parsed_date,
        created_at=now,
    )
    db.add(time_entry)

    await _log_audit(
        db,
        current_user.id,
        "create",
        "time_entry",
        entry_id,
        json.dumps({"ticket_id": ticket_id, "hours": hours_val, "date": entry_date}),
    )

    add_flash_message(request, f"Logged {hours_val}h successfully.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


# ─── Delete time entry (POST) ───────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/time-entries/{entry_id}/delete")
async def delete_time_entry(
    request: Request,
    ticket_id: str,
    entry_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(TimeEntry).where(TimeEntry.id == entry_id, TimeEntry.ticket_id == ticket_id)
    )
    time_entry = result.scalars().first()
    if not time_entry:
        raise HTTPException(status_code=404, detail="Time entry not found")

    if time_entry.user_id != current_user.id and current_user.role not in ("super_admin", "project_manager"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this time entry")

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "time_entry",
        entry_id,
        json.dumps({"ticket_id": ticket_id, "hours": time_entry.hours}),
    )

    await db.delete(time_entry)

    add_flash_message(request, "Time entry deleted.", "success")
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)