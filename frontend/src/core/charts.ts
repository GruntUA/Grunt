/**
 * Shared bits of the shadcn charts (`components/ui/chart` over unovis):
 * series colours from the theme tokens, the widget accent colours, and a PNG
 * export of the rendered SVG.
 */
import { h, render } from 'vue'
import { ChartTooltipContent, type ChartConfig } from '@/components/ui/chart'

/** Series colours: the theme's `--chart-1…5`, repeated past the fifth series. */
export function seriesColor(i: number): string {
  return `var(--chart-${(i % 5) + 1})`
}

// `DashboardWidget.color`; "primary" follows the theme like the other series.
const ACCENTS: Record<string, string> = {
  primary: 'var(--chart-1)',
  blue: '#3b82f6',
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  violet: '#8b5cf6',
  cyan: '#06b6d4',
}

export function accentColor(name?: string | null): string {
  return (name && ACCENTS[name]) || ACCENTS.primary
}

/**
 * A ChartConfig for series whose names are arbitrary text (group values,
 * column labels): keys are `s0, s1…` so the `--color-<key>` variables that
 * ChartContainer emits stay valid CSS; the names go to `label`.
 */
export function seriesConfig(names: string[], colors: string[]): ChartConfig {
  return Object.fromEntries(names.map((label, i) => [`s${i}`, { label, color: colors[i] }]))
}

/**
 * HTML of ChartTooltipContent for a unovis tooltip/crosshair template. Unlike
 * shadcn's componentToString it reads the config at call time, so series that
 * change with the data (group values) are labelled correctly.
 */
export function tooltipHtml(props: InstanceType<typeof ChartTooltipContent>['$props']): string {
  const div = document.createElement('div')
  render(h(ChartTooltipContent, props), div)
  const html = div.innerHTML
  render(null, div)
  return html
}

const PAINT = ['fill', 'stroke', 'opacity', 'fill-opacity', 'stroke-opacity', 'stroke-width', 'font-size', 'font-family', 'font-weight']

/**
 * PNG data URL of the chart's SVG. The colours come from CSS variables and
 * classes, which a standalone image can't see - so the computed paint of each
 * element is inlined into a clone before it is drawn on a canvas.
 */
export async function chartToPng(root: HTMLElement, scale = 2): Promise<string | null> {
  const svg = root.querySelector('svg')
  if (!svg) return null
  const { width, height } = svg.getBoundingClientRect()
  if (!width || !height) return null

  const clone = svg.cloneNode(true) as SVGSVGElement
  const source = [svg, ...svg.querySelectorAll('*')]
  const target = [clone, ...clone.querySelectorAll('*')]
  source.forEach((el, i) => {
    const style = getComputedStyle(el)
    const css = PAINT.map((p) => `${p}:${style.getPropertyValue(p)}`).join(';')
    target[i].setAttribute('style', `${target[i].getAttribute('style') ?? ''};${css}`)
  })
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')!
    const bg = getComputedStyle(root).backgroundColor
    ctx.fillStyle = bg && bg !== 'rgba(0, 0, 0, 0)' ? bg : getComputedStyle(document.body).backgroundColor
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png')
  } finally {
    URL.revokeObjectURL(url)
  }
}
