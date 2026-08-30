import { AlertTriangle, RefreshCw } from 'lucide-react';
import { getErrorMessage } from '@/services/api';

export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="w-8 h-8 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}

export function ErrorState({ error = null, message = '', onRetry = null }) {
  const text = message || getErrorMessage(error, 'Something went wrong. Please try again.');
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-6">
      <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-500/10 flex items-center justify-center">
        <AlertTriangle className="w-6 h-6 text-red-500" />
      </div>
      <p className="text-slate-600 dark:text-slate-300 max-w-sm">{text}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
      )}
    </div>
  );
}
