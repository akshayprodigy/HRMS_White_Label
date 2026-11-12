# Roadmap v2 — Phase 3 (Native Mobile App, React Native, white-label) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a white-label React Native app (iOS + Android) for employees and schedulers covering spec §3: existing mobile-web screens, geofence + selfie punch, offline punch queue, live location tracking during rostered shifts, push notifications with actions, and all Phase 1–2 self-service (schedule, swaps, open shifts, emergency leave, running late, mark safe, payslips, documents).

**Architecture:**
- New workspace `mobile/` in this repo: **Expo (latest stable SDK, ≥ 2 weeks old) + TypeScript + expo-router + development builds** (`expo prebuild` / EAS local builds) so native modules (camera, background location, push) are available. Talks to the existing FastAPI backend (`/api/v1`).
- White-label: `mobile/tenants/<tenant>/tenant.json` (name, slug, iOS bundle id, Android package, colors, API base URL, feature flags) + `icon.png` / `splash.png`; `app.config.ts` reads `TENANT` env; `scripts/build-tenant.sh <tenant> <platform> [profile]` produces per-client builds.
- Backend additions are small, isolated modules (device tokens + push channel, selfie punch, offline punch batch, location tracking) following the existing patterns (models + migrations + thin routers + services + tests).

**Tech Stack:** Expo SDK (latest stable), React Native, TypeScript, expo-router, @tanstack/react-query, axios, expo-secure-store, expo-sqlite (offline queue), expo-location + expo-task-manager (background location), expo-camera / react-native-vision-camera + face detection (selfie liveness), expo-notifications (push via Expo Push Service → FCM/APNs), react-native-maps; Jest + @testing-library/react-native; Maestro for simulator UI flows. Backend: FastAPI + async SQLAlchemy + MariaDB + Alembic.

Spec: `docs/superpowers/specs/2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` §3.
Branch: `feature/roadmap-v2-phase3`, stacked on `feature/roadmap-v2-phase2`. Migration head at start: run `alembic heads` (expected `c4f8a1d2e9b6`).

