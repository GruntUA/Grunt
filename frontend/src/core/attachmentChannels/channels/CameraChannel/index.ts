import { N_ } from '@/plugins/i18n'
import { Camera } from '@lucide/vue'
import type { AttachChannel } from '@/core/attachmentChannels/types'
import CameraChannelVue from './CameraChannel.vue'

export const cameraChannel: AttachChannel = {
  id: 'camera',
  icon: Camera,
  label: N_('Camera'),
  description: 'Take a photo with the camera',
  component: CameraChannelVue,
  isSupported: () => typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia,
}
