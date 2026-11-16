/**
 * The four primitives this app needs, hand-rolled.
 *
 * The AppKit version imports these from `@databricks/appkit-ui`. Dropping AppKit
 * means dropping that too, so they live here: ~60 lines of Tailwind rather than a
 * component dependency. Variants are deliberately few - severity is carried by
 * the variant, never by an ad-hoc colour at the call site.
 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

const BADGE: Record<BadgeVariant, string> = {
  default: 'bg-neutral-100 text-neutral-900',
  secondary: 'bg-neutral-800 text-neutral-300',
  destructive: 'bg-red-900/60 text-red-200',
  outline: 'border border-neutral-700 text-neutral-200',
};

export function Badge({
  children,
  variant = 'default',
  className = '',
  title,
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Button({ children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-md bg-neutral-100 px-3 py-2 text-sm font-medium text-neutral-900 transition hover:bg-white disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500 ${className}`}
    >
      {children}
    </button>
  );
}

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`w-full rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-100 outline-none focus:border-neutral-400 ${className}`}
    />
  );
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-neutral-800 ${className}`} />;
}
