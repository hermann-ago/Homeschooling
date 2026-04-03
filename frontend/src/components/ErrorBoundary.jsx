import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

/**
 * Error boundary component that catches React rendering errors
 * and shows a friendly fallback UI instead of a blank screen.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-full p-8">
          <div className="bg-surface rounded-2xl border border-border p-8 sm:p-12 text-center shadow-soft max-w-md">
            <div className="w-16 h-16 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-bold text-text-primary mb-2">Something went wrong</h2>
            <p className="text-text-secondary text-sm mb-6">
              An unexpected error occurred. Please try refreshing the page.
            </p>
            <button
              onClick={this.handleRetry}
              className="flex items-center mx-auto bg-accent text-white px-5 py-2.5 rounded-xl font-medium shadow-sm hover:bg-accent-hover transition"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
