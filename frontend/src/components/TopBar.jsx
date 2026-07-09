import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Bell, Sun, Moon, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const TopBar = ({ dark, onToggleTheme }) => {
  const navigate = useNavigate();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const menuRef = useRef(null);

  // Close user menu on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setShowUserMenu(false);
      }
    };
    if (showUserMenu) {
      document.addEventListener('mousedown', handleClick);
    }
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showUserMenu]);

  const handleKeyDown = useCallback(
    (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        document.querySelector('[data-search-input]')?.focus();
      }
    },
    [],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <header
      className="h-14 border-b flex items-center justify-between px-6 flex-shrink-0"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Search */}
      <div className="flex items-center flex-1 max-w-md">
        <div className="relative w-full">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2"
            size={16}
            style={{ color: 'var(--color-muted)' }}
          />
          <input
            data-search-input
            type="text"
            placeholder="Search patients, codes, encounters…"
            className="input pl-10 pr-10"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center pointer-events-none">
            <span className="kbd">⌘K</span>
          </div>
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Theme toggle */}
        <button
          onClick={onToggleTheme}
          className="btn-ghost btn-sm !min-h-[36px] !min-w-[36px] !p-0 rounded-control"
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Notifications */}
        <button
          className="btn-ghost btn-sm !min-h-[36px] !min-w-[36px] !p-0 rounded-control relative"
          aria-label="Notifications"
        >
          <Bell size={16} />
          <span
            className="absolute top-2 right-2 w-2 h-2 rounded-full"
            style={{ backgroundColor: '#BE123C' }}
          />
        </button>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="btn-ghost btn-sm !min-h-[36px] !min-w-[36px] !p-0 rounded-control"
            aria-label="User menu"
            aria-haspopup="true"
            aria-expanded={showUserMenu}
          >
            <User size={16} />
          </button>

          {showUserMenu && (
            <div
              className="absolute right-0 top-full mt-2 w-56 rounded-card border py-1 z-50"
              style={{
                backgroundColor: 'var(--color-surface)',
                borderColor: 'var(--color-border)',
                boxShadow: dark
                  ? '0 4px 12px rgba(0,0,0,0.35)'
                  : '0 4px 12px rgba(21,48,45,0.12)',
              }}
              role="menu"
            >
              <div
                className="px-4 py-3 border-b"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <p
                  className="text-sm font-semibold"
                  style={{ color: 'var(--color-ink)' }}
                >
                  Operator
                </p>
                <p
                  className="text-xs"
                  style={{ color: 'var(--color-muted)' }}
                >
                  Coding Specialist
                </p>
              </div>
              <button
                onClick={() => { setShowUserMenu(false); navigate('/settings'); }}
                className="w-full text-left px-4 py-2 text-sm transition-colors"
                style={{ color: 'var(--color-secondary)' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--color-fill)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                role="menuitem"
              >
                Settings
              </button>
              <button
                className="w-full text-left px-4 py-2 text-sm transition-colors"
                style={{ color: 'var(--color-secondary)' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--color-fill)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                role="menuitem"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default TopBar;
