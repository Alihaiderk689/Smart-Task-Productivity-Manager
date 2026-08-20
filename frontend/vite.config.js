import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = dirname(fileURLToPath(import.meta.url))

// Same default api.js itself falls back to when VITE_API_ROOT is unset --
// a relative path, meaning same-origin (through this dev server's own
// /api proxy below in dev, or nginx's /api proxy in the docker-compose
// deployment). Only the Vercel+Render production deployment sets this to
// a full cross-origin URL (configured directly in Vercel's own env var
// UI, not committed anywhere in this repo).
const DEFAULT_API_ROOT = '/api'

function resolveApiOrigin(apiRoot) {
  if (!apiRoot || apiRoot.startsWith('/')) {
    return null // same-origin -- 'self' in the CSP below already covers it
  }
  try {
    return new URL(apiRoot).origin
  } catch {
    return null
  }
}

// Injects a Content-Security-Policy <meta> tag into the built index.html.
// A <meta> tag (not a response header) is the only option here because
// this SPA is served as static files by Vercel or nginx -- see
// frontend/vercel.json / frontend/nginx.conf -- never by this Django-free
// Vite build itself, so there's no request/response cycle at serve time
// for a header to be attached to. (frame-ancestors doesn't work via
// <meta> per spec; frontend/vercel.json and frontend/nginx.conf carry a
// static X-Frame-Options header instead to cover that.)
//
// The API origin is computed from VITE_API_ROOT at BUILD time -- the same
// env var api.js itself reads -- specifically so this can't drift out of
// sync with whatever backend the build was actually pointed at: Vercel
// and the Docker build both already inject VITE_API_ROOT as a real env
// var before `npm run build` runs (see frontend/Dockerfile), so there's
// nothing to hand-maintain per deployment.
function htmlSecurityHeaders() {
  return {
    name: 'html-security-headers',
    transformIndexHtml(html, ctx) {
      const apiRoot = ctx.server
        ? DEFAULT_API_ROOT // `vite dev` -- always same-origin via the proxy below
        : (loadEnv(process.env.NODE_ENV ?? 'production', projectRoot, 'VITE_').VITE_API_ROOT || DEFAULT_API_ROOT)
      const apiOrigin = resolveApiOrigin(apiRoot)

      const directives = {
        'default-src': ["'self'"],
        // Google Identity Services' own script -- see GoogleLoginButton.jsx
        // (@react-oauth/google), which loads it dynamically. No
        // 'unsafe-inline': the one script index.html needs is now an
        // external file (theme-init.js) precisely so this can stay strict.
        'script-src': ["'self'", 'https://accounts.google.com'],
        // Component-library inline `style="..."` attributes (Radix/shadcn-
        // style dynamic positioning, animation, etc.) are pervasive in
        // this codebase and aren't practical to eliminate or hash for a
        // static SPA build -- 'unsafe-inline' here is a deliberate,
        // narrower concession than allowing it on script-src too.
        // https://accounts.google.com is the Google Sign-In widget's own
        // stylesheet (accounts.google.com/gsi/style) -- confirmed needed
        // by actually loading the login page under this policy in a real
        // browser, not guessed (it 404'd the first time this was written).
        'style-src': ["'self'", "'unsafe-inline'", 'https://accounts.google.com'],
        'img-src': ["'self'", 'data:', 'https://res.cloudinary.com'],
        'font-src': ["'self'", 'data:'],
        // The Google Sign-In button itself renders inside an iframe Google
        // serves.
        'frame-src': ['https://accounts.google.com'],
        'connect-src': ["'self'", 'https://accounts.google.com'],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
      }

      if (apiOrigin) {
        directives['connect-src'].push(apiOrigin)
        // Locally-stored (non-Cloudinary) avatars are served from the
        // backend's own /media/ path -- same-origin when apiOrigin is
        // null (nginx/dev-proxy deployments), otherwise this is the only
        // other place they can come from.
        directives['img-src'].push(apiOrigin)
      }

      const csp = Object.entries(directives)
        .map(([key, values]) => `${key} ${values.join(' ')}`)
        .join('; ')

      return {
        html,
        tags: [
          {
            tag: 'meta',
            attrs: { 'http-equiv': 'Content-Security-Policy', content: csp },
            injectTo: 'head-prepend',
          },
        ],
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), htmlSecurityHeaders()],
  resolve: {
    alias: {
      '@': resolve(projectRoot, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
