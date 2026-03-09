/**
 * AlgoViz — WebSocket Hook
 *
 * Manages the WebSocket connection to the backend,
 * dispatching messages to the Zustand store.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { WS_URL } from '../api';

export function useWebSocket() {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
    const attempt = useRef(0);

    const { setWsStatus, setConnected, updateFeatures, addTrade, setInsights, addAlert } =
        useStore();

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        setWsStatus('connecting');
        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            setWsStatus('connected');
            setConnected(true);
            attempt.current = 0;
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);

                switch (msg.type) {
                    case 'features':
                        updateFeatures(msg.data);
                        break;
                    case 'trade':
                        addTrade(msg.data);
                        break;
                    case 'insights':
                        setInsights(msg.data);
                        break;
                    case 'alert':
                        addAlert(msg.data);
                        break;
                }
            } catch (err) {
                // ignore parse errors
            }
        };

        ws.onclose = () => {
            setWsStatus('disconnected');
            setConnected(false);
            wsRef.current = null;

            // Auto-reconnect with backoff
            attempt.current += 1;
            const delay = Math.min(1000 * 2 ** attempt.current, 30000);
            reconnectTimer.current = setTimeout(connect, delay);
        };

        ws.onerror = () => {
            ws.close();
        };

        wsRef.current = ws;
    }, [setWsStatus, setConnected, updateFeatures, addTrade, setInsights, addAlert]);

    useEffect(() => {
        connect();

        return () => {
            clearTimeout(reconnectTimer.current);
            wsRef.current?.close();
        };
    }, [connect]);

    return {
        connected: useStore((s) => s.connected),
        status: useStore((s) => s.wsStatus),
    };
}
