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
from sqlalchemy.orm import selectinload

from models.project import Project
from models.project_member import ProjectMember
from models.user import User
from tests.conftest import _create_user, get_auth_cookie, hash_password


@pytest.mark.asyncio
async def test_list_projects_unauthenticated(client: httpx.AsyncClient):
    """Unauthenticated users should be redirected to login."""
    response = await client.get("/projects", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_list_projects_authenticated(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Authenticated users can view the project list."""
    response = await authenticated_client_super_admin.get("/projects", follow_redirects=False)
    assert response.status_code == 200
    assert test_project.name in response.text


@pytest.mark.asyncio
async def test_list_projects_with_status_filter(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project list can be filtered by status."""
    response = await authenticated_client_super_admin.get(
        "/projects?status_filter=active",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert test_project.name in response.text

    response = await authenticated_client_super_admin.get(
        "/projects?status_filter=archived",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_projects_with_search(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project list can be searched by name."""
    search_term = test_project.name[:8]
    response = await authenticated_client_super_admin.get(
        f"/projects?search={search_term}",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert test_project.name in response.text


@pytest.mark.asyncio
async def test_create_project_form_super_admin(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    """Super admin can access the create project form."""
    response = await authenticated_client_super_admin.get(
        "/projects/create",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "New Project" in response.text or "Create" in response.text


@pytest.mark.asyncio
async def test_create_project_form_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
):
    """Viewer role cannot access the create project form."""
    response = await authenticated_client_viewer.get(
        "/projects/create",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_project_success(
    authenticated_client_super_admin: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Super admin can create a new project."""
    project_name = f"New Project {uuid.uuid4().hex[:8]}"
    response = await authenticated_client_super_admin.post(
        "/projects/create",
        data={
            "name": project_name,
            "description": "A test project description",
            "status": "planning",
            "owner_id": "",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(Project).where(Project.name == project_name)
    )
    project = result.scalars().first()
    assert project is not None
    assert project.name == project_name
    assert project.status == "planning"
    assert project.description == "A test project description"


@pytest.mark.asyncio
async def test_create_project_empty_name(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    """Creating a project with empty name should fail."""
    response = await authenticated_client_super_admin.post(
        "/projects/create",
        data={
            "name": "",
            "description": "No name project",
            "status": "planning",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "required" in response.text.lower() or "error" in response.text.lower()


@pytest.mark.asyncio
async def test_create_project_duplicate_name(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Creating a project with a duplicate name should fail."""
    response = await authenticated_client_super_admin.post(
        "/projects/create",
        data={
            "name": test_project.name,
            "description": "Duplicate name",
            "status": "planning",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "already exists" in response.text.lower()


@pytest.mark.asyncio
async def test_create_project_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
):
    """Viewer role cannot create projects."""
    response = await authenticated_client_viewer.post(
        "/projects/create",
        data={
            "name": f"Viewer Project {uuid.uuid4().hex[:6]}",
            "description": "Should not be created",
            "status": "planning",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_project_developer_forbidden(
    authenticated_client_developer: httpx.AsyncClient,
):
    """Developer role cannot create projects."""
    response = await authenticated_client_developer.post(
        "/projects/create",
        data={
            "name": f"Dev Project {uuid.uuid4().hex[:6]}",
            "description": "Should not be created",
            "status": "planning",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_project_detail_view(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Authenticated user can view project detail."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert test_project.name in response.text


@pytest.mark.asyncio
async def test_project_detail_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    """Viewing a non-existent project returns 404."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.get(
        f"/projects/{fake_id}",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_edit_project_form(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Super admin can access the edit project form."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/edit",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert test_project.name in response.text


@pytest.mark.asyncio
async def test_edit_project_form_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
    test_project: Project,
):
    """Viewer role cannot access the edit project form."""
    response = await authenticated_client_viewer.get(
        f"/projects/{test_project.id}/edit",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_edit_project_success(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    db_session: AsyncSession,
):
    """Super admin can update a project."""
    new_name = f"Updated Project {uuid.uuid4().hex[:6]}"
    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/edit",
        data={
            "name": new_name,
            "description": "Updated description",
            "status": "on_hold",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.expire_all()
    result = await db_session.execute(
        select(Project).where(Project.id == test_project.id)
    )
    updated_project = result.scalars().first()
    assert updated_project is not None
    assert updated_project.name == new_name
    assert updated_project.status == "on_hold"
    assert updated_project.description == "Updated description"


@pytest.mark.asyncio
async def test_edit_project_empty_name(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Editing a project with empty name should fail."""
    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/edit",
        data={
            "name": "",
            "description": "No name",
            "status": "active",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "required" in response.text.lower() or "error" in response.text.lower()


@pytest.mark.asyncio
async def test_edit_project_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    """Editing a non-existent project returns 404."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/projects/{fake_id}/edit",
        data={
            "name": "Ghost Project",
            "description": "",
            "status": "active",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_super_admin(
    authenticated_client_super_admin: httpx.AsyncClient,
    db_session: AsyncSession,
    super_admin_user: User,
):
    """Super admin can delete a project."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=str(uuid.uuid4()),
        key=f"DEL-{uuid.uuid4().hex[:4].upper()}",
        name=f"Delete Me {uuid.uuid4().hex[:6]}",
        description="To be deleted",
        status="active",
        owner_id=super_admin_user.id,
        start_date=now,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()

    project_id = project.id

    response = await authenticated_client_super_admin.post(
        f"/projects/{project_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(Project).where(Project.id == project_id)
    )
    deleted_project = result.scalars().first()
    assert deleted_project is None


@pytest.mark.asyncio
async def test_delete_project_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
    test_project: Project,
):
    """Viewer role cannot delete projects."""
    response = await authenticated_client_viewer.post(
        f"/projects/{test_project.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_project_developer_forbidden(
    authenticated_client_developer: httpx.AsyncClient,
    test_project: Project,
):
    """Developer role cannot delete projects."""
    response = await authenticated_client_developer.post(
        f"/projects/{test_project.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_project_pm_forbidden(
    authenticated_client_pm: httpx.AsyncClient,
    test_project: Project,
):
    """Project manager role cannot delete projects (only super_admin can)."""
    response = await authenticated_client_pm.post(
        f"/projects/{test_project.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_archive_project(
    authenticated_client_super_admin: httpx.AsyncClient,
    db_session: AsyncSession,
    super_admin_user: User,
):
    """Super admin can archive a project."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=str(uuid.uuid4()),
        key=f"ARC-{uuid.uuid4().hex[:4].upper()}",
        name=f"Archive Me {uuid.uuid4().hex[:6]}",
        description="To be archived",
        status="active",
        owner_id=super_admin_user.id,
        start_date=now,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()

    response = await authenticated_client_super_admin.post(
        f"/projects/{project.id}/archive",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.expire_all()
    result = await db_session.execute(
        select(Project).where(Project.id == project.id)
    )
    archived_project = result.scalars().first()
    assert archived_project is not None
    assert archived_project.status == "archived"


@pytest.mark.asyncio
async def test_add_member_form(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Super admin can access the add member form."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/members/add",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_add_member_success(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    db_session: AsyncSession,
):
    """Super admin can add a member to a project."""
    new_user = await _create_user(
        db_session,
        username=f"newmember_{uuid.uuid4().hex[:6]}",
        role="developer",
    )

    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/members/add",
        data={
            "user_id": new_user.id,
            "role": "developer",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == test_project.id,
            ProjectMember.user_id == new_user.id,
        )
    )
    membership = result.scalars().first()
    assert membership is not None
    assert membership.role == "developer"


@pytest.mark.asyncio
async def test_add_member_duplicate(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    super_admin_user: User,
):
    """Adding an already-existing member should redirect without error."""
    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/members/add",
        data={
            "user_id": super_admin_user.id,
            "role": "owner",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_add_member_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
    test_project: Project,
    viewer_user: User,
):
    """Viewer role cannot add members to a project."""
    response = await authenticated_client_viewer.post(
        f"/projects/{test_project.id}/members/add",
        data={
            "user_id": viewer_user.id,
            "role": "viewer",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_remove_member(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    db_session: AsyncSession,
):
    """Super admin can remove a member from a project."""
    member_user = await _create_user(
        db_session,
        username=f"removeme_{uuid.uuid4().hex[:6]}",
        role="developer",
    )

    membership = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=test_project.id,
        user_id=member_user.id,
        role="developer",
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(membership)
    await db_session.flush()
    await db_session.commit()

    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/members/{member_user.id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == test_project.id,
            ProjectMember.user_id == member_user.id,
        )
    )
    removed_membership = result.scalars().first()
    assert removed_membership is None


@pytest.mark.asyncio
async def test_remove_member_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Removing a non-existent membership returns 404."""
    fake_user_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.post(
        f"/projects/{test_project.id}/members/{fake_user_id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_member_viewer_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
    test_project: Project,
    super_admin_user: User,
):
    """Viewer role cannot remove members from a project."""
    response = await authenticated_client_viewer.post(
        f"/projects/{test_project.id}/members/{super_admin_user.id}/remove",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_kanban_board_view(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Authenticated user can view the Kanban board."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/board",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Kanban Board" in response.text or "board" in response.text.lower()


@pytest.mark.asyncio
async def test_kanban_board_not_found(
    authenticated_client_super_admin: httpx.AsyncClient,
):
    """Kanban board for non-existent project returns 404."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client_super_admin.get(
        f"/projects/{fake_id}/board",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_kanban_board_with_filters(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Kanban board supports filtering by assignee, label, and sprint."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/board?assignee_id=&label_id=&sprint_id=",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_kanban_board_unauthenticated(
    client: httpx.AsyncClient,
    test_project: Project,
):
    """Unauthenticated users cannot view the Kanban board."""
    response = await client.get(
        f"/projects/{test_project.id}/board",
        follow_redirects=False,
    )
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_project_tickets_redirect(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project tickets route redirects to the tickets list with project filter."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/tickets",
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)


@pytest.mark.asyncio
async def test_project_sprints_view(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project sprints route returns the sprints list."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/sprints",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_project_labels_view(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project labels route returns the labels list."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/labels",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_project_pm_allowed(
    db_session: AsyncSession,
    client: httpx.AsyncClient,
):
    """Project manager role can create projects."""
    pm_user = await _create_user(
        db_session,
        username=f"pm_create_{uuid.uuid4().hex[:6]}",
        role="project_manager",
    )
    cookies = get_auth_cookie(pm_user.id)
    client.cookies.update(cookies)

    project_name = f"PM Project {uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/projects/create",
        data={
            "name": project_name,
            "description": "Created by PM",
            "status": "planning",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(Project).where(Project.name == project_name)
    )
    project = result.scalars().first()
    assert project is not None


@pytest.mark.asyncio
async def test_project_detail_unauthenticated(
    client: httpx.AsyncClient,
    test_project: Project,
):
    """Unauthenticated users cannot view project detail."""
    response = await client.get(
        f"/projects/{test_project.id}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_project_detail_shows_members(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    super_admin_user: User,
):
    """Project detail page shows project members."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Members" in response.text
    assert super_admin_user.username in response.text


@pytest.mark.asyncio
async def test_project_detail_shows_quick_links(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Project detail page shows quick links to tickets, sprints, labels, board."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Tickets" in response.text
    assert "Sprints" in response.text
    assert "Labels" in response.text
    assert "Kanban Board" in response.text


@pytest.mark.asyncio
async def test_edit_project_viewer_post_forbidden(
    authenticated_client_viewer: httpx.AsyncClient,
    test_project: Project,
):
    """Viewer role cannot submit project edits."""
    response = await authenticated_client_viewer.post(
        f"/projects/{test_project.id}/edit",
        data={
            "name": "Hacked Name",
            "description": "",
            "status": "active",
            "owner_id": "",
            "start_date": "",
            "end_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_project_with_owner(
    authenticated_client_super_admin: httpx.AsyncClient,
    db_session: AsyncSession,
    super_admin_user: User,
):
    """Creating a project with an explicit owner sets the owner correctly."""
    target_user = await _create_user(
        db_session,
        username=f"owner_{uuid.uuid4().hex[:6]}",
        role="developer",
    )

    project_name = f"Owned Project {uuid.uuid4().hex[:8]}"
    response = await authenticated_client_super_admin.post(
        "/projects/create",
        data={
            "name": project_name,
            "description": "Has an owner",
            "status": "active",
            "owner_id": target_user.id,
            "start_date": "2025-03-01",
            "end_date": "2025-09-30",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(Project).where(Project.name == project_name)
    )
    project = result.scalars().first()
    assert project is not None
    assert project.owner_id == target_user.id


@pytest.mark.asyncio
async def test_kanban_board_renders_status_columns(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
):
    """Kanban board renders all expected status columns."""
    response = await authenticated_client_super_admin.get(
        f"/projects/{test_project.id}/board",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Backlog" in response.text
    assert "To Do" in response.text
    assert "In Progress" in response.text
    assert "In Review" in response.text
    assert "Done" in response.text
    assert "Closed" in response.text


@pytest.mark.asyncio
async def test_project_pagination(
    authenticated_client_super_admin: httpx.AsyncClient,
    db_session: AsyncSession,
    super_admin_user: User,
):
    """Project list supports pagination."""
    response = await authenticated_client_super_admin.get(
        "/projects?page=1",
        follow_redirects=False,
    )
    assert response.status_code == 200

    response = await authenticated_client_super_admin.get(
        "/projects?page=999",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_add_member_with_different_roles(
    authenticated_client_super_admin: httpx.AsyncClient,
    test_project: Project,
    db_session: AsyncSession,
):
    """Members can be added with different project roles."""
    for role in ["manager", "developer", "qa", "viewer"]:
        user = await _create_user(
            db_session,
            username=f"role_{role}_{uuid.uuid4().hex[:6]}",
            role="developer",
        )

        response = await authenticated_client_super_admin.post(
            f"/projects/{test_project.id}/members/add",
            data={
                "user_id": user.id,
                "role": role,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        result = await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == test_project.id,
                ProjectMember.user_id == user.id,
            )
        )
        membership = result.scalars().first()
        assert membership is not None
        assert membership.role == role