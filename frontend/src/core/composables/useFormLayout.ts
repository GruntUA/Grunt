import type { DocField, FieldType } from '@/types'

// Layout types

export interface LayoutTab {
  type: 'tab'
  label: string
  _fieldname: string
  _field: DocField | null // null for the implicit default tab
  sections: LayoutSection[]
}

export interface LayoutSection {
  type: 'section'
  label: string
  collapsible: boolean
  collapsed: boolean
  _fieldname: string
  _field: DocField | null // null for the implicit default section
  _columnFieldnames: string[] // fieldnames of Column break fields (first column has none)
  columns: DocField[][] // each inner array is one column's fields
}

export type FormLayout = LayoutTab[]

// Counters for implicit layout nodes

let _implicitCounter = 0
function implicitName(prefix: string): string {
  return `__${prefix}_${++_implicitCounter}`
}

// Parse flat DocField[] -> hierarchical FormLayout

export function parseLayout(fields: DocField[]): FormLayout {
  _implicitCounter = 0

  const tabs: LayoutTab[] = []
  let currentTab: LayoutTab = {
    type: 'tab',
    label: '',
    _fieldname: implicitName('tab'),
    _field: null,
    sections: [],
  }
  let currentSection: LayoutSection = {
    type: 'section',
    label: '',
    collapsible: false,
    collapsed: false,
    _fieldname: implicitName('section'),
    _field: null,
    _columnFieldnames: [],
    columns: [[]],
  }

  function pushSection() {
    if (currentSection.columns.some((col) => col.length > 0) || currentSection._field) {
      currentTab.sections.push(currentSection)
    }
  }

  function pushTab() {
    pushSection()
    if (currentTab.sections.length > 0 || currentTab._field) {
      tabs.push(currentTab)
    }
  }

  for (const f of fields) {
    if (f.fieldtype === 'Tab') {
      pushTab()
      currentTab = {
        type: 'tab',
        label: f.label,
        _fieldname: f.fieldname,
        _field: f,
        sections: [],
      }
      currentSection = {
        type: 'section',
        label: '',
        collapsible: false,
        collapsed: false,
        _fieldname: implicitName('section'),
        _field: null,
        _columnFieldnames: [],
        columns: [[]],
      }
    } else if (f.fieldtype === 'Section') {
      pushSection()
      currentSection = {
        type: 'section',
        label: f.label,
        collapsible: !!f.collapsible,
        collapsed: false,
        _fieldname: f.fieldname,
        _field: f,
        _columnFieldnames: [],
        columns: [[]],
      }
    } else if (f.fieldtype === 'Column') {
      const lastCol = currentSection.columns[currentSection.columns.length - 1]
      // If the ONLY current column is empty, just name it. Otherwise start new.
      if (lastCol.length === 0 && currentSection.columns.length === 1) {
        currentSection._columnFieldnames = [f.fieldname]
      } else {
        currentSection._columnFieldnames.push(f.fieldname)
        currentSection.columns.push([])
      }
    } else {
      const lastCol = currentSection.columns[currentSection.columns.length - 1]
      lastCol.push(f)
    }
  }

  pushTab()

  // Ensure at least one tab with one section
  if (tabs.length === 0) {
    currentTab.sections = [currentSection]
    tabs.push(currentTab)
  } else if (tabs.length > 0 && tabs[tabs.length - 1].sections.length === 0) {
    tabs[tabs.length - 1].sections.push(currentSection)
  }

  return tabs
}

// Flatten FormLayout -> flat DocField[]

export function flattenLayout(layout: FormLayout): DocField[] {
  const result: DocField[] = []

  for (const tab of layout) {
    // Only emit Tab field if it was explicitly defined
    if (tab._field) {
      result.push(tab._field)
    }

    for (const section of tab.sections) {
      // Only emit Section field if it was explicitly defined
      if (section._field) {
        result.push(section._field)
      }

      for (let ci = 0; ci < section.columns.length; ci++) {
        // Emit Column break for columns after the first
        if (ci > 0 && section._columnFieldnames[ci - 1]) {
          const colFieldname = section._columnFieldnames[ci - 1]
          result.push({
            fieldname: colFieldname,
            label: '',
            fieldtype: 'Column' as FieldType,
          })
        }

        for (const field of section.columns[ci]) {
          result.push(field)
        }
      }
    }
  }

  return result
}

// Find insert position in flat array for a specific column

export function findInsertPosition(
  fields: DocField[],
  sectionFieldname: string,
  columnIndex: number,
): number {
  const layout = parseLayout(fields)
  for (const tab of layout) {
    for (const section of tab.sections) {
      if (section._fieldname === sectionFieldname) {
        // Find the last field in the target column
        const col = section.columns[columnIndex]
        if (col && col.length > 0) {
          const lastField = col[col.length - 1]
          const idx = fields.findIndex((f) => f.fieldname === lastField.fieldname)
          return idx + 1
        }
        // Empty column - find the position after the column break (or section break)
        if (columnIndex === 0) {
          // After the section field itself
          if (section._field) {
            const idx = fields.findIndex((f) => f.fieldname === section._fieldname)
            return idx + 1
          }
        } else {
          // After the column break field
          const colFieldname = section._columnFieldnames[columnIndex - 1]
          if (colFieldname) {
            const idx = fields.findIndex((f) => f.fieldname === colFieldname)
            return idx + 1
          }
        }
      }
    }
  }
  return fields.length
}
