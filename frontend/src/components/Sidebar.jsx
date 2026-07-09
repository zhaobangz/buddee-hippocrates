import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  ClipboardList,
  ShieldCheck,
  Settings,
  LogOut,
} from 'lucide-react';
import useStore from '../store/useStore';

const Sidebar = () => {
  const tenantId = useStore((state) => state.tenantId);

  const menuItems = [
    { icon: LayoutDashboard, label: 'Today', path: '/' },
    { icon: ClipboardList, label: 'Review Queue', path: '/shadow' },
    { icon: MessageSquare, label: 'Ask Buddee', path: '/chat' },
    { icon: ShieldCheck, label: 'Audit Trail', path: '/audit' },
  ];

  return (
    <nav
      className="w-60 flex flex-col border-r"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Logo + name */}
      <div className="flex items-center gap-3 px-5 pt-6 pb-6">
        <img
          src="/Buddee_Health.png"
          alt="Buddee Health"
          className="w-8 h-8 rounded object-contain"
        />
        <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
          Buddee Health
        </span>
      </div>

      {/* Navigation items */}
      <div className="flex-1 px-3 space-y-0.5">
        {menuItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.path}
            className={({ isActive }) =>
              `nav-link${isActive ? ' active' : ''}`
            }
          >
            <item.icon className="w-5 h-5" />
            <span>{item.label}</span>
          </NavLink>
        ))}

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `nav-link${isActive ? ' active' : ''}`
          }
        >
          <Settings className="w-5 h-5" />
          <span>Settings</span>
        </NavLink>
      </div>

      {/* User profile footer */}
      <div
        className="p-4 border-t"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div
          className="flex items-center gap-3 p-2 rounded-control mb-3"
          style={{ backgroundColor: 'var(--color-fill)' }}
        >
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
            style={{
              backgroundColor: 'var(--color-primary)',
              color: '#FFFFFF',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            OP
          </div>
          <div className="flex-1 min-w-0">
            <p
              className="text-sm font-semibold truncate"
              style={{ color: 'var(--color-ink)' }}
            >
              Operator
            </p>
            <p
              className="text-xs truncate"
              style={{ color: 'var(--color-muted)' }}
            >
              Coding Specialist
            </p>
          </div>
        </div>

        {tenantId && (
          <p
            className="text-xs mb-3 px-2"
            style={{ color: 'var(--color-muted)' }}
            title="Organization ID"
          >
            {tenantId.slice(0, 8)}…
          </p>
        )}

        <button
          className="w-full flex items-center gap-3 px-2 py-2 text-sm rounded-control transition-colors duration-150 ease-out"
          style={{ color: 'var(--color-muted)' }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--color-fill)'; e.currentTarget.style.color = 'var(--color-ink)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = 'var(--color-muted)'; }}
        >
          <LogOut className="w-4 h-4" />
          <span>Sign out</span>
        </button>
      </div>
    </nav>
  );
};

export default Sidebar;
