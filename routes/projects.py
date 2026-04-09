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

from dependencies import get_current_user, get_db, require_role
from models.audit_log import AuditLog
from models.label import Label
from models.project import Project
from models.project_member import ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _generate_project_key(name: str) -> str:
    parts = name.strip().upper().split()
    if len(parts) >= 2:
        key = "".join(p[0] for p in parts[:4])
    else:
        key = name.strip().upper()[:5]
    key = "".join(c for c in key if c.isalnum())
    if not key:
        key = "PROJ"
    suffix = uuid.uuid4().hex[:4].upper()
    return f"{key}-{suffix}"


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


@router.get("/projects")
async def list_projects(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
):
    per_page = 20
    query = select(Project).options(
        selectinload(Project.owner),
        selectinload(Project.members).selectinload(ProjectMember.user),
        selectinload(Project.department),
    )

    if status_filter:
        query = query.where(Project.status == status_filter)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Project.name.ilike(search_term)) | (Project.key.ilike(search_term))
        )

    query = query.order_by(Project.created_at.desc())

    count_query = select(func.count()).select_from(Project)
    if status_filter:
        count_query = count_query.where(Project.status == status_filter)
    if search:
        search_term = f"%{search}%"
        count_query = count_query.where(
            (Project.name.ilike(search_term)) | (Project.key.ilike(search_term))
        )
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    projects = result.scalars().unique().all()

    return templates.TemplateResponse(
        request,
        "projects/list.html",
        context={
            "current_user": current_user,
            "projects": projects,
            "search": search or "",
            "status_filter": status_filter or "",
            "current_page": page,
            "total_pages": total_pages,
            "flash_messages": [],
        },
    )


@router.get("/projects/create")
async def create_project_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
):
    result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "projects/form.html",
        context={
            "current_user": current_user,
            "project": None,
            "users": users,
            "error": None,
            "flash_messages": [],
        },
    )


@router.post("/projects/create")
async def create_project(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
    name: str = Form(...),
    description: str = Form(""),
    status: str = Form("planning"),
    owner_id: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    if not name or not name.strip():
        result = await db.execute(
            select(User).where(User.is_active == True).order_by(User.username)
        )
        users = result.scalars().all()
        return templates.TemplateResponse(
            request,
            "projects/form.html",
            context={
                "current_user": current_user,
                "project": None,
                "users": users,
                "error": "Project name is required.",
                "flash_messages": [],
            },
        )

    existing = await db.execute(select(Project).where(Project.name == name.strip()))
    if existing.scalars().first():
        result = await db.execute(
            select(User).where(User.is_active == True).order_by(User.username)
        )
        users = result.scalars().all()
        return templates.TemplateResponse(
            request,
            "projects/form.html",
            context={
                "current_user": current_user,
                "project": None,
                "users": users,
                "error": "A project with this name already exists.",
                "flash_messages": [],
            },
        )

    key = _generate_project_key(name.strip())

    parsed_start = None
    parsed_end = None
    if start_date and start_date.strip():
        try:
            parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d")
        except ValueError:
            pass
    if end_date and end_date.strip():
        try:
            parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        except ValueError:
            pass

    effective_owner_id = owner_id.strip() if owner_id and owner_id.strip() else current_user.id

    project = Project(
        id=str(uuid.uuid4()),
        key=key,
        name=name.strip(),
        description=description.strip() if description else None,
        status=status if status in ("planning", "active", "on_hold", "completed", "archived") else "planning",
        owner_id=effective_owner_id,
        start_date=parsed_start,
        end_date=parsed_end,
    )
    db.add(project)
    await db.flush()

    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project.id,
        user_id=effective_owner_id,
        role="owner",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    if effective_owner_id != current_user.id:
        creator_member = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=current_user.id,
            role="manager",
            joined_at=datetime.now(timezone.utc),
        )
        db.add(creator_member)

    await _log_audit(db, current_user.id, "create", "project", project.id, f"Created project '{project.name}'")

    logger.info("Project '%s' created by user '%s'", project.name, current_user.username)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


