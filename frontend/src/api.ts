export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export async function api<T>(path: string, body?: unknown, method = 'GET', key = crypto.randomUUID()): Promise<T> {
  const token = sessionStorage.getItem('access_token');
  const response = await fetch(`${API}${path}`, { method, headers: { ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(method !== 'GET' ? { 'Idempotency-Key': key } : {}) }, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
  if (!response.ok) {
    if (response.status === 401) sessionStorage.removeItem('access_token');
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status}). Check the values and try again.`);
  }
  return response.json();
}
export async function downloadDocument(id: string, filename: string) {
  const token = sessionStorage.getItem('access_token');
  const response = await fetch(`${API}/api/documents/${id}/download`, { headers: token ? {Authorization: `Bearer ${token}`} : {} });
  if (!response.ok) throw new Error('Document download failed');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
