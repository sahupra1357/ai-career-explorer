import { useState, useRef, useEffect } from 'react';
import { sendExploreMessage } from '../api';
import type { RecommendedField, ExploreResponse } from '../types';
import ChatMessage from './ChatMessage';
import FieldRecommendationCard from './FieldRecommendationCard';

const SESSION_KEY = 'explore_session_id';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatInterfaceProps {
  onDeepDive: (fieldId: string) => void;
}

export default function ChatInterface({ onDeepDive }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: "Hi! I'm here to help you find STEM fields that match your interests. Tell me a bit about yourself — what do you enjoy doing, what subjects excite you, or what kind of problems you'd love to solve?",
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendedField[]>([]);
  const [status, setStatus] = useState<ExploreResponse['status']>('intake');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, recommendations]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);

    const sessionId = sessionStorage.getItem(SESSION_KEY);
    const result = await sendExploreMessage(text, sessionId);

    setLoading(false);

    if (!result.ok) {
      if (result.newSessionId) {
        sessionStorage.setItem(SESSION_KEY, result.newSessionId);
      }
      setError(result.message);
      return;
    }

    const { data } = result;
    sessionStorage.setItem(SESSION_KEY, data.session_id);
    setStatus(data.status);

    if (data.reply) {
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
    }

    if (data.recommended_fields.length > 0) {
      setRecommendations(data.recommended_fields);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleReset() {
    sessionStorage.removeItem(SESSION_KEY);
    setMessages([
      {
        role: 'assistant',
        content: "Hi! I'm here to help you find STEM fields that match your interests. Tell me a bit about yourself — what do you enjoy doing, what subjects excite you, or what kind of problems you'd love to solve?",
      },
    ]);
    setRecommendations([]);
    setStatus('intake');
    setError(null);
    setInput('');
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Chat window */}
      <div className="bg-slate-50 rounded-2xl border border-slate-200 p-4 h-[400px] overflow-y-auto">
        {messages.map((m, i) => (
          <ChatMessage key={i} role={m.role} content={m.content} />
        ))}

        {loading && (
          <div className="flex justify-start mb-3">
            <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-2.5 shadow-sm">
              <div className="flex gap-1 items-center h-4">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 my-2">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tell me about your interests… (Enter to send)"
          rows={2}
          disabled={loading || status === 'complete'}
          className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-50 disabled:text-slate-400"
        />
        <div className="flex flex-col gap-1.5">
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading || status === 'complete'}
            className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
          <button
            onClick={handleReset}
            className="px-4 py-2 rounded-xl border border-slate-200 text-slate-500 text-sm hover:bg-slate-50 transition-colors"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Fields that match your profile
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {recommendations.map((f) => (
              <FieldRecommendationCard key={f.field_id} field={f} onDeepDive={onDeepDive} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
