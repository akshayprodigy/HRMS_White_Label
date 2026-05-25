import type { UserRole } from '../types/erp';

export const normalizeRoleName = (roleName: string): string =>
  (roleName || '')
    .trim()
    .toLowerCase()
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ');

export const pickPrimaryRole = ({
  isSuperuser,
  roleNames,
}: {
  isSuperuser: boolean;
  roleNames: string[];
}): UserRole => {
  if (isSuperuser) return 'super admin';

  const roles = new Set(roleNames.map(normalizeRoleName));

  // Ordered by privilege/impact in the UI.
  const precedence: Array<{ when: boolean; role: UserRole }> = [
    { when: roles.has('super admin'), role: 'super admin' },
    { when: roles.has('admin'), role: 'admin' },
    { when: roles.has('ceo'), role: 'ceo' },
    { when: roles.has('coo'), role: 'coo' },
    { when: roles.has('dop'), role: 'dop' },
    { when: roles.has('hr'), role: 'hr' },
    { when: roles.has('recruiter'), role: 'recruiter' },
    { when: roles.has('dept head'), role: 'dept head' },
    { when: roles.has('bd manager'), role: 'bd manager' },
    { when: roles.has('business developer') || roles.has('bd'), role: 'bd' },
    { when: roles.has('pm'), role: 'pm' },
    { when: roles.has('client manager'), role: 'client manager' },
    { when: roles.has('employee'), role: 'employee' },
  ];

  for (const p of precedence) {
    if (p.when) return p.role;
  }

  return 'employee';
};