**Product decisions taken:**
- **Expo with development builds** (not bare RN CLI, not Expo Go): fastest white-label pipeline (config-driven app.config), OTA-capable, still allows native modules.
- **Push gateway = Expo Push Service** (one integration for FCM + APNs). Real delivery needs per-tenant credentials (FCM service account, APNs key) configured in EAS at go-live — a user action. Backend push provider is pluggable: `log` (dev default) and `expo`.
- **Live location (spec open decision #4): off by default for every role.** HR enables tracking per role (and optionally per employee). The employee must give in-app consent (revocable). Pings are accepted only during the employee's rostered shift window (effective shift start − 30 min … end + 30 min). Retention 30 days (purge job). Employees can see their own trail.
- **Offline punch queue:** the native app captures device GPS + timestamp while offline and syncs later; the server accepts only punches captured ≤ `attendance.offline_max_hours` (default 12) ago, never in the future, idempotent by client UUID, and **flags them for HR review** (`attendance.is_offline = true`, shown in Flagged Review). This supersedes the PWA service-worker decision only for the native app.
- **Selfie liveness:** on-device blink/turn challenge with face detection; server stores the selfie + `liveness_passed` and flags failures for review. Face match against a reference photo is out of scope (spec: "phase 2").
- **Time zone:** unchanged convention (UTC wall-clock for shift times); the app displays shift times labelled UTC where the web app does.

## Environment (all tasks)

- Backend: read "Environment (all tasks)" in `docs/superpowers/plans/2026-11-12-roadmap-v2-phase1b.md` (docker containers, pytest on the real dev DB with clean teardown, migrations linear + up/down/up, commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, never push).
- Mobile workspace `mobile/` (own package.json; do not touch `frontend/`'s dependencies). Node 23 is installed. Commands from `mobile/`: `npx tsc --noEmit`, `npx jest`, `npx expo-doctor`. Simulator builds: `npx expo prebuild --clean` then `npx expo run:ios --device "iPhone 15"` (Xcode + iOS simulators installed) — Android emulator images exist under `~/Library/Android/sdk` (add `platform-tools` to PATH: `export PATH=$HOME/Library/Android/sdk/platform-tools:$HOME/Library/Android/sdk/emulator:$PATH`).
- The iOS simulator reaches the dev backend at `http://localhost:8005/api/v1`; the Android emulator at `http://10.0.2.2:8005/api/v1` — the dev tenant config must pick per platform.
- Logins (password `test@12345`): `employee@gmail.com`, `pm@gmail.com`, `hr@gmail.com`, `admin@gmail.com`. Non-superusers must have punched in for gated `/roster/*` etc. routes (`deps.verify_attendance`) — the app's punch flow handles this naturally; tests may seed attendance for test users.
- UI verification: Maestro flows (`mobile/e2e/*.yaml`) run against the simulator; screenshots saved to `mobile/e2e/artifacts/` (gitignored) and LOOKED at. Install Maestro locally only if missing (`curl -Ls "https://get.maestro.mobile.dev" | bash`) — it installs to `~/.maestro`.
- Never commit secrets, signing keys, `google-services.json`/`GoogleService-Info.plist` with real values, or generated `ios/`/`android/` folders (`expo prebuild` output is gitignored; config lives in app.config + plugins).

## File map

| Path | Responsibility |
|---|---|
| `mobile/` | Expo app (expo-router `app/`, `src/api`, `src/features/*`, `src/components`, `src/theme`, `tenants/`, `scripts/`, `e2e/`) |
| `backend/app/models/device.py`, `services/push.py`, `endpoints/devices.py` | device tokens, push channel + actions |
| `backend/app/services/notifications_delivery.py` | PUSH channel fan-out |
| `backend/app/endpoints/attendance.py` (+ `services/selfie.py`) | selfie upload + liveness flags on punch |
| `backend/app/endpoints/attendance_offline.py` | offline punch batch sync |
| `backend/app/models/location.py`, `services/location_tracking.py`, `endpoints/tracking.py` | policy, consent, pings, field-now, trails, geofence-exit alerts, purge job |
| `frontend/src/components/field-team.tsx` (+ HR tracking policy UI) | web "Field team now" map + policy/consent admin |

---

### Task 1: Backend — device tokens + push channel with actions

- Model `device_token` (`user_id`, `platform` ios|android, `token` unique, `app_version`, `tenant`, `created_at`, `last_seen_at`, `revoked_at`). Endpoints: `POST /devices` (register/refresh, upsert by token, re-assign to current user if token moves), `DELETE /devices/{token}` (own), `GET /devices/my`.
- Channel `PUSH` in `models/notification_channel.py`; `dispatch_notification` creates PUSH delivery rows for users with active tokens (respect preferences/quiet hours like other channels; emergency category bypass like Task 7 of Phase 2). Provider interface `PushProvider.send(tokens, title, body, data, category)`; `LogPushProvider` (default) and `ExpoPushProvider` (HTTP POST to `https://exp.host/--/api/v2/push/send`, batches of 100, handles `DeviceNotRegistered` → revoke token; configured by `PUSH_PROVIDER=expo` + optional `EXPO_ACCESS_TOKEN`). Delivered by the existing `send_queued_notifications` job.
- Notification payload `data`: `{event_type, resource_type, resource_id, actions: [...]}`; action categories: `approval` (approve/reject), `open_shift` (claim), `broadcast_safety` (safe/need_help), `broadcast_ack` (acknowledge). Action endpoint `POST /notifications/actions {notification_id, action, comment?}` routes to the existing services (approval action incl. leave service + SoD + delegation; open-shift claim; broadcast safety/ack) with the caller's auth — never trusts payload ids beyond the notification row owned by the caller.
- Tests: token upsert/revoke/move; PUSH rows only for users with tokens; quiet-hours respected except emergency; Expo provider batching + DeviceNotRegistered revocation (mock HTTP); action endpoint each kind incl. auth/SoD failures.
- [ ] TDD → migration → commit `feat(push): device tokens, push channel and actionable notifications`.

### Task 2: Backend — selfie punch + offline punch sync

- Selfie: `POST /attendance/selfie` (multipart image ≤ 3 MB jpeg/png/webp → stored uuid name under `settings.ATTENDANCE_SELFIE_DIR`, returns `selfie_id`); `POST /attendance/mark` and punch-out accept optional `selfie_id`, `liveness_passed`, `liveness_score`. New Attendance columns `selfie_url`, `liveness_passed` (nullable bool), `is_offline` (bool default false), `client_uuid` (unique nullable), `device_captured_at`. Time rule `attendance.selfie_required` (0/1, default 0): when 1 a punch without selfie → 400; `liveness_passed=false` → punch accepted but flagged (`attribution_flag`/geo flag style column `review_flag='liveness_failed'`). HR selfie view endpoint (permission `hr employee read`), shown in Flagged Review UI.
- Offline: `POST /attendance/offline-sync {punches: [{client_uuid, kind: in|out, captured_at, latitude, longitude, accuracy, is_mock_location, selfie_id?, liveness_passed?}]}` (≤ 50) → per-item result (`created|duplicate|rejected` + reason). Rules: captured_at ≤ now + 2 min and ≥ now − `attendance.offline_max_hours` (default 12); idempotent by client_uuid; same geofence/shift attribution as live punches (reuse the mark/punch-out internals — extract a service function rather than duplicating); `is_offline=true` + `review_flag='offline'`; ordering: process in captured_at order; punch-out without open punch → rejected.
- Tests: selfie validation/size/type; selfie_required; liveness flag; offline sync idempotency, window, ordering, attribution parity with live punch, flags; Flagged Review includes offline/liveness rows.
- [ ] TDD → migration → commit `feat(attendance): selfie punch with liveness flag and offline punch sync`.

### Task 3: Backend — live location tracking

- Models: `tracking_policy` (singleton-ish rows per role: `role_id`, `enabled`, `interval_seconds` default 300, `distance_filter_m` default 100), `tracking_override` (`user_id`, `enabled`), `tracking_consent` (`user_id`, `consented_at`, `revoked_at`, `app_version`), `location_ping` (`user_id`, `captured_at`, `lat`, `lng`, `accuracy`, `speed`, `battery`, `work_date`, `received_at`; index (user_id, captured_at)).
- `GET /tracking/my-status` → {required: bool (policy/override), consented, window: {start,end}|null (today's rostered shift ±30 min using effective shift incl. overnight), interval_seconds, distance_filter_m}. `POST /tracking/consent` / `DELETE /tracking/consent`. `POST /tracking/pings {pings: [...] ≤ 200}` → accepts only pings within the shift window, with consent and enabled policy; others dropped with counts; dedupe by (user, captured_at).
- Scheduler views: `GET /tracking/field-now?department=` (manageable_subset; latest ping per user within last 15 min + status from live board), `GET /tracking/trail?user_id&date` (scope; ordered pings), web + mobile.
- Geofence exit alert: on ping ingest, if the user's assigned/matched geofence (reuse geofence models — find how punches match fences) is known and the ping is outside by > accuracy + 100 m for 2 consecutive pings during the shift → notify the user's schedulers once per shift (throttled; `tracking_alert` row unique (user, work_date, kind)).
- Retention job `location_ping_purge` daily: delete pings older than `tracking.retention_days` (default 30).
- HR admin endpoints for policy/overrides (permission `hr employee write`); audit changes; employee can view own trail.
- Tests: window enforcement (incl. overnight), consent gating, policy/override precedence, dedupe, scope on views, geofence exit alert once, purge job.
- [ ] TDD → migration → commit `feat(tracking): consent-based live location during rostered shifts`.

### Task 4: Web — field team page + tracking admin

- `frontend/src/components/field-team.tsx` (sidebar "Field Team", roles like roster planner): map of latest positions (Leaflet via existing deps? check `frontend/package.json`; if no map lib, add `leaflet` + `react-leaflet` pinned versions with OSM tiles), list with last-seen, click → trail for today. HR "Location tracking" settings card (per-role enable/interval/distance; per-employee overrides; consent status list). NO Tailwind build rules apply; tsc ≤ 164.
- [ ] Implement → browser verify (Playwright helpers in the e2e_ui scratchpad) → commit `feat(web): field team map and tracking settings`.

### Task 5: Mobile scaffold + white-label + API client

- `npx create-expo-app@latest mobile --template` (TypeScript, expo-router). Structure: `app/(auth)/login.tsx`, `app/(tabs)/...`, `src/api/client.ts` (axios, base URL from tenant config + platform override for Android emulator, bearer + refresh-on-401 via `/auth/refresh` with single-flight, error envelope → `ApiError` with `message`), `src/auth/` (expo-secure-store tokens, `useAuth`), `src/theme/` (tenant colors → theme tokens; light/dark), `src/i18n` stub, react-query provider, error boundary.
- White-label: `tenants/dev/` (localhost API) and `tenants/acme/` (example) with `tenant.json`, icon, splash; `app.config.ts` reads `process.env.TENANT` (default dev) → name, slug, scheme, bundle ids, icon, splash, colors, extra.apiBaseUrl, feature flags; `scripts/build-tenant.sh` (validates tenant, runs `expo prebuild --clean` with TENANT, then `eas build --local` or `expo run:*`); README section.
- Quality gates: ESLint (expo config), `tsc --noEmit`, Jest + RNTL with a sample test, `npm run check` aggregating them.
- Verify: `expo-doctor` clean; iOS simulator boots to login screen (screenshot).
- [ ] Implement → commit `feat(mobile): expo white-label scaffold, API client and auth storage`.

### Task 6: Mobile — auth, home, navigation, approvals

- Login (email/password → tokens), logout, session restore, change password link-out. Tabs: Home, Punch, Leave, Schedule, More (Approvals tab when user has approvals — reuse `/approvals/inbox` + `/approval-chains/my-queue` like `frontend/src/mobile/screens/mobile-approvals.tsx`). Home: today's shift, punch status, pending requests, active broadcasts banner. Approvals: list (overdue, acting-for badges), detail, approve/reject (+ comment), bulk select.
- Attendance gate parity: until punched in, non-admin users see the Punch screen first (same rule as web: `verify_attendance`); screens that call gated endpoints handle 403 gracefully.
- Tests: RNTL for login form, approvals list/actions (mock API); Maestro flow: login → home → approvals (as pm@gmail.com).
- [ ] Implement → commit `feat(mobile): auth, home, tabs and approvals`.

### Task 7: Mobile — punch: geofence, selfie liveness, offline queue

- Punch screen: location permission flow, current position + accuracy, mock-location detection where available, punch in/out via `/attendance/mark` / punch-out; geofence feedback from server response.
- Selfie: front camera capture with on-device liveness challenge (face detection; require a blink or head turn within N seconds; works on device; on simulator allow a dev-only bypass flag that marks `liveness_passed=null`), upload to `/attendance/selfie` then punch with `selfie_id`.
- Offline queue: if network fails, persist the punch (client_uuid, captured_at, coords, selfie file path) in expo-sqlite; background/foreground sync to `/attendance/offline-sync` with exponential backoff; UI shows "Pending sync (N)"; results surfaced (rejected reasons).
- Running-late button for today's shift when not punched (`/roster/my/running-late`).
- Tests: queue persistence + sync logic (unit, mocked network), punch screen states (RNTL); Maestro: punch in on simulator with simulated location (`xcrun simctl location booted set <lat>,<lng>`).
- [ ] Implement → commit `feat(mobile): geofence + selfie punch with offline queue`.

### Task 8: Mobile — leave, payslips, documents

- Leave: balances, apply (types, half-day, emergency toggle with back-date window + helper text), history with proof-due badge + upload proof (camera/document picker → `/leave/attachments` → `/leave/{id}/proof`), cancel.
- Payslips: list (`/payroll/my-payslips`), download PDF (`/payroll/payslips/{id}/download`) → share/open; Form 16 / documents if endpoints exist (grep backend for form16 / employee documents self endpoints) — list + download.
- Tests: RNTL leave form validation; Maestro: apply leave + view payslip list.
- [ ] Implement → commit `feat(mobile): leave, payslips and documents`.

### Task 9: Mobile — schedule self-service

- My schedule (week strip + month list, UTC-labelled times, transport flag, on-call days, acknowledgement banner for emergency changes), availability, swaps (propose/accept/decline/cancel), open shifts (claim/withdraw), give-away, calendar feed link (share URL), running-late. Reuse API shapes from `frontend/src/components/my-schedule/my-schedule-api.ts` (port types to `mobile/src/api/types.ts`).
- Tests: RNTL for swap dialog + open shift claim; Maestro: schedule tabs.
- [ ] Implement → commit `feat(mobile): schedule, swaps, open shifts, availability`.

### Task 10: Mobile — push notifications + emergency broadcast

- Register for push after login (expo-notifications; permission prompt with rationale), send token to `POST /devices`, unregister on logout. Notification categories with action buttons (approval approve/reject, open shift claim, broadcast safe/need help, acknowledge) → call `POST /notifications/actions` (works from background on iOS/Android via notification response listener); tapping a notification deep-links to the resource (expo-router linking).
- In-app emergency broadcast: poll `/broadcasts/my` (and on push), critical = full-screen modal (can't dismiss without action), mark safe / need help + note, acknowledge.
- Tests: action routing unit tests; Maestro: broadcast modal flow (seed a broadcast via API for a test department).
- [ ] Implement → commit `feat(mobile): push notifications with actions and emergency broadcast`.

### Task 11: Mobile — live location tracking + field team

- Consent screen (explains: only during rostered shifts, what is collected, retention 30 days, revoke anytime) → `POST /tracking/consent`; settings toggle to revoke. Background tracking via expo-location `startLocationUpdatesAsync` + TaskManager **only while `my-status.window` is active** (start/stop on app foreground, on a scheduled check, and when the window ends); battery-aware (`Accuracy.Balanced`, `distanceInterval` from policy, `deferredUpdatesInterval`), persistent queue + batch upload to `/tracking/pings`; Android foreground-service notification text "Shift location sharing on".
- Scheduler "Field team" screen (map with latest positions + trail) for users with roster scope.
- Tests: window start/stop logic (unit, mocked clock), queue batching; Maestro: consent screen; simulator location ping appears in field-now (API check).
- [ ] Implement → commit `feat(mobile): consent-based shift location tracking and field team map`.

### Task 12: Phase verification (controller)

1. Backend full suite (only the 2 known `test_hr_employees` failures), migration chain, web tsc ≤ 164.
2. Mobile: `npm run check` (lint, tsc, jest) green; `expo-doctor` clean; iOS simulator build + full Maestro suite (login, punch incl. offline queue, leave, schedule, approvals, broadcast, tracking consent) with screenshots reviewed; Android emulator smoke (login + punch) if the emulator boots.
3. API E2E agent for the new backend endpoints + browser agent for the web field-team/tracking pages; fix findings; re-run.
4. Final whole-branch review → fix → memory update → continue to Phase 4.
