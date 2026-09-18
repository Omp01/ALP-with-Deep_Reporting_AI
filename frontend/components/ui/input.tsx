"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Shared field chrome                                                        */
/* -------------------------------------------------------------------------- */

const fieldBase =
  "w-full rounded-md border bg-surface-elevated text-sm text-fg placeholder:text-fg-subtle " +
  "transition-colors focus:outline-2 focus:outline-offset-0 focus:outline-primary " +
  "disabled:cursor-not-allowed disabled:bg-surface disabled:text-fg-subtle";

function stateClasses(invalid?: boolean) {
  return invalid
    ? "border-danger focus:outline-danger"
    : "border-border hover:border-border-strong";
}

/* -------------------------------------------------------------------------- */
/* Label                                                                      */
/* -------------------------------------------------------------------------- */

export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement> & { required?: boolean }
>(({ className, required, children, ...props }, ref) => (
  <label
    ref={ref}
    className={cn("block text-sm font-medium text-fg mb-1.5", className)}
    {...props}
  >
    {children}
    {required && (
      <span className="text-danger ml-0.5" aria-hidden="true">
        *
      </span>
    )}
  </label>
));
Label.displayName = "Label";

/* -------------------------------------------------------------------------- */
/* Messages                                                                   */
/* -------------------------------------------------------------------------- */

export function FieldError({ children, id }: { children?: React.ReactNode; id?: string }) {
  if (!children) return null;
  return (
    <p
      id={id}
      role="alert"
      className="mt-1.5 flex items-start gap-1.5 text-xs font-medium text-danger"
    >
      <AlertCircle className="size-3.5 mt-px shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

export function FieldHint({ children, id }: { children?: React.ReactNode; id?: string }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1.5 text-xs text-fg-muted">
      {children}
    </p>
  );
}

/* -------------------------------------------------------------------------- */
/* Input                                                                      */
/* -------------------------------------------------------------------------- */

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  /** Rendered inside the field on the left — a search or mail icon, typically. */
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, invalid, leadingIcon, trailingIcon, ...props }, ref) => {
    const field = (
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          fieldBase,
          stateClasses(invalid),
          "h-9 px-3",
          leadingIcon && "pl-9",
          trailingIcon && "pr-9",
          className
        )}
        {...props}
      />
    );

    if (!leadingIcon && !trailingIcon) return field;

    return (
      <div className="relative">
        {leadingIcon && (
          <span
            className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle [&_svg]:size-4"
            aria-hidden="true"
          >
            {leadingIcon}
          </span>
        )}
        {field}
        {trailingIcon && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-fg-subtle [&_svg]:size-4">
            {trailingIcon}
          </span>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

/* -------------------------------------------------------------------------- */
/* Textarea                                                                   */
/* -------------------------------------------------------------------------- */

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, invalid, rows = 4, ...props }, ref) => (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, stateClasses(invalid), "px-3 py-2 resize-y", className)}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";

/* -------------------------------------------------------------------------- */
/* Field — label + control + message, wired for accessibility                 */
/* -------------------------------------------------------------------------- */

/**
 * Wraps a control with its label, hint, and error, and connects them via
 * `aria-describedby` so screen readers announce the message with the field.
 * Pass a render function to receive the ids to spread onto the control.
 */
export function Field({
  label,
  required,
  error,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string;
  required?: boolean;
  error?: React.ReactNode;
  hint?: React.ReactNode;
  htmlFor: string;
  children: (props: {
    id: string;
    invalid: boolean;
    "aria-describedby": string | undefined;
  }) => React.ReactNode;
  className?: string;
}) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;
  const describedBy = error ? errorId : hint ? hintId : undefined;

  return (
    <div className={className}>
      <Label htmlFor={htmlFor} required={required}>
        {label}
      </Label>
      {children({
        id: htmlFor,
        invalid: Boolean(error),
        "aria-describedby": describedBy,
      })}
      <FieldError id={errorId}>{error}</FieldError>
      {!error && <FieldHint id={hintId}>{hint}</FieldHint>}
    </div>
  );
}

export { fieldBase, stateClasses };
