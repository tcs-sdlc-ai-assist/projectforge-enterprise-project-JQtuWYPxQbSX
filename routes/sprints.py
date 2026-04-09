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
from models.audit_log import AuditLog
from models.project import Project
from models.sprint import Sprint
from models.ticket import Ticket
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


async def _get_project_or_404(
    project_id: str,
    db: AsyncSession,
) -> Project:
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.owner),
            selectinload(Project.department),
            selectinload(Project.members),
            selectinload(Project.sprints),
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_sprint_or_404(
    sprint_id: str,
    db: AsyncSession,
) -> Sprint:
    result = await db.execute(
        select(Sprint)
        .where(Sprint.id == sprint_id)
        .options(
            selectinload(Sprint.project),
            selectinload(Sprint.tickets),
        )
    )
    sprint = result.scalars().first()
    if not sprint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")
    return sprint


async def _log_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    user_id: str,
    details: Optional[str] = None,
) -> None:
    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        details=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(audit_entry)


@router.get("/projects/{project_id}/sprints")
async def list_project_sprints(
    request: Request,
    project_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await _get_project_or_404(project_id, db)

    result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id)
        .options(
            selectinload(Sprint.project),
            selectinload(Sprint.tickets),
        )
        .order_by(Sprint.created_at.desc())
    )
    sprints = result.scalars().all()

    sprints_with_counts = []
    for sprint in sprints:
        ticket_count_result = await db.execute(
            select(func.count(Ticket.id)).where(Ticket.sprint_id == sprint.id)
        )
        ticket_count = ticket_count_result.scalar() or 0
        sprint.ticket_count = ticket_count
        sprints_with_counts.append(sprint)

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "current_user": current_user,
            "project": project,
            "sprints": sprints_with_counts,
            "flash_messages": flash_messages,
        },
    )


@router.get("/projects/{project_id}/sprints/create")
async def create_sprint_form(
    request: Request,
    project_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await _get_project_or_404(project_id, db)

    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.department))
        .order_by(Project.name)
    )
    projects = result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/form.html",
        context={
            "current_user": current_user,
            "project": project,
            "projects": projects,
            "sprint": None,
            "form_data": {"project_id": project_id},
            "errors": None,
            "flash_messages": flash_messages,
        },
    )


@router.post("/projects/{project_id}/sprints")
async def create_sprint(
    request: Request,
    project_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Form(...),
    goal: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    project_id_form: str = Form("", alias="project_id"),
):
    project = await _get_project_or_404(project_id, db)

    errors = []
    if not name or not name.strip():
        errors.append("Sprint name is required.")

    if not start_date:
        errors.append("Start date is required.")

    if not end_date:
        errors.append("End date is required.")

    if start_date and end_date and start_date > end_date:
        errors.append("End date must be after start date.")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": project,
                "projects": projects,
                "sprint": None,
                "form_data": {
                    "name": name,
                    "goal": goal,
                    "start_date": start_date,
                    "end_date": end_date,
                    "project_id": project_id,
                },
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    parsed_start_date = None
    parsed_end_date = None
    try:
        if start_date:
            from datetime import date as date_type
            parts = start_date.split("-")
            parsed_start_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        if end_date:
            from datetime import date as date_type
            parts = end_date.split("-")
            parsed_end_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        errors.append("Invalid date format. Use YYYY-MM-DD.")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": project,
                "projects": projects,
                "sprint": None,
                "form_data": {
                    "name": name,
                    "goal": goal,
                    "start_date": start_date,
                    "end_date": end_date,
                    "project_id": project_id,
                },
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    now = datetime.now(timezone.utc)
    sprint = Sprint(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=name.strip(),
        goal=goal.strip() if goal else None,
        status="planning",
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        created_at=now,
        updated_at=now,
    )
    db.add(sprint)
    await db.flush()

    await _log_audit(
        db=db,
        entity_type="sprint",
        entity_id=sprint.id,
        action="create",
        user_id=current_user.id,
        details=f"Created sprint '{sprint.name}' for project '{project.name}'",
    )

    add_flash_message(request, f"Sprint '{sprint.name}' created successfully.", "success")
    logger.info("Sprint '%s' created by user '%s' for project '%s'", sprint.name, current_user.username, project.name)

    return RedirectResponse(
        url=f"/projects/{project_id}/sprints",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/sprints")
async def list_all_sprints(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Sprint)
        .options(
            selectinload(Sprint.project),
            selectinload(Sprint.tickets),
        )
        .order_by(Sprint.created_at.desc())
    )
    sprints = result.scalars().all()

    sprints_with_counts = []
    for sprint in sprints:
        ticket_count_result = await db.execute(
            select(func.count(Ticket.id)).where(Ticket.sprint_id == sprint.id)
        )
        ticket_count = ticket_count_result.scalar() or 0
        sprint.ticket_count = ticket_count
        sprints_with_counts.append(sprint)

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "current_user": current_user,
            "project": None,
            "sprints": sprints_with_counts,
            "flash_messages": flash_messages,
        },
    )


