import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from dependencies import create_session, get_db
from main import app
from models.department import Department
from models.project import Project
from models.project_member import ProjectMember
from models.user import User

try:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

except Exception:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

test_async_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_department(db_session: AsyncSession) -> Department:
    now = datetime.now(timezone.utc)
    department = Department(
        id=str(uuid.uuid4()),
        name="Test Engineering",
        code="TENG",
        description="Test engineering department",
        head_id=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(department)
    await db_session.flush()
    await db_session.commit()
    return department


async def _create_user(
    db_session: AsyncSession,
    username: str,
    role: str,
    email: str | None = None,
    password: str = "testpassword123",
    department_id: str | None = None,
) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        hashed_password=hash_password(password),
        email=email or f"{username}@test.projectforge.io",
        full_name=f"Test {username.title()}",
        role=role,
        department_id=department_id,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def super_admin_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username=f"superadmin_{uuid.uuid4().hex[:6]}",
        role="super_admin",
    )


@pytest_asyncio.fixture
async def project_manager_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username=f"pm_{uuid.uuid4().hex[:6]}",
        role="project_manager",
    )


@pytest_asyncio.fixture
async def team_lead_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username=f"teamlead_{uuid.uuid4().hex[:6]}",
        role="team_lead",
    )


@pytest_asyncio.fixture
async def developer_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username=f"dev_{uuid.uuid4().hex[:6]}",
        role="developer",
    )


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username=f"viewer_{uuid.uuid4().hex[:6]}",
        role="viewer",
    )


@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, super_admin_user: User) -> Project:
    now = datetime.now(timezone.utc)
    project = Project(
        id=str(uuid.uuid4()),
        key="TEST-PROJ",
        name=f"Test Project {uuid.uuid4().hex[:6]}",
        description="A test project for unit tests.",
        status="active",
        owner_id=super_admin_user.id,
        start_date=now,
        end_date=None,
    )
    db_session.add(project)
    await db_session.flush()

    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project.id,
        user_id=super_admin_user.id,
        role="owner",
        joined_at=now,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.commit()
    return project


def get_auth_cookie(user_id: str) -> dict[str, str]:
    from itsdangerous import URLSafeTimedSerializer

    from config import settings

    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    token = serializer.dumps(user_id, salt="user-session")
    return {"session": token}


@pytest_asyncio.fixture
async def authenticated_client_super_admin(
    client: httpx.AsyncClient,
    super_admin_user: User,
) -> httpx.AsyncClient:
    cookies = get_auth_cookie(super_admin_user.id)
    client.cookies.update(cookies)
    return client


@pytest_asyncio.fixture
async def authenticated_client_pm(
    client: httpx.AsyncClient,
    project_manager_user: User,
) -> httpx.AsyncClient:
    cookies = get_auth_cookie(project_manager_user.id)
    client.cookies.update(cookies)
    return client


@pytest_asyncio.fixture
async def authenticated_client_developer(
    client: httpx.AsyncClient,
    developer_user: User,
) -> httpx.AsyncClient:
    cookies = get_auth_cookie(developer_user.id)
    client.cookies.update(cookies)
    return client


@pytest_asyncio.fixture
async def authenticated_client_viewer(
    client: httpx.AsyncClient,
    viewer_user: User,
) -> httpx.AsyncClient:
    cookies = get_auth_cookie(viewer_user.id)
    client.cookies.update(cookies)
    return client