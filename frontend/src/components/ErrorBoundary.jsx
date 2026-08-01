import { Component } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

// Error boundaries must be class components -- React has no hook equivalent
// for getDerivedStateFromError/componentDidCatch. Without this, a render
// crash anywhere in the tree unmounts the whole app to a blank white screen
// with no feedback at all.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // eslint-disable-next-line no-console
    console.error('Unhandled error caught by ErrorBoundary:', error, errorInfo);
  }

  handleReload = () => {
    window.location.href = '/';
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50 dark:bg-slate-950">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-red-100 dark:bg-red-500/10 mx-auto">
            <AlertTriangle className="w-7 h-7 text-red-600 dark:text-red-400" aria-hidden="true" />
          </div>
          <div className="space-y-3">
            <h1 className="text-2xl font-medium text-slate-800 dark:text-slate-200">
              Something went wrong
            </h1>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              An unexpected error occurred. Reloading usually fixes it -- if it keeps happening, let us know what you were doing.
            </p>
          </div>
          <button
            onClick={this.handleReload}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
            Reload app
          </button>
        </div>
      </div>
    );
  }
}
