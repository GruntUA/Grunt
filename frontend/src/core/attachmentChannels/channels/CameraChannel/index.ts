import { Camera } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import CameraChannelVue from './CameraChannel.vue'

export const cameraChannel: AttachChannel = {
  id: 'camera',
  icon: Camera,
  label: 'Камера',
  description: 'Зробити фото за допомогою камери',
  component: CameraChannelVue,
  isSupported: () => typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia,
}
