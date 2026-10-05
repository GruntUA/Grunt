/**
 * Filter Registry
 *
 * Maps fieldtype -> filter configuration: which comparison operators are
 * available and which Vue component renders the value input.
 *
 * Built-in registrations are in app-hooks.ts.
 * External apps can register custom configurations before mount:
 *
 *   import { registerFilterConfig } from '@/core/filterRegistry'
 *   import MyFilterInput from './MyFilterInput.vue'
 *   registerFilterConfig('MyType', { operators: ['=', '!='], filterInput: MyFilterInput })
 *
 * FilterInput components must accept these props:
 *   field:         DocField - full field metadata (options, linked doctype, etc.)
 *   modelValue:    string - the raw filter value sent to the API
 *   displayValue:  string - human-readable label (used by Link fields)
 *   op:            string - currently selected operator
 *
 * And emit:
 *   update:modelValue   (value: string)
 *   update:displayValue (value: string)
 *   submit              () - user pressed Enter / confirmed
 */

import type { Component } from 'vue'

export interface FilterConfig {
  operators: string[]
  /** Optional Vue component for the value input. Falls back to DefaultFilterInput. */
  filterInput?: Component
}

const _registry = new Map<string, FilterConfig>()

/** Register or overwrite a filter configuration for a fieldtype. */
export function registerFilterConfig(fieldtype: string, config: FilterConfig): void {
  _registry.set(fieldtype, config)
}

/** Retrieve the filter config for a fieldtype. Falls back to text config if unregistered. */
export function getFilterConfig(fieldtype: string): FilterConfig {
  return _registry.get(fieldtype) ?? _registry.get('_default') ?? { operators: ['=', '!=', 'like'] }
}
