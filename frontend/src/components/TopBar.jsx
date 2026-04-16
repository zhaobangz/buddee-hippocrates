import React from 'react';
import { Search, Bell, Users, ShieldCheck, Zap } from 'lucide-react';
import useStore from '../store/useStore';

const TopBar = () => {
  const currentPatient = useStore((state) => state.currentPatient);

  return (
    <header className="h-16 border-b border-white/5 bg-slate-900/50 backdrop-blur-md px-6 flex items-center justify-between z-10">
      <div className="flex items-center flex-1 max-w-xl">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input 
            type="text" 
            placeholder="Search clinical records, codes, or medications... (⌘K)"
            className="w-full bg-white/5 border border-white/10 rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:border-medical-500/50 transition-all"
          />
        </div>
      </div>

      <div className="flex items-center space-x-6">
        {/* System Health */}
        <div className="flex items-center space-x-4 px-4 py-1.5 rounded-full bg-white/5 border border-white/5">
          <div className="flex items-center space-x-2">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/80">LLM-01 Core Active</span>
          </div>
          <div className="w-[1px] h-3 bg-white/10" />
          <div className="flex items-center space-x-2">
            <Zap className="w-3 h-3 text-amber-400" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-amber-400/80">Latency 180ms</span>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button className="relative w-10 h-10 rounded-xl hover:bg-white/5 flex items-center justify-center transition-colors">
            <Bell className="w-5 h-5 text-slate-400" />
            <span className="absolute top-2 right-2 w-2 h-2 bg-rose-500 rounded-full border border-slate-900" />
          </button>
          
          <div className="w-[1px] h-6 bg-white/10 mx-2" />
          
          <div className="flex items-center space-x-3">
             <div className="flex flex-col items-end">
               <span className="text-xs font-bold text-slate-400 uppercase tracking-tighter">Current Patient</span>
               <span className="text-sm font-semibold text-medical-400">{currentPatient.name}</span>
             </div>
             <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center border border-white/10">
                <Users className="w-5 h-5 text-slate-300" />
             </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopBar;
