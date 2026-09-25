import type { SessionState } from './types';

const API_ROOT = '/api/v1';

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(detail?.message ?? detail?.error ?? detail ?? `HTTP ${response.status}`);
  }
  return body as T;
}

export function createRoom(nickname: string): Promise<SessionState> {
  return request('/rooms', {
    method: 'POST',
    body: JSON.stringify({ nickname }),
  });
}

export function joinRoom(roomCode: string, nickname: string): Promise<SessionState> {
  return request(`/rooms/${encodeURIComponent(roomCode)}/join`, {
    method: 'POST',
    body: JSON.stringify({ nickname }),
  });
}

export function reconnectRoom(session: SessionState): Promise<SessionState & { private_snapshot: unknown }> {
  return request(`/rooms/${encodeURIComponent(session.room_code)}/reconnect`, {
    method: 'POST',
    body: JSON.stringify({
      player_id: session.player_id,
      reconnect_token: session.reconnect_token,
    }),
  });
}

export function roomWebSocketUrl(roomCode: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return protocol + '//' + window.location.host + API_ROOT + '/rooms/' + encodeURIComponent(roomCode) + '/ws';
}
