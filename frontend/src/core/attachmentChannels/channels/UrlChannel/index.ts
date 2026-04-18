import { Link } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import UrlChannelVue from './UrlChannel.vue'

export const urlChannel: AttachChannel = {
  id: 'url',
  icon: Link,
  label: 'URL',
  description: 'Вказати посилання на файл у інтернеті',
  component: UrlChannelVue,
}
