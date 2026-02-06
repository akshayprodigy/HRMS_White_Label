import type { ApiError } from '../api/client';
import type { DprCreate } from '../api/projects/dprs';
import { createDpr } from '../api/projects/dprs';
import { del, getAll, getByKey, openDb, put, txDone } from './idb';

export type DprQueueStatus = 'pending' | 'syncing' | 'synced' | 'failed';

export type DprQueueItem = {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: DprQueueStatus;
  payload: DprCreate;
  attemptCount: number;
  lastAttemptAt: string | null;
  serverDprId: number | null;
  errorMessage: string | null;
};

const DB_NAME = 'ue_erp_offline';
const DB_VERSION = 1;
const STORE = 'dpr_queue';

let cachedDb: IDBDatabase | null = null;

function nowIso(): string {
  return new Date().toISOString();
}

function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function getDb(): Promise<IDBDatabase> {
  if (cachedDb) return cachedDb;
  cachedDb = await openDb(DB_NAME, DB_VERSION, (db) => {
    if (!db.objectStoreNames.contains(STORE)) {
      const store = db.createObjectStore(STORE, { keyPath: 'id' });
      store.createIndex('status', 'status', { unique: false });
      store.createIndex('createdAt', 'createdAt', { unique: false });
    }
  });
  return cachedDb;
}

export async function enqueueDpr(payload: DprCreate): Promise<DprQueueItem> {
  const db = await getDb();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);

  const item: DprQueueItem = {
    id: newId(),
    createdAt: nowIso(),
    updatedAt: nowIso(),
    status: 'pending',
    payload,
    attemptCount: 0,
    lastAttemptAt: null,
    serverDprId: null,
    errorMessage: null,
  };

  await put(store, item);
  await txDone(tx);
  return item;
}

export async function listDprQueue(): Promise<DprQueueItem[]> {
  const db = await getDb();
  const tx = db.transaction(STORE, 'readonly');
  const store = tx.objectStore(STORE);
  const items = await getAll<DprQueueItem>(store);
  await txDone(tx);
  return items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function getDprQueueItem(id: string): Promise<DprQueueItem | undefined> {
  const db = await getDb();
  const tx = db.transaction(STORE, 'readonly');
  const store = tx.objectStore(STORE);
  const item = await getByKey<DprQueueItem>(store, id);
  await txDone(tx);
  return item;
}

export async function updateDprQueueItem(id: string, patch: Partial<DprQueueItem>): Promise<void> {
  const db = await getDb();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);

  const existing = await getByKey<DprQueueItem>(store, id);
  if (!existing) {
    await txDone(tx);
    return;
  }

  const next: DprQueueItem = {
    ...existing,
    ...patch,
    updatedAt: nowIso(),
  };

  await put(store, next);
  await txDone(tx);
}

export async function deleteDprQueueItem(id: string): Promise<void> {
  const db = await getDb();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);
  await del(store, id);
  await txDone(tx);
}

export async function getDprQueueCounts(): Promise<{
  pending: number;
  syncing: number;
  failed: number;
  synced: number;
}> {
  const items = await listDprQueue();
  return {
    pending: items.filter((i) => i.status === 'pending').length,
    syncing: items.filter((i) => i.status === 'syncing').length,
    failed: items.filter((i) => i.status === 'failed').length,
    synced: items.filter((i) => i.status === 'synced').length,
  };
}

function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === 'object' &&
    err !== null &&
    'status' in err &&
    'message' in err &&
    typeof (err as { status: unknown }).status === 'number'
  );
}

export async function syncDprQueue(options?: { includeFailed?: boolean }): Promise<void> {
  const includeFailed = options?.includeFailed ?? true;

  const items = await listDprQueue();
  const candidates = items.filter(
    (i) => i.status === 'pending' || (includeFailed && i.status === 'failed'),
  );

  for (const item of candidates) {
    await updateDprQueueItem(item.id, {
      status: 'syncing',
      attemptCount: item.attemptCount + 1,
      lastAttemptAt: nowIso(),
      errorMessage: null,
    });

    try {
      const created = await createDpr(item.payload);
      await updateDprQueueItem(item.id, {
        status: 'synced',
        serverDprId: created.id,
        errorMessage: null,
      });
    } catch (err) {
      if (isApiError(err) && err.status >= 400 && err.status < 500) {
        await updateDprQueueItem(item.id, {
          status: 'failed',
          errorMessage: err.message || 'Validation error',
        });
      } else if (isApiError(err) && err.status >= 500) {
        await updateDprQueueItem(item.id, {
          status: 'pending',
          errorMessage: err.message || 'Server error',
        });
      } else {
        await updateDprQueueItem(item.id, {
          status: 'pending',
          errorMessage: 'Network error. Will retry when online.',
        });
      }
    }
  }
}
