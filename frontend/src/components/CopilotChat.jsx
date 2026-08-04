import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import ChatHeader from './ChatHeader';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';
import { userCopilotApi, getErrorMessage } from '@/services/api';

// Session-only memory, per the spec -- nothing here is ever sent to a
// database. sessionStorage (not localStorage) is deliberate: it survives
// client-side route navigation within the app but clears itself the
// moment the browser tab closes, matching "remember during the current
// browser session" exactly without needing any backend persistence.
const STORAGE_KEY = 'taskflow-copilot-history';

function loadHistory() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(messages) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    // sessionStorage can throw in private-browsing/quota-exceeded edge
    // cases -- losing the persisted copy isn't worth crashing the chat.
  }
}

export default function CopilotChat({ open, onClose }) {
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [minimized, setMinimized] = useState(false);

  useEffect(() => {
    saveHistory(messages);
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    // Close on an outside click, but never on a click inside the panel
    // itself or on the toggle button that opened it -- CopilotButton
    // carries the same [data-copilot-widget] marker specifically so a
    // click on it doesn't get treated as "outside" here (which would
    // otherwise race against the button's own open/close toggle: this
    // handler closes it, then the button's click handler immediately
    // reopens it).
    const handlePointerDown = (e) => {
      if (!e.target.closest('[data-copilot-widget]')) onClose();
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  const sendMessage = async (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed || sending) return;

    // The backend is stateless -- it only knows this conversation's past
    // turns because we resend them every time (see
    // usercopilot/services/chat_service.py's module docstring).
    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content: trimmed }]);
    setInput('');
    setSending(true);
    try {
      const { data } = await userCopilotApi.chatSend(trimmed, history);
      setMessages((prev) => [...prev, { id: `local-reply-${Date.now()}`, role: 'assistant', content: data.reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { id: `local-error-${Date.now()}`, role: 'assistant', content: getErrorMessage(err, 'Something went wrong -- please try again.') }]);
    } finally {
      setSending(false);
    }
  };

  const handleClear = () => {
    setMessages([]);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.96 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          data-copilot-widget
          className="fixed top-20 right-4 sm:right-8 z-50 w-[calc(100vw-2rem)] sm:w-[420px] max-w-[440px] bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col overflow-hidden"
          style={{ height: minimized ? 'auto' : 'min(620px, calc(100vh - 6rem))' }}
        >
          <ChatHeader
            onClose={onClose}
            onMinimize={() => setMinimized((m) => !m)}
            minimized={minimized}
            onClear={messages.length > 0 ? handleClear : null}
          />
          {!minimized && (
            <>
              <ChatMessages messages={messages} sending={sending} onSuggestionSelect={sendMessage} />
              <ChatInput value={input} onChange={setInput} onSend={() => sendMessage(input)} disabled={sending} />
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
