import React from 'react';
import { 
  Heart, 
  Droplet, 
  Scale, 
  ChevronRight, 
  AlertCircle,
  FileText,
  Clock
} from 'lucide-react';
import useStore from '../store/useStore';

const PatientBrief = () => {
  const patient = useStore((state) => state.currentPatient);

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-white/5">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Intelligence Brief</h2>
        <div className="glass-card rounded-2xl p-4 border-medical-500/20 bg-medical-500/5">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold text-medical-400 px-2 py-0.5 rounded bg-medical-500/10 uppercase tracking-tight">Active Case</span>
            <span className="text-[10px] text-slate-500 font-mono">{patient.id}</span>
          </div>
          <p className="text-lg font-bold text-slate-100 mb-1">{patient.name}</p>
          <div className="flex items-center space-x-2 text-xs text-slate-500">
            <span>{patient.age}y</span>
            <span>•</span>
            <span>{patient.gender}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
        {/* Core Vitals */}
        <section>
          <h3 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center">
            <Activity className="w-3 h-3 mr-2 text-medical-400" />
            Core Metrics
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="glass-card rounded-xl p-3 flex flex-col">
              <span className="text-[10px] font-bold text-slate-500 uppercase">A1C Level</span>
              <span className="text-lg font-bold text-amber-500">{patient.labs.a1c}%</span>
              <span className="text-[9px] text-slate-500 mt-1 flex items-center">
                <Clock className="w-2 h-2 mr-1" /> Mar 12, 2026
              </span>
            </div>
            <div className="glass-card rounded-xl p-3 flex flex-col">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Blood Pressure</span>
              <span className="text-lg font-bold text-rose-500">{patient.labs.bp}</span>
              <span className="text-[9px] text-slate-500 mt-1 flex items-center">
                <Clock className="w-2 h-2 mr-1" /> Measured Today
              </span>
            </div>
          </div>
        </section>

        {/* Focus Areas */}
        <section>
          <h3 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center">
            <ShieldAlert className="w-3 h-3 mr-2 text-rose-400" />
            Clinical Focus
          </h3>
          <div className="space-y-2">
            <div className="glass-card rounded-xl p-3 border-rose-500/20 bg-rose-500/5 cursor-pointer hover:bg-rose-500/10 group transition-all">
              <div className="flex items-start">
                <AlertCircle className="w-4 h-4 text-rose-500 mr-3 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs font-bold text-slate-200 group-hover:text-white">A1C Trend Upward</p>
                  <p className="text-[10px] text-slate-500 line-clamp-2 mt-1">Increasing glycemic volatility detected over last 6 months (+0.8%).</p>
                </div>
                <ChevronRight className="w-3 h-3 text-slate-600 group-hover:text-slate-400" />
              </div>
            </div>
          </div>
        </section>

        {/* Medications */}
        <section>
          <h3 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center">
             <Droplet className="w-3 h-3 mr-2 text-brand-cyan" />
             Medication Regimen
          </h3>
          <div className="space-y-2">
            {patient.medications.map((med, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 text-xs">
                <span className="text-slate-300 font-medium">{med}</span>
                <span className="text-[10px] font-bold text-medical-500 bg-medical-500/10 px-1.5 py-0.5 rounded">Daily</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="p-4 bg-slate-900 border-t border-white/10">
        <button className="w-full btn-primary flex items-center justify-center space-x-2 py-3">
          <FileText className="w-4 h-4" />
          <span>Generate Full Intelligence Report</span>
        </button>
      </div>
    </div>
  );
};

// Internal Activity icon definition if needed
const Activity = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
  </svg>
);

const ShieldAlert = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  </svg>
);

export default PatientBrief;
