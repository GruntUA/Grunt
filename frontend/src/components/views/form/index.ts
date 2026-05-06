import { FileText } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

const def: ViewDefinition = {
  type: 'form',
  label: 'Форма',
  icon: FileText,
  order: -1,
  showInToolbar: false,

  component: () => Promise.reject(new Error('Form view is configured via the document form route, not the list view router.')),
  settingsComponent: () => import('./FormViewSettings.vue').then((m) => m.default),
}

export default def