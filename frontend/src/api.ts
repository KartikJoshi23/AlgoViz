/**
 * AlgoViz — API Client
 *
 * Axios instance configured for the backend API.
 */

import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
    baseURL: `${API_BASE}/api/v1`,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add auth token if available
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('algoviz_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export const WS_URL = `${API_BASE.replace('http', 'ws')}/ws`;

export default api;
