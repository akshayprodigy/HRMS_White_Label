import { useRef, useState } from 'react';
import { Share, View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { useDeleteFeed, useFeedStatus, useGuardedRun, useRotateFeed } from './hooks';
import { ConfirmAction, ErrorText } from './ui';

/** Calendar subscription link. The server shows the URL once (it stores only a hash), so it is kept in memory only. */
export function CalendarFeedCard() {
  const status = useFeedStatus();
  const rotate = useRotateFeed();
  const del = useDeleteFeed();
  const { run, error, isBusy } = useGuardedRun();
  const [url, setUrl] = useState<string | null>(null);
  const [shareErr, setShareErr] = useState<string | null>(null);
  const sharing = useRef(false);
  const active = status.data?.active;

  const share = async () => {
    if (!url || sharing.current) return;
    sharing.current = true;
    setShareErr(null);
    try {
      await Share.share({ message: url });
    } catch {
      setShareErr('Could not open the share sheet. Copy the link above instead.');
    } finally {
      sharing.current = false;
    }
  };

  return (
    <Card testID="feed-card" style={{ gap: 8 }}>
      <Text weight="700">Calendar feed</Text>
      <Text muted size={13}>Subscribe to your published roster shifts from Google, Outlook or Apple Calendar. Shifts that come only from a default assignment are not included.</Text>
      {status.data ? <Text testID="feed-status" size={14} weight="600">{active ? 'Active' : 'Off'}</Text> : null}
      {url ? (
        <View style={{ gap: 8 }}>
          <Text testID="feed-warning" size={13}>Copy or share this link now. It will not be shown again.</Text>
          <Text testID="feed-url" selectable size={13}>{url}</Text>
          <Button testID="feed-share" title="Share link" onPress={() => void share()} />
          {shareErr ? <ErrorText testID="feed-share-error">{shareErr}</ErrorText> : null}
        </View>
      ) : null}
      {error ? <ErrorText testID="feed-error">{error}</ErrorText> : null}
      <Button
        testID="feed-create"
        variant={url ? 'secondary' : 'primary'}
        title={active ? 'Create a new link' : 'Create calendar link'}
        loading={isBusy('rotate')}
        disabled={status.isPending || isBusy('off')}
        onPress={() => void run('rotate', async () => setUrl(await rotate.mutateAsync()))}
      />
      {active ? <Text muted size={12}>Creating a new link stops the old one from working.</Text> : null}
      {active ? (
        <ConfirmAction id="feed-off" label="Turn off feed" prompt="Turn the calendar feed off? Subscribed calendars will stop updating." busy={isBusy('off')} onConfirm={() => void run('off', async () => { await del.mutateAsync(); setUrl(null); })} />
      ) : null}
    </Card>
  );
}
