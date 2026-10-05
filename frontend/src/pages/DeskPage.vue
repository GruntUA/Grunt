<script setup lang="ts">
import { formatNumber } from '@/core/currency'
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useUIStore } from '@/stores/ui'
import { workspaceApi } from '@/core/api/workspace'
import AppCard from '@/components/desk/AppCard.vue'
import ActivityStream from '@/components/dashboard/ActivityStream.vue'
import MyWorkPanel from '@/components/dashboard/MyWorkPanel.vue'
import { readRecent, looksLikeId, type RecentDoc } from '@/core/recentDocs'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'
import { Button } from '@/components/ui/button'
import ShortcutKbd from '@/components/ShortcutKbd.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Search,
  LayoutGrid,
  Eye,
  Sunrise,
  Sun,
  Sunset,
  Moon,
  Monitor,
  PackageOpen,
} from '@lucide/vue'
import { docUrl } from '@/core/workspaceUrl'

const { t } = useI18n()

const auth = useAuthStore()
async function exitImpersonation() {
  await auth.stopImpersonation()
  window.location.href = '/'
}
const appStore = useAppStore()
const uiStore = useUIStore()
const router = useRouter()
const colorMode = useColorMode()
async function onThemeChange(theme: unknown) { await auth.setTheme(theme as Theme) }

const allCounts = ref<Record<string, Record<string, number>>>({})

const recentDocs = ref<RecentDoc[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  // full_name is "Прізвище Ім'я [По-батькові]" (see User.before_save on the
  // backend) - the first name is the second word, not the first.
  const parts = auth.user?.full_name?.split(' ') ?? []
  const name = parts[1] ?? parts[0] ?? t('user')
  if (hour < 5) return { text: t('Good night, {name}', { name }), icon: Moon }
  if (hour < 12) return { text: t('Good morning, {name}', { name }), icon: Sunrise }
  if (hour < 18) return { text: t('Good afternoon, {name}', { name }), icon: Sun }
  return { text: t('Good evening, {name}', { name }), icon: Sunset }
})

// Honest, deduplicated business-document total (excludes logs/sessions/config).
// Falls back to summing per-workspace counts if the stats call fails.
const businessDocsTotal = ref<number | null>(null)
const totalDocsCount = computed(() => {
  if (businessDocsTotal.value !== null) return businessDocsTotal.value
  let total = 0
  for (const ws of Object.values(allCounts.value)) {
    total += Object.values(ws).reduce((s, v) => s + v, 0)
  }
  return total
})

onMounted(async () => {
  await appStore.loadAll()

  // Read history, dropping entries whose workspace is no longer installed.
  recentDocs.value = readRecent(appStore.workspaces.map(w => w.name))

  // Fire all count requests at once instead of walking workspaces serially -
  // they are independent, so serial awaits only added round-trips.
  const [counts] = await Promise.all([
    Promise.all(
      appStore.workspaces.map(async ws =>
        [ws.name, await workspaceApi.getCounts(ws.name).catch(() => ({}))] as const
      )
    ),
    workspaceApi.getDocumentStats()
      .then(s => { businessDocsTotal.value = s.total })
      .catch(() => { /* keep the per-workspace fallback in totalDocsCount */ }),
  ])
  allCounts.value = Object.fromEntries(counts)
})

function timeAgo(ts: number): string {
  const diff = Date.now() - ts
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return t('just now')
  if (minutes < 60) return t('{n} min', { n: String(minutes) })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('{n} h', { n: String(hours) })
  const days = Math.floor(hours / 24)
  return t('{n} d', { n: String(days) })
}

function findWorkspaceForDoc(doc: RecentDoc) {
  return appStore.workspaces.find(w => w.name === doc.workspace)
}

// Returns a human-readable display title for a document.
// Falls back to "DocType · short-id" when the title is blank or looks like an
// opaque id (UUID or hash name).
function hasRealTitle(doc: RecentDoc): boolean {
  return !!doc.title && !looksLikeId(doc.title)
}

function docDisplayTitle(doc: RecentDoc): string {
  if (hasRealTitle(doc)) return doc.title
  return `${doc.doctype} · ${doc.id.slice(0, 8)}`
}

function docInitials(doc: RecentDoc): string {
  if (hasRealTitle(doc)) return doc.title.slice(0, 2).toUpperCase()
  return doc.doctype.slice(0, 2).toUpperCase()
}
</script>

