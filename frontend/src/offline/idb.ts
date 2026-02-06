export type IDBUpgrade = (db: IDBDatabase, oldVersion: number, newVersion: number | null) => void;

function requestToPromise<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function openDb(
  name: string,
  version: number,
  upgrade?: IDBUpgrade,
): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(name, version);

    req.onupgradeneeded = (evt: IDBVersionChangeEvent) => {
      if (upgrade) {
        upgrade(req.result, evt.oldVersion, evt.newVersion);
      }
    };

    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export function getAll<T>(store: IDBObjectStore): Promise<T[]> {
  return requestToPromise(store.getAll()) as Promise<T[]>;
}

export function getByKey<T>(store: IDBObjectStore, key: IDBValidKey): Promise<T | undefined> {
  return requestToPromise(store.get(key)) as Promise<T | undefined>;
}

export function put<T>(store: IDBObjectStore, value: T): Promise<IDBValidKey> {
  return requestToPromise(store.put(value as unknown as Record<string, unknown>));
}

export function del(store: IDBObjectStore, key: IDBValidKey): Promise<void> {
  return requestToPromise(store.delete(key)) as Promise<void>;
}
