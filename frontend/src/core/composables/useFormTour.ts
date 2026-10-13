import { computed, ref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { workspaceApi, type FormTour } from '@/core/api/workspace'

/**
 * Form tours (FormTour) of a DocType's form. Once the form has loaded, the tour
 * named in `?tour=` starts (a checklist step links there), else the first
 * `auto_start` tour the user hasn't taken. Finishing or closing a tour marks it
 * taken; the form's menu («Take a tour», global_form.js) starts it again.
 */
export function useFormTour(doctype: string, ready: Ref<boolean>) {
  const route = useRoute()
  const router = useRouter()
  const tours = ref<FormTour[]>([])
  const active = ref<FormTour | null>(null)
  let loaded = false

  function start(name?: string) {
    active.value = tours.value.find((t) => !name || t.name === name) ?? null
  }

  function finish() {
    const tour = active.value
    active.value = null
    if (!tour) return
    tour.taken = true
    workspaceApi.completeFormTour(tour.name).catch(() => { /* a hint, not the page */ })
    if (route.query.tour) void router.replace({ query: { ...route.query, tour: undefined } })
  }

  watch(ready, async (isReady) => {
    if (!isReady || loaded) return
    loaded = true
    try {
      tours.value = await workspaceApi.getFormTours(doctype)
    } catch { return }
    const requested = route.query.tour
    const auto = tours.value.find((t) => t.auto_start && !t.taken)
    if (typeof requested === 'string') start(requested)
    else if (auto) start(auto.name)
  }, { immediate: true })

  return { tours, active, hasTours: computed(() => tours.value.length > 0), start, finish }
}
