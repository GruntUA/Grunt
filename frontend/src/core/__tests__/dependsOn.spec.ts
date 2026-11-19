import { describe, expect, it } from 'vitest'
import { evalCondition, evalDependsOn } from '../dependsOn'

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

describe('evalCondition (mandatory_depends_on / read_only_depends_on)', () => {
  it('is false without an expression, and fails closed on a broken one', () => {
    expect(evalCondition(undefined, {})).toBe(false)
    expect(evalCondition('', {})).toBe(false)
    expect(evalCondition('eval:doc.(', {})).toBe(false)
  })

  it('evaluates bare fieldnames and eval: expressions', () => {
    expect(evalCondition('is_approved', { is_approved: 1 })).toBe(true)
    expect(evalCondition("eval:doc.status == 'Approved'", { status: 'Approved' })).toBe(true)
    expect(evalCondition("eval:doc.status == 'Approved'", { status: 'Draft' })).toBe(false)
  })

  it('knows a document not saved yet as doc.__islocal', () => {
    const rule = "eval:!doc.__islocal && doc.status == 'Approved'"
    // A typed-in name doesn't make it saved; created_at does.
    expect(evalCondition(rule, { name: 'X-1', status: 'Approved' })).toBe(false)
    expect(evalCondition(rule, { name: 'X-1', status: 'Approved', created_at: '2026-11-18' })).toBe(true)
    expect(evalDependsOn('eval:doc.__islocal', {})).toBe(true)
  })
})
