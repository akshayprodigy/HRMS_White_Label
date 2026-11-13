import React, { useState } from 'react';
import { View } from 'react-native';
import { Button, Text, TextInput } from '../../components/ui';
import { validateLogin, type LoginErrors } from '../../auth/loginValidation';
import { t } from '../../i18n';

export function LoginForm({ onSubmit }: { onSubmit: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<LoginErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const v = validateLogin(email, password);
    setErrors(v);
    setServerError(null);
    if (v.email || v.password) return;
    setBusy(true);
    try {
      await onSubmit(email.trim(), password);
    } catch (e) {
      setServerError(e instanceof Error ? e.message : t('common.somethingWrong'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View>
      <TextInput
        testID="login-email"
        label={t('login.email')}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="username"
        error={errors.email}
      />
      <TextInput
        testID="login-password"
        label={t('login.password')}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        textContentType="password"
        error={errors.password}
        onSubmitEditing={submit}
      />
      {serverError ? <Text testID="login-error" style={{ marginBottom: 12, color: '#DC2626' }}>{serverError}</Text> : null}
      <Button testID="login-submit" title={t('login.submit')} onPress={submit} loading={busy} />
    </View>
  );
}
