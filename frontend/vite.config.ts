import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],server:{port:5173,proxy:{'/api':'https://ai-powered-smart-recruitment-backend-production.up.railway.app/','/health':'https://ai-powered-smart-recruitment-backend-production.up.railway.app/'}}});

