#!/usr/bin/env node
// Smoke test against a running backend: login (form-urlencoded) -> /auth/me -> /auth/refresh.
// Usage: API=http://localhost:8005/api/v1 node scripts/smoke-api.js [email] [password]
const base = process.env.API || 'http://localhost:8005/api/v1';
const [email = 'employee@gmail.com', password = 'test@12345'] = process.argv.slice(2);
(async () => {
  const login = await fetch(`${base}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  });
  const tok = await login.json();
  if (!login.ok) throw new Error(`login ${login.status} ${JSON.stringify(tok)}`);
  const me = await (await fetch(`${base}/auth/me`, { headers: { Authorization: `Bearer ${tok.access_token}` } })).json();
  const ref = await fetch(`${base}/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: tok.refresh_token }),
  });
  console.log({ login: login.status, token_type: tok.token_type, me: me.email, refresh: ref.status });
})().catch((e) => { console.error(e); process.exit(1); });
