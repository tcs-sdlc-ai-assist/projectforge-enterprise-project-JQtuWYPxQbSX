# Changelog

All notable changes to ProjectForge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-01

### Added

#### Authentication System
- User registration with email validation and secure password hashing using bcrypt
- Login and logout functionality with JWT-based session management
- Password reset capability with token-based email verification
- Protected routes requiring authentication for all application pages

#### Role-Based Access Control (RBAC)
- Five distinct user roles with hierarchical permissions:
  - **Super Admin** — full system access, user management, and global configuration
  - **Project Manager** — project creation, team assignment, sprint management, and reporting
  - **Team Lead** — task assignment within teams, sprint planning, and team-level oversight
  - **Developer** — ticket creation, status updates, time logging, and comment participation
  - **Viewer** — read-only access to projects, boards, and reports
- Role-based route guards enforcing permissions at both API and UI levels
- Middleware-based authorization checks on all protected endpoints

#### Department Management
- Full CRUD operations for organizational departments
- Department-to-project association for organizational hierarchy
- Department listing with member counts and project summaries

#### Project Management
- Complete project CRUD with name, description, status, and date tracking
- Project membership management with role-based assignment
- Project dashboard displaying key metrics and recent activity
- Project filtering and search capabilities

#### Sprint Management
- Sprint creation with configurable start and end dates
- Sprint status lifecycle: Planning → Active → Completed
- Sprint backlog management with ticket assignment
- Sprint velocity tracking and burndown metrics

#### Ticket Management
- Full ticket CRUD with title, description, priority, status, and type fields
- Ticket assignment to team members with notification support
- Priority levels: Critical, High, Medium, Low
- Status workflow: Open → In Progress → In Review → Done → Closed
- Ticket types: Bug, Feature, Task, Improvement, Epic
- Ticket filtering by status, priority, assignee, sprint, and label

#### Kanban Board
- Interactive drag-and-drop Kanban board view per project
- Columns representing ticket statuses with real-time updates
- Ticket cards displaying key information: title, priority, assignee, and labels
- Board filtering by sprint, assignee, and priority

#### Comments System
- Threaded comments on tickets with nested reply support
- Comment creation, editing, and deletion with ownership checks
- Markdown-compatible comment formatting
- Timestamp and author attribution on all comments

#### Time Entries
- Time logging against individual tickets with date and duration
- Time entry CRUD with validation for positive durations
- Per-ticket and per-user time summaries
- Sprint-level and project-level time aggregation for reporting

#### Labels
- Custom label creation with name and color attributes
- Label assignment to tickets for categorization and filtering
- Project-scoped labels with reuse across tickets
- Label-based ticket filtering on boards and list views

#### Audit Logging
- Comprehensive audit trail for all create, update, and delete operations
- Audit log entries capturing user, action, entity type, entity ID, and timestamp
- Detailed change tracking with before and after values stored as JSON
- Admin-accessible audit log viewer with filtering by entity and user

#### Analytics Dashboard
- Project-level analytics with ticket distribution by status and priority
- Sprint velocity charts showing completed vs planned story points
- Team workload visualization displaying ticket counts per assignee
- Time tracking summaries with breakdowns by project, sprint, and user
- Filterable date ranges for all analytics views

#### User Management
- Admin panel for user listing, creation, editing, and deactivation
- Role assignment and modification by Super Admin users
- User profile pages with activity history and time log summaries
- Bulk user operations for role changes and department assignments

#### Responsive UI
- Fully responsive design built with Tailwind CSS utility classes
- Mobile-friendly navigation with collapsible sidebar
- Responsive data tables with horizontal scroll on small screens
- Dark mode support via Tailwind `dark:` variant classes
- Consistent design system with reusable component patterns

#### Database & Seeding
- SQLAlchemy 2.0 async models with full relationship mapping
- Alembic-compatible migration support for schema evolution
- Database seeding script generating sample departments, projects, users, sprints, tickets, comments, time entries, and labels
- Default Super Admin account created during initial seed

#### API & Infrastructure
- FastAPI application with versioned API routes
- Pydantic v2 request and response schemas with strict validation
- CORS middleware configuration for cross-origin requests
- Structured logging with Python logging module
- Environment-based configuration via Pydantic Settings with `.env` file support
- Health check endpoint for deployment monitoring