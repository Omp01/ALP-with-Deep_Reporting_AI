/**
 * The Adaptive LMS component library.
 *
 * One component per file, re-exported here so pages import from a single
 * place: `import { Button, Card, EmptyState } from "@/components/ui"`.
 *
 * Rules for this directory:
 *   - Primitives are presentational. They never fetch, and they never compute
 *     a business metric — they receive what they display.
 *   - Colour comes from design tokens (`bg-surface`, `text-fg-muted`), never
 *     from raw palette classes like `bg-slate-50`.
 *   - Every interactive component is keyboard-operable and carries the ARIA
 *     roles its pattern requires.
 */

export { Button, buttonVariants, type ButtonProps } from "./button";
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardToolbar,
  type CardProps,
} from "./card";
export { Badge, StatusDot, badgeVariants, type BadgeProps } from "./badge";
export {
  Input,
  Textarea,
  Label,
  Field,
  FieldError,
  FieldHint,
  type InputProps,
  type TextareaProps,
} from "./input";
export { Select, type SelectOption, type SelectProps } from "./select";
export {
  Skeleton,
  SkeletonText,
  SkeletonStat,
  SkeletonCard,
  SkeletonTable,
  LoadingRegion,
} from "./skeleton";
export { Spinner, SpinnerBlock } from "./spinner";
export {
  Progress,
  MasteryBar,
  masteryBand,
  masteryLabel,
  type MasteryBand,
} from "./progress";
export { Avatar } from "./avatar";
export { Alert, alertVariants, type AlertProps } from "./alert";
export { EmptyState, InsufficientEvidenceState } from "./empty-state";
export { ErrorState, InlineError } from "./error-state";
export { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";
export { Breadcrumb, type Crumb } from "./breadcrumb";
export { Dialog, ConfirmDialog, type DialogProps } from "./dialog";
export {
  DropdownMenu,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
} from "./dropdown-menu";
export { Tooltip } from "./tooltip";
export {
  ToastProvider,
  useToastContext,
  useToast,
  type Toast,
  type ToastInput,
  type ToastVariant,
} from "./toast";
export { Stat, StatGrid } from "./stat";
export { TableContainer, Table, THead, TBody, TR, TH, TD } from "./table";
export { Separator } from "./separator";
