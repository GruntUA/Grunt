import { ref } from 'vue'

export interface ServerErrorDebug {
  exc_type: string
  message: string
  traceback: string
  sql?: string
  sql_params?: string
  db_error?: string
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
