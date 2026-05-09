/**
 * AlgoViz — Error Boundary
 *
 * Catches React rendering errors and shows a graceful fallback UI
 * instead of a white screen.
 */

import { Component, type ReactNode } from 'react';

interface Props {
    children: ReactNode;
    fallbackMessage?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: { componentStack?: string | null }) {
        console.error('[AlgoViz] Component error:', error, info.componentStack);
    }

    handleRetry = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="error-fallback">
                    <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>⚠️</div>
                    <h3>Something went wrong</h3>
                    <p>{this.props.fallbackMessage || 'This component encountered an error. Try refreshing.'}</p>
                    <button
                        onClick={this.handleRetry}
                        className="btn-primary"
                        style={{
                            padding: '8px 24px',
                            borderRadius: 8,
                            border: 'none',
                            cursor: 'pointer',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                            background: 'var(--gradient-primary)',
                            color: '#fff',
                        }}
                    >
                        Retry
                    </button>
                    {this.state.error && (
                        <pre style={{
                            marginTop: 16,
                            padding: 12,
                            background: 'var(--bg-secondary)',
                            borderRadius: 8,
                            fontSize: '0.72rem',
                            color: 'var(--text-muted)',
                            maxWidth: '100%',
                            overflow: 'auto',
                            textAlign: 'left',
                        }}>
                            {this.state.error.message}
                        </pre>
                    )}
                </div>
            );
        }

        return this.props.children;
    }
}
