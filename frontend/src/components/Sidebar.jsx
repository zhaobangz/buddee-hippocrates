import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  MessageSquare, 
  ShieldAlert, 
  History, 
  Activity, 
  Settings,
  BrainCircuit,
  LogOut
} from 'lucide-react';

const Sidebar = () => {
  const menuItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: MessageSquare, label: 'Clinical Agent', path: '/chat' },
    { icon: BrainCircuit, label: 'Shadow Mode', path: '/shadow' },
    { icon: ShieldAlert, label: 'Safety Audit', path: '/audit' },
    { icon: History, label: 'Care History', path: '/history' },
  ];

  return (
    <nav className="w-64 border-r border-white/5 bg-slate-950/80 backdrop-blur-2xl flex flex-col pt-6">
      <div className="px-6 mb-8 flex items-center space-x-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-medical-400 to-brand-cyan flex items-center justify-center shadow-lg shadow-medical-500/20">
          <Activity className="w-5 h-5 text-slate-900" strokeWidth={2.5} />
        </div>
        <span className="text-xl font-bold medical-gradient-text tracking-tight">BUDDI</span>
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

      <div className="p-4 border-t border-white/5">
        <div className="flex items-center p-2 rounded-xl bg-white/5 mb-4">
          <div className="w-8 h-8 rounded-full bg-medical-500/20 flex items-center justify-center mr-3 border border-medical-500/30">
            <span className="text-xs font-bold text-medical-400">SC</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate text-slate-200">Dr. Sarah Chen</p>
            <p className="text-xs text-slate-500 truncate">Senior Oncologist</p>
          </div>
        </div>
        
        <button className="w-full flex items-center space-x-3 px-4 py-2 text-slate-400 hover:text-rose-400 transition-colors">
          <LogOut className="w-4 h-4" />
          <span className="text-sm font-medium">System Exit</span>
        </button>
      </div>
    </nav>
  );
};

export default Sidebar;