@router.get("/projects/{project_id}")
async def project_detail(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.owner),
            selectinload(Project.department),
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.sprints),
            selectinload(Project.tickets).selectinload(Ticket.assignee),
            selectinload(Project.labels),
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    members = []
    if project.members:
        for pm in project.members:
            if pm.user:
                user = pm.user
                user._project_role = pm.role
                members.append(user)

    ticket_count = len(project.tickets) if project.tickets else 0
    sprint_count = len(project.sprints) if project.sprints else 0
    label_count = len(project.labels) if project.labels else 0

    recent_tickets = sorted(
        project.tickets or [],
        key=lambda t: t.created_at or datetime.min,
        reverse=True,
    )[:5]

    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        context={
            "current_user": current_user,
            "project": project,
            "members": members,
            "ticket_count": ticket_count,
            "sprint_count": sprint_count,
            "label_count": label_count,
            "recent_tickets": recent_tickets,
            "flash_messages": [],
        },
    )


@router.get("/projects/{project_id}/edit")
async def edit_project_form(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.owner), selectinload(Project.department))
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    users = users_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "projects/form.html",
        context={
            "current_user": current_user,
            "project": project,
            "users": users,
            "error": None,
            "flash_messages": [],
        },
    )


@router.post("/projects/{project_id}/edit")
async def update_project(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
    name: str = Form(...),
    description: str = Form(""),
    status: str = Form("planning"),
    owner_id: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.owner), selectinload(Project.department))
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not name or not name.strip():
        users_result = await db.execute(
            select(User).where(User.is_active == True).order_by(User.username)
        )
        users = users_result.scalars().all()
        return templates.TemplateResponse(
            request,
            "projects/form.html",
            context={
                "current_user": current_user,
                "project": project,
                "users": users,
                "error": "Project name is required.",
                "flash_messages": [],
            },
        )

    if name.strip() != project.name:
        existing = await db.execute(
            select(Project).where(Project.name == name.strip(), Project.id != project_id)
        )
        if existing.scalars().first():
            users_result = await db.execute(
                select(User).where(User.is_active == True).order_by(User.username)
            )
            users = users_result.scalars().all()
            return templates.TemplateResponse(
                request,
                "projects/form.html",
                context={
                    "current_user": current_user,
                    "project": project,
                    "users": users,
                    "error": "A project with this name already exists.",
                    "flash_messages": [],
                },
            )

    changes = []
    if project.name != name.strip():
        changes.append(f"name: '{project.name}' -> '{name.strip()}'")
        project.name = name.strip()

    new_desc = description.strip() if description else None
    if project.description != new_desc:
        changes.append("description updated")
        project.description = new_desc

    valid_statuses = ("planning", "active", "on_hold", "completed", "archived")
    new_status = status if status in valid_statuses else project.status
    if project.status != new_status:
        changes.append(f"status: '{project.status}' -> '{new_status}'")
        project.status = new_status

    new_owner_id = owner_id.strip() if owner_id and owner_id.strip() else None
    if project.owner_id != new_owner_id:
        changes.append(f"owner changed")
        project.owner_id = new_owner_id

    parsed_start = None
    parsed_end = None
    if start_date and start_date.strip():
        try:
            parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d")
        except ValueError:
            pass
    if end_date and end_date.strip():
        try:
            parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        except ValueError:
            pass

    if project.start_date != parsed_start:
        changes.append("start_date updated")
        project.start_date = parsed_start
    if project.end_date != parsed_end:
        changes.append("end_date updated")
        project.end_date = parsed_end

    project.updated_at = datetime.now(timezone.utc)

    if changes:
        await _log_audit(
            db,
            current_user.id,
            "update",
            "project",
            project.id,
            f"Updated project '{project.name}': {'; '.join(changes)}",
        )

    logger.info("Project '%s' updated by user '%s'", project.name, current_user.username)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = project.name

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "project",
        project.id,
        f"Deleted project '{project_name}'",
    )

    await db.delete(project)

    logger.info("Project '%s' deleted by user '%s'", project_name, current_user.username)

    return RedirectResponse(url="/projects", status_code=303)


