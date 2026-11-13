import { Card, Screen, Text } from './ui';
import { t } from '../i18n';

export function Placeholder({ title }: { title: string }) {
  return (
    <Screen>
      <Card>
        <Text weight="600" size={18}>{title}</Text>
        <Text muted>{t('common.comingSoon')}</Text>
      </Card>
    </Screen>
  );
}
