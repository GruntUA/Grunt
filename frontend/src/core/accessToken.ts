import { ref } from 'vue'

/**
 * This tab's access token - in memory only, never in storage that script on
 * the page could read back later. The session itself is the HttpOnly
 * `grunt_session` cookie; `useAuthStore().refresh()` swaps it for a new access
 * token. Kept outside the store so the API client and WebSocket channels can
 * read it without Pinia.
 */
export const accessToken = ref<string | null>(null)
