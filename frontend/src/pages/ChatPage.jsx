import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Send, 
  Mic, 
  Paperclip, 
  Sparkles, 
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  Stethoscope
} from 'lucide-react';
import useStore from '../store/useStore';

const ChatPage = () => {
  const [input, setInput] = useState('');
  const messages = useStore((state) => state.messages);
  const sendMessage = useStore((state) => state.sendMessage);
  const chatEndRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6 pb-24">
        <AnimatePresence initial={false}>
          {messages.map((msg, index) => (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[85%] ${msg.role === 'user' ? 'bg-medical-600 text-white rounded-2xl rounded-tr-sm p-4' : 'glass-panel rounded-2xl rounded-tl-sm p-6 overflow-hidden relative'}`}>
                {msg.role === 'assistant' && (
                  <div className={`absolute top-0 left-0 w-1 h-full ${msg.isError ? 'bg-rose-500' : 'bg-medical-500'}`} />
                )}
                
                <div className="flex items-start space-x-3">
                  {msg.role === 'assistant' && (
                    <div className={`w-8 h-8 rounded-lg ${msg.isError ? 'bg-rose-500/10' : 'bg-medical-500/10'} flex items-center justify-center flex-shrink-0`}>
                      <Sparkles className={`w-4 h-4 ${msg.isError ? 'text-rose-400' : 'text-medical-400'}`} />
                    </div>
                  )}
                  <div className="flex-1 space-y-4">
                    <p className={`text-sm leading-relaxed ${msg.isError ? 'text-rose-400' : 'text-slate-200'}`}>{msg.content}</p>
                    
                    {msg.citations && (
                      <div className="pt-4 border-t border-white/5 space-y-2">
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center">
                          <ShieldCheck className="w-3 h-3 mr-1.5" />
                          Clinical Citations
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {msg.citations.map((cite, i) => (
                            <button key={i} className="text-[10px] bg-white/5 border border-white/10 px-2 py-1 rounded text-slate-400 hover:text-medical-400 transition-colors flex items-center">
                              {cite}
                              <ExternalLink className="w-2 h-2 ml-1" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={chatEndRef} />
      </div>

      {/* Input Area */}
      <div className="absolute bottom-6 left-6 right-6 lg:left-0 lg:right-0 max-w-4xl mx-auto">
        <div className="glass-panel p-2 rounded-2xl border-white/10 shadow-2xl relative">
          <div className="flex items-center space-x-2">
            <button className="p-2 text-slate-500 hover:text-white transition-colors">
              <Paperclip className="w-5 h-5" />
            </button>
            <input 
              type="text" 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Type clinical query or action (e.g. 'Draft Prior Auth for Farxiga')..."
              className="flex-1 bg-transparent border-0 focus:ring-0 text-sm py-3 text-slate-200"
            />
            <div className="flex items-center space-x-1 pr-1">
              <button className="p-2 text-slate-500 hover:text-medical-400 transition-colors">
                <Mic className="w-5 h-5" />
              </button>
              <button 
                onClick={handleSend}
                className="w-10 h-10 bg-medical-500 hover:bg-medical-400 text-white flex items-center justify-center rounded-xl transition-all shadow-lg shadow-medical-500/20"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
        
        <div className="flex justify-center mt-3">
          <p className="text-[10px] text-slate-500 flex items-center">
            <Stethoscope className="w-3 h-3 mr-2" />
            Clinical Decision Support: This tool does not provide medical diagnoses or prescriptions.
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
