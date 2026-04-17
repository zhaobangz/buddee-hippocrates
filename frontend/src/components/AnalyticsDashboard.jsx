import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  DollarSign, 
  ShieldCheck, 
  ShieldAlert, 
  Activity, 
  ArrowUpRight,
  RefreshCw
} from 'lucide-react';

const AnalyticsDashboard = () => {
  const [stats, setStats] = useState({
    recoveredRevenue: 12450.00,
    auditConsistency: 99.8,
    integrityStatus: 'healthy',
    pendingAudits: 14,
    lastVerify: new Date().toLocaleTimeString()
  });

  const [isVerifying, setIsVerifying] = useState(false);

  const handleVerify = async () => {
    setIsVerifying(true);
    // Simulate API call to /api/audit/verify
    setTimeout(() => {
      setIsVerifying(false);
      setStats(prev => ({ ...prev, lastVerify: new Date().toLocaleTimeString() }));
    }, 1500);
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Revenue Card */}
        <motion.div 
          whileHover={{ y: -5 }}
          className="glass-panel p-6 border-l-4 border-l-emerald-500 bg-emerald-500/5"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-500">
              <DollarSign className="w-5 h-5" />
            </div>
            <ArrowUpRight className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Recovered Revenue (MTD)</p>
          <h2 className="text-3xl font-bold text-slate-100 mt-1">
            ${stats.recoveredRevenue.toLocaleString()}
          </h2>
          <p className="text-xs text-emerald-500/80 mt-2 font-medium">+12.4% from last month</p>
        </motion.div>

        {/* Integrity Card */}
        <motion.div 
          whileHover={{ y: -5 }}
          className="glass-panel p-6 border-l-4 border-l-indigo-500 bg-indigo-500/5"
        >
          <div className="flex justify-between items-start mb-4">
            <div className={`p-2 rounded-lg ${stats.integrityStatus === 'healthy' ? 'bg-indigo-500/10 text-indigo-400' : 'bg-rose-500/10 text-rose-400'}`}>
              <ShieldCheck className="w-5 h-5" />
            </div>
            <button 
              onClick={handleVerify}
              className={`p-1 hover:bg-white/5 rounded transition-all ${isVerifying ? 'animate-spin' : ''}`}
            >
              <RefreshCw className="w-4 h-4 text-slate-500" />
            </button>
          </div>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Audit Trail Integrity</p>
          <h2 className="text-3xl font-bold text-slate-100 mt-1 uppercase">
            {stats.integrityStatus}
          </h2>
          <p className="text-xs text-slate-500 mt-2">Last verified: {stats.lastVerify}</p>
        </motion.div>

        {/* Performance Card */}
        <motion.div 
          whileHover={{ y: -5 }}
          className="glass-panel p-6 border-l-4 border-l-amber-500 bg-amber-500/5"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-amber-500/10 rounded-lg text-amber-500">
              <Activity className="w-5 h-5" />
            </div>
          </div>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">RAG Grounding Accuracy</p>
          <h2 className="text-3xl font-bold text-slate-100 mt-1">
            {stats.auditConsistency}%
          </h2>
          <p className="text-xs text-slate-500 mt-2">{stats.pendingAudits} shadow audits in queue</p>
        </motion.div>
      </div>

      {/* Specialty Breakdown */}
      <div className="glass-panel p-8">
        <h3 className="text-lg font-bold text-slate-100 mb-6 flex items-center">
          <ShieldAlert className="w-5 h-5 mr-3 text-indigo-400" />
          Revenue Leakage Preventions by Specialty
        </h3>
        <div className="space-y-4">
          {[
            { specialty: 'Oncology', recovered: 4200, codes: 12, health: 94 },
            { specialty: 'Gastroenterology', recovered: 3150, codes: 8, health: 98 },
            { specialty: 'Cardiology', recovered: 5100, codes: 15, health: 91 }
          ].map((item, i) => (
            <div key={i} className="flex items-center space-x-4 p-4 rounded-2xl bg-white/5 border border-white/5">
              <div className="flex-1">
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-bold text-slate-200">{item.specialty}</span>
                  <span className="text-sm font-bold text-emerald-400">+${item.recovered}</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5">
                  <div 
                    className="bg-indigo-500 h-1.5 rounded-full" 
                    style={{ width: `${item.health}%` }}
                  ></div>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-bold text-slate-500 uppercase">{item.codes} Flags</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
