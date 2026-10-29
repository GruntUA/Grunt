/**
 * Filter Registry
 *
 * Resolves a fieldtype's filter configuration: which comparison operators are
 * available and which Vue component renders the value input.
 *
 * Derived from the field type itself - operators from its storage_class /
 * traits, the input from components/fields/<Type>/FilterInput.vue - so a new
 * type needs no registration here. Plugin apps can still override one before
 * mount:
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
import DefaultFilterInput from '@/components/fields/Default/FilterInput.vue'
import { byFieldType, getFieldDef, getStorageClass, hasTrait, isChoiceType } from '@/core/fieldRegistry'

const _discovered = byFieldType(
  import.meta.glob<Component>('@/components/fields/*/FilterInput.vue', { eager: true, import: 'default' }),
)

export interface FilterConfig {
  operators: string[]
  /** Optional Vue component for the value input. Falls back to DefaultFilterInput. */
  filterInput?: Component
}

const EMPTY_OPS = ['is not set', 'is set']
const LIST_OPS = ['in', 'not in']
const TEXT_OPS = ['like', 'not like', '=', '!=', ...LIST_OPS, ...EMPTY_OPS]
const COMPARE_OPS = ['=', '!=', '>', '<', '>=', '<=', ...EMPTY_OPS]
const CHECK_OPS = ['=']
const CHOICE_OPS = ['=', '!=', ...LIST_OPS, ...EMPTY_OPS]
const LINK_OPS = ['=', '!=', ...LIST_OPS, 'child_of', ...EMPTY_OPS]

function operatorsFor(fieldtype: string): string[] {
  const declared = getFieldDef(fieldtype)?.filter_ops
  if (declared?.length) return declared
  const storage = getStorageClass(fieldtype)
  if (hasTrait(fieldtype, 'link')) return LINK_OPS
  // MultiSelect's JSON list stays text-matched.
  if (isChoiceType(fieldtype)) return CHOICE_OPS
  switch (storage) {
    case 'int':
    case 'float':
    case 'date':
    case 'datetime':
    case 'time':
      return COMPARE_OPS
    case 'bool':
      return CHECK_OPS
    default:
      return TEXT_OPS
  }
}

const _registry = new Map<string, FilterConfig>()

/** Register or overwrite a filter configuration for a fieldtype. */
export function registerFilterConfig(fieldtype: string, config: FilterConfig): void {
  _registry.set(fieldtype, config)
}

/** The filter config for a fieldtype - registered, or derived from the type itself. */
export function getFilterConfig(fieldtype: string): Required<FilterConfig> {
  const registered = _registry.get(fieldtype)
  return {
    operators: registered?.operators ?? operatorsFor(fieldtype),
    filterInput: registered?.filterInput ?? _discovered.get(fieldtype) ?? DefaultFilterInput,
  }
}
