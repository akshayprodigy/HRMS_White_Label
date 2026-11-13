import { Ionicons } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import { useEffect, useRef } from 'react';
import { useApprovalsAccess } from '../../src/features/approvals/hooks';
import { useAttendanceGate } from '../../src/features/attendance/gate';
import { useTheme } from '../../src/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

const TABS: { name: string; title: string; icon: IconName }[] = [
  { name: 'home', title: 'Home', icon: 'home-outline' },
  { name: 'punch', title: 'Punch', icon: 'finger-print-outline' },
  { name: 'leave', title: 'Leave', icon: 'calendar-outline' },
  { name: 'schedule', title: 'Schedule', icon: 'time-outline' },
  { name: 'more', title: 'More', icon: 'ellipsis-horizontal' },
];

export default function TabsLayout() {
  const { colors } = useTheme();
  const router = useRouter();
  const { gated } = useAttendanceGate();
  const approvals = useApprovalsAccess();

  // Gate parity: a non-exempt user who hasn't punched in lands on Punch once; navigation stays free afterwards.
  const redirected = useRef(false);
  useEffect(() => {
    if (gated && !redirected.current) {
      redirected.current = true;
      router.replace('/punch');
    }
  }, [gated, router]);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.mutedText,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{ title: t.title, tabBarIcon: ({ color, size }) => <Ionicons name={t.icon} color={color as string} size={size} /> }}
        />
      ))}
      {/* Hidden (href: null) unless the user is an approver by role/permission or has a non-empty queue. */}
      <Tabs.Screen
        name="approvals"
        options={{
          title: 'Approvals',
          href: approvals.show ? undefined : null,
          tabBarIcon: ({ color, size }) => <Ionicons name="checkmark-done-outline" color={color as string} size={size} />,
        }}
      />
    </Tabs>
  );
}
