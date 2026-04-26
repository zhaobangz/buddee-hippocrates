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
import useStore from '../store/useStore';

const AnalyticsDashboard = () => {
  const [isVerifying, setIsVerifying] = useState(false);
  const [lastVerify, setLastVerify] = useState(new Date().toLocaleTimeString());
  const metrics = useStore((state) => state.dashboardMetrics);
  const fetchDashboardMetrics = useStore((state) => state.fetchDashboardMetrics);
  const verifyAuditTrail = useStore((state) => state.verifyAuditTrail);

  useEffect(() => {
    fetchDashboardMetrics();
  }, [fetchDashboardMetrics]);

  const handleVerify = async () => {
    setIsVerifying(true);
    await verifyAuditTrail();
    setLastVerify(new Date().toLocaleTimeString());
    setIsVerifying(false);
  };

  const revenue = metrics.total_recovered_revenue || 0;
  const codeCount = metrics.missed_codes_found || 0;
  const avgValue = metrics.average_value_per_encounter || 0;
  const topCategories = metrics.top_categories?.length
    ? metrics.top_categories
    : [{ category: 'Run shadow audit', recovered: 0, codes: 0 }];

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
            ${revenue.toLocaleString()}
          </h2>
          <p className="text-xs text-emerald-500/80 mt-2 font-medium">
            {metrics.demo ? 'Synthetic demo estimate' : '+ live from accepted recovery events'}
          </p>
        </motion.div>

        {/* Integrity Card */}
        <motion.div 
          whileHover={{ y: -5 }}
          className="glass-panel p-6 border-l-4 border-l-indigo-500 bg-indigo-500/5"
        >
          <div className="flex justify-between items-start mb-4">
            <div className={`p-2 rounded-lg ${metrics.audit_integrity_status ? 'bg-indigo-500/10 text-indigo-400' : 'bg-rose-500/10 text-rose-400'}`}>
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
            {metrics.audit_integrity_status || 'pending'}
          </h2>
          <p className="text-xs text-slate-500 mt-2">Last verified: {lastVerify}</p>
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
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Missed Codes Found</p>
          <h2 className="text-3xl font-bold text-slate-100 mt-1">
            {codeCount}
          </h2>
          <p className="text-xs text-slate-500 mt-2">
            ${avgValue.toLocaleString()} average value / encounter
          </p>
        </motion.div>
      </div>

      {/* Specialty Breakdown */}
      <div className="glass-panel p-8">
        <h3 className="text-lg font-bold text-slate-100 mb-6 flex items-center">
          <ShieldAlert className="w-5 h-5 mr-3 text-indigo-400" />
          Top Recovered Code Categories
        </h3>
        <div className="space-y-4">
          {topCategories.map((item, i) => (
            <div key={i} className="flex items-center space-x-4 p-4 rounded-2xl bg-white/5 border border-white/5">
              <div className="flex-1">
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-bold text-slate-200">{item.category}</span>
                  <span className="text-sm font-bold text-emerald-400">+${Number(item.recovered || 0).toLocaleString()}</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5">
                  <div 
                    className="bg-indigo-500 h-1.5 rounded-full" 
                    style={{ width: `${Math.min(100, Math.max(8, ((item.recovered || 0) / Math.max(revenue, 1)) * 100))}%` }}
                  ></div>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-bold text-slate-500 uppercase">{item.codes} Codes</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
