import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditLog
from models.project import Project
from models.project_member import ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket
from models.user import User
from tests.conftest import (
    get_auth_cookie,
    hash_password,
    test_async_session_factory,
)


@pytest.mark.asyncio
async def test_dashboard_access_super_admin(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    response = await authenticated_client_super_admin.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Welcome back" in response.text


@pytest.mark.asyncio
async def test_dashboard_access_project_manager(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    user = User(
        id=str(uuid.uuid4()),
        username=f"pm_dash_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"pm_dash_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="PM Dashboard Test",
        role="project_manager",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Welcome back" in response.text


@pytest.mark.asyncio
async def test_dashboard_access_developer(
    authenticated_client_developer: httpx.AsyncClient,
):
    response = await authenticated_client_developer.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text


@pytest.mark.asyncio
async def test_dashboard_access_viewer(
    authenticated_client_viewer: httpx.AsyncClient,
):
    response = await authenticated_client_viewer.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text


@pytest.mark.asyncio
async def test_dashboard_redirects_unauthenticated(
    client: httpx.AsyncClient,
):
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_dashboard_summary_card_data_accuracy(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    admin_user = User(
        id=str(uuid.uuid4()),
        username=f"admin_summary_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"admin_summary_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Admin Summary Test",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.flush()

    project1 = Project(
        id=str(uuid.uuid4()),
        key=f"SP1-{uuid.uuid4().hex[:4].upper()}",
        name=f"Summary Project 1 {uuid.uuid4().hex[:6]}",
        description="First summary test project",
        status="active",
        owner_id=admin_user.id,
    )
    db_session.add(project1)
    await db_session.flush()

    project2 = Project(
        id=str(uuid.uuid4()),
        key=f"SP2-{uuid.uuid4().hex[:4].upper()}",
        name=f"Summary Project 2 {uuid.uuid4().hex[:6]}",
        description="Second summary test project",
        status="planning",
        owner_id=admin_user.id,
    )
    db_session.add(project2)
    await db_session.flush()

    sprint1 = Sprint(
        id=str(uuid.uuid4()),
        project_id=project1.id,
        name="Active Sprint 1",
        status="active",
        start_date=now.date(),
        end_date=now.date(),
        created_at=now,
        updated_at=now,
    )
    db_session.add(sprint1)
    await db_session.flush()

    for i in range(3):
        ticket = Ticket(
            id=str(uuid.uuid4()),
            project_id=project1.id,
            sprint_id=sprint1.id,
            key=f"SP1-{i + 1}",
            title=f"Summary Ticket {i + 1}",
            type="task",
            status="backlog",
            priority="medium",
            assignee_id=admin_user.id,
            reporter_id=admin_user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(ticket)

    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(admin_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200

    assert "Total Projects" in response.text
    assert "Total Tickets" in response.text
    assert "Total Users" in response.text
    assert "Active Sprints" in response.text


@pytest.mark.asyncio
async def test_dashboard_recent_activity_feed(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    admin_user = User(
        id=str(uuid.uuid4()),
        username=f"admin_activity_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"admin_activity_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Admin Activity Test",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.flush()

    for i in range(5):
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            entity_type="project",
            entity_id=str(uuid.uuid4()),
            action="create",
            user_id=admin_user.id,
            details=f"Created test project {i + 1} for activity feed",
            timestamp=now,
        )
        db_session.add(audit_log)

    audit_log_update = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action="update",
        user_id=admin_user.id,
        details="Updated ticket status from open to in_progress",
        timestamp=now,
    )
    db_session.add(audit_log_update)

    audit_log_delete = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="comment",
        entity_id=str(uuid.uuid4()),
        action="delete",
        user_id=admin_user.id,
        details="Deleted comment from ticket",
        timestamp=now,
    )
    db_session.add(audit_log_delete)

    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(admin_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200

    assert "Recent Activity" in response.text
    assert admin_user.username in response.text


@pytest.mark.asyncio
async def test_dashboard_top_contributors(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    contributor_user = User(
        id=str(uuid.uuid4()),
        username=f"contributor_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"contributor_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Top Contributor",
        role="developer",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(contributor_user)
    await db_session.flush()

    admin_user = User(
        id=str(uuid.uuid4()),
        username=f"admin_contrib_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"admin_contrib_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Admin Contributor Test",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.flush()

    project = Project(
        id=str(uuid.uuid4()),
        key=f"TC-{uuid.uuid4().hex[:4].upper()}",
        name=f"Contributor Project {uuid.uuid4().hex[:6]}",
        description="Project for top contributors test",
        status="active",
        owner_id=admin_user.id,
    )
    db_session.add(project)
    await db_session.flush()

    for i in range(5):
        ticket = Ticket(
            id=str(uuid.uuid4()),
            project_id=project.id,
            key=f"TC-{i + 1}",
            title=f"Contributor Ticket {i + 1}",
            type="task",
            status="in_progress",
            priority="medium",
            assignee_id=contributor_user.id,
            reporter_id=admin_user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(ticket)

    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(admin_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200

    assert "Top Contributors" in response.text
    assert contributor_user.username in response.text


@pytest.mark.asyncio
async def test_dashboard_empty_state(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    fresh_user = User(
        id=str(uuid.uuid4()),
        username=f"fresh_user_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"fresh_user_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Fresh User",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(fresh_user)
    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(fresh_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Total Projects" in response.text


@pytest.mark.asyncio
async def test_dashboard_shows_projects_section(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    admin_user = User(
        id=str(uuid.uuid4()),
        username=f"admin_proj_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"admin_proj_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Admin Projects Test",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.flush()

    project = Project(
        id=str(uuid.uuid4()),
        key=f"DP-{uuid.uuid4().hex[:4].upper()}",
        name=f"Dashboard Project {uuid.uuid4().hex[:6]}",
        description="Project visible on dashboard",
        status="active",
        owner_id=admin_user.id,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(admin_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200

    assert "Projects" in response.text
    assert project.name in response.text


@pytest.mark.asyncio
async def test_dashboard_ticket_status_distribution(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)

    admin_user = User(
        id=str(uuid.uuid4()),
        username=f"admin_dist_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password("testpassword123"),
        email=f"admin_dist_{uuid.uuid4().hex[:6]}@test.projectforge.io",
        full_name="Admin Distribution Test",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.flush()

    project = Project(
        id=str(uuid.uuid4()),
        key=f"TD-{uuid.uuid4().hex[:4].upper()}",
        name=f"Distribution Project {uuid.uuid4().hex[:6]}",
        description="Project for ticket distribution test",
        status="active",
        owner_id=admin_user.id,
    )
    db_session.add(project)
    await db_session.flush()

    statuses = ["backlog", "todo", "in_progress", "in_review", "done"]
    for i, status_val in enumerate(statuses):
        ticket = Ticket(
            id=str(uuid.uuid4()),
            project_id=project.id,
            key=f"TD-{i + 1}",
            title=f"Distribution Ticket {status_val}",
            type="task",
            status=status_val,
            priority="medium",
            assignee_id=admin_user.id,
            reporter_id=admin_user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(ticket)

    await db_session.flush()
    await db_session.commit()

    cookies = get_auth_cookie(admin_user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard")
    assert response.status_code == 200

    assert "Ticket Status Distribution" in response.text


@pytest.mark.asyncio
async def test_dashboard_navigation_links(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    response = await authenticated_client_super_admin.get("/dashboard")
    assert response.status_code == 200

    assert 'href="/projects"' in response.text
    assert 'href="/tickets"' in response.text
    assert 'href="/sprints"' in response.text