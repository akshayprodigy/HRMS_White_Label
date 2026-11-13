// i18n stub: single English catalogue; swap for a real library when locales are added.
const en = {
  'login.title': 'Sign in',
  'login.email': 'Email',
  'login.password': 'Password',
  'login.submit': 'Sign in',
  'login.emailRequired': 'Enter your email',
  'login.emailInvalid': 'Enter a valid email address',
  'login.passwordRequired': 'Enter your password',
  'common.comingSoon': 'Coming soon',
  'common.signOut': 'Sign out',
  'common.somethingWrong': 'Something went wrong',
  'common.tryAgain': 'Try again',
} as const;

export type MessageKey = keyof typeof en;
export function t(key: MessageKey): string {
  return en[key];
}