@router.post("/projects/{project_id}/archive")
async def archive_project(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin"]))],
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    old_status = project.status
    project.status = "archived"
    project.updated_at = datetime.now(timezone.utc)

    await _log_audit(
        db,
        current_user.id,
        "update",
        "project",
        project.id,
        f"Archived project '{project.name}' (was '{old_status}')",
    )

    logger.info("Project '%s' archived by user '%s'", project.name, current_user.username)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


@router.get("/projects/{project_id}/members/add")
async def add_member_form(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.members))
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing_member_ids = {pm.user_id for pm in (project.members or [])}

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.username)
    )
    all_users = users_result.scalars().all()
    available_users = [u for u in all_users if u.id not in existing_member_ids]

    return templates.TemplateResponse(
        request,
        "projects/add_member.html",
        context={
            "current_user": current_user,
            "project": project,
            "available_users": available_users,
            "flash_messages": [],
        },
    )


@router.post("/projects/{project_id}/members/add")
async def add_member(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
    user_id: str = Form(...),
    role: str = Form("developer"),
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.members))
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalars().first():
        return RedirectResponse(url=f"/projects/{project_id}", status_code=303)

    user_result = await db.execute(select(User).where(User.id == user_id))
    target_user = user_result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    valid_roles = ("owner", "manager", "developer", "qa", "viewer")
    member_role = role if role in valid_roles else "developer"

    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project_id,
        user_id=user_id,
        role=member_role,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    await _log_audit(
        db,
        current_user.id,
        "create",
        "project_member",
        member.id,
        f"Added user '{target_user.username}' to project '{project.name}' as '{member_role}'",
    )

    logger.info(
        "User '%s' added to project '%s' by '%s'",
        target_user.username,
        project.name,
        current_user.username,
    )

    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


@router.post("/projects/{project_id}/members/{user_id}/remove")
async def remove_member(
    request: Request,
    project_id: str,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager"]))],
):
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    membership = result.scalars().first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    user_result = await db.execute(select(User).where(User.id == user_id))
    target_user = user_result.scalars().first()

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalars().first()

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "project_member",
        membership.id,
        f"Removed user '{target_user.username if target_user else user_id}' from project '{project.name if project else project_id}'",
    )

    await db.delete(membership)

    logger.info(
        "User '%s' removed from project '%s' by '%s'",
        target_user.username if target_user else user_id,
        project.name if project else project_id,
        current_user.username,
    )

    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


@router.get("/projects/{project_id}/board")
async def kanban_board(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    assignee_id: Optional[str] = None,
    label_id: Optional[str] = None,
    sprint_id: Optional[str] = None,
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.owner),
            selectinload(Project.sprints),
            selectinload(Project.labels),
            selectinload(Project.members).selectinload(ProjectMember.user),
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ticket_query = (
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .options(
            selectinload(Ticket.assignee),
            selectinload(Ticket.sprint),
            selectinload(Ticket.labels),
            selectinload(Ticket.reporter),
        )
    )

    if assignee_id and assignee_id.strip():
        ticket_query = ticket_query.where(Ticket.assignee_id == assignee_id.strip())

    if sprint_id and sprint_id.strip():
        ticket_query = ticket_query.where(Ticket.sprint_id == sprint_id.strip())

    ticket_result = await db.execute(ticket_query)
    all_tickets = ticket_result.scalars().unique().all()

    if label_id and label_id.strip():
        filtered_tickets = []
        for t in all_tickets:
            if t.labels and any(lbl.id == label_id.strip() for lbl in t.labels):
                filtered_tickets.append(t)
        all_tickets = filtered_tickets

    status_columns = ["backlog", "todo", "in_progress", "in_review", "done", "closed"]
    columns = {s: [] for s in status_columns}
    for ticket in all_tickets:
        ticket_status = ticket.status or "backlog"
        if ticket_status in columns:
            columns[ticket_status].append(ticket)
        else:
            columns["backlog"].append(ticket)

    members = []
    if project.members:
        for pm in project.members:
            if pm.user:
                members.append(pm.user)

    filters = {
        "assignee_id": assignee_id or "",
        "label_id": label_id or "",
        "sprint_id": sprint_id or "",
    }

    return templates.TemplateResponse(
        request,
        "projects/board.html",
        context={
            "current_user": current_user,
            "project": project,
            "columns": columns,
            "members": members,
            "labels": project.labels or [],
            "sprints": project.sprints or [],
            "filters": filters,
            "flash_messages": [],
        },
    )


