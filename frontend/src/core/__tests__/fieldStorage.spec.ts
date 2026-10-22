import { describe, it, expect } from 'vitest'
import { storageClassOf, describeTypeChange } from '@/core/fieldStorage'

describe('storageClassOf', () => {
  it('maps core field types to their column affinity', () => {
    expect(storageClassOf('Data')).toBe('text')
    expect(storageClassOf('LongText')).toBe('text')
    expect(storageClassOf('Select')).toBe('text')
    expect(storageClassOf('Link')).toBe('text')
    expect(storageClassOf('Int')).toBe('int')
    expect(storageClassOf('Check')).toBe('bool')
    expect(storageClassOf('Float')).toBe('float')
    expect(storageClassOf('Rating')).toBe('float')
    expect(storageClassOf('Date')).toBe('date')
    expect(storageClassOf('Datetime')).toBe('datetime')
    expect(storageClassOf('JSON')).toBe('json')
    expect(storageClassOf('Table')).toBe('none')
    expect(storageClassOf('MultiLink')).toBe('none')
    expect(storageClassOf('Section')).toBe('none')
  })

  it('falls back to text for unknown / plugin types', () => {
    expect(storageClassOf('SomePluginField')).toBe('text')
  })
})

describe('describeTypeChange', () => {
  it('returns null when the column is untouched', () => {
    expect(describeTypeChange('Data', 'Data')).toBeNull()
    expect(describeTypeChange('Data', 'LongText')).toBeNull()
    expect(describeTypeChange('Data', 'Select')).toBeNull()
    expect(describeTypeChange('Link', 'Data')).toBeNull()
    expect(describeTypeChange('Attach', 'Image')).toBeNull()
    expect(describeTypeChange('Float', 'Rating')).toBeNull()
  })

  it('gives one generic note for any column retype', () => {
    for (const [from, to] of [
      ['Int', 'Float'], ['Check', 'Int'], ['Date', 'Datetime'], ['Int', 'Data'],
      ['Data', 'Int'], ['Datetime', 'Date'], ['Float', 'Int'], ['Data', 'JSON'],
    ]) {
      expect(describeTypeChange(from, to)).toEqual(
        expect.objectContaining({ severity: 'info', message: expect.stringContaining('column type changes') }),
      )
    }
  })

  it('flags moves to / from a non-physical type as danger', () => {
    const toTable = describeTypeChange('Data', 'Table')
    expect(toTable?.severity).toBe('danger')
    expect(toTable?.message).toContain('child table')

    expect(describeTypeChange('MultiLink', 'Data')?.severity).toBe('danger')
  })
})
