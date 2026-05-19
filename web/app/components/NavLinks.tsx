"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/today", label: "Today" },
  { href: "/alerts", label: "Alerts" },
  { href: "/clv", label: "CLV" },
  { href: "/backtest", label: "Backtest" },
  { href: "/about", label: "About" },
];

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-0.5">
      {NAV_LINKS.map(({ href, label }) => {
        const active =
          pathname === href || (href === "/today" && pathname === "/");
        return (
          <Link
            key={href}
            href={href}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
