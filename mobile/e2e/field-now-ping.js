// Maestro runScript (GraalJS): HR reads /tracking/field-now and asserts THE employee (matched by user id) has a fresh ping.
// Env (maestro test -e KEY=value): API_BASE (default http://localhost:8005/api/v1), HR_EMAIL, HR_PASSWORD (HR needs roster
// scope over the employee), EMPLOYEE_EMAIL (default employee@gmail.com), EMPLOYEE_PASSWORD (default test@12345).
var base = typeof API_BASE !== 'undefined' && API_BASE ? API_BASE : 'http://localhost:8005/api/v1';
var empEmail = typeof EMPLOYEE_EMAIL !== 'undefined' && EMPLOYEE_EMAIL ? EMPLOYEE_EMAIL : 'employee@gmail.com';
var empPass = typeof EMPLOYEE_PASSWORD !== 'undefined' && EMPLOYEE_PASSWORD ? EMPLOYEE_PASSWORD : 'test@12345';
if (typeof HR_EMAIL === 'undefined' || typeof HR_PASSWORD === 'undefined') throw new Error('Pass -e HR_EMAIL=... -e HR_PASSWORD=...');

// /auth/login is OAuth2PasswordRequestForm: form-urlencoded username/password.
function login(email, password) {
  var r = http.post(base + '/auth/login', {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'username=' + encodeURIComponent(email) + '&password=' + encodeURIComponent(password),
  });
  if (!r.ok) throw new Error('login failed for ' + email + ': ' + r.status);
  return json(r.body).access_token;
}

var me = http.get(base + '/auth/me', { headers: { Authorization: 'Bearer ' + login(empEmail, empPass) } });
if (!me.ok) throw new Error('/auth/me failed: ' + me.status);
var empId = json(me.body).id;

var res = http.get(base + '/tracking/field-now', { headers: { Authorization: 'Bearer ' + login(HR_EMAIL, HR_PASSWORD) } });
if (!res.ok) throw new Error('field-now failed: ' + res.status + ' ' + res.body);
var rows = json(res.body).rows || [];
var row = rows.filter(function (r) { return r.user_id === empId; })[0];
if (!row) throw new Error('Employee ' + empId + ' is not in field-now (not tracked / no consent / outside scope)');
if (!row.ping) throw new Error('Employee ' + empId + ' is tracked but has no ping');
var cap = row.ping.captured_at;
var capMs = Date.parse(/([zZ]|[+-]\d\d:?\d\d)$/.test(cap) ? cap : cap + 'Z');
var ageMin = (Date.now() - capMs) / 60000;
if (isNaN(ageMin) || ageMin > 10 || ageMin < -2) throw new Error('Ping is not fresh: captured_at=' + cap + ' (' + ageMin.toFixed(1) + ' min old)');
output.pingLat = row.ping.lat;
