# Grunt Framework

**Grunt** is a metadata-driven application framework for building business applications — CRMs, ERPs, registries, and more — without writing repetitive boilerplate.

## What is Grunt?

Grunt is a **framework for frameworks**. You describe your data model using **DocTypes**, and Grunt automatically generates:

- A database table (via SQLAlchemy + Alembic)
- A full REST API (`/api/v1/docs/{DocType}`)
- A dynamic list view and form view
- A WebSocket channel for real-time updates
- Role-based access control

```
DocType "Invoice"
├── fields: title, amount, status, customer (Link)
├── workflow: Draft → Submitted → Paid → Cancelled
└── permissions: Accountant (read/write), Manager (submit)

→ Automatically generates:
   ├── grunt_app_invoice table in DB
   ├── GET/POST/PUT/DELETE /api/v1/docs/Invoice
   ├── ListView with filters and search
   ├── FormView with field validation
   └── WebSocket channel for live updates
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Metadata-driven** | Define models as JSON — no manual migrations |
| **Full-stack** | FastAPI backend + Vue 3 frontend in one framework |
| **Workflow engine** | Visual state machine with approval flows |
| **RBAC** | Role-based permissions per DocType, per row |
| **Real-time** | WebSocket updates via Redis Pub/Sub |
| **Apps** | Extend with installable apps (like plugins) |
| **Reports** | Query, Script, and dynamic List reports |
| **i18n** | Multi-language support (English + Ukrainian built-in) |

## Quick Start

```bash
# Install
pip install grunt[postgres,redis]

# Initialize a new project
grunt init

# Create your first app
grunt create-app my_crm

# Start the server
grunt serve --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Your Apps  (CRM, HR, ERP...)                        │
├──────────────────────────────────────────────────────┤
│  Grunt Core                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ DocType  │ │ Workflow │ │   RBAC   │ │Reports │  │
│  │ Engine   │ │  Engine  │ │ & Perms  │ │        │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
├──────────────────────────────────────────────────────┤
│  Runtime: FastAPI + SQLAlchemy + Redis + Vue 3       │
└──────────────────────────────────────────────────────┘
```

## Community

- [GitHub Issues](https://github.com/your-org/grunt/issues) — Bug reports and feature requests
- [Discussions](https://github.com/your-org/grunt/discussions) — Questions and ideas
