<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PencilLine } from '@lucide/vue'
import { useAppStore } from '@/stores/app'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PERMS_KEY } from '@/core/permissions'
import { docsApi } from '@/core/api/docs'
import { getPageData, getPageWidgetData } from '@/core/api/pages'
import { WIDGET_PERIOD_LOADER } from '@/core/widgetPeriod'
import AppIcon from '@/components/AppIcon.vue'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import OnboardingChecklists from '@/components/desk/OnboardingChecklists.vue'
import { setPageTitle } from '@/core/composables/usePageTitle'
import { useMasonryGrid } from '@/core/composables/useMasonryGrid'
import type { DashboardWidget } from '@/types'
import { docUrl } from '@/core/workspaceUrl'

const { t } = useI18n()

const props = defineProps<{ workspaceName: string }>()
const appStore = useAppStore()

const route = useRoute()
const router = useRouter()

const widgets = ref<DashboardWidget[]>([])
const widgetData = ref<Record<string, unknown>>({})
const loading = ref(false)
const canEdit = ref(false)
const grid = ref<HTMLElement | null>(null)
useMasonryGrid(grid)

const dashboards = computed(() => appStore.active?.dashboards ?? [])
/** `?page=` picks one of the app's dashboards; the home page otherwise. */
const currentPage = computed(() => {
  const wanted = typeof route.query.page === 'string' ? route.query.page : null
  if (wanted && dashboards.value.some((d) => d.name === wanted)) return wanted
  return dashboards.value[0]?.name ?? appStore.active?.home_page ?? null
})
const hasWidgets = computed(() => widgets.value.length > 0)

function selectPage(name: string | number) {
  const page = String(name)
  router.replace({ query: { ...route.query, page: page === appStore.active?.home_page ? undefined : page } })
}

provide(WIDGET_PERIOD_LOADER, async (widget, period) => {
  if (!currentPage.value) return null
  return getPageWidgetData(currentPage.value, widget.id, period)
})

let loadSeq = 0

async function loadPage(pageName: string) {
  const seq = ++loadSeq // a quick tab switch must not show the previous page's answer
  loading.value = true
  try {
    const doc = await docsApi.get('Page', pageName) as { widgets?: DashboardWidget[] } & Record<string, unknown>
    const data = await getPageData(pageName)
    if (seq !== loadSeq) return
    widgets.value = [...(doc.widgets ?? [])].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
    canEdit.value = !!(doc[PERMS_KEY] as { write?: boolean } | undefined)?.write
    widgetData.value = data
  } catch {
    if (seq !== loadSeq) return
    widgets.value = []
    widgetData.value = {}
    canEdit.value = false
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function init() {
  if (!appStore.active || appStore.active.name !== props.workspaceName) {
    await appStore.setActive(props.workspaceName)
  }
  setPageTitle(appStore.active?.label || props.workspaceName)
}

onMounted(init)
watch(() => props.workspaceName, init)

// One load per (app, dashboard) - switching tabs or apps both land here.
watch(
  () => (appStore.active?.name === props.workspaceName ? `${props.workspaceName}|${currentPage.value ?? ''}` : null),
  (key) => {
    if (key === null) return
    widgets.value = []
    widgetData.value = {}
    canEdit.value = false
    if (currentPage.value) void loadPage(currentPage.value)
  },
  { immediate: true },
)
</script>

<template>
  <div class="flex flex-1 flex-col gap-4 p-4 md:p-5 animate-in fade-in duration-500">
    <!-- Header -->
    <div v-if="appStore.active" class="flex items-center gap-3 mb-6">
      <SidebarTrigger class="shrink-0 -ml-1.5 text-muted-foreground/80" />
      <AppIcon :icon="appStore.active.icon || 'folder'" class="size-8 shrink-0" />
      <div class="min-w-0 flex-1">
        <h1 class="text-xl font-semibold text-foreground">{{ appStore.active.label }}</h1>
        <p v-if="appStore.active.description" class="text-muted-foreground">
          {{ appStore.active.description }}
        </p>
      </div>
      <Button v-if="canEdit && currentPage" variant="outline" size="sm" as-child>
        <router-link :to="docUrl('Page', currentPage, workspaceName)">
          <PencilLine /> {{ t('Edit') }}
        </router-link>
      </Button>
    </div>

    <!-- Dashboard switcher -->
    <Tabs v-if="dashboards.length > 1" :model-value="currentPage ?? undefined" class="-mt-4 mb-2" @update:model-value="selectPage">
      <TabsList class="max-w-full overflow-x-auto">
        <TabsTrigger v-for="d in dashboards" :key="d.name" :value="d.name">{{ d.label }}</TabsTrigger>
      </TabsList>
    </Tabs>

    <!-- First steps of this app (ModuleOnboarding) -->
    <OnboardingChecklists v-if="appStore.active?.app" :key="appStore.active.name"
      :app="appStore.active.app" :workspace="workspaceName" />

    <!-- Loading skeleton -->
    <div v-if="loading" class="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
      <div v-for="i in 4" :key="i" class="h-32 bg-muted animate-pulse rounded-lg" />
    </div>

    <!-- Widgets grid -->
    <div v-else-if="hasWidgets" ref="grid" class="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
      <WidgetCard
        v-for="widget in widgets"
        :key="widget.id"
        :widget="widget"
        :data="(widgetData[widget.id] ?? null) as unknown"
        :loading="loading"
        :workspace-name="workspaceName"
      />
    </div>

    <!-- Empty state -->
    <div v-else-if="appStore.active" class="flex flex-col items-center justify-center py-20 text-center">
      <AppIcon :icon="appStore.active.icon || 'folder'" class="size-12 mb-4 text-muted-foreground/40" />
      <p class="text-muted-foreground">{{ t('The home page is not set up.') }}</p>
      <p class="text-muted-foreground/60 mt-1">
        {{ t('Create a') }} <router-link :to="docUrl('Page', null, workspaceName)" class="text-primary hover:underline">{{ t('link|Page') }}</router-link>
        {{ t('and set it in the «Home page» field of the AppMenu settings.') }}
      </p>
    </div>
  </div>
</template>
