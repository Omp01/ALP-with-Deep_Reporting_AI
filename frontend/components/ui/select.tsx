"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { fieldBase, stateClasses } from "./input";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
  invalid?: boolean;
  /** Shown as a disabled first option when the value is empty. */
  placeholder?: string;
}

/**
 * A native `<select>` with the app's field chrome.
 *
 * Deliberately native rather than a custom listbox: it is keyboard- and
 * screen-reader-correct for free, and it uses the platform picker on mobile,
 * which is what a filter control on a course catalogue should do. Reach for a
 * custom popover only when an option needs rich content.
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, options, invalid, placeholder, value, ...props }, ref) => (
    <div className="relative">
      <select
        ref={ref}
        value={value}
        aria-invalid={invalid || undefined}
        className={cn(
          fieldBase,
          stateClasses(invalid),
          "h-9 pl-3 pr-9 appearance-none cursor-pointer",
          className
        )}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 size-4 text-fg-subtle"
        aria-hidden="true"
      />
    </div>
  )
);
Select.displayName = "Select";
