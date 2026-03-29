import { describe, it, expect, beforeEach } from 'vitest'
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

    it('allSelected is false', () => {
      const { allSelected } = setup()
      expect(allSelected.value).toBe(false)
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

    it('selects multiple ids', () => {
      const { selectedIds, toggle } = setup()
      toggle('a')
      toggle('b')
      expect(selectedIds.value).toHaveLength(2)
    })

    it('when allSelected is active, clears allSelected and selectedIds', () => {
      const { allSelected, selectedIds, selectAllDocuments, toggle } = setup()
      selectAllDocuments()
      expect(allSelected.value).toBe(true)
      toggle('a')
      expect(allSelected.value).toBe(false)
      expect(selectedIds.value).toEqual([])
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

    it('returns true for any id when allSelected is true', () => {
      const { selectAllDocuments, isSelected } = setup()
      selectAllDocuments()
      expect(isSelected('anything')).toBe(true)
    })
  })

  describe('toggleAll', () => {
    it('selects all ids when none are selected', () => {
      const { selectedIds, toggleAll } = setup()
      toggleAll(['a', 'b', 'c'])
      expect(selectedIds.value).toEqual(['a', 'b', 'c'])
    })

    it('deselects all when all are already selected', () => {
      const { selectedIds, toggleAll } = setup()
      toggleAll(['a', 'b'])
      toggleAll(['a', 'b'])
      expect(selectedIds.value).toEqual([])
    })

    it('does not set allSelected flag', () => {
      const { allSelected, toggleAll } = setup()
      toggleAll(['a', 'b'])
      expect(allSelected.value).toBe(false)
    })
  })

  describe('selectAllDocuments', () => {
    it('sets allSelected to true', () => {
      const { allSelected, selectAllDocuments } = setup()
      selectAllDocuments()
      expect(allSelected.value).toBe(true)
    })

    it('count returns -1 when allSelected', () => {
      const { count, selectAllDocuments } = setup()
      selectAllDocuments()
      expect(count.value).toBe(-1)
    })

    it('clears selectedIds', () => {
      const { selectedIds, toggle, selectAllDocuments } = setup()
      toggle('a')
      selectAllDocuments()
      expect(selectedIds.value).toEqual([])
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

    it('resets allSelected', () => {
      const { allSelected, selectAllDocuments, clear } = setup()
      selectAllDocuments()
      clear()
      expect(allSelected.value).toBe(false)
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
