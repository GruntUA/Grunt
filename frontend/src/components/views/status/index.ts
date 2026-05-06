import { CircleDot } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

const def: ViewDefinition = {
  type: 'status',
  label: 'Статуси',
  icon: CircleDot,
  order: -1,
  showInToolbar: false,

  component: () => Promise.reject(new Error('Status settings are a builder-only configuration surface.')),
  settingsComponent: () => import('./StatusSettings.vue').then((m) => m.default),
}

export default def