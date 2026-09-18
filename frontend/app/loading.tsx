import { SpinnerBlock } from "@/components/ui/spinner";

/**
 * Route-level loading state. Shown while a segment's server work resolves, so
 * navigation never lands on a blank screen (§65).
 */
export default function Loading() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface">
      <SpinnerBlock label="Loading" />
    </div>
  );
}
