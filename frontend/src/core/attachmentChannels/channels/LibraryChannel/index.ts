import { LibraryBig } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import LibraryChannelVue from './LibraryChannel.vue'

export const libraryChannel: AttachChannel = {
  id: 'library',
  icon: LibraryBig,
  label: 'Бібліотека',
  description: 'Вибрати з раніше завантажених файлів',
  component: LibraryChannelVue,
}
