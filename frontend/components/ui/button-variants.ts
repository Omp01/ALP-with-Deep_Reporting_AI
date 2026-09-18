import { cva, type VariantProps } from "class-variance-authority";

/**
 * Button styling, kept in a module with no `"use client"` directive.
 *
 * Server components need these classes to style a `<Link>` as a button, and a
 * function exported from a client module cannot be *called* from the server —
 * only rendered as a component. Splitting the variants out lets `app/error.tsx`
 * and `app/not-found.tsx` use them directly.
 */
export const buttonVariants = cva(
  // Base: every button is a flex row so an icon and a label always align,
  // and disabled state is uniform regardless of variant.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-colors " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
    "disabled:pointer-events-none disabled:opacity-50 " +
    "[&_svg]:shrink-0 [&_svg]:pointer-events-none",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-foreground shadow-xs hover:bg-primary-hover active:bg-primary-active",
        secondary:
          "bg-surface-elevated text-fg border border-border shadow-xs hover:bg-surface hover:border-border-strong",
        outline:
          "border border-primary-border bg-transparent text-primary hover:bg-primary-light",
        ghost: "bg-transparent text-fg-muted hover:bg-surface hover:text-fg",
        danger: "bg-danger text-white shadow-xs hover:brightness-95 active:brightness-90",
        link: "bg-transparent text-primary underline-offset-4 hover:underline p-0 h-auto",
      },
      size: {
        sm: "h-8 px-3 text-xs [&_svg]:size-3.5",
        md: "h-9 px-4 text-sm [&_svg]:size-4",
        lg: "h-11 px-6 text-sm [&_svg]:size-4",
        icon: "h-9 w-9 p-0 [&_svg]:size-4",
      },
      fullWidth: {
        true: "w-full",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export type ButtonVariantProps = VariantProps<typeof buttonVariants>;