@router.get("/sprints/create")
async def create_sprint_form_global(
    request: Request,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.department))
        .order_by(Project.name)
    )
    projects = result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/form.html",
        context={
            "current_user": current_user,
            "project": None,
            "projects": projects,
            "sprint": None,
            "form_data": None,
            "errors": None,
            "flash_messages": flash_messages,
        },
    )


@router.post("/sprints/create")
async def create_sprint_global(
    request: Request,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Form(...),
    goal: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    project_id: str = Form(...),
):
    errors = []
    if not name or not name.strip():
        errors.append("Sprint name is required.")

    if not project_id:
        errors.append("Project is required.")

    if not start_date:
        errors.append("Start date is required.")

    if not end_date:
        errors.append("End date is required.")

    if start_date and end_date and start_date > end_date:
        errors.append("End date must be after start date.")

    project = None
    if project_id:
        proj_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = proj_result.scalars().first()
        if not project:
            errors.append("Selected project does not exist.")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": None,
                "projects": projects,
                "sprint": None,
                "form_data": {
                    "name": name,
                    "goal": goal,
                    "start_date": start_date,
                    "end_date": end_date,
                    "project_id": project_id,
                },
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    parsed_start_date = None
    parsed_end_date = None
    try:
        if start_date:
            from datetime import date as date_type
            parts = start_date.split("-")
            parsed_start_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        if end_date:
            from datetime import date as date_type
            parts = end_date.split("-")
            parsed_end_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        errors.append("Invalid date format. Use YYYY-MM-DD.")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": None,
                "projects": projects,
                "sprint": None,
                "form_data": {
                    "name": name,
                    "goal": goal,
                    "start_date": start_date,
                    "end_date": end_date,
                    "project_id": project_id,
                },
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    now = datetime.now(timezone.utc)
    sprint = Sprint(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=name.strip(),
        goal=goal.strip() if goal else None,
        status="planning",
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        created_at=now,
        updated_at=now,
    )
    db.add(sprint)
    await db.flush()

    await _log_audit(
        db=db,
        entity_type="sprint",
        entity_id=sprint.id,
        action="create",
        user_id=current_user.id,
        details=f"Created sprint '{sprint.name}' for project '{project.name if project else project_id}'",
    )

    add_flash_message(request, f"Sprint '{sprint.name}' created successfully.", "success")
    logger.info("Sprint '%s' created by user '%s'", sprint.name, current_user.username)

    return RedirectResponse(
        url="/sprints",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/sprints/{sprint_id}")
async def sprint_detail(
    request: Request,
    sprint_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sprint = await _get_sprint_or_404(sprint_id, db)

    ticket_count_result = await db.execute(
        select(func.count(Ticket.id)).where(Ticket.sprint_id == sprint.id)
    )
    sprint.ticket_count = ticket_count_result.scalar() or 0

    result = await db.execute(
        select(Ticket)
        .where(Ticket.sprint_id == sprint_id)
        .options(
            selectinload(Ticket.assignee),
            selectinload(Ticket.reporter),
            selectinload(Ticket.labels),
        )
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "current_user": current_user,
            "project": sprint.project,
            "sprints": [sprint],
            "tickets": tickets,
            "flash_messages": flash_messages,
        },
    )


@router.get("/sprints/{sprint_id}/edit")
async def edit_sprint_form(
    request: Request,
    sprint_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sprint = await _get_sprint_or_404(sprint_id, db)

    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.department))
        .order_by(Project.name)
    )
    projects = result.scalars().all()

    flash_messages = get_flash_messages(request)

    return templates.TemplateResponse(
        request,
        "sprints/form.html",
        context={
            "current_user": current_user,
            "project": sprint.project,
            "projects": projects,
            "sprint": sprint,
            "form_data": None,
            "errors": None,
            "flash_messages": flash_messages,
        },
    )


