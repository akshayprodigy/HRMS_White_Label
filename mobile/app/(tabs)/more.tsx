import { useAuth } from '../../src/auth/AuthProvider';
import { Button, Card, Screen, Text } from '../../src/components/ui';
import { t } from '../../src/i18n';

export default function MoreTab() {
  const { user, logout } = useAuth();
  return (
    <Screen>
      <Card style={{ gap: 12 }}>
        <Text weight="600" size={18}>More</Text>
        <Text muted>{user?.email}</Text>
        <Button testID="logout" variant="secondary" title={t('common.signOut')} onPress={logout} />
      </Card>
    </Screen>
  );
}
