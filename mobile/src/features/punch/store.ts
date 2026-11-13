import { Directory, File, Paths } from 'expo-file-system';

/** Where the queue JSON lives. A single small JSON document is enough here: the queue holds a handful of punches
 * (a person punches ~2x/day), so expo-sqlite's native module + migrations would be overkill; expo-file-system is
 * already needed to keep selfie images alive until they are synced. */
export interface PersistentStore {
  read(): Promise<string | null>;
  /** Atomic: a crash mid-write must never leave a half-written main file. */
  write(data: string): Promise<void>;
  /** The previous good copy (kept as .bak), used when the main file is unreadable. */
  readBackup?(): Promise<string | null>;
  /** Candidates to restore from when the main file is missing or unreadable, newest first (.tmp, then .bak). */
  readRecovery?(): Promise<string[]>;
  /** Move an unreadable file aside so it is not overwritten and can be inspected. */
  quarantine?(): Promise<void>;
}
/** Selfie image files that must outlive the app cache until the punch is synced. */
export interface SelfieFiles {
  persist(uri: string, id: string): Promise<string>;
  remove(path: string): Promise<void>;
}

/**
 * Queue data (punch coordinates + selfies) is personal data, so it is kept in a no-backup location: expo-file-system
 * has no "exclude from backup" API, so we use the cache directory (never included in iCloud/Google backups).
 * Tradeoff: the OS may evict cache files under storage pressure; the queue is small and synced within minutes of
 * connectivity, and eviction of a selfie only makes the server decide without it.
 */
const root = () => new Directory(Paths.cache, 'punch');
function ensureRoot() {
  const d = root();
  if (!d.exists) d.create();
  return d;
}

export function fileStore(name = 'punch-queue.json'): PersistentStore {
  const f = (n: string) => new File(ensureRoot(), n);
  const readIf = async (n: string) => {
    const file = f(n);
    return file.exists ? await file.text() : null;
  };
  return {
    read: () => readIf(name),
    readBackup: () => readIf(`${name}.bak`),
    async readRecovery() {
      const out: string[] = [];
      for (const n of [`${name}.tmp`, `${name}.bak`]) {
        try { const t = await readIf(n); if (t) out.push(t); } catch { /* skip */ }
      }
      return out;
    },
    // Order matters: the complete new data (.tmp) and the previous good copy (.bak) both exist before main is
    // removed, so a crash at any point leaves a recoverable file (see readRecovery: .tmp first, then .bak).
    async write(data) {
      const tmp = f(`${name}.tmp`);
      if (tmp.exists) tmp.delete();
      tmp.create();
      tmp.write(data);
      const main = f(name);
      if (main.exists) {
        const bak = f(`${name}.bak`);
        if (bak.exists) bak.delete();
        main.copy(bak);
        main.delete();
      }
      tmp.move(main); // moving the file removes .tmp, so a leftover .tmp always means an interrupted write
    },
    async quarantine() {
      const main = f(name);
      if (!main.exists) return;
      const q = f(`${name}.corrupt`);
      if (q.exists) q.delete();
      main.move(q);
    },
  };
}

export const selfieFiles: SelfieFiles = {
  async persist(uri, id) {
    const dir = new Directory(ensureRoot(), 'selfies');
    if (!dir.exists) dir.create();
    const dest = new File(dir, `${id}.jpg`);
    if (dest.exists) dest.delete();
    new File(uri).copy(dest);
    return dest.uri;
  },
  async remove(path) {
    try {
      const f = new File(path);
      if (f.exists) f.delete();
    } catch {
      /* best effort */
    }
  },
};

export function memoryStore(initial: string | null = null): PersistentStore & { data: string | null; bak: string | null; tmp: string | null; quarantined: string | null } {
  const s = {
    data: initial,
    bak: null as string | null,
    tmp: null as string | null,
    quarantined: null as string | null,
    async read() { return s.data; },
    async write(d: string) { if (s.data !== null) s.bak = s.data; s.data = d; },
    async readBackup() { return s.bak; },
    async readRecovery() { return [s.tmp, s.bak].filter((x): x is string => !!x); },
    async quarantine() { s.quarantined = s.data; s.data = null; },
  };
  return s;
}
export function memorySelfieFiles(): SelfieFiles & { files: Set<string> } {
  const files = new Set<string>();
  return {
    files,
    async persist(uri, id) { const p = `mem://selfies/${id}.jpg`; files.add(p); void uri; return p; },
    async remove(p) { files.delete(p); },
  };
}
