import { useState } from 'react';
import { RefreshControl, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { Card, Chip, Screen, Text } from '../../components/ui';
import { AvailabilityPanel } from './AvailabilityPanel';
import { MyShifts } from './MyShifts';
import { OpenShiftsPanel } from './OpenShiftsPanel';
import { SwapsPanel } from './SwapsPanel';

type Section = 'shifts' | 'swaps' | 'open' | 'availability';
const SECTIONS: { id: Section; label: string }[] = [
  { id: 'shifts', label: 'My shifts' },
  { id: 'swaps', label: 'Swaps' },
  { id: 'open', label: 'Open shifts' },
  { id: 'availability', label: 'Availability' },
];

export function ScheduleScreen({ initialSection }: { initialSection?: string }) {
  const qc = useQueryClient();
  const [section, setSection] = useState<Section>(SECTIONS.some((s) => s.id === initialSection) ? (initialSection as Section) : 'shifts');
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Lifted here so the once-shown feed URL survives sub-tab switches and dialogs.
  const [feedUrl, setFeedUrl] = useState<string | null>(null);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await qc.invalidateQueries({ queryKey: ['schedule'] });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />} style={{ gap: 12 }}>
      <Text weight="700" size={20}>Schedule</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {SECTIONS.map((s) => (
          <Chip key={s.id} testID={`sched-tab-${s.id}`} label={s.label} selected={section === s.id} onPress={() => { setSection(s.id); setNotice(null); }} />
        ))}
      </View>
      {notice ? <Card><Text testID="sched-notice" accessibilityLiveRegion="polite">{notice}</Text></Card> : null}
      {section === 'shifts' ? (
        <MyShifts
          feedUrl={feedUrl}
          onFeedUrl={setFeedUrl}
          onDone={(what) => {
            setNotice(what === 'swap' ? 'Swap requested. Your colleague has been notified.' : 'Give-away requested and sent to your approver.');
            setSection('swaps');
          }}
        />
      ) : null}
      {section === 'swaps' ? <SwapsPanel /> : null}
      {section === 'open' ? <OpenShiftsPanel /> : null}
      {section === 'availability' ? <AvailabilityPanel /> : null}
    </Screen>
  );
}
