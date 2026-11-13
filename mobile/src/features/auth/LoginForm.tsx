import React, { useRef, useState } from 'react';
import { View } from 'react-native';
import { Button, Text, TextInput } from '../../components/ui';
import { validateLogin, type LoginErrors } from '../../auth/loginValidation';
import { t } from '../../i18n';
import { useTheme } from '../../theme';

export function LoginForm({ onSubmit }: { onSubmit: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<LoginErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef<{ focus: () => void } | null>(null);
  const { colors } = useTheme();

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
        onChangeText={(v) => {
          setEmail(v);
          setErrors((e) => ({ ...e, email: undefined }));
          setServerError(null);
        }}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="username"
        autoComplete="email"
        returnKeyType="next"
        onSubmitEditing={() => passwordRef.current?.focus()}
        submitBehavior="submit"
        error={errors.email}
      />
      <TextInput
        testID="login-password"
        label={t('login.password')}
        value={password}
        onChangeText={(v) => {
          setPassword(v);
          setErrors((e) => ({ ...e, password: undefined }));
          setServerError(null);
        }}
        secureTextEntry
        ref={(r) => {
          passwordRef.current = r;
        }}
        textContentType="password"
        autoComplete="current-password"
        returnKeyType="go"
        error={errors.password}
        onSubmitEditing={submit}
      />
      {serverError ? <Text testID="login-error" accessibilityRole="alert" accessibilityLiveRegion="polite" style={{ marginBottom: 12, color: colors.danger }}>{serverError}</Text> : null}
      <Button testID="login-submit" title={t('login.submit')} onPress={submit} loading={busy} />
    </View>
  );
}
