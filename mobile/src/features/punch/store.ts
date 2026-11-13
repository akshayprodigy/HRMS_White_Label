import { Directory, File, Paths } from 'expo-file-system';

/** Where the queue JSON lives. A single small JSON document is enough here: the queue holds a handful of punches
 * (a person punches ~2x/day), so expo-sqlite's native module + migrations would be overkill; expo-file-system is
 * already needed to keep selfie images alive until they are synced. */
export interface PersistentStore {
  read(): Promise<string | null>;
  write(data: string): Promise<void>;
}
/** Selfie image files that must outlive the app cache until the punch is synced. */
export interface SelfieFiles {
  persist(uri: string, id: string): Promise<string>;
  remove(path: string): Promise<void>;
}

export function fileStore(name = 'punch-queue.json'): PersistentStore {
  const file = () => new File(Paths.document, name);
  return {
    async read() {
      const f = file();
      return f.exists ? await f.text() : null;
    },
    async write(data) {
      const f = file();
      if (!f.exists) f.create();
      f.write(data);
    },
  };
}

export const selfieFiles: SelfieFiles = {
  async persist(uri, id) {
    const dir = new Directory(Paths.document, 'selfies');
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

export function memoryStore(initial: string | null = null): PersistentStore & { data: string | null } {
  const s = {
    data: initial,
    async read() { return s.data; },
    async write(d: string) { s.data = d; },
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
