import { Bot, X, Minus, Plus, Trash2 } from 'lucide-react';

export default function ChatHeader({ onClose, onMinimize, minimized, onClear }) {
  return (
    <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-3 bg-gradient-to-r from-violet-600 via-indigo-600 to-purple-600 text-white">
      <div className="flex items-center gap-2 min-w-0">
        <div className="w-7 h-7 shrink-0 rounded-lg bg-white/15 flex items-center justify-center">
          <Bot className="w-4 h-4" />
        </div>
        <span className="font-semibold text-sm truncate">TaskFlow Copilot</span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            aria-label="Clear conversation"
            title="Clear conversation"
            className="p-1.5 rounded-lg hover:bg-white/15 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={onMinimize}
          aria-label={minimized ? 'Expand' : 'Minimize'}
          title={minimized ? 'Expand' : 'Minimize'}
          className="p-1.5 rounded-lg hover:bg-white/15 transition-colors"
        >
          {minimized ? <Plus className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          title="Close"
          className="p-1.5 rounded-lg hover:bg-white/15 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
