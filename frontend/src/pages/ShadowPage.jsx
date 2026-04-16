import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Zap, 
  Brain, 
  UserCheck, 
  ArrowRightLeft, 
  CheckCircle2, 
  XCircle,
  AlertCircle
} from 'lucide-react';

const ShadowPage = () => {
  const [activeCase, setActiveCase] = useState(0);

  const cases = [
    {
      title: 'Farxiga Initiation for T2D',
      input: 'Recommend therapy adjustment for patient with A1C 7.4% and stage 2 CKD.',
      ai: {
        recommendation: 'Initiate SGLT2 inhibitor (Dapagliflozin 10mg) based on cardiorenal benefits.',
        logic: 'SGLT2i are prioritized in patients with CKD and T2D independent of glycemic control.'
      },
      expert: {
        recommendation: 'Initiate SGLT2 inhibitor (Dapagliflozin 10mg) or GLP-1 RA.',
        logic: 'Patient history supports both, but SGLT2i offers slightly better renal protection here.'
      },
      status: 'Match',
      confidence: 94
    },
    {
      title: 'Lisinopril Dosage Escalation',
      input: 'Patient BP is 154/92. Current med: Lisinopril 10mg once daily.',
      ai: {
        recommendation: 'Increase Lisinopril to 20mg or add Amlodipine 5mg.',
        logic: 'Current dose is sub-therapeutic for Stage 2 hypertension.'
      },
      expert: {
        recommendation: 'Always check BMP (potassium/creatinine) before increasing ACEi.',
        logic: 'Safety protocol requires renal function check due to CKD history before dosage increase.'
      },
      status: 'Advisory',
      confidence: 82
    }
  ];

  const currentCase = cases[activeCase];

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-100 tracking-tight flex items-center">
            <Zap className="w-8 h-8 mr-3 text-amber-400 fill-amber-400/20" />
            Shadow Mode
          </h1>
          <p className="text-slate-500 mt-1">Cross-referencing AI recommendations with Expert Clinical Baseline</p>
        </div>
        <div className="flex space-x-2">
           <button 
             onClick={() => setActiveCase(0)}
             className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeCase === 0 ? 'bg-medical-500 text-white' : 'bg-white/5 text-slate-400'}`}
           >
             Case #1
           </button>
           <button 
             onClick={() => setActiveCase(1)}
             className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeCase === 1 ? 'bg-medical-500 text-white' : 'bg-white/5 text-slate-400'}`}
           >
             Case #2
           </button>
        </div>
      </div>

      <div className="glass-panel p-6 rounded-3xl border-white/5">
        <div className="flex items-center space-x-3 mb-6">
          <div className="p-2 rounded-lg bg-white/5 border border-white/10">
            <ArrowRightLeft className="w-4 h-4 text-slate-400" />
          </div>
          <p className="text-sm font-semibold text-slate-200">{currentCase.title}</p>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-white/5 mb-8">
           <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2 font-bold">Input Context</p>
           <p className="text-sm text-slate-300 italic">"{currentCase.input}"</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative">
          {/* AI Panel */}
          <div className="space-y-6">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 rounded bg-indigo-500/20 flex items-center justify-center">
                <Brain className="w-4 h-4 text-indigo-400" />
              </div>
              <span className="text-sm font-bold text-slate-100 uppercase tracking-widest">Buddi AI Suggestion</span>
              <div className="flex-1" />
              <div className="flex items-center space-x-2 px-3 py-1 bg-emerald-500/10 rounded-full">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span className="text-[10px] font-bold text-emerald-500">{currentCase.confidence}% Confidence</span>
              </div>
            </div>
            <div className="glass-card rounded-2xl p-6 border-indigo-500/20 h-40">
              <p className="text-sm text-slate-200 leading-relaxed font-semibold">"{currentCase.ai.recommendation}"</p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Internal Rationale</p>
              <p className="text-xs text-slate-400">{currentCase.ai.logic}</p>
            </div>
          </div>

          <div className="hidden md:flex absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-slate-800 border-2 border-slate-700 items-center justify-center z-10">
             <span className="text-xs font-bold text-slate-500">VS</span>
          </div>

          {/* Expert Panel */}
          <div className="space-y-6">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 rounded bg-medical-500/20 flex items-center justify-center">
                <UserCheck className="w-4 h-4 text-medical-400" />
              </div>
              <span className="text-sm font-bold text-slate-100 uppercase tracking-widest">Expert Clinical Baseline</span>
              <div className="flex-1" />
              {currentCase.status === 'Match' ? (
                <div className="flex items-center space-x-2 px-3 py-1 bg-emerald-500/10 rounded-full">
                  <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                  <span className="text-[10px] font-bold text-emerald-500">Alignment Verified</span>
                </div>
              ) : (
                <div className="flex items-center space-x-2 px-3 py-1 bg-rose-500/10 rounded-full">
                  <AlertCircle className="w-3 h-3 text-rose-500" />
                  <span className="text-[10px] font-bold text-rose-500">Advisory Variance</span>
                </div>
              )}
            </div>
            <div className={`glass-card rounded-2xl p-6 h-40 ${currentCase.status === 'Match' ? 'border-emerald-500/20' : 'border-rose-500/20'}`}>
              <p className="text-sm text-slate-200 leading-relaxed font-semibold">"{currentCase.expert.recommendation}"</p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Clinical Logic</p>
              <p className="text-xs text-slate-400">{currentCase.expert.logic}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ShadowPage;
