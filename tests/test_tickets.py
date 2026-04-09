import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.comment import Comment
from models.label import Label
from models.project import Project
from models.project_member import ProjectMember
from models.sprint import Sprint
from models.ticket import Ticket, ticket_labels
from models.time_entry import TimeEntry
from models.user import User
from tests.conftest import (
    _create_user,
    get_auth_cookie,
    hash_password,
    test_async_session_factory,
)


@pytest_asyncio.fixture
async def project_with_members(
    db_session: AsyncSession,
    super_admin_user: User,
    developer_user: User,
) -> Project:
    now = datetime.now(timezone.utc)
    project = Project(
        id=str(uuid.uuid4()),
        key="TKT",
        name=f"Ticket Test Project {uuid.uuid4().hex[:6]}",
        description="Project for ticket tests",
        status="active",
        owner_id=super_admin_user.id,
        start_date=now,
    )
    db_session.add(project)
    await db_session.flush()

    owner_member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project.id,
        user_id=super_admin_user.id,
        role="owner",
        joined_at=now,
    )
    db_session.add(owner_member)

    dev_member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project.id,
        user_id=developer_user.id,
        role="developer",
        joined_at=now,
    )
    db_session.add(dev_member)

    await db_session.flush()
    await db_session.commit()
    return project


@pytest_asyncio.fixture
async def test_sprint(
    db_session: AsyncSession,
    project_with_members: Project,
) -> Sprint:
    now = datetime.now(timezone.utc)
    sprint = Sprint(
        id=str(uuid.uuid4()),
        project_id=project_with_members.id,
        name="Sprint 1",
        goal="Test sprint goal",
        status="active",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 14),
        created_at=now,
        updated_at=now,
    )
    db_session.add(sprint)
    await db_session.flush()
    await db_session.commit()
    return sprint


@pytest_asyncio.fixture
async def test_label(
    db_session: AsyncSession,
    project_with_members: Project,
) -> Label:
    label = Label(
        id=str(uuid.uuid4()),
        project_id=project_with_members.id,
        name="bug",
        color="#ef4444",
        created_at=datetime.utcnow(),
    )
    db_session.add(label)
    await db_session.flush()
    await db_session.commit()
    return label


@pytest_asyncio.fixture
async def test_ticket(
    db_session: AsyncSession,
    project_with_members: Project,
    super_admin_user: User,
    developer_user: User,
    test_sprint: Sprint,
) -> Ticket:
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=str(uuid.uuid4()),
        project_id=project_with_members.id,
        sprint_id=test_sprint.id,
        key="TKT-1",
        title="Test Ticket for Unit Tests",
        description="This is a test ticket description.",
        type="bug",
        status="backlog",
        priority="high",
        assignee_id=developer_user.id,
        reporter_id=super_admin_user.id,
        estimated_hours=4.0,
        created_at=now,
        updated_at=now,
    )
    db_session.add(ticket)
    await db_session.flush()
    await db_session.commit()
    return ticket


