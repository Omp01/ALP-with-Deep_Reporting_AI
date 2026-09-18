"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Tracks a CSS media query from JavaScript.
 *
 * Use it only when layout genuinely cannot be expressed in CSS — deciding
 * whether the sidebar renders as a drawer or a fixed rail, for instance.
 * Anything a Tailwind responsive prefix can do should stay in CSS, since this
 * returns `false` during the server render and can cause a flash.
 *
 * Implemented with `useSyncExternalStore` rather than `useState` + `useEffect`:
 * `matchMedia` is exactly the kind of external system the hook exists for, and
 * it avoids the extra render that reading the initial value inside an effect
 * would cost.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query]
  );

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);

  // No media queries match on the server; assume the smaller layout and let the
  // client correct it, rather than flashing a desktop rail on a phone.
  const getServerSnapshot = useCallback(() => false, []);

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Matches Tailwind's `lg` breakpoint — the point the sidebar becomes a rail. */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}
