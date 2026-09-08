import { shallowReactive } from 'vue'
import type { AttachChannel } from './types'

const _channels = shallowReactive<AttachChannel[]>([])

export function registerAttachChannel(channel: AttachChannel): void {
  const idx = _channels.findIndex(c => c.id === channel.id)
  if (idx !== -1) _channels[idx] = channel
  else _channels.push(channel)
}

export function unregisterAttachChannel(id: string): void {
  const idx = _channels.findIndex(c => c.id === id)
  if (idx !== -1) _channels.splice(idx, 1)
}

export function getAttachChannels(imageOnly = false): AttachChannel[] {
  return _channels.filter(ch => {
    if (ch.isSupported && !ch.isSupported()) return false
    if (ch.imageOnlyChannel && !imageOnly) return false
    return true
  })
}
