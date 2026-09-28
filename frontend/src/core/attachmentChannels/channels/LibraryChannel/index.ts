import { N_ } from '@/plugins/i18n'
import { LibraryBig } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import LibraryChannelVue from './LibraryChannel.vue'

export const libraryChannel: AttachChannel = {
  id: 'library',
  icon: LibraryBig,
  label: N_('Library'),
  description: 'Choose from previously uploaded files',
  component: LibraryChannelVue,
}
