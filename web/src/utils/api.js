/**
 * Core API helpers for communication with FastAPI backend
 */
export const API = (typeof window !== 'undefined' && window.location && window.location.origin)
  ? `${window.location.origin}/api`
  : '/api';

export const post = (url, body) => {
  let serialized = '{}';
  try {
    // If body contains React synthetic events or circular references, sanitize
    serialized = JSON.stringify(body || {});
  } catch (err) {
    console.error('JSON serialize error in post:', err);
    serialized = '{}';
  }
  return fetch(`${API}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: serialized,
  });
};

export const toAssetUrl = (url) => {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) return url;
  const base = (typeof window !== 'undefined' && window.location && window.location.origin) ? window.location.origin : '';
  if (url.startsWith('/api/')) return `${base}${url}`;
  if (url.startsWith('/')) return `${base}/api${url}`;
  return `${base}/api/${url}`;
};
