# ProjectForge

A comprehensive project management platform built with Python and FastAPI, designed for teams to plan, track, and deliver projects efficiently.

## Features

- **User Authentication & Authorization** — Secure login/registration with JWT tokens and role-based access control
- **Project Management** — Create, update, and archive projects with detailed metadata
- **Sprint Planning** — Organize work into time-boxed sprints with start/end dates and goals
- **Ticket Tracking** — Full-featured ticket system with priorities, statuses, assignments, and comments
- **Role-Based Access Control** — Granular permissions based on user roles (Super Admin, Project Manager, Developer, Viewer)
- **Dashboard & Reporting** — Overview dashboards with project statistics and recent activity
- **Search & Filtering** — Filter tickets by status, priority, assignee, sprint, and more
- **Responsive UI** — Server-rendered templates with Tailwind CSS for a clean, responsive interface
- **RAG-Powered Search** — Vector database integration with ChromaDB for intelligent document search

## Tech Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **Database:** SQLite with SQLAlchemy 2.0 (async via aiosqlite)
- **Authentication:** JWT tokens via python-jose, password hashing via bcrypt
- **Templates:** Jinja2 with Tailwind CSS
- **Vector DB:** ChromaDB for RAG/semantic search
- **Validation:** Pydantic v2
- **Configuration:** pydantic-settings with `.env` file support

## Folder Structure

```
projectforge/
├── main.py                  # FastAPI application entry point
├── config.py                # Application settings (BaseSettings)
├── database.py              # Async SQLAlchemy engine & session setup
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not committed)
├── README.md                # This file
├── models/
│   ├── __init__.py          # Re-exports all models
│   ├── user.py              # User model
│   ├── project.py           # Project model
│   ├── sprint.py            # Sprint model
│   ├── ticket.py            # Ticket model
│   └── comment.py           # Comment model
├── schemas/
│   ├── __init__.py          # Re-exports all schemas
│   ├── user.py              # User request/response schemas
│   ├── project.py           # Project schemas
│   ├── sprint.py            # Sprint schemas
│   ├── ticket.py            # Ticket schemas
│   └── comment.py           # Comment schemas
├── routes/
│   ├── __init__.py          # Route registration
│   ├── auth.py              # Authentication routes (login, register, logout)
│   ├── dashboard.py         # Dashboard routes
│   ├── projects.py          # Project CRUD routes
│   ├── sprints.py           # Sprint CRUD routes
│   ├── tickets.py           # Ticket CRUD routes
│   └── comments.py          # Comment routes
├── dependencies/
│   ├── __init__.py
│   ├── auth.py              # Auth dependencies (get_current_user, require_role)
│   └── database.py          # Database session dependency
├── services/
│   ├── __init__.py
│   ├── auth.py              # Auth service (JWT, password hashing)
│   ├── project.py           # Project business logic
│   ├── sprint.py            # Sprint business logic
│   ├── ticket.py            # Ticket business logic
│   └── comment.py           # Comment business logic
├── templates/
│   ├── base.html            # Base layout template
│   ├── login.html           # Login page
│   ├── register.html        # Registration page
│   ├── dashboard.html       # Dashboard page
│   ├── projects/
│   │   ├── list.html        # Project list
│   │   ├── detail.html      # Project detail
│   │   └── form.html        # Project create/edit form
│   ├── sprints/
│   │   ├── list.html        # Sprint list
│   │   ├── detail.html      # Sprint detail
│   │   └── form.html        # Sprint create/edit form
│   ├── tickets/
│   │   ├── list.html        # Ticket list
│   │   ├── detail.html      # Ticket detail
│   │   └── form.html        # Ticket create/edit form
│   └── components/
│       ├── navbar.html      # Navigation bar partial
│       ├── sidebar.html     # Sidebar partial
│       └── pagination.html  # Pagination partial
├── static/
│   └── css/
│       └── output.css       # Compiled Tailwind CSS
└── tests/
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures
    ├── test_auth.py          # Auth endpoint tests
    ├── test_projects.py      # Project endpoint tests
    ├── test_tickets.py       # Ticket endpoint tests
    └── test_sprints.py       # Sprint endpoint tests
```

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd projectforge
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
APP_NAME=ProjectForge
DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///./projectforge.db
SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440
CORS_ORIGINS=["http://localhost:8000","http://127.0.0.1:8000"]
CHROMA_DB_PATH=./chroma_data
```

> **Important:** Replace `SECRET_KEY` with a strong random string in production. Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 5. Run the Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at [http://localhost:8000](http://localhost:8000).

### 6. Run Tests

```bash
pytest tests/ -v
```

## Default Admin Credentials

On first startup, the application seeds a default super admin account:

| Field    | Value                  |
|----------|------------------------|
| Email    | `admin@projectforge.io`|
| Password | `admin123!`            |

> **Important:** Change the default admin password immediately after first login in production environments.

## Role Descriptions

| Role              | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| **Super Admin**   | Full system access. Can manage all users, projects, and system settings.    |
| **Project Manager** | Can create and manage projects, sprints, and assign tickets to team members. |
| **Developer**     | Can view assigned projects, update ticket statuses, and add comments.       |
| **Viewer**        | Read-only access to projects and tickets they are granted access to.        |

## API Documentation

FastAPI provides interactive API documentation out of the box:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Deployment Notes

### Vercel

1. Add a `vercel.json` configuration file to the project root:

```json
{
  "builds": [
    {
      "src": "main.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "main.py"
    }
  ]
}
```

2. Set all environment variables in the Vercel dashboard under **Settings → Environment Variables**.

3. Ensure `SECRET_KEY` is set to a strong random value and `DEBUG` is set to `false`.

4. For production, switch to a hosted PostgreSQL database (e.g., Supabase, Neon) and update `DATABASE_URL` accordingly:

```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/projectforge
```

5. Add `asyncpg` to `requirements.txt` if using PostgreSQL.

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t projectforge .
docker run -p 8000:8000 --env-file .env projectforge
```

## License

Private — All rights reserved.