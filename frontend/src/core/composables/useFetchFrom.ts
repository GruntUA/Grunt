import { watch, type Ref } from 'vue'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'

interface UseFetchFromParams {
    doctype: Ref<DocType | null>
    modelValue: Ref<Record<string, unknown>>
    updateField: (fieldname: string, value: unknown) => void
}

export function useFetchFrom({ doctype, modelValue, updateField }: UseFetchFromParams) {
    // Track previous values of link fields manually — Vue does NOT clone
    // oldVal for object refs in deep watch (prevDoc === doc by reference).
    const prevLinkValues = new Map<string, unknown>()

    watch(
        doctype,
        (dt) => {
            // When schema changes, reset baseline from the current form values
            prevLinkValues.clear()
            if (!dt) return
            for (const field of dt.fields) {
                if (field.fetch_from?.includes('.')) {
                    const linkField = field.fetch_from.split('.')[0]
                    prevLinkValues.set(linkField, modelValue.value[linkField])
                }
            }
        },
        { immediate: true },
    )

    watch(
        modelValue,
        async (doc) => {
            const dt = doctype.value
            if (!dt) return

            for (const field of dt.fields) {
                if (!field.fetch_from?.includes('.')) continue

                const [linkField, sourceField] = field.fetch_from.split('.')
                const newVal = doc[linkField]
                const oldVal = prevLinkValues.get(linkField)

                if (newVal === oldVal) continue

                // Update baseline immediately to avoid double-triggering
                prevLinkValues.set(linkField, newVal)

                if (newVal) {
                    const fieldMeta = dt.fields.find(f => f.fieldname === linkField)
                    if (!fieldMeta?.options) continue

                    try {
                        const linkedDoc = await docsApi.get(fieldMeta.options, String(newVal))
                        const fetchedVal = linkedDoc[sourceField]
                        if (fetchedVal !== undefined) {
                            updateField(field.fieldname, fetchedVal)
                        }
                    } catch (err) {
                        console.error(`[fetch_from] Failed to fetch ${fieldMeta.options}/${newVal}`, err)
                    }
                } else {
                    // Link was cleared — reset target field
                    updateField(field.fieldname, null)
                }
            }
        },
        { deep: true },
    )
}
