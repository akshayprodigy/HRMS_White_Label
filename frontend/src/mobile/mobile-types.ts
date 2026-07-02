export type MobileTab =
  | 'home'
  | 'attendance'
  | 'leave'
  | 'payslip'
  | 'approvals';

export const APPROVER_ROLES: ReadonlyArray<string> = [
  'hr',
  'pm',
  'admin',
  'super admin',
  'dop',
  'coo',
  'bd manager',
  'dept head',
  'ceo',
  'client manager',
];
