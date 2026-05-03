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

    async function applyFetchFrom(dt: NonNullable<typeof doctype.value>, linkField: string, linkValue: unknown) {
        const fetchFields = dt.fields.filter(
            f => f.fetch_from?.startsWith(`${linkField}.`)
        )
        if (!fetchFields.length) return

        if (!linkValue) {
            for (const field of fetchFields) updateField(field.fieldname, null)
            return
        }

        const fieldMeta = dt.fields.find(f => f.fieldname === linkField)
        if (!fieldMeta?.options) return

        try {
            const linkedDoc = await docsApi.get(fieldMeta.options, String(linkValue))
            for (const field of fetchFields) {
                const sourceField = field.fetch_from!.split('.')[1]
                const fetchedVal = linkedDoc[sourceField]
                if (fetchedVal !== undefined) updateField(field.fieldname, fetchedVal)
            }
        } catch (err) {
            console.error(`[fetch_from] Failed to fetch ${fieldMeta.options}/${linkValue}`, err)
        }
    }

    watch(
        doctype,
        (dt) => {
            prevLinkValues.clear()
            if (!dt) return

            const seen = new Set<string>()
            for (const field of dt.fields) {
                if (!field.fetch_from?.includes('.')) continue
                const linkField = field.fetch_from.split('.')[0]
                const linkValue = modelValue.value[linkField]
                prevLinkValues.set(linkField, linkValue)

                // Fetch on initial load for every unique link field that has a value
                if (!seen.has(linkField)) {
                    seen.add(linkField)
                    applyFetchFrom(dt, linkField, linkValue)
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

            const seen = new Set<string>()
            for (const field of dt.fields) {
                if (!field.fetch_from?.includes('.')) continue

                const linkField = field.fetch_from.split('.')[0]
                if (seen.has(linkField)) continue
                seen.add(linkField)

                const newVal = doc[linkField]
                const oldVal = prevLinkValues.get(linkField)
                if (newVal === oldVal) continue

                prevLinkValues.set(linkField, newVal)
                await applyFetchFrom(dt, linkField, newVal)
            }
        },
        { deep: true },
    )
}
