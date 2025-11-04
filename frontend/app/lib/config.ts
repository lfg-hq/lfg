const DEFAULT_BACKEND_BASE = 'http://localhost:8000/';
const DEFAULT_API_PATH = 'api/v1/';

function ensureTrailingSlash(value: string): string {
  return value.endsWith('/') ? value : `${value}/`;
}

function getBackendBase(): string {
  const provided = process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!provided) {
    return DEFAULT_BACKEND_BASE;
  }
  try {
    const url = new URL(provided);
    return ensureTrailingSlash(url.toString());
  } catch (error) {
    return DEFAULT_BACKEND_BASE;
  }
}

export const BACKEND_BASE_URL = ensureTrailingSlash(getBackendBase());

function getApiBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit) {
    try {
      const url = new URL(explicit);
      return ensureTrailingSlash(url.toString());
    } catch (error) {
      // fall back to constructing from backend base
    }
  }

  const apiPath = ensureTrailingSlash(process.env.NEXT_PUBLIC_API_PATH ?? DEFAULT_API_PATH);
  const apiUrl = new URL(apiPath, BACKEND_BASE_URL);
  return ensureTrailingSlash(apiUrl.toString());
}

export const API_BASE_URL = getApiBase();

function resolveWsBase(): string {
  const explicitWs = process.env.NEXT_PUBLIC_WS_BASE_URL;
  if (explicitWs) {
    try {
      const url = new URL(explicitWs);
      return ensureTrailingSlash(url.toString());
    } catch (error) {
      // fall through to derive from backend
    }
  }

  try {
    const base = new URL(BACKEND_BASE_URL);
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    return ensureTrailingSlash(base.toString());
  } catch (error) {
    return 'ws://localhost:8000/';
  }
}

export const WS_BASE_URL = resolveWsBase();

function joinUrl(base: string, path: string, acceptedProtocols: string[]): string {
  if (acceptedProtocols.some((protocol) => path.startsWith(`${protocol}:`))) {
    return path;
  }
  const normalizedBase = ensureTrailingSlash(base);
  const normalizedPath = path.replace(/^\/+/, '');
  return `${normalizedBase}${normalizedPath}`;
}

export function buildApiUrl(path: string): string {
  return joinUrl(API_BASE_URL, path, ['http', 'https']);
}

export function buildBackendUrl(path: string): string {
  return joinUrl(BACKEND_BASE_URL, path, ['http', 'https']);
}

export function buildWsUrl(path: string): string {
  return joinUrl(WS_BASE_URL, path, ['ws', 'wss']);
}
