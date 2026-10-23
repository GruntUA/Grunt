import { describe, it, expect } from 'vitest'
import { useListSelection } from '@/core/composables/useListSelection'

describe('useListSelection', () => {
  function setup() {
    return useListSelection()
  }

  describe('initial state', () => {
    it('has no selected ids', () => {
      const { selectedIds } = setup()
      expect(selectedIds.value).toEqual([])
    })

    it('count is 0', () => {
      const { count } = setup()
      expect(count.value).toBe(0)
    })
  })

  describe('toggle', () => {
    it('selects an id', () => {
      const { selectedIds, toggle } = setup()
      toggle('a')
      expect(selectedIds.value).toContain('a')
    })

    it('deselects an already-selected id', () => {
      const { selectedIds, toggle } = setup()
      toggle('a')
      toggle('a')
      expect(selectedIds.value).not.toContain('a')
    })

    it('unticks one id of a «select all» selection, keeping the rest', () => {
      const { selectedIds, setSelected, toggle } = setup()
      setSelected(['a', 'b', 'c'])
      toggle('b')
      expect(selectedIds.value).toEqual(['a', 'c'])
    })
  })

  describe('isSelected', () => {
    it('returns false for unselected id', () => {
      const { isSelected } = setup()
      expect(isSelected('x')).toBe(false)
    })

    it('returns true for selected id', () => {
      const { toggle, isSelected } = setup()
      toggle('x')
      expect(isSelected('x')).toBe(true)
    })
  })

  describe('toggleAll', () => {
    it('selects the page ids when none are selected', () => {
      const { selectedIds, toggleAll } = setup()
      toggleAll(['a', 'b', 'c'])
      expect(selectedIds.value).toEqual(['a', 'b', 'c'])
    })

    it('adds the page ids to a selection from other pages', () => {
      const { selectedIds, toggle, toggleAll } = setup()
      toggle('x')
      toggleAll(['a', 'b'])
      expect(selectedIds.value).toEqual(['x', 'a', 'b'])
    })

    it('completes a partly ticked page', () => {
      const { selectedIds, toggle, toggleAll } = setup()
      toggle('a')
      toggleAll(['a', 'b'])
      expect(selectedIds.value).toEqual(['a', 'b'])
    })

    it('clears the selection once every page id is ticked', () => {
      const { selectedIds, setSelected, toggleAll } = setup()
      setSelected(['a', 'b', 'c', 'd'])
      toggleAll(['a', 'b'])
      expect(selectedIds.value).toEqual([])
    })
  })

  describe('setSelected', () => {
    it('replaces the selection', () => {
      const { selectedIds, toggle, setSelected } = setup()
      toggle('x')
      setSelected(['a', 'b'])
      expect(selectedIds.value).toEqual(['a', 'b'])
    })
  })

  describe('clear', () => {
    it('resets selectedIds', () => {
      const { selectedIds, toggle, clear } = setup()
      toggle('a')
      toggle('b')
      clear()
      expect(selectedIds.value).toEqual([])
    })
  })

  describe('count', () => {
    it('reflects number of selected ids', () => {
      const { count, toggle } = setup()
      toggle('a')
      toggle('b')
      expect(count.value).toBe(2)
    })
  })
})
