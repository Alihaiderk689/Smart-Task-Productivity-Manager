import { Bot } from 'lucide-react';

const SUGGESTIONS = [
  'What are my tasks today?',
  'Create a meeting tomorrow.',
  'Show overdue tasks.',
  'Complete my assignment.',
  'What reminders do I have today?',
  'How many pending tasks do I have?',
];

export default function SuggestedPrompts({ onSelect }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-2 py-6">
      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center mb-3">
        <Bot className="w-5 h-5 text-white" />
      </div>
      <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">Hi! I'm your TaskFlow Copilot.</p>
      <p className="text-xs text-slate-400 mb-4">Ask me to create, find, or manage your tasks.</p>
      <div className="w-full space-y-1.5">
        {SUGGESTIONS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelect(prompt)}
            className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500/50 hover:bg-indigo-50/50 dark:hover:bg-indigo-500/10 transition-colors"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
