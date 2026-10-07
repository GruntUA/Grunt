import { describe, expect, it } from 'vitest'
import { evalDependsOn } from '../dependsOn'

describe('evalDependsOn', () => {
  it('shows the field when there is no rule', () => {
    expect(evalDependsOn(undefined, {})).toBe(true)
    expect(evalDependsOn('', {})).toBe(true)
  })

  it('treats a bare fieldname as "that field is truthy"', () => {
    expect(evalDependsOn('is_tree', { is_tree: 1 })).toBe(true)
    expect(evalDependsOn('is_tree', { is_tree: 0 })).toBe(false)
    expect(evalDependsOn('is_tree', {})).toBe(false)
  })

  it('evaluates eval: expressions against doc', () => {
    expect(evalDependsOn("eval:doc.status == 'Open'", { status: 'Open' })).toBe(true)
    expect(evalDependsOn("eval: doc.status == 'Open'", { status: 'Closed' })).toBe(false)
    expect(evalDependsOn('eval:!doc.is_child && !doc.is_singleton', { is_child: 0 })).toBe(true)
  })

  it('keeps literal true/false as expressions', () => {
    expect(evalDependsOn('true', {})).toBe(true)
    expect(evalDependsOn('false', {})).toBe(false)
  })

  it('fails open on a broken expression', () => {
    expect(evalDependsOn('eval:doc.(', {})).toBe(true)
  })
})
