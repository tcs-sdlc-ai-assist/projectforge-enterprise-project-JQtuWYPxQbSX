import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_current_user, get_db
from models.audit_log import AuditLog
from models.project import Project
from models.sprint import Sprint
from models.ticket import Ticket
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

from jinja2 import Environment

templates_dir = str(Path(__file__).resolve().parent.parent / "templates")

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=templates_dir)


@router.get("/dashboard")
async def dashboard(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Total projects
    total_projects_result = await db.execute(select(func.count(Project.id)))
    total_projects = total_projects_result.scalar() or 0

    # Total tickets
    total_tickets_result = await db.execute(select(func.count(Ticket.id)))
    total_tickets = total_tickets_result.scalar() or 0

    # Total users
    total_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )
    total_users = total_users_result.scalar() or 0

    # Active sprints
    active_sprints_result = await db.execute(
        select(func.count(Sprint.id)).where(Sprint.status == "active")
    )
    active_sprints = active_sprints_result.scalar() or 0

    # Ticket status distribution
    ticket_status_rows = await db.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    )
    ticket_status_distribution = {}
    for row in ticket_status_rows.all():
        status_val = row[0]
        count_val = row[1]
        ticket_status_distribution[status_val] = count_val

    # Recent activity from audit log (last 30 entries)
    recent_activity_result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.timestamp.desc())
        .limit(30)
    )
    audit_logs = recent_activity_result.scalars().all()

    recent_activity = []
    for log in audit_logs:
        recent_activity.append(
            {
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details or "",
                "timestamp": log.timestamp,
                "username": log.user.username if log.user else "System",
            }
        )

    # Projects list for quick links
    projects_result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.tickets))
        .order_by(Project.created_at.desc())
        .limit(10)
    )
    projects_list = projects_result.scalars().all()

    projects = []
    for project in projects_list:
        projects.append(
            type(
                "ProjectProxy",
                (),
                {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                    "owner": project.owner,
                    "ticket_count": len(project.tickets) if project.tickets else 0,
                },
            )()
        )

    # Top contributors by ticket count (assigned tickets)
    top_contributors_result = await db.execute(
        select(
            User.id,
            User.username,
            User.role,
            func.count(Ticket.id).label("ticket_count"),
        )
        .join(Ticket, Ticket.assignee_id == User.id)
        .where(User.is_active == True)
        .group_by(User.id, User.username, User.role)
        .order_by(func.count(Ticket.id).desc())
        .limit(5)
    )
    top_contributors_rows = top_contributors_result.all()

    top_contributors = []
    for row in top_contributors_rows:
        top_contributors.append(
            {
                "id": row[0],
                "username": row[1],
                "role": row[2],
                "ticket_count": row[3],
            }
        )

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        context={
            "current_user": current_user,
            "total_projects": total_projects,
            "total_tickets": total_tickets,
            "total_users": total_users,
            "active_sprints": active_sprints,
            "ticket_status_distribution": ticket_status_distribution,
            "recent_activity": recent_activity,
            "projects": projects,
            "top_contributors": top_contributors,
        },
    )