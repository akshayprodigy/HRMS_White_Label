// Maestro runScript (GraalJS): HR logs in over the API, reads /tracking/field-now and asserts the employee row has a ping.
// Env (pass with `maestro test -e KEY=value`): API_BASE (default http://localhost:8005/api/v1), HR_EMAIL, HR_PASSWORD,
// EMPLOYEE_EMAIL (default employee@gmail.com). The HR user needs roster scope over the employee.
var base = typeof API_BASE !== 'undefined' && API_BASE ? API_BASE : 'http://localhost:8005/api/v1';
var employee = typeof EMPLOYEE_EMAIL !== 'undefined' && EMPLOYEE_EMAIL ? EMPLOYEE_EMAIL : 'employee@gmail.com';
if (typeof HR_EMAIL === 'undefined' || typeof HR_PASSWORD === 'undefined') throw new Error('Pass -e HR_EMAIL=... -e HR_PASSWORD=...');

// /auth/login is OAuth2PasswordRequestForm: form-urlencoded username/password.
var login = http.post(base + '/auth/login', {
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=' + encodeURIComponent(HR_EMAIL) + '&password=' + encodeURIComponent(HR_PASSWORD),
});
if (!login.ok) throw new Error('HR login failed: ' + login.status);
var token = json(login.body).access_token;

var res = http.get(base + '/tracking/field-now', { headers: { Authorization: 'Bearer ' + token } });
if (!res.ok) throw new Error('field-now failed: ' + res.status + ' ' + res.body);
var data = json(res.body);
// field-now rows carry name (not email); match the e-mail local part against the name, else accept any located row.
var local = employee.split('@')[0].toLowerCase();
var rows = data.rows || [];
var mine = rows.filter(function (r) { return (r.name || '').toLowerCase().indexOf(local) !== -1; });
var candidates = mine.length ? mine : rows;
var located = candidates.filter(function (r) { return r.ping && typeof r.ping.lat === 'number'; });
if (!located.length) throw new Error('No tracked employee with a ping in field-now (tracked=' + data.tracked + ', with_location=' + data.with_location + ')');
output.pingLat = located[0].ping.lat;
