import React from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  CheckCircle2, 
  MoreHorizontal,
  Info
} from 'lucide-react';
import useStore from '../store/useStore';
import AnalyticsDashboard from '../components/AnalyticsDashboard';

const Dashboard = () => {
  const { currentPatient: patient } = useStore();

  const getColorClass = (color) => {
    switch (color) {
      case 'rose': return 'bg-rose-500/10 text-rose-500';
      case 'amber': return 'bg-amber-500/10 text-amber-500';
      case 'emerald': return 'bg-emerald-500/10 text-emerald-500';
      default: return 'bg-slate-500/10 text-slate-500';
    }
  };

  const riskFactors = [
    { label: 'Hyperkalemia Risk', value: 'High', color: 'rose', trend: 'up', info: 'K+ level 5.4 in last draw' },
    { label: 'Adherence', value: '98%', color: 'emerald', trend: 'down', info: 'Last fill 14 days ago' },
    { label: 'BP Control', value: '138/88', color: 'amber', trend: 'up', info: 'Stage 1 Hypertension' },
    { label: 'A1c Target', value: '7.4', color: 'amber', trend: 'down', info: 'Target < 7.0' }
  ];

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-slate-100 tracking-tight">Executive Integrity Dashboard</h1>
          <p className="text-slate-500 mt-1">Real-time revenue recovery and audit monitoring</p>
        </div>
      </div>

      <AnalyticsDashboard />

      <div className="pt-8 border-t border-white/5">
        <h2 className="text-xl font-bold text-slate-100 mb-6 tracking-tight">Clinical Focus: {patient.name}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {riskFactors.map((risk, index) => (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            key={risk.label}
            className={`glass-card p-5 rounded-2xl border-l-4 ${
              risk.color === 'rose' ? 'border-l-rose-500' : 
              risk.color === 'amber' ? 'border-l-amber-500' : 
              'border-l-emerald-500'
            }`}
          >
            <div className="flex justify-between items-start mb-4">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{risk.label}</span>
              <div className={`p-1 rounded ${getColorClass(risk.color)}`}>
                <Info className="w-3 h-3" />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-xl font-bold ${
                risk.color === 'rose' ? 'text-rose-400' : 
                risk.color === 'amber' ? 'text-amber-400' : 
                'text-emerald-400'
              }`}>{risk.value}</span>
              {risk.trend === 'up' && <TrendingUp className="w-4 h-4 text-rose-500" />}
              {risk.trend === 'down' && <TrendingDown className="w-4 h-4 text-emerald-500" />}
            </div>
            <p className="text-[10px] text-slate-500 mt-3 italic">{risk.info}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel rounded-3xl p-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-5">
            <ActivityIcon className="w-48 h-48" />
          </div>
          
          <h3 className="text-lg font-bold text-slate-100 mb-6 flex items-center">
            <CheckCircle2 className="w-5 h-5 mr-3 text-indigo-400" />
            AI Care Coordination Plan
          </h3>

          <div className="space-y-4">
            <div className="p-4 rounded-2xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-sm font-bold text-slate-200">Lab Discrepancy Detected</h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-md">Patient reported fatigue but last CBC (Feb) was normal. Suggested action: Repeat iron studies and ferritin.</p>
                </div>
                <button className="text-[10px] font-bold text-indigo-400 hover:underline">ORDER NOW</button>
              </div>
            </div>
            
            <div className="p-4 rounded-2xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-sm font-bold text-slate-200">Medication Interaction Check</h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-md">Lisinopril x Atorvastatin: No contraindications found. Patient adherence is high (98%).</p>
                </div>
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-rose-500/5 border border-rose-500/10">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-sm font-bold text-rose-400">Missing Care Element</h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-md">Annual Diabetic Retinal Exam is overdue by 3 months. Recommend referral to Opthalmology.</p>
                </div>
                <AlertTriangle className="w-4 h-4 text-rose-500" />
              </div>
            </div>
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6 bg-indigo-500/5 border-indigo-500/10">
          <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-6">Suggested Questions</h3>
          <div className="space-y-3">
            {[
              "Review Marcus's weight trend over 12 months",
              "Generate a Patient Visit Summary (PVS)",
              "Look up ACC guidelines for Hypertension",
              "Draft a follow-up email about Lab results"
            ].map((q, i) => (
              <button key={i} className="w-full text-left p-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 transition-all flex items-center group">
                <span className="text-xs text-slate-400 group-hover:text-slate-200 flex-1">{q}</span>
                <MoreHorizontal className="w-4 h-4 text-slate-600" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const ActivityIcon = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
  </svg>
);

export default Dashboard;
