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

from models.user import User
from tests.conftest import (
    _create_user,
    get_auth_cookie,
    hash_password,
    test_async_session_factory,
)


@pytest.mark.asyncio
async def test_register_page_loads(client: httpx.AsyncClient):
    response = await client.get("/auth/register")
    assert response.status_code == 200
    assert "Create your account" in response.text


@pytest.mark.asyncio
async def test_register_with_valid_data(client: httpx.AsyncClient):
    unique = uuid.uuid4().hex[:8]
    response = await client.post(
        "/auth/register",
        data={
            "username": f"newuser_{unique}",
            "email": f"newuser_{unique}@test.com",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "New Test User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")
    assert "session" in response.cookies


@pytest.mark.asyncio
async def test_register_with_duplicate_username(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    existing_user = await _create_user(
        db_session,
        username=f"existinguser_{unique}",
        role="developer",
        email=f"existing_{unique}@test.com",
        password="testpassword123",
    )

    response = await client.post(
        "/auth/register",
        data={
            "username": existing_user.username,
            "email": f"different_{unique}@test.com",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "Duplicate User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "already exists" in response.text


@pytest.mark.asyncio
async def test_register_with_duplicate_email(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    existing_user = await _create_user(
        db_session,
        username=f"emailuser_{unique}",
        role="developer",
        email=f"dupemail_{unique}@test.com",
        password="testpassword123",
    )

    response = await client.post(
        "/auth/register",
        data={
            "username": f"differentuser_{unique}",
            "email": existing_user.email,
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "Duplicate Email User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "already exists" in response.text


@pytest.mark.asyncio
async def test_register_with_password_mismatch(client: httpx.AsyncClient):
    unique = uuid.uuid4().hex[:8]
    response = await client.post(
        "/auth/register",
        data={
            "username": f"mismatchuser_{unique}",
            "email": f"mismatch_{unique}@test.com",
            "password": "securepassword123",
            "confirm_password": "differentpassword456",
            "full_name": "Mismatch User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "do not match" in response.text


@pytest.mark.asyncio
async def test_register_with_short_password(client: httpx.AsyncClient):
    unique = uuid.uuid4().hex[:8]
    response = await client.post(
        "/auth/register",
        data={
            "username": f"shortpw_{unique}",
            "email": f"shortpw_{unique}@test.com",
            "password": "short",
            "confirm_password": "short",
            "full_name": "Short Password User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "at least 8 characters" in response.text


@pytest.mark.asyncio
async def test_register_with_short_username(client: httpx.AsyncClient):
    unique = uuid.uuid4().hex[:8]
    response = await client.post(
        "/auth/register",
        data={
            "username": "ab",
            "email": f"shortname_{unique}@test.com",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "Short Username User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "at least 3 characters" in response.text


@pytest.mark.asyncio
async def test_register_with_invalid_email(client: httpx.AsyncClient):
    unique = uuid.uuid4().hex[:8]
    response = await client.post(
        "/auth/register",
        data={
            "username": f"bademail_{unique}",
            "email": "notanemail",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "Bad Email User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "valid email" in response.text


@pytest.mark.asyncio
async def test_login_page_loads(client: httpx.AsyncClient):
    response = await client.get("/auth/login")
    assert response.status_code == 200
    assert "Sign in to ProjectForge" in response.text


@pytest.mark.asyncio
async def test_login_with_valid_credentials(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    password = "validpassword123"
    user = await _create_user(
        db_session,
        username=f"loginuser_{unique}",
        role="developer",
        email=f"login_{unique}@test.com",
        password=password,
    )

    response = await client.post(
        "/auth/login",
        data={
            "username": user.username,
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")
    assert "session" in response.cookies


@pytest.mark.asyncio
async def test_login_with_invalid_password(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"badpwuser_{unique}",
        role="developer",
        email=f"badpw_{unique}@test.com",
        password="correctpassword123",
    )

    response = await client.post(
        "/auth/login",
        data={
            "username": user.username,
            "password": "wrongpassword456",
        },
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.text


@pytest.mark.asyncio
async def test_login_with_nonexistent_username(client: httpx.AsyncClient):
    response = await client.post(
        "/auth/login",
        data={
            "username": f"nonexistent_{uuid.uuid4().hex[:8]}",
            "password": "somepassword123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.text


@pytest.mark.asyncio
async def test_login_with_deactivated_user(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    password = "deactivatedpass123"
    user = await _create_user(
        db_session,
        username=f"deactivated_{unique}",
        role="developer",
        email=f"deactivated_{unique}@test.com",
        password=password,
    )
    user.is_active = False
    await db_session.flush()
    await db_session.commit()

    response = await client.post(
        "/auth/login",
        data={
            "username": user.username,
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "deactivated" in response.text


@pytest.mark.asyncio
async def test_logout_clears_session(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"logoutuser_{unique}",
        role="developer",
        email=f"logout_{unique}@test.com",
        password="logoutpassword123",
    )

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/" == response.headers.get("location", "")

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "session" in set_cookie_header


@pytest.mark.asyncio
async def test_logout_get_clears_session(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"logoutget_{unique}",
        role="developer",
        email=f"logoutget_{unique}@test.com",
        password="logoutpassword123",
    )

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/" == response.headers.get("location", "")


@pytest.mark.asyncio
async def test_protected_route_redirects_unauthenticated(client: httpx.AsyncClient):
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)
    if response.status_code == 302:
        location = response.headers.get("location", "")
        assert "/auth/login" in location or "/" in location


@pytest.mark.asyncio
async def test_authenticated_user_can_access_dashboard(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"dashuser_{unique}",
        role="developer",
        email=f"dashuser_{unique}@test.com",
        password="dashpassword123",
    )

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    assert "Dashboard" in response.text


@pytest.mark.asyncio
async def test_login_page_redirects_authenticated_user(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"alreadyauth_{unique}",
        role="developer",
        email=f"alreadyauth_{unique}@test.com",
        password="authpassword123",
    )

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_register_page_redirects_authenticated_user(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    unique = uuid.uuid4().hex[:8]
    user = await _create_user(
        db_session,
        username=f"alreadyreg_{unique}",
        role="developer",
        email=f"alreadyreg_{unique}@test.com",
        password="regpassword123",
    )

    cookies = get_auth_cookie(user.id)
    client.cookies.update(cookies)

    response = await client.get("/auth/register", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_register_creates_user_in_database(
    client: httpx.AsyncClient,
):
    unique = uuid.uuid4().hex[:8]
    username = f"dbcheck_{unique}"
    email = f"dbcheck_{unique}@test.com"

    response = await client.post(
        "/auth/register",
        data={
            "username": username,
            "email": email,
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "full_name": "DB Check User",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    async with test_async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        created_user = result.scalars().first()
        assert created_user is not None
        assert created_user.email == email
        assert created_user.full_name == "DB Check User"
        assert created_user.role == "viewer"
        assert created_user.is_active is True
        assert created_user.hashed_password != "securepassword123"


@pytest.mark.asyncio
async def test_expired_session_cookie_rejected(client: httpx.AsyncClient):
    from itsdangerous import URLSafeTimedSerializer

    from config import settings

    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    fake_user_id = str(uuid.uuid4())
    token = serializer.dumps(fake_user_id, salt="user-session")

    client.cookies.set("session", token)

    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_invalid_session_cookie_rejected(client: httpx.AsyncClient):
    client.cookies.set("session", "completely-invalid-token-value")

    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)