@pytest_asyncio.fixture
async def test_comment(
    db_session: AsyncSession,
    test_ticket: Ticket,
    super_admin_user: User,
) -> Comment:
    now = datetime.now(timezone.utc)
    comment = Comment(
        id=str(uuid.uuid4()),
        ticket_id=test_ticket.id,
        author_id=super_admin_user.id,
        parent_id=None,
        content="This is a test comment.",
        is_internal=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(comment)
    await db_session.flush()
    await db_session.commit()
    return comment


@pytest_asyncio.fixture
async def internal_comment(
    db_session: AsyncSession,
    test_ticket: Ticket,
    super_admin_user: User,
) -> Comment:
    now = datetime.now(timezone.utc)
    comment = Comment(
        id=str(uuid.uuid4()),
        ticket_id=test_ticket.id,
        author_id=super_admin_user.id,
        parent_id=None,
        content="This is an internal note.",
        is_internal=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(comment)
    await db_session.flush()
    await db_session.commit()
    return comment


@pytest_asyncio.fixture
async def test_time_entry(
    db_session: AsyncSession,
    test_ticket: Ticket,
    developer_user: User,
) -> TimeEntry:
    now = datetime.now(timezone.utc)
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        ticket_id=test_ticket.id,
        user_id=developer_user.id,
        hours=2.5,
        description="Worked on bug fix",
        entry_date=date.today(),
        created_at=now,
    )
    db_session.add(entry)
    await db_session.flush()
    await db_session.commit()
    return entry


# ─── Ticket Listing Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_all_tickets_authenticated(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get("/tickets")
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_unauthenticated(client: httpx.AsyncClient):
    response = await client.get("/tickets", follow_redirects=False)
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_list_tickets_with_status_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"status": "backlog"}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_with_type_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"type": "bug"}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_with_priority_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"priority": "high"}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_with_assignee_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    developer_user: User,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"assignee_id": developer_user.id}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_with_sprint_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_sprint: Sprint,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"sprint_id": test_sprint.id}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_with_project_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    project_with_members: Project,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"project_id": project_with_members.id}
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_tickets_filter_no_results(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    response = await authenticated_client_super_admin.get(
        "/tickets", params={"priority": "critical", "status": "closed"}
    )
    assert response.status_code == 200
    assert "No tickets found" in response.text


@pytest.mark.asyncio
async def test_list_project_tickets(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    project_with_members: Project,
):
    response = await authenticated_client_super_admin.get(
        f"/projects/{project_with_members.id}/tickets"
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_list_project_tickets_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.get(
        f"/projects/{fake_id}/tickets"
    )
    assert response.status_code == 404


# ─── Ticket Creation Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_ticket_form_get(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await authenticated_client_super_admin.get(
        f"/projects/{project_with_members.id}/tickets/new"
    )
    assert response.status_code == 200
    assert "Create" in response.text or "Ticket" in response.text


@pytest.mark.asyncio
async def test_create_ticket_form_global_get(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await authenticated_client_super_admin.get(
        "/tickets/create", params={"project_id": project_with_members.id}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_ticket_post_global(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
    developer_user: User,
    super_admin_user: User,
):
    response = await authenticated_client_super_admin.post(
        "/tickets/create",
        data={
            "title": "New Bug Report",
            "project_id": project_with_members.id,
            "type": "bug",
            "priority": "critical",
            "status": "backlog",
            "description": "A critical bug found in production.",
            "assignee_id": developer_user.id,
            "reporter_id": super_admin_user.id,
            "sprint_id": "",
            "parent_id": "",
            "estimated_hours": "8.0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/tickets/" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_ticket_post_project_scoped(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
    developer_user: User,
    super_admin_user: User,
    test_sprint: Sprint,
):
    response = await authenticated_client_super_admin.post(
        f"/projects/{project_with_members.id}/tickets",
        data={
            "title": "Feature Request: Dark Mode",
            "type": "feature",
            "priority": "medium",
            "status": "todo",
            "description": "Add dark mode support.",
            "assignee_id": developer_user.id,
            "reporter_id": super_admin_user.id,
            "sprint_id": test_sprint.id,
            "parent_id": "",
            "estimated_hours": "16",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/tickets/" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_ticket_with_labels(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
    test_label: Label,
):
    response = await authenticated_client_super_admin.post(
        "/tickets/create",
        data={
            "title": "Ticket With Labels",
            "project_id": project_with_members.id,
            "type": "task",
            "priority": "low",
            "status": "backlog",
            "description": "",
            "assignee_id": "",
            "reporter_id": "",
            "sprint_id": "",
            "parent_id": "",
            "estimated_hours": "",
            "label_ids": test_label.id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_create_ticket_invalid_project(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        "/tickets/create",
        data={
            "title": "Orphan Ticket",
            "project_id": fake_id,
            "type": "task",
            "priority": "low",
            "status": "backlog",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_ticket_as_developer(
    authenticated_client_developer: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await authenticated_client_developer.post(
        "/tickets/create",
        data={
            "title": "Developer Created Ticket",
            "project_id": project_with_members.id,
            "type": "task",
            "priority": "medium",
            "status": "backlog",
            "description": "Created by developer",
            "assignee_id": "",
            "reporter_id": "",
            "sprint_id": "",
            "parent_id": "",
            "estimated_hours": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_create_ticket_as_viewer_allowed(
    authenticated_client_viewer: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await authenticated_client_viewer.get(
        f"/projects/{project_with_members.id}/tickets/new"
    )
    assert response.status_code == 200


# ─── Ticket Detail Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ticket_detail(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text
    assert "Description" in response.text
    assert "Details" in response.text


@pytest.mark.asyncio
async def test_ticket_detail_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.get(f"/tickets/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ticket_detail_with_comments(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_comment: Comment,
):
    response = await authenticated_client_super_admin.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    assert test_comment.content in response.text


@pytest.mark.asyncio
async def test_ticket_detail_with_time_entries(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_time_entry: TimeEntry,
):
    response = await authenticated_client_super_admin.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    assert "2.50" in response.text or "2.5" in response.text


@pytest.mark.asyncio
async def test_ticket_detail_project_redirect(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    project_with_members: Project,
):
    response = await authenticated_client_super_admin.get(
        f"/projects/{project_with_members.id}/tickets/{test_ticket.id}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"/tickets/{test_ticket.id}" in response.headers.get("location", "")


# ─── Ticket Edit Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_ticket_form_get(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.get(
        f"/tickets/{test_ticket.id}/edit"
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_edit_ticket_form_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.get(
        f"/tickets/{fake_id}/edit"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_edit_ticket_post(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    project_with_members: Project,
    developer_user: User,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/edit",
        data={
            "title": "Updated Ticket Title",
            "project_id": project_with_members.id,
            "type": "feature",
            "priority": "critical",
            "status": "in_progress",
            "description": "Updated description.",
            "assignee_id": developer_user.id,
            "reporter_id": "",
            "sprint_id": "",
            "parent_id": "",
            "estimated_hours": "12",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"/tickets/{test_ticket.id}" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_edit_ticket_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{fake_id}/edit",
        data={
            "title": "Ghost Ticket",
            "project_id": project_with_members.id,
            "type": "task",
            "priority": "low",
            "status": "backlog",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404


# ─── Ticket Delete Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_ticket(
    authenticated_client_super_admin: httpx.AsyncClient,
    project_with_members: Project,
    super_admin_user: User,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=str(uuid.uuid4()),
        project_id=project_with_members.id,
        key="TKT-DEL",
        title="Ticket To Delete",
        type="task",
        status="backlog",
        priority="low",
        reporter_id=super_admin_user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(ticket)
    await db_session.flush()
    await db_session.commit()

    response = await authenticated_client_super_admin.post(
        f"/tickets/{ticket.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_delete_ticket_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{fake_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 404


# ─── Ticket Status Change Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_ticket_status_via_form(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/status",
        data={"status": "in_progress"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"/tickets/{test_ticket.id}" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_change_ticket_status_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{fake_id}/status",
        data={"status": "done"},
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_change_ticket_status(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.patch(
        f"/api/tickets/{test_ticket.id}/status",
        json={"status": "in_review"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "in_review"
    assert data["ticket_id"] == test_ticket.id


@pytest.mark.asyncio
async def test_api_change_ticket_status_missing_status(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.patch(
        f"/api/tickets/{test_ticket.id}/status",
        json={},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_change_ticket_status_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.patch(
        f"/api/tickets/{fake_id}/status",
        json={"status": "done"},
    )
    assert response.status_code == 404


# ─── Comment Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_comment(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/comments",
        data={
            "content": "This is a new comment from tests.",
            "parent_id": "",
            "is_internal": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"/tickets/{test_ticket.id}" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_add_internal_comment(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/comments",
        data={
            "content": "Internal note: needs review.",
            "parent_id": "",
            "is_internal": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_reply_comment(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_comment: Comment,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/comments",
        data={
            "content": "This is a reply to the original comment.",
            "parent_id": test_comment.id,
            "is_internal": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_comment_ticket_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{fake_id}/comments",
        data={
            "content": "Comment on nonexistent ticket.",
            "parent_id": "",
            "is_internal": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_comment_by_author(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_comment: Comment,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/comments/{test_comment.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_delete_comment_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/comments/{fake_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_comment_unauthorized(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
    db_session: AsyncSession,
    super_admin_user: User,
):
    now = datetime.now(timezone.utc)
    comment = Comment(
        id=str(uuid.uuid4()),
        ticket_id=test_ticket.id,
        author_id=super_admin_user.id,
        content="Admin's comment",
        is_internal=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(comment)
    await db_session.flush()
    await db_session.commit()

    response = await authenticated_client_developer.post(
        f"/tickets/{test_ticket.id}/comments/{comment.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_internal_comment_visible_to_admin(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    internal_comment: Comment,
):
    response = await authenticated_client_super_admin.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    assert internal_comment.content in response.text


@pytest.mark.asyncio
async def test_internal_comment_visible_to_developer(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
    internal_comment: Comment,
):
    response = await authenticated_client_developer.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    # Internal comments are only visible to super_admin, project_manager, team_lead
    # Developer should NOT see internal comments
    # The template checks: if not comment.is_internal or (current_user and current_user.role in ['super_admin', 'project_manager', 'team_lead'])
    assert internal_comment.content not in response.text


# ─── Time Entry Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_time_entry(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "3.5",
            "entry_date": "2025-01-15",
            "description": "Code review and testing",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"/tickets/{test_ticket.id}" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_add_time_entry_invalid_hours(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "abc",
            "entry_date": "2025-01-15",
            "description": "Invalid hours",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_time_entry_negative_hours(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "-1",
            "entry_date": "2025-01-15",
            "description": "Negative hours",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_time_entry_invalid_date(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "2",
            "entry_date": "not-a-date",
            "description": "Invalid date",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_time_entry_ticket_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{fake_id}/time-entries",
        data={
            "hours": "1",
            "entry_date": "2025-01-15",
            "description": "Nonexistent ticket",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_time_entry_by_owner(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
    test_time_entry: TimeEntry,
):
    response = await authenticated_client_developer.post(
        f"/tickets/{test_ticket.id}/time-entries/{test_time_entry.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_delete_time_entry_by_admin(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
    test_time_entry: TimeEntry,
):
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries/{test_time_entry.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_delete_time_entry_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_ticket: Ticket,
):
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/tickets/{test_ticket.id}/time-entries/{fake_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_time_entry_unauthorized(
    db_session: AsyncSession,
    test_ticket: Ticket,
    super_admin_user: User,
):
    now = datetime.now(timezone.utc)
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        ticket_id=test_ticket.id,
        user_id=super_admin_user.id,
        hours=1.0,
        description="Admin's time entry",
        entry_date=date.today(),
        created_at=now,
    )
    db_session.add(entry)
    await db_session.flush()
    await db_session.commit()

    viewer_user = await _create_user(
        db_session,
        username=f"viewer_te_{uuid.uuid4().hex[:6]}",
        role="viewer",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=__import__("main").app),
        base_url="http://testserver",
    ) as client:
        cookies = get_auth_cookie(viewer_user.id)
        client.cookies.update(cookies)

        response = await client.post(
            f"/tickets/{test_ticket.id}/time-entries/{entry.id}/delete",
            follow_redirects=False,
        )
        # Viewer role should not be able to delete others' time entries
        # The route checks: if time_entry.user_id != current_user.id and current_user.role not in (...)
        assert response.status_code == 403


# ─── RBAC Enforcement Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_can_view_tickets(
    authenticated_client_viewer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_viewer.get("/tickets")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_viewer_can_view_ticket_detail(
    authenticated_client_viewer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_viewer.get(
        f"/tickets/{test_ticket.id}"
    )
    assert response.status_code == 200
    assert test_ticket.title in response.text


@pytest.mark.asyncio
async def test_developer_can_create_ticket(
    authenticated_client_developer: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await authenticated_client_developer.get("/tickets/create")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_developer_can_edit_ticket(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_developer.get(
        f"/tickets/{test_ticket.id}/edit"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_developer_can_change_status(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_developer.post(
        f"/tickets/{test_ticket.id}/status",
        data={"status": "in_progress"},
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_developer_can_add_comment(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_developer.post(
        f"/tickets/{test_ticket.id}/comments",
        data={
            "content": "Developer comment.",
            "parent_id": "",
            "is_internal": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_developer_can_log_time(
    authenticated_client_developer: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await authenticated_client_developer.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "1.5",
            "entry_date": "2025-01-20",
            "description": "Dev work",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_unauthenticated_cannot_create_ticket(
    client: httpx.AsyncClient,
    project_with_members: Project,
):
    response = await client.post(
        "/tickets/create",
        data={
            "title": "Unauthorized Ticket",
            "project_id": project_with_members.id,
            "type": "task",
            "priority": "low",
            "status": "backlog",
        },
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_view_ticket_detail(
    client: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await client.get(
        f"/tickets/{test_ticket.id}",
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_add_comment(
    client: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await client.post(
        f"/tickets/{test_ticket.id}/comments",
        data={
            "content": "Unauthorized comment.",
            "parent_id": "",
            "is_internal": "",
        },
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_log_time(
    client: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await client.post(
        f"/tickets/{test_ticket.id}/time-entries",
        data={
            "hours": "1",
            "entry_date": "2025-01-15",
            "description": "Unauthorized time",
        },
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_change_status(
    client: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await client.post(
        f"/tickets/{test_ticket.id}/status",
        data={"status": "done"},
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_delete_ticket(
    client: httpx.AsyncClient,
    test_ticket: Ticket,
):
    response = await client.post(
        f"/tickets/{test_ticket.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code in (401, 302)