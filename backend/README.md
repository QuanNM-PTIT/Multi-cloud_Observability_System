# Observability Portal Backend

FastAPI backend for the MasterPTIT multi-cloud VM observability portal.

## Run with Docker Compose

```bash
docker compose up -d postgres
docker compose --profile app up -d --build admin-backend
```

The backend container runs:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Local Development

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## Core Endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/vms`
- `GET /api/vms`
- `GET /api/vms/{vm_id}`
- `PUT /api/vms/{vm_id}`
- `DELETE /api/vms/{vm_id}`
- `POST /api/vms/{vm_id}/agent-package`
- `GET /api/vms/{vm_id}/agent-package/download`
- `GET /api/vms/{vm_id}/agent-status`
- `GET /api/vms/{vm_id}/dashboard`
- `GET /api/vms/{vm_id}/dashboard/panels`
- `GET|POST /internal/agent-token/validate`
