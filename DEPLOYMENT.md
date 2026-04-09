# ProjectForge Deployment Guide

## Table of Contents

- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [Vercel Deployment](#vercel-deployment)
- [Database Considerations for Serverless](#database-considerations-for-serverless)
- [vercel.json Configuration](#verceljson-configuration)
- [Production Security Checklist](#production-security-checklist)

---

## Local Development

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Git

### Setup

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd projectforge
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create a `.env` file** in the project root:

   ```env
   SECRET_KEY=your-local-secret-key-at-least-32-characters-long
   DATABASE_URL=sqlite+aiosqlite:///./projectforge.db
   ENVIRONMENT=development
   DEBUG=true
   CORS_ORIGINS=http://localhost:3000,http://localhost:8000
   ACCESS_TOKEN_EXPIRE_MINUTES=60
   ```

5. **Run the development server:**

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   The API will be available at `http://localhost:8000`.
   Interactive docs are at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` (ReDoc).

### Running Tests

```bash
pytest -v
```

For async test support, ensure `pytest-asyncio` and `httpx` are installed (both are listed in `requirements.txt`).

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | Secret key for JWT signing. Must be at least 32 characters. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | **Yes** | `sqlite+aiosqlite:///./projectforge.db` | Async SQLAlchemy database URL |
| `ENVIRONMENT` | No | `development` | `development`, `staging`, or `production` |
| `DEBUG` | No | `false` | Enable debug mode. **Must be `false` in production** |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated list of allowed CORS origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | JWT access token expiration in minutes |
| `LOG_LEVEL` | No | `info` | Logging level: `debug`, `info`, `warning`, `error`, `critical` |

### Generating a Secure Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Never reuse secret keys across environments. Never commit secret keys to version control.

---

## Vercel Deployment

### Step-by-Step

1. **Install the Vercel CLI** (optional, for CLI-based deployment):

   ```bash
   npm install -g vercel
   ```

2. **Ensure `vercel.json` exists** in the project root (see [vercel.json Configuration](#verceljson-configuration) below).

3. **Connect your repository to Vercel:**

   - Go to [vercel.com](https://vercel.com) and sign in.
   - Click **"Add New Project"** and import your Git repository.
   - Vercel will auto-detect the `vercel.json` configuration.

4. **Configure environment variables in Vercel:**

   - Navigate to **Project Settings → Environment Variables**.
   - Add each variable from the [Environment Variables](#environment-variables) table.
   - Set `ENVIRONMENT=production` and `DEBUG=false`.
   - Use a production-grade `DATABASE_URL` (see [Database Considerations](#database-considerations-for-serverless)).

5. **Deploy:**

   - Push to your main branch for automatic deployment, or run:

     ```bash
     vercel --prod
     ```

6. **Verify the deployment:**

   - Visit `https://your-project.vercel.app/docs` to confirm the API is running.
   - Check Vercel function logs for any startup errors.

### Build Settings in Vercel Dashboard

| Setting | Value |
|---|---|
| Framework Preset | Other |
| Build Command | `pip install -r requirements.txt` |
| Output Directory | (leave empty) |
| Install Command | (leave empty — handled by runtime) |

---

## Database Considerations for Serverless

### SQLite Limitations on Vercel

**SQLite is NOT suitable for Vercel production deployments.** Vercel serverless functions have an ephemeral filesystem — any SQLite database file written during a function invocation is lost when the function instance is recycled. This means:

- Data written in one request may not be available in the next.
- Concurrent function instances each get their own filesystem, so they cannot share a SQLite database.
- The `/tmp` directory is writable but not persistent across invocations.

### Recommended Production Databases

| Provider | Database URL Format | Notes |
|---|---|---|
| **Neon (PostgreSQL)** | `postgresql+asyncpg://user:pass@host/dbname` | Free tier available. Serverless-friendly with connection pooling. |
| **Supabase (PostgreSQL)** | `postgresql+asyncpg://user:pass@host:port/dbname` | Free tier available. Use the connection pooler URL. |
| **PlanetScale (MySQL)** | `mysql+aiomysql://user:pass@host/dbname?ssl=true` | Requires `aiomysql` in requirements.txt. |
| **CockroachDB** | `cockroachdb+asyncpg://user:pass@host:port/dbname` | Distributed PostgreSQL-compatible. |
| **Railway (PostgreSQL)** | `postgresql+asyncpg://user:pass@host:port/dbname` | Simple setup with auto-provisioning. |

### Migration from SQLite to PostgreSQL

1. Update `DATABASE_URL` in your environment to point to the PostgreSQL instance.
2. Add `asyncpg` to `requirements.txt`:

   ```
   asyncpg>=0.29.0
   ```

3. Ensure your SQLAlchemy models use portable column types (avoid SQLite-specific types).
4. Run your table creation or migration tool (e.g., Alembic) against the new database.

### SQLite for Local Development

SQLite remains an excellent choice for local development and testing:

```env
DATABASE_URL=sqlite+aiosqlite:///./projectforge.db
```

This keeps local setup simple with no external database dependencies.

---

## vercel.json Configuration

Create a `vercel.json` file in the project root:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "main.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "/static/$1"
    },
    {
      "src": "/(.*)",
      "dest": "main.py"
    }
  ],
  "env": {
    "ENVIRONMENT": "production",
    "DEBUG": "false"
  }
}
```

### Configuration Breakdown

- **`builds`**: Tells Vercel to use the Python runtime for `main.py`. The `@vercel/python` runtime automatically installs packages from `requirements.txt`.
- **`routes`**: Routes all incoming requests to the FastAPI application via `main.py`. Static files are served directly.
- **`env`**: Default environment variables (override in Vercel dashboard for secrets).

### Important Notes

- The entry point (`main.py`) must expose the FastAPI app as `app` at the module level:

  ```python
  app = FastAPI()
  ```

- Vercel expects the ASGI app object to be named `app` in the file specified by `builds.src`.
- Maximum function execution time on Vercel Hobby plan is 10 seconds (60 seconds on Pro).
- Maximum deployment size is 250 MB (compressed).

---

## Production Security Checklist

### Authentication & Secrets

- [ ] `SECRET_KEY` is set to a cryptographically random value (minimum 32 characters)
- [ ] `SECRET_KEY` is unique per environment (dev, staging, production)
- [ ] `SECRET_KEY` is stored in Vercel environment variables, **not** in code or `vercel.json`
- [ ] `DEBUG` is set to `false`
- [ ] `ENVIRONMENT` is set to `production`
- [ ] All passwords are hashed with bcrypt — no plaintext passwords stored anywhere
- [ ] JWT tokens have a reasonable expiration time (30–60 minutes for access tokens)
- [ ] No default or example credentials exist in the deployed application

### CORS & Network

- [ ] `CORS_ORIGINS` contains only specific, trusted origins — **never** use `*` in production
- [ ] HTTPS is enforced (Vercel provides this automatically)
- [ ] API rate limiting is configured (consider a middleware or external service)
- [ ] No sensitive data is logged (passwords, tokens, full request bodies)

### Database

- [ ] Production database is **not** SQLite (use PostgreSQL or equivalent)
- [ ] Database credentials are stored as environment variables, not in code
- [ ] Database connection uses SSL/TLS in production
- [ ] Database user has minimal required permissions (not superuser)
- [ ] Connection pooling is configured appropriately for serverless (low `pool_size`, short `pool_recycle`)

### Dependencies

- [ ] All Python packages are pinned to specific versions in `requirements.txt`
- [ ] `bcrypt==4.0.1` is pinned if using `passlib` (newer versions break passlib)
- [ ] No known security vulnerabilities in dependencies (run `pip audit` or `safety check`)
- [ ] No unnecessary packages are included

### Application

- [ ] All API endpoints that modify data require authentication
- [ ] Role-based access control is enforced on sensitive endpoints
- [ ] Input validation is handled by Pydantic models on all endpoints
- [ ] Error responses do not leak internal details (stack traces, SQL queries, file paths)
- [ ] File upload endpoints validate file type and size
- [ ] SQL injection is prevented by using SQLAlchemy parameterized queries (never raw SQL with string interpolation)

### Monitoring & Logging

- [ ] Structured logging is enabled with appropriate log level (`info` or `warning` in production)
- [ ] Application errors are captured (consider integrating Sentry or similar)
- [ ] Vercel function logs are monitored for errors
- [ ] Health check endpoint exists (e.g., `GET /health`) for uptime monitoring

### Pre-Deployment Verification

```bash
# Run tests
pytest -v

# Check for known vulnerabilities
pip audit

# Verify no secrets in codebase
grep -r "SECRET_KEY\s*=" --include="*.py" .
grep -r "password\s*=" --include="*.py" .

# Verify environment is production-ready
python -c "
from config import settings
assert settings.ENVIRONMENT == 'production', 'Not production'
assert settings.DEBUG is False, 'Debug is enabled'
assert len(settings.SECRET_KEY) >= 32, 'Secret key too short'
print('All checks passed')
"
```

---

## Troubleshooting

### Common Vercel Deployment Issues

| Issue | Cause | Solution |
|---|---|---|
| `ModuleNotFoundError` | Missing package in `requirements.txt` | Add the package and redeploy |
| `Internal Server Error` (500) | App crashes on startup | Check Vercel function logs; verify all env vars are set |
| `Function timeout` | Request takes too long | Optimize database queries; check connection pooling |
| `File not found` for templates | Relative path issue | Use `Path(__file__).resolve().parent / "templates"` |
| Database data disappears | SQLite on ephemeral filesystem | Switch to a hosted PostgreSQL database |
| `MissingGreenlet` error | Lazy loading in async context | Add `lazy="selectin"` to all SQLAlchemy relationships |

### Checking Vercel Logs

```bash
vercel logs your-project.vercel.app
```

Or view logs in the Vercel dashboard under **Deployments → Functions**.