@router.get("/projects/{project_id}/tickets")
async def project_tickets(
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
        raise HTTPException(status_code=404, detail="Project not found")

    return RedirectResponse(url=f"/tickets?project_id={project_id}", status_code=303)


@router.get("/projects/{project_id}/sprints")
async def project_sprints(
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
        raise HTTPException(status_code=404, detail="Project not found")

    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id)
        .options(selectinload(Sprint.tickets))
        .order_by(Sprint.created_at.desc())
    )
    sprints = sprint_result.scalars().unique().all()

    sprint_list = []
    for s in sprints:
        s.ticket_count = len(s.tickets) if s.tickets else 0
        sprint_list.append(s)

    return templates.TemplateResponse(
        request,
        "sprints/list.html",
        context={
            "current_user": current_user,
            "project": project,
            "sprints": sprint_list,
            "flash_messages": [],
        },
    )


@router.get("/projects/{project_id}/labels")
async def project_labels(
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
        raise HTTPException(status_code=404, detail="Project not found")

    label_result = await db.execute(
        select(Label)
        .where(Label.project_id == project_id)
        .order_by(Label.name)
    )
    labels = label_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "labels/list.html",
        context={
            "current_user": current_user,
            "project": project,
            "labels": labels,
            "flash_messages": [],
        },
    )


@router.post("/projects/{project_id}/labels")
async def create_label(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
    name: str = Form(...),
    color: str = Form("#6366f1"),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = await db.execute(
        select(Label).where(Label.project_id == project_id, Label.name == name.strip())
    )
    if existing.scalars().first():
        return RedirectResponse(url=f"/projects/{project_id}/labels", status_code=303)

    label = Label(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=name.strip(),
        color=color.strip() if color else "#6366f1",
        created_at=datetime.utcnow(),
    )
    db.add(label)

    await _log_audit(
        db,
        current_user.id,
        "create",
        "label",
        label.id,
        f"Created label '{label.name}' for project '{project.name}'",
    )

    logger.info("Label '%s' created for project '%s' by '%s'", label.name, project.name, current_user.username)

    return RedirectResponse(url=f"/projects/{project_id}/labels", status_code=303)


@router.post("/projects/{project_id}/labels/{label_id}/delete")
async def delete_label(
    request: Request,
    project_id: str,
    label_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(["super_admin", "project_manager", "team_lead"]))],
):
    result = await db.execute(
        select(Label).where(Label.id == label_id, Label.project_id == project_id)
    )
    label = result.scalars().first()
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")

    label_name = label.name

    await _log_audit(
        db,
        current_user.id,
        "delete",
        "label",
        label.id,
        f"Deleted label '{label_name}' from project '{project_id}'",
    )

    await db.delete(label)

    logger.info("Label '%s' deleted by '%s'", label_name, current_user.username)

    return RedirectResponse(url=f"/projects/{project_id}/labels", status_code=303)


@router.get("/projects/{project_id}/tickets/new")
async def new_ticket_for_project(
    request: Request,
    project_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return RedirectResponse(url=f"/tickets/create?project_id={project_id}", status_code=303)