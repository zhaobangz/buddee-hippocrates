import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  ExternalLink,
  MessageSquare,
  WifiOff,
} from 'lucide-react';
import useStore from '../store/useStore';

const ChatPage = () => {
  const [input, setInput] = useState('');
  const messages = useStore((state) => state.messages);
  const sendMessage = useStore((state) => state.sendMessage);
  const demoMode = useStore((state) => state.demoMode);
  const chatEndRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const askBuddiPrompts = [
    'Which HCC codes are at risk for the current encounter?',
    'Draft a prior-auth letter for this patient',
    'Summarize audit exposure for this encounter',
    'What documentation supports the chief complaint?',
  ];

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 220px)' }}>
      {/* Demo mode banner */}
      {demoMode && (
        <div
          className="flex items-center gap-2 px-4 py-2.5 rounded-card mb-4 text-sm"
          style={{
            backgroundColor: 'var(--color-caution-bg, #FEF3E2)',
            color: '#B45309',
            border: '1px solid rgba(180, 83, 9, 0.2)',
          }}
        >
          <WifiOff size={16} />
          <span>
            Demo mode — responses are pre-written samples, not the live clinical agent.
          </span>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4" role="log" aria-live="polite" aria-label="Chat messages">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-card p-4 ${
                msg.role === 'user'
                  ? 'text-white'
                  : ''
              }`}
              style={
                msg.role === 'user'
                  ? { backgroundColor: 'var(--color-primary)' }
                  : {
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-ink)',
                    }
              }
            >
              {/* Assistant icon */}
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mb-2">
                  <div
                    className="w-6 h-6 rounded flex items-center justify-center"
                    style={{
                      backgroundColor: msg.isError
                        ? 'var(--color-risk-bg, #FDECEF)'
                        : 'var(--color-fill)',
                    }}
                  >
                    <Sparkles
                      size={14}
                      style={{
                        color: msg.isError ? '#BE123C' : 'var(--color-primary)',
                      }}
                    />
                  </div>
                  <span className="text-xs font-medium" style={{ color: 'var(--color-muted)' }}>
                    Buddee
                  </span>
                </div>
              )}

              {/* Message content */}
              <p
                className="text-sm leading-relaxed whitespace-pre-wrap"
                style={msg.role === 'user' ? { color: '#FFFFFF' } : msg.isError ? { color: '#BE123C' } : {}}
              >
                {msg.content}
              </p>

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--color-border)' }}>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                      Sources:
                    </span>
                    {msg.citations.map((cite, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--color-fill)',
                          color: 'var(--color-secondary)',
                        }}
                      >
                        {cite}
                        <ExternalLink size={10} />
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Empty state — starter prompts */}
      {messages.length <= 1 && !demoMode && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-3">
            <MessageSquare size={16} style={{ color: 'var(--color-muted)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
              Ask about coding, documentation, or prior auth for the encounter you're reviewing
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {askBuddiPrompts.map((q) => (
              <button
                key={q}
                onClick={() => {
                  sendMessage(q);
                }}
                className="btn-ghost btn-sm text-left"
                style={{
                  border: '1px solid var(--color-border)',
                  maxWidth: '320px',
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input area — normal flow, not absolutely positioned */}
      <div className="flex-shrink-0">
        <div
          className="flex items-center gap-2 rounded-card border p-2"
          style={{
            backgroundColor: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about coding, documentation, or prior auth…"
            className="flex-1 bg-transparent border-0 focus:ring-0 text-sm px-2 py-2"
            style={{ color: 'var(--color-ink)', outline: 'none' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="btn-primary btn-sm !min-h-[36px] !min-w-[36px] !p-0 rounded-control flex items-center justify-center"
            aria-label="Send message"
          >
            <Send size={16} />
          </button>
        </div>

        <p className="text-xs text-center mt-3" style={{ color: 'var(--color-muted)' }}>
          Buddee provides coding and documentation support, not medical advice. Nothing here is submitted anywhere.
        </p>
      </div>
    </div>
  );
};

export default ChatPage;
