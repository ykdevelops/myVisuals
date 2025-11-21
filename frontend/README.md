# AudioGiphy Frontend

Vue.js frontend for AudioGiphy video renderer.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Development

- `npm run dev` - Start Vite dev server
- `npm run build` - Build for production
- `npm run preview` - Preview production build

## Backend

Make sure the Flask API server is running:
```bash
python -m audiogiphy.api_server
```

The API runs on `http://localhost:5000` and the frontend proxies `/api` requests to it.


