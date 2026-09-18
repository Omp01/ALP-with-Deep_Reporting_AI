"use client";

import * as React from "react";
import Link from "next/link";
import { Building2, ChevronDown, LogOut, Menu, User } from "lucide-react";

import { cn } from "@/lib/utils";
import { roleLabel } from "@/lib/auth";
import { useAuth } from "@/hooks/use-auth";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  DropdownSeparator,
} from "@/components/ui/dropdown-menu";

/**
 * Application header: menu toggle, tenant identity, and the profile menu.
 *
 * The organisation name comes from the session (`user.organization.name`). The
 * previous header fell back to a hardcoded "Acme Corporation" whenever it was
 * missing, which displayed one tenant's name to every other tenant.
 */
export function Topbar({
  onMenuClick,
  children,
}: {
  onMenuClick?: () => void;
  /** Optional slot for page-level controls — search, filters, primary action. */
  children?: React.ReactNode;
}) {
  const { user, role, ready, logout } = useAuth();

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-surface-elevated/95 px-4 backdrop-blur sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        onClick={onMenuClick}
        aria-label="Open navigation"
        aria-controls="primary-navigation"
        className="lg:hidden"
      >
        <Menu aria-hidden="true" />
      </Button>

      {/* Tenant. Hidden on the narrowest screens so it never crowds the
          page title, which matters more. */}
      {ready && user?.organization?.name && (
        <div className="hidden items-center gap-1.5 text-sm text-fg-muted sm:flex">
          <Building2 className="size-4 text-fg-subtle" aria-hidden="true" />
          <span className="font-medium text-fg truncate max-w-[16rem]">
            {user.organization.name}
          </span>
        </div>
      )}

      <div className="flex-1 min-w-0">{children}</div>

      {!ready ? (
        <div className="flex items-center gap-2.5">
          <Skeleton className="size-9 rounded-full" />
          <Skeleton className="hidden h-3.5 w-24 sm:block" />
        </div>
      ) : user ? (
        <DropdownMenu
          trigger={({ open }) => (
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={open}
              className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 transition-colors hover:bg-surface"
            >
              <Avatar name={user.full_name} src={user.avatar_url} size="md" />
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-semibold leading-tight text-fg">
                  {user.full_name}
                </span>
                <span className="block text-xs leading-tight text-fg-muted">
                  {roleLabel(role)}
                </span>
              </span>
              <ChevronDown
                className={cn(
                  "size-4 shrink-0 text-fg-subtle transition-transform",
                  open && "rotate-180"
                )}
                aria-hidden="true"
              />
            </button>
          )}
        >
          <DropdownLabel>Signed in as</DropdownLabel>
          <div className="px-3 pb-2">
            <p className="truncate text-sm font-medium text-fg">{user.full_name}</p>
            <p className="truncate text-xs text-fg-muted">{user.email}</p>
            <Badge variant="primary" size="sm" className="mt-1.5">
              {roleLabel(role)}
            </Badge>
          </div>
          <DropdownSeparator />
          <DropdownItem icon={LogOut} destructive onSelect={logout}>
            Sign out
          </DropdownItem>
        </DropdownMenu>
      ) : (
        // A link styled as a button — not a <Button> wrapping an <a>, which
        // would nest an anchor inside a button element.
        <Link href="/login" className={buttonVariants({ size: "sm" })}>
          <User className="size-4" aria-hidden="true" />
          Sign in
        </Link>
      )}
    </header>
  );
}
