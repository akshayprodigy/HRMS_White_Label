import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text as RNText,
  TextInput as RNTextInput,
  View,
  type RefreshControlProps,
  type StyleProp,
  type TextInputProps,
  type TextProps,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../theme';

export function Screen({ children, scroll = false, style, refreshControl }: { children: React.ReactNode; scroll?: boolean; style?: StyleProp<ViewStyle>; refreshControl?: React.ReactElement<RefreshControlProps> }) {
  const { colors, spacing } = useTheme();
  const insets = useSafeAreaInsets();
  const base: ViewStyle = { flex: 1, backgroundColor: colors.background };
  const pad: ViewStyle = { padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.md };
  if (scroll) {
    return (
      <ScrollView style={base} contentContainerStyle={[pad, style]} keyboardShouldPersistTaps="handled" refreshControl={refreshControl}>
        {children}
      </ScrollView>
    );
  }
  return <View style={[base, pad, style]}>{children}</View>;
}

export function Text({ muted, weight, size = 16, style, ...rest }: TextProps & { muted?: boolean; weight?: 'normal' | '600' | '700'; size?: number }) {
  const { colors } = useTheme();
  return <RNText {...rest} style={[{ color: muted ? colors.mutedText : colors.text, fontSize: size, fontWeight: weight }, style]} />;
}

export function Card({ children, style, testID, accessibilityRole, accessibilityLiveRegion }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; testID?: string; accessibilityRole?: 'alert' | 'summary'; accessibilityLiveRegion?: 'polite' | 'assertive' }) {
  const { colors, spacing, radius } = useTheme();
  return (
    <View testID={testID} accessibilityRole={accessibilityRole} accessibilityLiveRegion={accessibilityLiveRegion} style={[{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius, padding: spacing.md }, style]}>
      {children}
    </View>
  );
}

export function Button({ title, onPress, loading, disabled, variant = 'primary', testID }: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary';
  testID?: string;
}) {
  const { colors, radius } = useTheme();
  const primary = variant === 'primary';
  const off = disabled || loading;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => ({
        backgroundColor: primary ? colors.primary : 'transparent',
        borderColor: colors.primary,
        borderWidth: 1,
        borderRadius: radius,
        paddingVertical: 14,
        alignItems: 'center',
        opacity: off ? 0.5 : pressed ? 0.85 : 1,
      })}
    >
      {loading ? (
        <ActivityIndicator color={primary ? colors.primaryText : colors.primary} />
      ) : (
        <RNText style={{ color: primary ? colors.primaryText : colors.primary, fontSize: 16, fontWeight: '600' }}>{title}</RNText>
      )}
    </Pressable>
  );
}

export function TextInput({ label, error, ...rest }: TextInputProps & { label: string; error?: string | null; ref?: React.ComponentProps<typeof RNTextInput>['ref'] }) {
  const { colors, radius, spacing } = useTheme();
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text size={14} weight="600" style={{ marginBottom: spacing.xs }}>{label}</Text>
      <RNTextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.mutedText}
        {...rest}
        style={{
          color: colors.text,
          backgroundColor: colors.surface,
          borderColor: error ? colors.danger : colors.border,
          borderWidth: 1,
          borderRadius: radius,
          paddingHorizontal: 14,
          paddingVertical: 12,
          fontSize: 16,
        }}
      />
      {error ? (
        <Text size={13} accessibilityRole="alert" accessibilityLiveRegion="polite" style={{ color: colors.danger, marginTop: spacing.xs }}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

export function Chip({ label, selected, onPress, testID }: { label: string; selected: boolean; onPress: () => void; testID?: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={{ paddingVertical: 8, paddingHorizontal: 14, borderRadius: 20, borderWidth: 1, borderColor: colors.primary, backgroundColor: selected ? colors.primary : 'transparent' }}
    >
      <Text size={14} weight="600" style={{ color: selected ? colors.primaryText : colors.primary }}>{label}</Text>
    </Pressable>
  );
}
