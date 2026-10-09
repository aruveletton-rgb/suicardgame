export function createPublicInviteUrl(roomCode: string, href = typeof window === 'undefined' ? '' : window.location.href) {
  const normalized = roomCode.trim().toUpperCase();
  try {
    const url = new URL(href || 'http://localhost/');
    url.username = '';
    url.password = '';
    url.search = '';
    url.hash = '';
    url.searchParams.set('room', normalized);
    return url.toString();
  } catch {
    return `?room=${encodeURIComponent(normalized)}`;
  }
}
