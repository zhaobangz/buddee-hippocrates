import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  MessageSquare, 
  ShieldAlert, 
  History, 
  Settings,
  BrainCircuit,
  LogOut
} from 'lucide-react';

const Sidebar = () => {
  const menuItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: MessageSquare, label: 'Ask Buddi', path: '/chat' },
    { icon: BrainCircuit, label: 'Shadow Mode', path: '/shadow' },
    { icon: ShieldAlert, label: 'Audit Trail', path: '/audit' },
    { icon: History, label: 'History', path: '/history' },
  ];

  return (
    <nav className="w-64 border-r border-white/5 bg-slate-950/80 backdrop-blur-2xl flex flex-col pt-6">
      <div className="px-6 mb-8 flex items-center space-x-3">
        <img src="/Buddee_Health.png" alt="Buddee Health" className="w-8 h-8 rounded-lg object-contain" />
        <span className="text-xl font-bold medical-gradient-text tracking-tight">Buddee Health</span>
      </div>

      <div className="flex-1 px-3 space-y-1">
        {menuItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.path}
            className={({ isActive }) =>
              `nav-link ${isActive ? 'active' : ''}`
            }
          >
            <item.icon className="w-5 h-5" />
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
      </div>

      <div className="px-3 mb-2">
        <div className="flex items-center space-x-2 px-3 py-2 rounded-xl bg-teal-500/8 border border-teal-500/15">
          <div className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-teal-400/80">Shadow Mode Active</span>
        </div>
      </div>

      <div className="p-4 border-t border-white/5">
        <div className="flex items-center p-2 rounded-xl bg-white/5 mb-4">
          <div className="w-8 h-8 rounded-full bg-medical-500/20 flex items-center justify-center mr-3 border border-medical-500/30">
            <span className="text-xs font-bold text-medical-400">OP</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate text-slate-200">Operator</p>
            <p className="text-xs text-slate-500 truncate">Buddi Portal</p>
          </div>
        </div>

        <button className="w-full flex items-center space-x-3 px-4 py-2 text-slate-400 hover:text-slate-300 transition-colors">
          <LogOut className="w-4 h-4" />
          <span className="text-sm font-medium">Sign Out</span>
        </button>
      </div>
    </nav>
  );
};

export default Sidebar;
