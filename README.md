<div align="center">

# ⚡ AlgoViz

### Professional-Grade Algorithmic Trading Intelligence Platform

Real-time market data streaming · ML-powered predictions · On-chain analytics

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

</div>

---

## 🎯 Overview

AlgoViz is a full-stack, production-grade trading intelligence dashboard that streams real-time market data from Binance, computes technical features on-the-fly, runs ML predictions for price direction, and presents everything through a professional dark-mode terminal UI.

> **Not a toy project.** This is a complete trading intelligence platform with a real ML pipeline (scikit-learn ensemble), WebSocket data streaming, rate-limited API, and deployment-ready infrastructure.

---

## ✨ Features

| Category | Features |
|---|---|
| **Real-Time Data** | Binance WebSocket streaming, VWAP/TWAP, spread, velocity, imbalance, volatility |
| **Dashboard** | MarketPulse animated hero, TradingView price chart, order book depth, velocity gauge, spread heatmap, volatility monitor |
| **ML Engine** | RandomForest + GradientBoosting ensemble, SHAP explainability, online retraining, model persistence |
| **Strategies** | Create/manage rule-based strategies, backtest with historical data |
| **Alerts** | Priority-based alert system with toast notifications and Discord webhook support |
| **On-Chain** | Placeholder for Foundry-based Ethereum analytics (whale tracking, DEX analysis) |
| **UX** | Command palette (Ctrl+K), dark/light theme, keyboard navigation, glassmorphism UI |
| **Production** | Rate limiting, request correlation IDs, response timing, health checks, Docker support |

---

## 🏗️ Architecture

