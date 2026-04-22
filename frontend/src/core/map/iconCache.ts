import { createApp, h, type Component } from 'vue'
import L from 'leaflet'

const iconPathCache = new Map<string, string>()
type IconMap = Record<string, Component>
let lucideLib: IconMap | null = null

export async function ensureLucide(): Promise<IconMap> {
  if (!lucideLib) lucideLib = await import('@lucide/vue') as unknown as IconMap
  return lucideLib
}

export async function getIconPaths(iconName: string): Promise<string> {
  if (iconPathCache.has(iconName)) return iconPathCache.get(iconName)!
  const lib = await ensureLucide()
  const pascal = iconName
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('')
  const IconComp = lib[pascal] as Component | undefined
  if (!IconComp) return ''

  const div = document.createElement('div')
  const app = createApp({ render: () => h(IconComp, { size: 12, 'stroke-width': 2.5 }) })
  app.mount(div)
  const paths = div.querySelector('svg')?.innerHTML ?? ''
  app.unmount()
  iconPathCache.set(iconName, paths)
  return paths
}

export function createIcon(color: string, iconPaths?: string): L.DivIcon {
  const inner = iconPaths
    ? `<circle cx="12" cy="12" r="7" fill="white" opacity="0.92"/>
       <svg x="6" y="6" width="12" height="12" viewBox="0 0 24 24"
         fill="none" stroke="${color}" stroke-width="2.5"
         stroke-linecap="round" stroke-linejoin="round">${iconPaths}</svg>`
    : `<circle cx="12" cy="12" r="5" fill="white" opacity="0.85"/>`

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="24" height="32">
    <path d="M12 0C5.373 0 0 5.373 0 12c0 9 12 20 12 20s12-11 12-20C24 5.373 18.627 0 12 0z"
      fill="${color}" stroke="white" stroke-width="1.5"/>
    ${inner}
  </svg>`

  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [24, 32],
    iconAnchor: [12, 32],
    popupAnchor: [0, -34],
  })
}
