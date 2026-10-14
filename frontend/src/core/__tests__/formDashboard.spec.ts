import { describe, expect, it } from 'vitest'
import {
  createFormDashboard,
  isDashboardEmpty,
} from '@/core/scripting/formDashboard'

describe('Form Dashboard API', () => {
  it('initializes in empty state', () => {
    const dashboard = createFormDashboard()
    expect(isDashboardEmpty(dashboard.state)).toBe(true)
    expect(dashboard.state.hidden).toBe(false)
    expect(dashboard.state.headline).toBeNull()
    expect(dashboard.state.indicators).toEqual([])
    expect(dashboard.state.progress).toEqual([])
    expect(dashboard.state.graph).toBeNull()
    expect(dashboard.state.heatmap).toBeNull()
    expect(dashboard.state.sections).toEqual([])
    expect(dashboard.state.comments).toEqual([])
    expect(dashboard.state.transactions).toEqual([])
    expect(dashboard.state.docstatus_icon).toBeNull()
  })

  it('manages headlines with permanence and colors', () => {
    const dashboard = createFormDashboard()
    dashboard.set_headline('Review needed', 'orange')
    expect(isDashboardEmpty(dashboard.state)).toBe(false)
    expect(dashboard.state.headline).toEqual({
      html: 'Review needed',
      color: 'orange',
      permanent: false,
    })

    // Reset clears non-permanent headline
    dashboard.reset()
    expect(dashboard.state.headline).toBeNull()

    // Permanent headline survives reset
    dashboard.set_headline('Locked document', 'red', true)
    dashboard.reset()
    expect(dashboard.state.headline).toEqual({
      html: 'Locked document',
      color: 'red',
      permanent: true,
    })

    dashboard.clear_headline()
    expect(dashboard.state.headline).toBeNull()
  })

  it('supports stat indicators', () => {
    const dashboard = createFormDashboard()
    dashboard.add_indicator('Total: 1000', 'green')
    dashboard.add_indicator('Pending: 2', 'orange')

    expect(dashboard.state.indicators).toEqual([
      { label: 'Total: 1000', color: 'green' },
      { label: 'Pending: 2', color: 'orange' },
    ])
  })

  it('handles progress bars with numbers and segments', () => {
    const dashboard = createFormDashboard()
    dashboard.add_progress('Task Completion', 75, '3 of 4 tasks completed')
    expect(dashboard.state.progress).toEqual([
      {
        title: 'Task Completion',
        segments: [{ width: 75 }],
        message: '3 of 4 tasks completed',
      },
    ])

    // Re-adding with same title replaces it
    dashboard.show_progress('Task Completion', 100, 'All done')
    expect(dashboard.state.progress).toEqual([
      {
        title: 'Task Completion',
        segments: [{ width: 100 }],
        message: 'All done',
      },
    ])

    // Multi-segment progress bar
    dashboard.add_progress('Multi', [
      { title: 'Done', width: 40, color: 'green' },
      { title: 'Pending', width: 30, progress_class: 'progress-bar-warning' },
    ])
    const multi = dashboard.state.progress.find((p) => p.title === 'Multi')
    expect(multi?.segments).toEqual([
      { title: 'Done', width: 40, color: 'green' },
      { title: 'Pending', width: 30, color: 'orange' },
    ])
  })

  it('renders graph and heatmap', () => {
    const dashboard = createFormDashboard()
    dashboard.render_graph({
      title: 'Sales',
      type: 'line',
      colors: ['#3b82f6'],
      data: {
        labels: ['Jan', 'Feb', 'Mar'],
        datasets: [{ name: '2026', values: [10, 20, 30] }],
      },
    })
    expect(dashboard.state.graph?.title).toBe('Sales')
    expect(dashboard.state.graph?.labels).toEqual(['Jan', 'Feb', 'Mar'])
    expect(dashboard.state.graph?.datasets[0].values).toEqual([10, 20, 30])
    expect(dashboard.state.graph?.colors).toEqual(['#3b82f6'])

    dashboard.render_heatmap({
      title: 'Activity',
      data: {
        dataPoints: {
          '2026-10-10': 3,
          '2026-10-11': 7,
        },
      },
    })
    expect(dashboard.state.heatmap?.title).toBe('Activity')
    expect(dashboard.state.heatmap?.entries).toContainEqual({
      date: '2026-10-10',
      count: 3,
    })
    expect(dashboard.state.heatmap?.entries).toContainEqual({
      date: '2026-10-11',
      count: 7,
    })
  })

  it('supports related document transactions and badge counts', () => {
    const dashboard = createFormDashboard()
    dashboard.add_transactions({
      label: 'Related Documents',
      items: ['Sales Order', 'Delivery Note'],
    })
    expect(dashboard.state.transactions).toEqual([
      {
        label: 'Related Documents',
        items: ['Sales Order', 'Delivery Note'],
      },
    ])

    dashboard.set_badge_count_for_external_link('Sales Order', 5, 10)
    expect(dashboard.state.badges['Sales Order']).toEqual({
      open_count: 5,
      count: 10,
    })
  })

  it('supports custom sections and clearing by section name/type', () => {
    const dashboard = createFormDashboard()
    const sec1 = dashboard.add_section('<p>Custom 1</p>', 'Info')
    const sec2 = dashboard.add_section('<p>Custom 2</p>', 'Details')
    expect(dashboard.state.sections.length).toBe(2)

    dashboard.clear_section(sec1)
    expect(dashboard.state.sections.map((s) => s.name)).toEqual([sec2])

    // clear_section('chart') and 'heatmap'
    dashboard.render_graph({ data: { labels: ['A'], datasets: [{ values: [1] }] } })
    expect(dashboard.state.graph).not.toBeNull()
    dashboard.clear_section('chart')
    expect(dashboard.state.graph).toBeNull()
  })

  it('supports docstatus icons and comments with alert classes', () => {
    const dashboard = createFormDashboard()
    dashboard.set_docstatus_icon(1)
    expect(dashboard.state.docstatus_icon).toBe('Submitted')

    dashboard.set_docstatus_icon('Draft')
    expect(dashboard.state.docstatus_icon).toBe('Draft')

    dashboard.add_comment('Important note', 'alert-warning', false)
    dashboard.add_comment('Permanent notice', 'alert-danger', true)
    expect(dashboard.state.comments).toEqual([
      { html: 'Important note', color: 'orange', permanent: false },
      { html: 'Permanent notice', color: 'red', permanent: true },
    ])

    dashboard.reset()
    // Non-permanent comment was cleared, permanent remains
    expect(dashboard.state.comments).toEqual([
      { html: 'Permanent notice', color: 'red', permanent: true },
    ])
  })

  it('respects show and hide', () => {
    const dashboard = createFormDashboard()
    dashboard.set_headline('Hello')
    expect(isDashboardEmpty(dashboard.state)).toBe(false)

    dashboard.hide()
    expect(dashboard.state.hidden).toBe(true)
    expect(isDashboardEmpty(dashboard.state)).toBe(true)

    dashboard.show()
    expect(dashboard.state.hidden).toBe(false)
    expect(isDashboardEmpty(dashboard.state)).toBe(false)
  })
})
