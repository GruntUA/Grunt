import { N_ } from '@/plugins/i18n'
import { HardDriveUpload } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import LocalFileChannelVue from './LocalFileChannel.vue'

export const localFileChannel: AttachChannel = {
  id: 'local',
  icon: HardDriveUpload,
  label: N_('Local file'),
  description: 'Upload a file from disk',
  component: LocalFileChannelVue,
}
