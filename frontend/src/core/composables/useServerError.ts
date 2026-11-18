import { ref } from 'vue'

/**
 * What a debug-mode error response carries: the exception type and where to
 * read the rest - never the exception text or traceback themselves (those are
 * in the ErrorLog record, opened by the modal, and in the server log).
 */
export interface ServerErrorDebug {
  exc_type: string
  /** The ErrorLog record with the message (SQL, failing fields) and traceback */
  error_log?: string | null
  request_id?: string | null
}

interface ServerErrorState {
  open: boolean
  status: number
  debug: ServerErrorDebug | null
  plainMessage: string
}

const state = ref<ServerErrorState>({
  open: false,
  status: 500,
  debug: null,
  plainMessage: '',
})

export function useServerError() {
  function show(status: number, debug: ServerErrorDebug | null, plainMessage = '') {
    state.value = { open: true, status, debug, plainMessage }
  }

  function close() {
    state.value.open = false
  }

  return { state, show, close }
}
