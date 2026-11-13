/**
 * Access key for the write API (sent as a bearer token).
 * Stored only in this browser; every storage call is guarded (private mode, blocked storage).
 * No emojis used.
 */

const STORAGE_KEY = "luas_condo_access_key";

export function getAccessKey(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setAccessKey(value: string): void {
  try {
    if (value) {
      window.localStorage.setItem(STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* storage unavailable: the key lasts only until reload */
  }
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const key = getAccessKey();
  return key ? { ...extra, Authorization: `Bearer ${key}` } : { ...extra };
}

export const AUTH_ERROR_MESSAGE =
  'Chave de acesso ausente ou invalida. Informe a chave em "Chave de acesso" no topo da pagina.';
