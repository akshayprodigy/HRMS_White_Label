import React from 'react';
import { Text, View } from 'react-native';
import { Button } from './ui';
import { ThemeProvider, useTheme } from '../theme';
import { t } from '../i18n';

type State = { error: Error | null };

function Fallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, justifyContent: 'center', padding: 24, gap: 16, backgroundColor: colors.background }}>
      <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text }}>{t('common.somethingWrong')}</Text>
      {__DEV__ ? <Text style={{ color: colors.mutedText }}>{error.message}</Text> : null}
      <Button title={t('common.tryAgain')} onPress={onRetry} />
    </View>
  );
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error('Unhandled UI error', error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <ThemeProvider>
        <Fallback error={this.state.error} onRetry={() => this.setState({ error: null })} />
      </ThemeProvider>
    );
  }
}
