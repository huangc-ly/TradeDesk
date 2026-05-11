# TradeDesk

Personal quantitative trading system.

## Tech Stack

- **Backend**: FastAPI + DuckDB
- **Frontend**: Vue 3 + TypeScript + Element Plus + ECharts

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs for API documentation.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173 for the app.

## Project Structure

```
TradeDesk/
├── backend/          # FastAPI backend
│   └── app/
│       ├── api/      # API routers
│       ├── core/     # Config & database
│       ├── models/   # Data models
│       └── schemas/  # Pydantic schemas
├── frontend/         # Vue 3 frontend
│   └── src/
│       ├── api/      # HTTP client
│       ├── components/
│       ├── layouts/
│       ├── router/
│       ├── stores/   # Pinia stores
│       └── views/    # Page views
├── stocks/           # Daily stock data (parquet)
├── indexes/          # Index data (parquet)
└── docker-compose.yml
```