```
┌─────────────────────────┐      WebSocket       ┌──────────────────────────┐
│     Frontend (Vercel)    │◄────────────────────►│    Backend (Render)       │
│                          │      REST API        │                          │
│  React 19 + Vite         │◄────────────────────►│  FastAPI + SQLAlchemy     │
│  Zustand + TanStack      │                      │  scikit-learn + SHAP      │
│  TradingView Charts      │                      │  Binance WebSocket        │
│  Framer Motion           │                      │  Rate Limiter + Logging   │
└─────────────────────────┘                      └──────────────────────────┘
                                                          │
                                                          ▼
                                                  ┌──────────────┐
                                                  │   Binance     │
                                                  │   WebSocket   │
                                                  │   (Live Data) │
                                                  └──────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Node.js** ≥ 18 and **npm**
- **Python** ≥ 3.11
- **Git**

### 1. Clone

```bash
git clone https://github.com/KartikJoshi23/AlgoViz.git
cd AlgoViz
```

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000` with docs at `/docs`.

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3002` — the dashboard connects to the backend automatically via the dev proxy.

### 4. Docker (Alternative)

```bash
docker-compose up --build
# Backend → localhost:8001
# Frontend → localhost:3001
```

---

## 🌐 Deployment

### Frontend → Vercel

1. Import repo on [Vercel](https://vercel.com)
2. Set **Root Directory** to `frontend`
3. Set **Framework Preset** to `Vite`
4. Add environment variable:
   ```
   VITE_API_URL = https://your-backend.onrender.com
   ```
5. Deploy

### Backend → Render

1. Create a new **Web Service** on [Render](https://render.com)
2. Connect GitHub repo
3. Set **Root Directory** to `backend`
4. Set **Build Command**: `pip install -r requirements.txt`
5. Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Set environment variables:
   ```
   ENVIRONMENT = production
   DEBUG = false
   SECRET_KEY = <generate-a-strong-key>
   ```
7. Deploy — Render auto-detects the `render.yaml`

> **Important:** After deploying the backend, update the `VITE_API_URL` environment variable on Vercel to point to your Render URL.

---

## 📁 Project Structure

```
AlgoViz/
├── backend/                    # FastAPI backend
│   ├── api/                    # REST API routers
│   │   ├── analytics.py        # ML predictions, SHAP, insights
│   │   ├── alerts.py           # Alert management
│   │   ├── auth.py             # JWT authentication
│   │   ├── market.py           # Market data endpoints
│   │   └── strategies.py       # Strategy CRUD + backtesting
│   ├── core/                   # Middleware & utilities
│   │   └── middleware.py       # Rate limit, timing, request IDs
│   ├── models/                 # SQLAlchemy ORM models
│   ├── services/               # Business logic
│   │   ├── market_data.py      # Binance WS, feature engine
│   │   └── ml_engine.py        # Ensemble ML pipeline + SHAP
│   ├── ws/                     # WebSocket hub
│   ├── config.py               # Pydantic settings
│   ├── database.py             # SQLAlchemy async setup
│   ├── main.py                 # FastAPI app entry point
│   └── requirements.txt        # Python dependencies
│
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   │   ├── MarketPulse.tsx  # Animated market heartbeat hero
│   │   │   ├── PriceChart.tsx   # TradingView lightweight chart
│   │   │   ├── OrderBookChart   # Depth visualization
│   │   │   ├── VelocityGauge   # Radial speedometer
│   │   │   ├── SpreadHeatmap   # Canvas heatmap
│   │   │   ├── VolatilityChart # Area chart with regimes
│   │   │   ├── CommandPalette  # Ctrl+K power-user palette
│   │   │   ├── ToastProvider   # Notification system
│   │   │   └── ...
│   │   ├── pages/              # Route pages
│   │   │   ├── Dashboard.tsx    # Main trading dashboard
│   │   │   ├── Analytics.tsx    # ML predictions & SHAP
│   │   │   ├── Strategies.tsx   # Strategy management
│   │   │   ├── Alerts.tsx       # Alert history
│   │   │   ├── OnChain.tsx      # On-chain analytics (planned)
│   │   │   └── Settings.tsx     # Preferences & theme
│   │   ├── hooks/              # Custom React hooks
│   │   ├── store.ts            # Zustand global state
│   │   ├── api.ts              # Axios client
│   │   └── App.tsx             # Root component
│   ├── vercel.json             # Vercel SPA config
│   └── package.json
│
├── tests/                      # Test suites
├── docker-compose.yml          # Docker dev setup
├── render.yaml                 # Render deployment config
├── .env.example                # Environment template
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite 7, TypeScript 5.9 |
| **State Management** | Zustand, TanStack Query |
| **Charts** | TradingView Lightweight Charts, Canvas API |
| **Animations** | Framer Motion |
| **Styling** | Custom CSS design system (glassmorphism dark theme) |
| **Backend** | FastAPI, SQLAlchemy (async), SQLite |
| **ML/AI** | scikit-learn (RandomForest + GradientBoosting), SHAP |
| **Real-Time** | WebSocket (Binance streams → FastAPI hub → React) |
| **Auth** | JWT (python-jose) |
| **Deployment** | Vercel (frontend), Render (backend), Docker |

---

## 📸 Screenshots

> Screenshots are auto-generated from the running application.

| Dashboard | Analytics |
|---|---|
| MarketPulse hero, live price chart, order book, velocity gauge, spread heatmap | ML predictions, SHAP feature importance, model info |

| Strategies | Settings |
|---|---|
| Create & backtest trading strategies | Theme toggle, connection status, preferences |

---

## 📄 API Documentation

Once the backend is running, interactive API docs are available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`

### Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health + uptime |
| `GET` | `/api/v1/market/features` | Current computed features |
| `GET` | `/api/v1/analytics/prediction` | ML price direction prediction |
| `GET` | `/api/v1/analytics/insights` | Active trading insights |
| `GET` | `/api/v1/analytics/model-info` | ML model status & metrics |
| `GET` | `/api/v1/strategies/` | List all strategies |
| `POST` | `/api/v1/strategies/` | Create a new strategy |
| `WS` | `/ws` | Real-time data stream |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License — see the [LICENSE](./LICENSE) file for details.

---

<div align="center">

**Built with ❤️ by [Kartik Joshi](https://github.com/KartikJoshi23)**

⭐ Star this repo if you find it useful!

</div>
