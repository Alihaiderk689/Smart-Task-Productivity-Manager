import { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { MessageSquare, Send, Loader2 } from 'lucide-react';
import { copilotApi, getErrorMessage } from '@/services/api';
import { cn } from '@/lib/utils';

// Shared "ask the copilot" chat box -- same live Groq-backed chat used on
// the full Admin Copilot page, embeddable anywhere an admin should be able
// to query the system in plain English (e.g. straight from the dashboard).
// Each mount is scoped to its own `sessionId` so a conversation started here
// doesn't get mixed into a different session's history.
export default function CopilotQueryBox({
  sessionId = 'default',
  title = 'Ask the Copilot',
  placeholder = 'e.g. Which users have been inactive for 90+ days?',
  emptyHint = 'Ask about task stats, inactive users, overdue tasks, or ask it to propose an action for your approval.',
  onProposed = undefined,
  className = undefined,
}) {
  const [llmConfigured, setLlmConfigured] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messageListRef = useRef(null);

  useEffect(() => {
    copilotApi.dashboardSummary().then(({ data }) => setLlmConfigured(data.llm_configured)).catch(() => {});
  }, []);

  useEffect(() => {
    copilotApi.chatHistory(sessionId).then(({ data }) => setMessages(data)).catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    // Scroll only the message list itself, not `messagesEndRef.scrollIntoView()`
    // -- that scrolls every ancestor scroll container into view, including the
    // page's own scroll on pages (like the dashboard) where this box sits
    // mid-page, yanking the whole window down every time a message arrives.
    const el = messageListRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const handleSend = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'admin', content: text }]);
    setInput('');
    setSending(true);
    try {
      const { data } = await copilotApi.chatSend(text, sessionId);
      setMessages((prev) => [...prev, { id: `local-reply-${Date.now()}`, role: 'agent', content: data.reply }]);
      if (data.proposed_recommendation) {
        toast.success(`Proposed: ${data.proposed_recommendation.title} -- awaiting your approval.`);
        onProposed?.(data.proposed_recommendation);
      }
    } catch (err) {
      setMessages((prev) => [...prev, { id: `local-error-${Date.now()}`, role: 'agent', content: getErrorMessage(err, 'Something went wrong.') }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={cn('bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-5', className)}>
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 flex items-center gap-2">
        <MessageSquare className="w-4 h-4" /> {title}
      </h2>

      <div ref={messageListRef} className="h-72 overflow-y-auto rounded-xl border border-slate-100 dark:border-slate-800 p-3 mb-3 space-y-2 bg-slate-50/50 dark:bg-slate-950/40">
        {messages.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8">{emptyHint}</p>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={cn('flex', m.role === 'admin' ? 'justify-end' : 'justify-start')}>
              <div
                className={cn(
                  'max-w-[80%] px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap',
                  m.role === 'admin'
                    ? 'bg-indigo-600 text-white rounded-br-sm'
                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-100 dark:border-slate-700 rounded-bl-sm'
                )}
              >
                {m.content}
              </div>
            </div>
          ))
        )}
        {sending && (
          <div className="flex justify-start">
            <div className="px-3 py-2 rounded-2xl rounded-bl-sm bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
              <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
            </div>
          </div>
        )}
      </div>

      {llmConfigured ? (
        <form onSubmit={handleSend} className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            disabled={sending}
            className="flex-1 px-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/30 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="shrink-0 flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      ) : (
        <p className="text-sm text-slate-400 text-center py-2">
          Chat requires <code className="font-mono">GROQ_API_KEY</code> to be configured.
        </p>
      )}
    </div>
  );
}
