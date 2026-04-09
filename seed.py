import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session_factory
from models.user import User
from models.department import Department
from models.project import Project
from models.label import Label

logger = logging.getLogger(__name__)

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
except Exception:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def seed_database() -> None:
    """Seed the database with initial data if it doesn't already exist."""
    async with async_session_factory() as session:
        try:
            await _seed_default_admin(session)
            await _seed_engineering_department(session)
            await _seed_sample_labels(session)
            await session.commit()
            logger.info("Database seeding completed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error("Database seeding failed: %s", str(e))
            raise


async def _seed_default_admin(session: AsyncSession) -> User | None:
    """Create the default admin user if it doesn't exist."""
    username = settings.DEFAULT_ADMIN_USERNAME
    password = settings.DEFAULT_ADMIN_PASSWORD

    result = await session.execute(
        select(User).where(User.username == username)
    )
    existing_user = result.scalars().first()

    if existing_user is not None:
        logger.info("Default admin user '%s' already exists. Skipping.", username)
        return existing_user

    hashed = hash_password(password)
    now = datetime.now(timezone.utc)

    admin_user = User(
        id=str(uuid.uuid4()),
        username=username,
        hashed_password=hashed,
        email="admin@projectforge.io",
        full_name="System Administrator",
        role="super_admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(admin_user)
    await session.flush()
    logger.info("Default admin user '%s' created successfully.", username)
    return admin_user


async def _seed_engineering_department(session: AsyncSession) -> Department | None:
    """Create the 'Engineering' department if it doesn't exist."""
    result = await session.execute(
        select(Department).where(Department.code == "ENG")
    )
    existing_dept = result.scalars().first()

    if existing_dept is not None:
        logger.info("Engineering department already exists. Skipping.")
        return existing_dept

    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(User).where(User.role == "super_admin").limit(1)
    )
    admin_user = result.scalars().first()

    department = Department(
        id=str(uuid.uuid4()),
        name="Engineering",
        code="ENG",
        description="Software engineering and development team.",
        head_id=admin_user.id if admin_user else None,
        created_at=now,
        updated_at=now,
    )
    session.add(department)
    await session.flush()
    logger.info("Engineering department created successfully.")
    return department


async def _seed_sample_labels(session: AsyncSession) -> list[Label]:
    """Create sample labels for any existing projects that have no labels."""
    default_labels = [
        {"name": "bug", "color": "#ef4444"},
        {"name": "feature", "color": "#3b82f6"},
        {"name": "enhancement", "color": "#8b5cf6"},
        {"name": "documentation", "color": "#6366f1"},
        {"name": "urgent", "color": "#dc2626"},
        {"name": "good first issue", "color": "#22c55e"},
        {"name": "help wanted", "color": "#f59e0b"},
        {"name": "wontfix", "color": "#6b7280"},
    ]

    result = await session.execute(select(Project))
    projects = result.scalars().all()

    if not projects:
        logger.info("No projects found. Skipping sample label seeding.")
        return []

    created_labels: list[Label] = []

    for project in projects:
        result = await session.execute(
            select(Label).where(Label.project_id == project.id).limit(1)
        )
        existing_label = result.scalars().first()

        if existing_label is not None:
            logger.info(
                "Project '%s' already has labels. Skipping label seeding for this project.",
                project.name,
            )
            continue

        for label_data in default_labels:
            label = Label(
                id=str(uuid.uuid4()),
                project_id=project.id,
                name=label_data["name"],
                color=label_data["color"],
                created_at=datetime.utcnow(),
            )
            session.add(label)
            created_labels.append(label)

        logger.info(
            "Created %d sample labels for project '%s'.",
            len(default_labels),
            project.name,
        )

    if created_labels:
        await session.flush()

    return created_labels