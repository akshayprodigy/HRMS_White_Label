# Branching & Deployment

This repo serves two products from one codebase.

## Branches

| Branch | Purpose | Production server |
|---|---|---|
| `main` | United Exploration (UE) — the original customer | `root@62.72.58.90` → https://ueiplerp.co.in |
| `white-label` | Reusable generic build for new customers / second servers | set per deployment via `REMOTE_HOST` / `REMOTE_DIR` |

## Deploying

`deploy/rsync_and_redeploy_prod.sh` reads two env vars:

- `REMOTE_HOST` — defaults to `root@62.72.58.90` (the UE box)
- `REMOTE_DIR` — required, e.g. `/root/erp-united-exploration`

**Always override BOTH when deploying `white-label` to a non-UE server**, otherwise you'll overwrite UE prod.

```bash
# Deploy UE (main)
git checkout main
REMOTE_DIR=/root/erp-united-exploration ./deploy/rsync_and_redeploy_prod.sh

# Deploy a white-label customer (different box, different path)
git checkout white-label
REMOTE_HOST=root@NEW.SERVER.IP REMOTE_DIR=/root/erp ./deploy/rsync_and_redeploy_prod.sh
```

The script excludes `.git` and `.env` from rsync — production secrets live on each server and are not overwritten.

## Flowing fixes between branches

Bug fixes done on `main` should reach `white-label`:

```bash
git checkout white-label
git merge main                # fast-forward or merge commit
git push origin white-label
```

Single-commit backport:

```bash
git checkout white-label
git cherry-pick <sha>
git push origin white-label
```

UE-only customizations stay on `main`. Generic features done on `white-label` can be merged back to `main` with `git merge white-label` when applicable.

## What's customer-specific today

- `.env` — lives on each server, never committed.
- Branding (logo, product name, colors) in `frontend/` — still wired to UE; parameterize when white-labeling.
- Seed scripts in `backend/scripts/seed_*.py` — UE-specific demo users and roles.
- TLS certs and domain — set per server (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Operational notes

- All 16 functional areas live in UE prod as of 2026-06-30. A fresh white-label deploy will start empty — use **Admin → Functional Areas → Bulk Upload** with the downloadable template to seed them.
- `employee leave write` must be granted to PM / CEO / COO / BD MANAGER / Business Developer / DEPT_HEAD / RECRUITER roles (fixed in [`8605c1b`](https://github.com/akshayprodigy/united-exploration-erp/commit/8605c1b)) or those users can't apply for their own leave.
- No git on production VPS; deploys are rsync + `docker compose` rebuild.
