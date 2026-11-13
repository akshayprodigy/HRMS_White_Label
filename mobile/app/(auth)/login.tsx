import { View } from 'react-native';
import { useAuth } from '../../src/auth/AuthProvider';
import { Card, Screen, Text } from '../../src/components/ui';
import { LoginForm } from '../../src/features/auth/LoginForm';
import { getTenant } from '../../src/config/tenant';
import { t } from '../../src/i18n';

export default function LoginScreen() {
  const { login } = useAuth();
  return (
    <Screen scroll style={{ flexGrow: 1, justifyContent: 'center' }}>
      <View style={{ marginBottom: 24 }}>
        <Text size={28} weight="700">{getTenant().name}</Text>
        <Text muted>{t('login.title')}</Text>
      </View>
      <Card>
        <LoginForm onSubmit={login} />
      </Card>
    </Screen>
  );
}
