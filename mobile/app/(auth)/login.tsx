import { KeyboardAvoidingView, Platform, View } from 'react-native';
import { useAuth } from '../../src/auth/AuthProvider';
import { Card, Screen, Text } from '../../src/components/ui';
import { LoginForm } from '../../src/features/auth/LoginForm';
import { getTenant } from '../../src/config/tenant';
import { t } from '../../src/i18n';

export default function LoginScreen() {
  const { login } = useAuth();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {/* scrollable + keyboardShouldPersistTaps="handled" (Screen scroll); form sits in the top third */}
      <Screen scroll style={{ flexGrow: 1, paddingTop: 48 }}>
        <View style={{ marginBottom: 24 }}>
          <Text size={28} weight="700">{getTenant().name}</Text>
          <Text muted>{t('login.title')}</Text>
        </View>
        <Card>
          <LoginForm onSubmit={login} />
        </Card>
      </Screen>
    </KeyboardAvoidingView>
  );
}
