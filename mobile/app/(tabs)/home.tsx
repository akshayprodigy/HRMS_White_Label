import { useAuth } from '../../src/auth/AuthProvider';
import { Card, Screen, Text } from '../../src/components/ui';

export default function HomeTab() {
  const { user } = useAuth();
  return (
    <Screen>
      <Card>
        <Text weight="600" size={18}>Home</Text>
        <Text muted testID="home-user">{user?.full_name || user?.email}</Text>
      </Card>
    </Screen>
  );
}
