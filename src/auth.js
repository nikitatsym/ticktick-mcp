import fs from 'node:fs';
import path from 'node:path';

const TICKTICK_TOKEN_URL = 'https://ticktick.com/oauth/token';
const REDIRECT_URI = 'https://nikitatsym.github.io/ticktick-mcp/';
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
 * Get a valid access token — from env, file, or auth code exchange.
 * Returns { accessToken, tokens }.
 */
export async function getAccessToken(clientId, clientSecret) {
  // Priority 1: env var access token
  if (process.env.TICKTICK_ACCESS_TOKEN) {
    const tokens = {
      access_token: process.env.TICKTICK_ACCESS_TOKEN,
      refresh_token: process.env.TICKTICK_REFRESH_TOKEN || null,
      expires_at: null,
    };
    // Persist to disk so refresh works on 401
    saveTokens(tokens);
    return { accessToken: tokens.access_token, tokens };
  }

  // Priority 2: saved tokens from disk
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
          tokens = null;
        }
      } else {
        tokens = null;
      }
    }
  }

  if (tokens) {
    return { accessToken: tokens.access_token, tokens };
  }

  // Priority 3: one-time auth code exchange (from GitHub Pages setup)
  if (process.env.TICKTICK_AUTH_CODE && clientId && clientSecret) {
    console.error('Exchanging auth code for tokens...');
    try {
      tokens = await exchangeCode(process.env.TICKTICK_AUTH_CODE, clientId, clientSecret);
      saveTokens(tokens);
      console.error('Tokens saved to ' + TOKEN_FILE);
      return { accessToken: tokens.access_token, tokens };
    } catch (err) {
      console.error(`Auth code exchange failed: ${err.message}`);
      // Fall through to error
    }
  }

  // No tokens available
  throw new Error(
    'No authentication tokens found.\n' +
      'Visit https://nikitatsym.github.io/ticktick-mcp/ to set up authorization.\n' +
      'See README.md for details.'
  );
}
