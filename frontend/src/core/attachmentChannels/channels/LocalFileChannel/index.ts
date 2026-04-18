import { HardDriveUpload } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import LocalFileChannelVue from './LocalFileChannel.vue'

export const localFileChannel: AttachChannel = {
  id: 'local',
  icon: HardDriveUpload,
  label: 'Локальний файл',
  description: 'Завантажити файл з диску',
  component: LocalFileChannelVue,
}
