import { renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Slot, Stack } from 'expo-router';
import { Text } from 'react-native';
import { AuthRedirect } from '../src/components/AuthRedirect';
import { setPendingRoute } from '../src/auth/redirect';

let mockUser: { id: number } | null = null;
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: mockUser }) }));

// Same guard structure as app/_layout.tsx, with trivial screens.
function tree() {
  return {
    _layout: function Root() {
      return (
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Protected guard={!!mockUser}>
            <Stack.Screen name="(tabs)" />
          </Stack.Protected>
          <Stack.Protected guard={!mockUser}>
            <Stack.Screen name="(auth)" />
          </Stack.Protected>
        </Stack>
      );
    },
    index: () => <AuthRedirect path="/" />,
    '+not-found': () => <AuthRedirect />,
    '(auth)/_layout': () => <Slot />,
    '(tabs)/_layout': () => <Slot />,
    '(auth)/login': () => <Text>LOGIN SCREEN</Text>,
    '(tabs)/home': () => <Text>HOME SCREEN</Text>,
    '(tabs)/leave': () => <Text>LEAVE SCREEN</Text>,
  };
}

beforeEach(() => setPendingRoute(null));

describe('routing', () => {
  it('cold launch logged out resolves "/" to login', async () => {
    mockUser = null;
    await renderRouter(tree(), { initialUrl: '/' });
    await waitFor(() => expect(screen.getByText('LOGIN SCREEN')).toBeTruthy());
  });
  it('cold launch logged in resolves "/" to home', async () => {
    mockUser = { id: 1 };
    await renderRouter(tree(), { initialUrl: '/' });
    await waitFor(() => expect(screen.getByText('HOME SCREEN')).toBeTruthy());
  });
  it('deep link to a protected route while logged out lands on login', async () => {
    mockUser = null;
    await renderRouter(tree(), { initialUrl: '/leave' });
    await waitFor(() => expect(screen.getByText('LOGIN SCREEN')).toBeTruthy());
  });
});
