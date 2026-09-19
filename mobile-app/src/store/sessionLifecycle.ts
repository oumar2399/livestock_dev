// An epoch identifies one login session, including its in-flight requests.
let sessionEpoch = 0;
let storageQueue: Promise<unknown> = Promise.resolve();
const listeners = new Set<(epoch: number) => void>();

export const getSessionEpoch = (): number => sessionEpoch;

export function advanceSessionEpoch(): number {
  ++sessionEpoch;
  listeners.forEach((listener) => listener(sessionEpoch));
  return sessionEpoch;
}

export function onSessionChange(listener: (epoch: number) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

// Serialize credential/farm storage so an old write cannot undo a later logout.
export function withSessionStorage<T>(operation: () => Promise<T>): Promise<T> {
  const result = storageQueue.then(operation);
  storageQueue = result.catch(() => undefined);
  return result;
}
