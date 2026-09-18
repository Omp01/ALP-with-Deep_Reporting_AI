"use client";

import { useSyncExternalStore } from "react";

/** Nothing to subscribe to — the value is constant per environment. */
const subscribe = () => () => {};

/**
 * `false` during the server render and the hydration pass, `true` afterwards.
 *
 * Needed by anything that touches `document` — portals, in particular. The
 * `useState(false)` + `useEffect(() => setMounted(true))` idiom does the same
 * job but sets state synchronously inside an effect, which triggers a cascading
 * render. `useSyncExternalStore` expresses "this value differs between server
 * and client" directly and costs one render fewer.
 */
export function useIsMounted(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false
  );
}
