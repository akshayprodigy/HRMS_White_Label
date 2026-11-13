import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { LoginForm } from '../src/features/auth/LoginForm';
import { ThemeProvider } from '../src/theme';
import { validateLogin } from '../src/auth/loginValidation';
import dev from '../tenants/dev/tenant.json';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));

const renderForm = (onSubmit: jest.Mock) =>
  render(
    <ThemeProvider>
      <LoginForm onSubmit={onSubmit} />
    </ThemeProvider>,
  );

describe('validateLogin', () => {
  it('requires email and password and checks email shape', () => {
    expect(validateLogin('', '')).toEqual({ email: 'Enter your email', password: 'Enter your password' });
    expect(validateLogin('abc', 'x').email).toBe('Enter a valid email address');
    expect(validateLogin(' a@b.co ', 'x')).toEqual({});
  });
});

describe('LoginForm', () => {
  it('shows validation errors and does not submit invalid input', async () => {
    const onSubmit = jest.fn();
    await renderForm(onSubmit);
    await fireEvent.press(screen.getByTestId('login-submit'));
    expect(screen.getByText('Enter your email')).toBeTruthy();
    expect(screen.getByText('Enter your password')).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });
  it('submits trimmed email + password and shows server errors', async () => {
    const onSubmit = jest.fn().mockRejectedValue(new Error('Incorrect email or password'));
    await renderForm(onSubmit);
    await fireEvent.changeText(screen.getByTestId('login-email'), ' employee@gmail.com ');
    await fireEvent.changeText(screen.getByTestId('login-password'), 'test@12345');
    await fireEvent.press(screen.getByTestId('login-submit'));
    await waitFor(() => expect(screen.getByTestId('login-error')).toBeTruthy());
    expect(onSubmit).toHaveBeenCalledWith('employee@gmail.com', 'test@12345');
    expect(screen.getByText('Incorrect email or password')).toBeTruthy();
    expect(dev.name).toBe('HRMS Dev');
  });
});
