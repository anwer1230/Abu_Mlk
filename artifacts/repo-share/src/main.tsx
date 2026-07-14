import { createRoot } from 'react-dom/client';
import { setBaseUrl } from '@workspace/api-client-react';

import App from './App';

import './index.css';

// On Replit the frontend and API share one origin, so relative "/api/..."
// paths just work. When deploying the frontend and backend as separate
// services (e.g. on Render), set VITE_API_BASE_URL at build time to the
// backend's full URL so API calls resolve correctly.
const externalApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
if (externalApiBaseUrl) {
  setBaseUrl(externalApiBaseUrl);
}

createRoot(document.getElementById('root')!).render(<App />);
