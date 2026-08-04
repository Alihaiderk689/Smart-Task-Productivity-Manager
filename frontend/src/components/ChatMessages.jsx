import { useEffect, useRef } from 'react';
import ChatMessage from './ChatMessage';
import SuggestedPrompts from './SuggestedPrompts';

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 px-3.5 py-3 rounded-2xl rounded-bl-sm bg-slate-100 dark:bg-slate-800">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce"
            style={{ animationDelay: `${i * 0.12}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function ChatMessages({ messages, sending, onSuggestionSelect }) {
  const containerRef = useRef(null);

  useEffect(() => {
    // Scroll only this container's own scroll position, never
    // scrollIntoView() -- that bubbles to every ancestor scroll container
    // including the page itself, yanking the whole dashboard down every
    // time a message arrives (a real bug hit and fixed elsewhere in this
    // app's chat widgets).
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3 bg-slate-50/50 dark:bg-slate-950/40">
      {messages.length === 0 ? (
        <SuggestedPrompts onSelect={onSuggestionSelect} />
      ) : (
        messages.map((m) => <ChatMessage key={m.id} role={m.role} content={m.content} />)
      )}
      {sending && <TypingIndicator />}
    </div>
  );
}