@router.post("/sprints/{sprint_id}/edit")
async def edit_sprint(
    request: Request,
    sprint_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Form(...),
    goal: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    status_field: str = Form("planning", alias="status"),
    project_id: str = Form(""),
):
    sprint = await _get_sprint_or_404(sprint_id, db)

    errors = []
    if not name or not name.strip():
        errors.append("Sprint name is required.")

    if not start_date:
        errors.append("Start date is required.")

    if not end_date:
        errors.append("End date is required.")

    if start_date and end_date and start_date > end_date:
        errors.append("End date must be after start date.")

    valid_statuses = ["planning", "active", "completed"]
    if status_field not in valid_statuses:
        errors.append(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": sprint.project,
                "projects": projects,
                "sprint": sprint,
                "form_data": None,
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    parsed_start_date = None
    parsed_end_date = None
    try:
        if start_date:
            from datetime import date as date_type
            parts = start_date.split("-")
            parsed_start_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        if end_date:
            from datetime import date as date_type
            parts = end_date.split("-")
            parsed_end_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        errors.append("Invalid date format. Use YYYY-MM-DD.")

    if errors:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.department))
            .order_by(Project.name)
        )
        projects = result.scalars().all()

        flash_messages = get_flash_messages(request)

        return templates.TemplateResponse(
            request,
            "sprints/form.html",
            context={
                "current_user": current_user,
                "project": sprint.project,
                "projects": projects,
                "sprint": sprint,
                "form_data": None,
                "errors": errors,
                "flash_messages": flash_messages,
            },
        )

    old_name = sprint.name
    sprint.name = name.strip()
    sprint.goal = goal.strip() if goal else None
    sprint.start_date = parsed_start_date
    sprint.end_date = parsed_end_date
    sprint.status = status_field
    sprint.updated_at = datetime.now(timezone.utc)

    await db.flush()

    await _log_audit(
        db=db,
        entity_type="sprint",
        entity_id=sprint.id,
        action="update",
        user_id=current_user.id,
        details=f"Updated sprint '{old_name}' -> '{sprint.name}'",
    )

    add_flash_message(request, f"Sprint '{sprint.name}' updated successfully.", "success")
    logger.info("Sprint '%s' updated by user '%s'", sprint.name, current_user.username)

    return RedirectResponse(
        url=f"/projects/{sprint.project_id}/sprints",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/sprints/{sprint_id}/start")
async def start_sprint(
    request: Request,
    sprint_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sprint = await _get_sprint_or_404(sprint_id, db)

    if sprint.status != "planning":
        add_flash_message(
            request,
            f"Sprint '{sprint.name}' cannot be started because it is currently '{sprint.status}'.",
            "error",
        )
        return RedirectResponse(
            url=f"/projects/{sprint.project_id}/sprints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    active_result = await db.execute(
        select(Sprint).where(
            Sprint.project_id == sprint.project_id,
            Sprint.status == "active",
            Sprint.id != sprint.id,
        )
    )
    active_sprint = active_result.scalars().first()

    if active_sprint:
        add_flash_message(
            request,
            f"Cannot start sprint '{sprint.name}'. Sprint '{active_sprint.name}' is already active for this project. Complete it first.",
            "error",
        )
        return RedirectResponse(
            url=f"/projects/{sprint.project_id}/sprints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    sprint.status = "active"
    sprint.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _log_audit(
        db=db,
        entity_type="sprint",
        entity_id=sprint.id,
        action="update",
        user_id=current_user.id,
        details=f"Started sprint '{sprint.name}' (status: planning -> active)",
    )

    add_flash_message(request, f"Sprint '{sprint.name}' is now active.", "success")
    logger.info("Sprint '%s' started by user '%s'", sprint.name, current_user.username)

    return RedirectResponse(
        url=f"/projects/{sprint.project_id}/sprints",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/sprints/{sprint_id}/complete")
async def complete_sprint(
    request: Request,
    sprint_id: str,
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sprint = await _get_sprint_or_404(sprint_id, db)

    if sprint.status != "active":
        add_flash_message(
            request,
            f"Sprint '{sprint.name}' cannot be completed because it is currently '{sprint.status}'.",
            "error",
        )
        return RedirectResponse(
            url=f"/projects/{sprint.project_id}/sprints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    sprint.status = "completed"
    sprint.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _log_audit(
        db=db,
        entity_type="sprint",
        entity_id=sprint.id,
        action="update",
        user_id=current_user.id,
        details=f"Completed sprint '{sprint.name}' (status: active -> completed)",
    )

    add_flash_message(request, f"Sprint '{sprint.name}' has been completed.", "success")
    logger.info("Sprint '%s' completed by user '%s'", sprint.name, current_user.username)

    return RedirectResponse(
        url=f"/projects/{sprint.project_id}/sprints",
        status_code=status.HTTP_303_SEE_OTHER,
    )