import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { DocType, DocField, DocTypePermission, WorkflowDef, WorkflowState, WorkflowTransition, WorkflowStep, FieldType, IndexHint } from '@/types'
import { metaApi } from '@/core/api'
import { parseLayout, flattenLayout } from '@/core/composables/useFormLayout'
import type { FormLayout } from '@/core/composables/useFormLayout'

export const useBuilderStore = defineStore('builder', () => {
  const doctype = ref<DocType | null>(null)
  const isDirty = ref(false)
  const isNew = ref(false)
  const _selectedFieldIdx = ref<number | null>(null)
  const isSaving = ref(false)
  const activeTab = ref<string>('form')
  const indexHints = ref<IndexHint[]>([])
  const exportedTo = ref<string | null>(null)

  // ── Computed ─────────────────────────────────────────────────────────

  const selectedField = computed<DocField | null>(() => {
    if (_selectedFieldIdx.value === null || !doctype.value) return null
    return doctype.value.fields[_selectedFieldIdx.value] ?? null
  })

  const selectedFieldName = computed<string | null>(() =>
    selectedField.value?.fieldname ?? null
  )

  const layout = computed<FormLayout>(() => {
    if (!doctype.value) return []
    return parseLayout(doctype.value.fields)
  })

  // ── Load / Save ──────────────────────────────────────────────────────

  async function loadDocType(name: string) {
    if (name === 'new') {
      doctype.value = { name: '', label: '', module: '', fields: [], permissions: [] }
      isNew.value = true
      isDirty.value = false
      _selectedFieldIdx.value = null
      return
    }
    doctype.value = await metaApi.get(name)
    isNew.value = false
    isDirty.value = false
    _selectedFieldIdx.value = null
  }

  async function save(): Promise<DocType | null> {
    if (!doctype.value) return null
    isSaving.value = true
    try {
      const result = isNew.value
        ? await metaApi.create(doctype.value)
        : await metaApi.update(doctype.value)
      if (isNew.value) isNew.value = false
      await metaApi.sync(result.data.name)
      doctype.value = result.data
      indexHints.value = result.hints ?? []
      exportedTo.value = result.exported_to ?? null
      isDirty.value = false
      return result.data
    } finally {
      isSaving.value = false
    }
  }

  // ── Fieldname generator ──────────────────────────────────────────────

  function generateFieldname(fieldtype: string): string {
    const base = fieldtype.toLowerCase().replace(/[^a-z]/g, '') + '_field'
    const existing = new Set((doctype.value?.fields ?? []).map((f) => f.fieldname))
    if (!existing.has(base)) return base
    let i = 2
    while (existing.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  // ── Selection ────────────────────────────────────────────────────────

  function selectField(fieldname: string | null) {
    if (fieldname === null || !doctype.value) { _selectedFieldIdx.value = null; return }
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    _selectedFieldIdx.value = idx === -1 ? null : idx
  }

  // ── Field CRUD (by fieldname) ────────────────────────────────────────

  function updateField(fieldname: string, patch: Partial<DocField>) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return
    doctype.value.fields[idx] = { ...doctype.value.fields[idx], ...patch }
    // Index stays the same even if fieldname changed
    isDirty.value = true
  }

  function removeField(fieldname: string) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return
    doctype.value.fields.splice(idx, 1)
    if (_selectedFieldIdx.value === idx) {
      _selectedFieldIdx.value = null
    } else if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value > idx) {
      _selectedFieldIdx.value -= 1
    }
    isDirty.value = true
  }

  function updateDocType(patch: Partial<DocType>) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, ...patch }
    isDirty.value = true
  }

  // ── Layout sync ──────────────────────────────────────────────────────

  function rebuildFlatFields(newLayout: FormLayout) {
    if (!doctype.value) return
    doctype.value.fields = flattenLayout(newLayout)
    isDirty.value = true
  }

  // ── Tab operations ───────────────────────────────────────────────────

  function addTab(afterTabFieldname?: string) {
    if (!doctype.value) return
    const tabField: DocField = {
      fieldname: generateFieldname('Tab'),
      label: 'New Tab',
      fieldtype: 'Tab',
    }
    const sectionField: DocField = {
      fieldname: generateFieldname('Section'),
      label: '',
      fieldtype: 'Section',
    }

    if (afterTabFieldname) {
      // Find the end of the target tab (next Tab field or end of array)
      const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === afterTabFieldname)
      if (tabIdx === -1) {
        doctype.value.fields.push(tabField, sectionField)
      } else {
        let endIdx = doctype.value.fields.length
        for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
          if (doctype.value.fields[i].fieldtype === 'Tab') {
            endIdx = i
            break
          }
        }
        doctype.value.fields.splice(endIdx, 0, tabField, sectionField)
      }
    } else {
      doctype.value.fields.push(tabField, sectionField)
    }
    isDirty.value = true
  }

  function removeTab(tabFieldname: string) {
    if (!doctype.value) return
    const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tabFieldname)
    if (tabIdx === -1) return

    // Find the range: from this Tab to the next Tab (or end)
    let endIdx = doctype.value.fields.length
    for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const removed = doctype.value.fields.splice(tabIdx, endIdx - tabIdx)
    // Deselect if selection was within removed range
    if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value >= tabIdx && _selectedFieldIdx.value < tabIdx + removed.length) {
      _selectedFieldIdx.value = null
    } else if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value >= tabIdx + removed.length) {
      _selectedFieldIdx.value -= removed.length
    }
    isDirty.value = true
  }

  // ── Section operations ───────────────────────────────────────────────

  function addSection(tabFieldname: string) {
    if (!doctype.value) return
    const sectionField: DocField = {
      fieldname: generateFieldname('Section'),
      label: '',
      fieldtype: 'Section',
    }

    // Find end of the tab
    const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tabFieldname)
    let endIdx = doctype.value.fields.length
    if (tabIdx !== -1) {
      for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
        if (doctype.value.fields[i].fieldtype === 'Tab') {
          endIdx = i
          break
        }
      }
    }

    doctype.value.fields.splice(endIdx, 0, sectionField)
    isDirty.value = true
  }

  /**
   * Converts an implicit (auto-generated) section into an explicit Section field.
   * Returns the new fieldname, or the original fieldname if already explicit.
   */
  function promoteImplicitSection(implicitFieldname: string): string {
    if (!doctype.value) return implicitFieldname
    const currentLayout = parseLayout(doctype.value.fields)
    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname !== implicitFieldname || section._field) continue
        const fieldname = generateFieldname('Section')
        const sectionField: DocField = { fieldname, label: section.label, fieldtype: 'Section' }
        let insertIdx: number
        if (tab._field) {
          const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tab._fieldname)
          insertIdx = tabIdx + 1
        } else {
          insertIdx = 0
        }
        doctype.value.fields.splice(insertIdx, 0, sectionField)
        isDirty.value = true
        return fieldname
      }
    }
    return implicitFieldname
  }

  function removeSection(sectionFieldname: string) {
    if (!doctype.value) return
    const secIdx = doctype.value.fields.findIndex((f) => f.fieldname === sectionFieldname)
    if (secIdx === -1) return

    // Find range: from this Section to next Section/Tab or end
    let endIdx = doctype.value.fields.length
    for (let i = secIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Section' || doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const removed = doctype.value.fields.splice(secIdx, endIdx - secIdx)
    if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value >= secIdx && _selectedFieldIdx.value < secIdx + removed.length) {
      _selectedFieldIdx.value = null
    } else if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value >= secIdx + removed.length) {
      _selectedFieldIdx.value -= removed.length
    }
    isDirty.value = true
  }

  // ── Column operations ────────────────────────────────────────────────

  function setSectionColumns(sectionFieldname: string, count: number) {
    if (!doctype.value || count < 1 || count > 4) return
    const currentLayout = parseLayout(doctype.value.fields)

    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname !== sectionFieldname) continue

        const currentCount = section.columns.length

        if (count > currentCount) {
          // Add columns: insert Column break fields + empty column arrays
          for (let i = currentCount; i < count; i++) {
            section._columnFieldnames.push(generateFieldname('Column'))
            section.columns.push([])
          }
        } else if (count < currentCount) {
          // Remove columns from the end, moving orphaned fields to the last kept column
          const lastKeptCol = section.columns[count - 1]
          for (let i = count; i < currentCount; i++) {
            lastKeptCol.push(...section.columns[i])
          }
          section.columns.splice(count)
          section._columnFieldnames.splice(count - 1)
        }

        doctype.value.fields = flattenLayout(currentLayout)
        isDirty.value = true
        return
      }
    }
  }

  // ── Add field to specific column ─────────────────────────────────────

  function addFieldToColumn(fieldtype: FieldType, sectionFieldname: string, columnIndex: number) {
    if (!doctype.value) return
    const newField: DocField = {
      fieldname: generateFieldname(fieldtype),
      label: fieldtype,
      fieldtype,
    }

    const currentLayout = parseLayout(doctype.value.fields)
    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname === sectionFieldname) {
          const col = section.columns[columnIndex]
          if (col) {
            col.push(newField)
            doctype.value.fields = flattenLayout(currentLayout)
            _selectedFieldIdx.value = doctype.value.fields.findIndex((f) => f.fieldname === newField.fieldname)
            isDirty.value = true
            return
          }
        }
      }
    }

    // Fallback: append to end
    doctype.value.fields.push(newField)
    _selectedFieldIdx.value = doctype.value.fields.length - 1
    isDirty.value = true
  }

  // ── Simple add (for palette click) ───────────────────────────────────

  function addField(fieldtype: FieldType) {
    if (!doctype.value) return
    const newField: DocField = {
      fieldname: generateFieldname(fieldtype),
      label: fieldtype,
      fieldtype,
    }
    doctype.value.fields.push(newField)
    _selectedFieldIdx.value = doctype.value.fields.length - 1
    isDirty.value = true
  }

  // ── Permission operations ────────────────────────────────────────────

  function addPermission(role: string) {
    if (!doctype.value) return
    const perms = [...(doctype.value.permissions ?? [])]
    perms.push({ role, read: true })
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  function updatePermission(index: number, patch: Partial<DocTypePermission>) {
    if (!doctype.value?.permissions) return
    const perms = [...doctype.value.permissions]
    perms[index] = { ...perms[index], ...patch }
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  function removePermission(index: number) {
    if (!doctype.value?.permissions) return
    const perms = [...doctype.value.permissions]
    perms.splice(index, 1)
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  // ── Workflow operations ─────────────────────────────────────────────

  function updateWorkflow(patch: Partial<WorkflowDef>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    doctype.value = { ...doctype.value, workflow: { ...wf, ...patch } }
    isDirty.value = true
  }

  function addWorkflowState(state?: Partial<WorkflowState>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    const newState: WorkflowState = {
      name: state?.name ?? `state_${wf.states.length + 1}`,
      label: state?.label ?? `State ${wf.states.length + 1}`,
      color: state?.color ?? 'gray',
      is_initial: wf.states.length === 0,
      is_final: false,
    }
    updateWorkflow({ states: [...wf.states, newState] })
  }

  function removeWorkflowState(index: number) {
    if (!doctype.value?.workflow) return
    const states = [...doctype.value.workflow.states]
    const removed = states.splice(index, 1)[0]
    // Also remove transitions referencing this state
    const transitions = doctype.value.workflow.transitions.filter(
      (t) => t.from_state !== removed.name && t.to_state !== removed.name
    )
    updateWorkflow({ states, transitions })
  }

  function addWorkflowTransition(transition?: Partial<WorkflowTransition>) {
    if (!doctype.value?.workflow) return
    const wf = doctype.value.workflow
    const newTransition: WorkflowTransition = {
      action: transition?.action ?? 'Action',
      from_state: transition?.from_state ?? (wf.states[0]?.name ?? ''),
      to_state: transition?.to_state ?? (wf.states[1]?.name ?? wf.states[0]?.name ?? ''),
      allowed_roles: transition?.allowed_roles ?? [],
    }
    updateWorkflow({ transitions: [...wf.transitions, newTransition] })
  }

  function removeWorkflowTransition(index: number) {
    if (!doctype.value?.workflow) return
    const transitions = [...doctype.value.workflow.transitions]
    transitions.splice(index, 1)
    updateWorkflow({ transitions })
  }

  function addWorkflowStep(partial?: Partial<WorkflowStep>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    const steps = wf.steps ?? []
    const newStep: WorkflowStep = {
      id: crypto.randomUUID(),
      name: partial?.name ?? `step_${steps.length + 1}`,
      title: partial?.title ?? '',
      step_type: partial?.step_type ?? 'state',
      variable: partial?.variable ?? null,
      sequence: steps.length,
      is_active: true,
      next_steps: [],
      config: {},
    }
    updateWorkflow({ steps: [...steps, newStep] })
    return newStep
  }

  function updateWorkflowStep(id: string, patch: Partial<WorkflowStep>) {
    if (!doctype.value?.workflow) return
    const steps = (doctype.value.workflow.steps ?? []).map(s =>
      s.id === id ? { ...s, ...patch } : s
    )
    updateWorkflow({ steps })
  }

  function removeWorkflowStep(id: string) {
    if (!doctype.value?.workflow) return
    const steps = (doctype.value.workflow.steps ?? []).filter(s => s.id !== id)
    // Remove references from other steps' next_steps
    const cleaned = steps.map(s => ({
      ...s,
      next_steps: s.next_steps.filter(nid => nid !== id && steps.some(x => x.id === nid)),
    }))
    updateWorkflow({ steps: cleaned })
  }

  function reorderWorkflowSteps(newSteps: WorkflowStep[]) {
    updateWorkflow({ steps: newSteps.map((s, i) => ({ ...s, sequence: i })) })
  }

  return {
    doctype,
    isDirty,
    isNew,
    selectedFieldName,
    selectedField,
    isSaving,
    activeTab,
    layout,
    indexHints,
    exportedTo,
    loadDocType,
    addField,
    removeField,
    updateField,
    updateDocType,
    selectField,
    save,
    generateFieldname,
    rebuildFlatFields,
    addTab,
    removeTab,
    addSection,
    promoteImplicitSection,
    removeSection,
    setSectionColumns,
    addFieldToColumn,
    addPermission,
    updatePermission,
    removePermission,
    updateWorkflow,
    addWorkflowState,
    removeWorkflowState,
    addWorkflowTransition,
    removeWorkflowTransition,
    addWorkflowStep,
    updateWorkflowStep,
    removeWorkflowStep,
    reorderWorkflowSteps,
  }
})
