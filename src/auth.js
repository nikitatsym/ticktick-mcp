#!/usr/bin/env node

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { URL } from 'node:url';
import open from 'open';

const TICKTICK_AUTH_URL = 'https://ticktick.com/oauth/authorize';
const TICKTICK_TOKEN_URL = 'https://ticktick.com/oauth/token';
const CALLBACK_PORT = 8585;
const REDIRECT_URI = `http://localhost:${CALLBACK_PORT}/callback`;
const SCOPES = 'tasks:read tasks:write';
const TOKEN_DIR = path.join(process.env.HOME || process.env.USERPROFILE || '', '.ticktick-mcp');
const TOKEN_FILE = path.join(TOKEN_DIR, 'tokens.json');

/**
 * Save tokens to disk.
 */
export function saveTokens(tokens) {
  fs.mkdirSync(TOKEN_DIR, { recursive: true });
  fs.writeFileSync(TOKEN_FILE, JSON.stringify(tokens, null, 2), 'utf-8');
}

/**
 * Load tokens from disk.
 */
export function loadTokens() {
  try {
    return JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8'));
  } catch {
    return null;
  }
}

/**
 * Exchange authorization code for tokens.
 */
export async function exchangeCode(code, clientId, clientSecret) {
  const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: REDIRECT_URI,
    scope: SCOPES,
  });

  const res = await fetch(TICKTICK_TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${basicAuth}`,
    },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token exchange failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    token_type: data.token_type,
    expires_at: Date.now() + (data.expires_in || 3600) * 1000,
    scope: data.scope,
  };
}

/**
 * Refresh an expired access token.
 */
export async function refreshAccessToken(refreshToken, clientId, clientSecret) {
  const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
  });

  const res = await fetch(TICKTICK_TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${basicAuth}`,
    },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token refresh failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token || refreshToken,
    token_type: data.token_type,
    expires_at: Date.now() + (data.expires_in || 3600) * 1000,
    scope: data.scope,
  };
}

/**
 * Run the interactive OAuth flow: open browser, catch callback, exchange code.
 * Returns token object.
 */
export function runOAuthFlow(clientId, clientSecret) {
  return new Promise((resolve, reject) => {
    const state = Math.random().toString(36).slice(2);

    const server = http.createServer(async (req, res) => {
      const url = new URL(req.url, `http://localhost:${CALLBACK_PORT}`);
      if (url.pathname !== '/callback') {
        res.writeHead(404);
        res.end('Not found');
        return;
      }

      const code = url.searchParams.get('code');
      const returnedState = url.searchParams.get('state');

      if (returnedState !== state) {
        res.writeHead(400);
        res.end('State mismatch — possible CSRF attack. Please try again.');
        server.close();
        reject(new Error('State mismatch'));
        return;
      }

      if (!code) {
        res.writeHead(400);
        res.end('No authorization code received.');
        server.close();
        reject(new Error('No code'));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`
        <html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
          <div style="text-align:center">
            <h1>✅ Authorized!</h1>
            <p>You can close this tab and return to your terminal.</p>
          </div>
        </body></html>
      `);

      try {
        const tokens = await exchangeCode(code, clientId, clientSecret);
        server.close();
        resolve(tokens);
      } catch (err) {
        server.close();
        reject(err);
      }
    });

    server.listen(CALLBACK_PORT, () => {
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: REDIRECT_URI,
        response_type: 'code',
        scope: SCOPES,
        state,
      });

      const authUrl = `${TICKTICK_AUTH_URL}?${params}`;
      console.error(`Opening browser for TickTick authorization...`);
      console.error(`If the browser doesn't open, go to:\n${authUrl}\n`);
      open(authUrl).catch(() => {});
    });

    server.on('error', (err) => {
      reject(new Error(`Could not start OAuth callback server on port ${CALLBACK_PORT}: ${err.message}`));
    });

    // Timeout after 5 minutes
    setTimeout(() => {
      server.close();
      reject(new Error('OAuth flow timed out after 5 minutes'));
    }, 5 * 60 * 1000);
  });
}

/**
 * Get a valid access token — from env, file, or interactive flow.
 * Returns { accessToken, tokens } where tokens is the full token object.
 */
export async function getAccessToken(clientId, clientSecret) {
  // Priority 1: env vars
  if (process.env.TICKTICK_ACCESS_TOKEN) {
    return {
      accessToken: process.env.TICKTICK_ACCESS_TOKEN,
      tokens: {
        access_token: process.env.TICKTICK_ACCESS_TOKEN,
        refresh_token: process.env.TICKTICK_REFRESH_TOKEN || null,
        expires_at: null, // unknown
      },
    };
  }

  // Priority 2: saved tokens
  let tokens = loadTokens();

  if (tokens) {
    // Check expiry (with 60s buffer)
    if (tokens.expires_at && Date.now() > tokens.expires_at - 60_000) {
      if (tokens.refresh_token && clientId && clientSecret) {
        console.error('Access token expired, refreshing...');
        try {
          tokens = await refreshAccessToken(tokens.refresh_token, clientId, clientSecret);
          saveTokens(tokens);
          console.error('Token refreshed successfully.');
        } catch (err) {
          console.error(`Token refresh failed: ${err.message}`);
          tokens = null; // fall through to interactive flow
        }
      } else {
        tokens = null;
      }
    }
  }

  if (tokens) {
    return { accessToken: tokens.access_token, tokens };
  }

  // Priority 3: interactive OAuth flow
  if (!clientId || !clientSecret) {
    throw new Error(
      'No tokens found and TICKTICK_CLIENT_ID / TICKTICK_CLIENT_SECRET are not set.\n' +
        'Either set TICKTICK_ACCESS_TOKEN directly, or provide client credentials for OAuth flow.\n' +
        'See README.md for setup instructions.'
    );
  }

  console.error('No saved tokens found, starting OAuth flow...');
  tokens = await runOAuthFlow(clientId, clientSecret);
  saveTokens(tokens);
  console.error('Tokens saved to ' + TOKEN_FILE);
  return { accessToken: tokens.access_token, tokens };
}

// Standalone mode — run `node auth.js` to get tokens
const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname);

if (isMain) {
  const clientId = process.env.TICKTICK_CLIENT_ID;
  const clientSecret = process.env.TICKTICK_CLIENT_SECRET;

  if (!clientId || !clientSecret) {
    console.error('Usage:');
    console.error('  TICKTICK_CLIENT_ID=xxx TICKTICK_CLIENT_SECRET=yyy node src/auth.js');
    console.error('');
    console.error('Register your app at https://developer.ticktick.com');
    console.error('Set redirect URI to http://localhost:8585/callback');
    process.exit(1);
  }

  try {
    const tokens = await runOAuthFlow(clientId, clientSecret);
    saveTokens(tokens);

    console.log('\n=== Tokens received! ===\n');
    console.log('Saved to:', TOKEN_FILE);
    console.log('\nFor remote server setup, add these env variables to your MCP config:\n');
    console.log(JSON.stringify({
      TICKTICK_CLIENT_ID: clientId,
      TICKTICK_CLIENT_SECRET: clientSecret,
      TICKTICK_ACCESS_TOKEN: tokens.access_token,
      TICKTICK_REFRESH_TOKEN: tokens.refresh_token,
    }, null, 2));
    console.log('');
  } catch (err) {
    console.error('Auth failed:', err.message);
    process.exit(1);
  }
}
