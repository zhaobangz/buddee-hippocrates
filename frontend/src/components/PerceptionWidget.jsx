import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Scan, Brain, X } from 'lucide-react';

const PerceptionWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const startProcessing = () => {
    setIsProcessing(true);
    setTimeout(() => setIsProcessing(false), 3000);
  };

  return (
    <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            className="absolute bottom-20 left-1/2 -translate-x-1/2 w-80 glass-panel rounded-3xl p-6 overflow-hidden"
          >
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-medical-400 via-brand-cyan to-indigo-500 overflow-hidden">
               {isProcessing && (
                 <motion.div 
                   animate={{ x: ['-100%', '100%'] }} 
                   transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                   className="w-1/2 h-full bg-white shadow-[0_0_15px_rgba(255,255,255,0.8)]"
                 />
               )}
            </div>

            <div className="flex justify-between items-center mb-6">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">Multi-Modal perception</span>
              <button onClick={() => setIsOpen(false)} className="text-slate-500 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex justify-around mb-2">
              <button 
                onClick={startProcessing}
                className="flex flex-col items-center group"
              >
                <div className="w-12 h-12 rounded-2xl bg-medical-500/10 border border-medical-500/20 flex items-center justify-center group-hover:bg-medical-500/20 group-hover:border-medical-500/40 transition-all mb-2">
                  <Mic className="w-5 h-5 text-medical-400" />
                </div>
                <span className="text-[10px] font-bold text-slate-500 group-hover:text-slate-300">VOICE</span>
              </button>
              
              <button 
                onClick={startProcessing}
                className="flex flex-col items-center group"
              >
                <div className="w-12 h-12 rounded-2xl bg-brand-cyan/10 border border-brand-cyan/20 flex items-center justify-center group-hover:bg-brand-cyan/20 group-hover:border-brand-cyan/40 transition-all mb-2">
                  <Scan className="w-5 h-5 text-brand-cyan" />
                </div>
                <span className="text-[10px] font-bold text-slate-500 group-hover:text-slate-300">SCREEN OCR</span>
              </button>

              <button 
                onClick={startProcessing}
                className="flex flex-col items-center group"
              >
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center group-hover:bg-indigo-500/20 group-hover:border-indigo-500/40 transition-all mb-2">
                  <Brain className="w-5 h-5 text-indigo-400" />
                </div>
                <span className="text-[10px] font-bold text-slate-500 group-hover:text-slate-300">CONTEXT</span>
              </button>
            </div>
            
            <div className="mt-4 pt-4 border-t border-white/5 flex flex-col items-center">
              {isProcessing ? (
                <p className="text-xs text-medical-400 animate-pulse font-medium italic">Buddee Health is processing environment...</p>
              ) : (
                <p className="text-xs text-slate-500">Awaiting clinical input...</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(!isOpen)}
        className="w-16 h-16 rounded-full bg-slate-900 border border-white/10 flex items-center justify-center relative shadow-2xl overflow-hidden group"
      >
        <div className="absolute inset-0 bg-gradient-to-tr from-medical-500/20 to-brand-cyan/20 opacity-0 group-hover:opacity-100 transition-opacity" />
        
        {/* The "Orb" core */}
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-medical-400 to-brand-cyan blur shadow-[0_0_20px_rgba(45,212,191,0.5)] animate-pulse" />
        <div className="absolute w-6 h-6 rounded-full border-2 border-white/20 animate-[spin_3s_linear_infinite]" />
        <div className="absolute w-8 h-8 rounded-full border border-white/10 animate-[spin_4s_linear_infinite_reverse]" />
      </motion.button>
    </div>
  );
};

export default PerceptionWidget;