<template>
  <div class="h-screen overflow-y-auto bg-background">
    <main class="mx-auto max-w-6xl px-6 py-10 md:py-14">

      <!-- TOP BAR: theme toggle -->
      <div class="mb-4 flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon-sm" :title="t('Theme')">
              <component :is="colorMode.isDark.value ? Moon : Sun" class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value" @update:model-value="onThemeChange">
              <DropdownMenuRadioItem value="light" class="gap-2 p-2">
                <Sun class="size-4 shrink-0" />
                <span>{{ t('Light') }}</span>
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark" class="gap-2 p-2">
                <Moon class="size-4 shrink-0" />
                <span>{{ t('Dark') }}</span>
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system" class="gap-2 p-2">
                <Monitor class="size-4 shrink-0" />
                <span>{{ t('System') }}</span>
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <!-- HERO: greeting + search -->
      <section class="mx-auto max-w-xl space-y-5 pb-10 text-center">
        <div class="flex flex-col items-center gap-2">
          <div class="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <component :is="greeting.icon" class="size-5" />
          </div>
          <h1 class="text-2xl font-semibold tracking-tight text-foreground">
            <router-link v-if="auth.user" :to="`/app/grunt/User/${auth.user.id}`" :title="t('Open my profile')"
              class="transition-colors hover:text-primary">
              {{ greeting.text }}
            </router-link>
            <template v-else>{{ greeting.text }}</template>
          </h1>
          <p class="text-muted-foreground">{{ t('What are you planning to do today?') }}</p>
        </div>

        <div v-if="auth.isImpersonating"
          class="flex items-center justify-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-warning">
          <Eye class="size-3.5 shrink-0" />
          <span>{{ t('Viewing as {name}', { name: auth.user?.full_name ?? '' }) }} —
            <button type="button" class="font-semibold underline underline-offset-2" @click="exitImpersonation">
              {{ t('switch back') }}
            </button>
          </span>
        </div>

        <button type="button"
          class="flex w-full items-center gap-3 rounded-lg border bg-card px-4 py-3 text-left shadow-xs transition-colors hover:border-primary/40"
          @click="uiStore.openCommandPalette">
          <Search class="size-4 shrink-0 text-muted-foreground" />
          <span class="flex-1 text-muted-foreground">
            {{ t('Search documents, apps or actions...') }}
          </span>
          <ShortcutKbd shortcut="Mod+K" class="hidden shrink-0 sm:inline-flex" />
        </button>

        <p class="text-muted-foreground">
          {{ t('{apps} apps · {docs} documents in the system', { apps: String(appStore.workspaces.length), docs: formatNumber(totalDocsCount) }) }}
        </p>
      </section>

      <!-- CONTINUE: recent documents strip -->
      <section v-if="recentDocs.length" class="space-y-3 pb-10">
        <h2 class="font-medium text-foreground">{{ t('Continue') }}</h2>
        <div class="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1">
          <button v-for="doc in recentDocs.slice(0, 10)" :key="doc.id"
            class="group flex w-56 shrink-0 flex-col gap-2.5 rounded-lg border bg-card p-3 text-left transition-colors hover:border-primary/40"
            @click="router.push(docUrl(doc.doctype, doc.id, doc.workspace))">
            <div class="flex items-center justify-between">
              <div class="flex size-8 shrink-0 items-center justify-center rounded-md font-semibold"
                :style="{
                  backgroundColor: `color-mix(in srgb, ${findWorkspaceForDoc(doc)?.color ?? 'var(--primary)'} 15%, transparent)`,
                  color: findWorkspaceForDoc(doc)?.color ?? 'var(--primary)'
                }">
                {{ docInitials(doc) }}
              </div>
              <span class="font-mono text-muted-foreground/70">{{ timeAgo(doc.ts) }}</span>
            </div>
            <div class="min-w-0">
              <p class="truncate font-semibold text-foreground transition-colors group-hover:text-primary">
                {{ docDisplayTitle(doc) }}
              </p>
              <p class="truncate font-mono text-muted-foreground/70">{{ doc.doctype }}</p>
            </div>
          </button>
        </div>
      </section>

      <!-- MAIN: apps launcher + attention sidebar -->
      <div class="grid grid-cols-1 items-start gap-8 pb-12 lg:grid-cols-[1fr_340px]">

        <!-- Apps -->
        <section class="space-y-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <LayoutGrid class="size-3.5 text-muted-foreground" />
              <h2 class="font-semibold text-foreground">{{ t('Your apps') }}</h2>
            </div>
            <span class="text-muted-foreground">{{ t('{n} installed', { n: String(appStore.workspaces.length) }) }}</span>
          </div>

          <!-- Loading skeleton -->
          <div v-if="appStore.loading" class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div v-for="i in 4" :key="i" class="h-16 animate-pulse rounded-lg border bg-card" />
          </div>

          <!-- Empty state -->
          <div v-else-if="appStore.workspaces.length === 0 && !auth.isSystemManager"
            class="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-20 text-center">
            <PackageOpen class="size-8 text-muted-foreground/50" />
            <p class="text-muted-foreground">{{ t('No apps installed') }}</p>
          </div>

          <!-- Cards grid -->
          <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <AppCard v-for="ws in appStore.workspaces" :key="ws.name" :workspace="ws" :counts="allCounts[ws.name]" />
          </div>
        </section>

        <!-- Attention: my work + activity -->
        <aside class="space-y-6 lg:sticky lg:top-14">
          <MyWorkPanel />
          <div class="h-[380px]">
            <ActivityStream />
          </div>
        </aside>
      </div>

    </main>
  </div>
</template>
