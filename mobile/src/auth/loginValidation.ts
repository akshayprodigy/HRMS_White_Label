import { t } from '../i18n';

export type LoginErrors = { email?: string; password?: string };

export function validateLogin(email: string, password: string): LoginErrors {
  const errors: LoginErrors = {};
  const e = email.trim();
  if (!e) errors.email = t('login.emailRequired');
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) errors.email = t('login.emailInvalid');
  if (!password) errors.password = t('login.passwordRequired');
  return errors;
}
