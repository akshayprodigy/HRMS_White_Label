import { useCallback, useState } from 'react';
import { normalizeError } from '../api/errors';
import { downloadAndShare } from './download';

/** One download at a time per screen: tracks which row is busy and the last friendly error. */
export function useDownload() {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (key: string, path: string, fileName: string) => {
    setError(null);
    setBusyKey(key);
    try {
      await downloadAndShare(path, fileName);
    } catch (e) {
      setError(normalizeError(e).message);
    } finally {
      setBusyKey(null);
    }
  }, []);
  return { busyKey, error, run };
}
