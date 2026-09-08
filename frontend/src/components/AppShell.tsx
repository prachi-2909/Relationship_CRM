import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { ROLE_LABELS } from "../types";
import { Button } from "./ui";

interface NavItem {
  to: string;
  label: string;
  adminOnly?: boolean;
}

interface NavGroup {
  heading: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    heading: "Overview",
    items: [{ to: "/", label: "Dashboard" }],
  },
  {
    heading: "System of record",
    items: [
      { to: "/organisation", label: "Organisation" },
      { to: "/officials", label: "Officials" },
      { to: "/relationships", label: "Relationships" },
      { to: "/interactions", label: "Interactions" },
      { to: "/follow-ups", label: "Follow-ups" },
    ],
  },
  {
    heading: "Intelligence",
    items: [
      { to: "/moments", label: "Engagement Moments" },
      { to: "/import", label: "Data Ingestion" },
    ],
  },
  {
    heading: "Admin",
    items: [
      { to: "/users", label: "Users", adminOnly: true },
      { to: "/audit", label: "Audit Log", adminOnly: true },
    ],
  },
];

const ALL_ITEMS = NAV.flatMap((g) => g.items);

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  const current = ALL_ITEMS.find(
    (i) => i.to === location.pathname || (i.to !== "/" && location.pathname.startsWith(i.to)),
  );

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const sidebar = (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-3.5">
        <img src="/eko-logo.png" alt="Eko Kiosk" className="h-7 w-auto" />
        <div className="leading-tight">
          <div className="font-heading text-[13px] font-bold text-secondary">
            Relationship CRM
          </div>
          <div className="text-[11px] text-muted-foreground">Eko Kiosk</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto p-3">
        {NAV.map((group) => {
          const items = group.items.filter(
            (i) => !i.adminOnly || user?.role === "admin",
          );
          if (items.length === 0) return null;
          return (
            <div key={group.heading} className="mb-4 last:mb-0">
              <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {group.heading}
              </div>
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  onClick={() => setNavOpen(false)}
                  className={({ isActive }) =>
                    [
                      "relative flex items-center rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-primary/10 font-semibold text-secondary before:absolute before:-left-3 before:top-1.5 before:bottom-1.5 before:w-1 before:rounded-r before:bg-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    ].join(" ")
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
    </aside>
  );

  return (
    <div className="flex h-full bg-background">
      <div className="hidden md:flex">{sidebar}</div>

      {navOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="absolute inset-0 bg-foreground/30" onClick={() => setNavOpen(false)} />
          <div className="relative z-50">{sidebar}</div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-2.5 md:px-6">
          <div className="flex items-center gap-2">
            <button
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted md:hidden"
              onClick={() => setNavOpen(true)}
              aria-label="Open menu"
            >
              ☰
            </button>
            <span className="font-heading text-sm font-semibold text-foreground">
              {current?.label ?? "Relationship CRM"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {user?.name}
            </span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              {user ? ROLE_LABELS[user.role] : ""}
            </span>
            <Button variant="secondary" size="sm" onClick={handleLogout}>
              Sign out
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
