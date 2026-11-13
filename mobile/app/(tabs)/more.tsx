import { Alert } from 'react-native';
import { useAuth } from '../../src/auth/AuthProvider';
import { Button, Card, Screen, Text } from '../../src/components/ui';
import { usePunchQueue } from '../../src/features/punch/hooks';
import { t } from '../../src/i18n';

export default function MoreTab() {
  const { user, logout } = useAuth();
  const { items } = usePunchQueue();
  const signOut = () => {
    if (!items.length) return void logout();
    const n = items.length;
    Alert.alert(
      t('common.signOut'),
      `${n} punch${n === 1 ? '' : 'es'} not yet synced. They stay on this device and are sent the next time you sign in, but the server can't accept punches older than 12 hours, so sync them first if you can.`,
      [{ text: 'Cancel', style: 'cancel' }, { text: t('common.signOut'), style: 'destructive', onPress: () => void logout() }],
    );
  };
  return (
    <Screen>
      <Card style={{ gap: 12 }}>
        <Text weight="600" size={18}>More</Text>
        <Text muted>{user?.email}</Text>
        <Button testID="logout" variant="secondary" title={t('common.signOut')} onPress={signOut} />
      </Card>
    </Screen>
  );
}
