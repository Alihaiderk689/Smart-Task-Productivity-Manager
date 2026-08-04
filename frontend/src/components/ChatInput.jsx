import { Send } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

export default function ChatInput({ value, onChange, onSend, disabled }) {
  const handleKeyDown = (e) => {
    // Enter sends; Shift+Enter inserts a newline (standard chat UX --
    // ChatGPT/Copilot Chat/Intercom all do this).
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="border-t border-slate-100 dark:border-slate-800 p-3 flex items-end gap-2 bg-white dark:bg-slate-900">
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask your Copilot..."
        disabled={disabled}
        rows={1}
        className="min-h-[40px] max-h-32 resize-none text-sm py-2.5"
      />
      <button
        type="button"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className={cn(
          'shrink-0 flex items-center justify-center w-9 h-9 rounded-xl text-white transition-colors',
          'bg-gradient-to-br from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500',
          'disabled:opacity-40 disabled:cursor-not-allowed'
        )}
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  );
}
