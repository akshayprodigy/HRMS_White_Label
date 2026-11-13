import React from 'react';
import { Text, View } from 'react-native';
import { Button } from './ui';
import { ThemeProvider } from '../theme';
import { t } from '../i18n';

type State = { error: Error | null };

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
        <View style={{ flex: 1, justifyContent: 'center', padding: 24, gap: 16 }}>
          <Text style={{ fontSize: 18, fontWeight: '600' }}>{t('common.somethingWrong')}</Text>
          <Text>{this.state.error.message}</Text>
          <Button title={t('common.tryAgain')} onPress={() => this.setState({ error: null })} />
        </View>
      </ThemeProvider>
    );
  }
}
