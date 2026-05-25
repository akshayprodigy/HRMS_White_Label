# Deployment Guide - Hostinger KVM 4

This project is optimized for production deployment on a VPS like Hostinger KVM 4 (4 vCPU / 16GB RAM).

## Prerequisites
1. Ubuntu 22.04 or 24.04 (recommended)
2. Docker and Docker Compose installed
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

## Setup Instructions

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd erp-united-exploration
```

### 2. Configure Environment Variables
Copy the production environment template and fill in the values.
```bash
cp backend/production.env.example .env
# Edit .env with your secrets
nano .env
```
**Required Variables:**
- `SECRET_KEY`: Generate a secure random string (e.g., `openssl rand -hex 32`)
- `DB_PASSWORD`: Secure password for MariaDB
- `BACKEND_CORS_ORIGINS`: List of allowed origins, e.g., `["https://erp.yourdomain.com"]`

### 3. Build and Start Production Stack
```bash
sudo docker compose -f docker-compose.prod.yml up -d --build
```
This command will:
1. Build the frontend into a static bundle served by Nginx.
2. Build the backend using Gunicorn with optimized worker counts for your CPU.
3. Automatically run database migrations via Alembic.
4. Start a MariaDB 11 instance.

### 4. Seed Initial Data
```bash
# Run one-time seeding for roles/permissions and initial users
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/seed_admin.py
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/create_admin.py
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/seed_hr_permissions.py
```

### 5. Verify Services
- API Health Check: `http://<your-ip>/api/v1/health`
- Frontend: `http://<your-ip>/`

## Production testing (recommended approach)

Running a full automated test suite directly against a live production database is risky because tests create/modify data (leads, estimates, projects, tasks, approvals). Instead:

1) Local “prod-like” validation (before pushing to VPS)
- Use the prod build (Nginx + Gunicorn) locally without needing real TLS certs:
  - Start: `docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml up -d --build`
  - Frontend: `http://localhost:8088/`
  - API health: `http://localhost:8088/api/v1/health`

2) Staging validation (preferred for complete testing)
- Deploy the same `docker-compose.prod.yml` stack to a staging VPS/domain.
- Use staging DB.
- Run end-to-end smoke tests (see below) and any load testing.

3) Production validation (safe smoke checks only)
- Verify health endpoint and login.
- Verify key read-only screens load (projects list, tasks list, approvals inbox).

### Optional: run seeds + smoke tests during redeploy

The repo includes `deploy/hostinger_prod_redeploy.sh`.

- Safe default: it redeploys only.
- Enable system seeding (fresh production install; does NOT create demo users):
  - `RUN_SYSTEM_SEEDS=1 ./deploy/hostinger_prod_redeploy.sh`
- Enable demo provisioning (fresh install / staging only):
  - `RUN_SEEDS=1 ./deploy/hostinger_prod_redeploy.sh`
- Enable API smoke test run (staging only unless you accept test data in prod):
  - `RUN_SMOKE_TESTS=1 ./deploy/hostinger_prod_redeploy.sh`

- Enable production-safe read-only smoke tests (recommended for production):
  - `RUN_READONLY_SMOKE_TESTS=1 SMOKE_USERNAME='<email>' SMOKE_PASSWORD='<password>' ./deploy/hostinger_prod_redeploy.sh`

### Redeploy when VPS is not a git checkout

If the VPS folder does not contain `.git`, `deploy/hostinger_prod_redeploy.sh` will **not** be able to `git pull`.
In that case, sync code from your local machine to the VPS first (without overwriting production `.env`), then redeploy.

Recommended one-command workflow from your local machine:

```bash
chmod +x deploy/rsync_and_redeploy_prod.sh
REMOTE_HOST='root@<your-vps-ip>' REMOTE_DIR='/root/erp-united-exploration' ./deploy/rsync_and_redeploy_prod.sh
```

Fresh install tip (safe for production):

```bash
REMOTE_HOST='root@<your-vps-ip>' \
REMOTE_DIR='/root/erp-united-exploration' \
RUN_SYSTEM_SEEDS=1 \
RUN_READONLY_SMOKE_TESTS=1 \
SMOKE_USERNAME='<email>' SMOKE_PASSWORD='<password>' \
./deploy/rsync_and_redeploy_prod.sh
```

Notes:
- The sync step intentionally excludes `.env` so production secrets stay on the server.
- The redeploy step uses `docker compose -f docker-compose.prod.yml down` + `up -d --build`.

Smoke tests run `backend/happy_path_test.py` inside the backend container using:
- `SMOKE_BASE_URL` (default `http://backend:8000/api/v1`)
- `ERP_PASSWORD` (default `test@12345`, used by demo users)

Read-only smoke tests run `backend/readonly_smoke_test.py` and will:
- login
- ensure attendance is marked for that user (only write)
- call a small set of GET endpoints to confirm core flows are reachable

### 6. Troubleshooting
- **Redeploy after changes**: If you updated code and the server still shows old UI behavior, rebuild and restart the stack.
  ```bash
  chmod +x deploy/hostinger_prod_redeploy.sh
  ./deploy/hostinger_prod_redeploy.sh
  ```
  After redeploy, do a hard refresh in the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

- **No visible scrollbars**: On macOS/iOS/Chrome, scrollbars can be hidden by OS settings even when scrolling works. Try scrolling (trackpad two-finger / mouse wheel) inside the modal content.

- **Port 80 Conflict**: If the host has an existing Nginx service, stop it before starting Docker.
  ```bash
  sudo systemctl stop nginx && sudo systemctl disable nginx
  ```
- **Migration Issues**: If database migrations fail due to existing tables, resolve the schema state in Alembic.
  ```bash
  # If you must inspect the DB, run the command inside the db container.
  sudo docker compose -f docker-compose.prod.yml exec db mariadb -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" -e 'SHOW TABLES;'
  ```

### 7. SSL Certificate Renewal
Certbot is configured to renew certificates automatically. However, you need to reload Nginx after renewal to apply the new certificates.
Add this hook to your renewal config on the host:
```bash
echo 'renew_hook = docker exec erp-united-exploration-frontend-1 nginx -s reload' | sudo tee -a /etc/letsencrypt/cli.ini
```

### 8. Post-Deployment (Recommended)
- **SSL**: Set up Certbot (Let's Encrypt) to enable HTTPS.
- **Firewall**: Ensure only ports 80 and 443 are open (and 22 for SSH).
  ```bash
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  ```

## Production Architecture
- **Web Server**: Gunicorn with Uvicorn workers (async/await support).
- **Process Management**: Docker restart policies ensure services come back up after crashes or reboots.
- **Reverse Proxy**: Nginx handles static file delivery and routes API requests to the backend.
- **Database**: MariaDB with persistent volume mapped to the host.
- **Security**: 
  - Attendance Gating: Policy-level check for workspace access.
  - RBAC: Role-based access control enforced at the API router level.
  - JWT: Secure token-based authentication.

## Resource Usage (Hostinger KVM 4)
- **CPU**: 4 vCPU allows ~9 Gunicorn workers. Each worker handles dozens of concurrent requests.
- **RAM**: 16 GB is extremely generous for this stack. MariaDB can be tuned for high performance with this headroom.
- **Disk**: 200 GB NVMe provides fast I/O for database operations.
