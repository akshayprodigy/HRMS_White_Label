import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';

const TABS = [
  { name: 'home', title: 'Home' },
  { name: 'punch', title: 'Punch' },
  { name: 'leave', title: 'Leave' },
  { name: 'schedule', title: 'Schedule' },
  { name: 'more', title: 'More' },
] as const;

export default function TabsLayout() {
  const { colors } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTintColor: colors.text,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.mutedText,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen key={t.name} name={t.name} options={{ title: t.title, tabBarIcon: () => null, tabBarIconStyle: { display: 'none' } }} />
      ))}
    </Tabs>
  );
}
