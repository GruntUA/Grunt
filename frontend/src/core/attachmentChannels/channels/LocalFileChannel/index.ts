import { HardDriveUpload } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import LocalFileChannelVue from './LocalFileChannel.vue'

export const localFileChannel: AttachChannel = {
  id: 'local',
  icon: HardDriveUpload,
  label: 'Local file',
  description: 'Upload a file from disk',
  component: LocalFileChannelVue,
}
