<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { BookOpen, CircleCheck, CircleDashed, SkipForward, Undo2, X } from '@lucide/vue'
import { workspaceApi, type Onboarding, type OnboardingStep, type OnboardingStepStatus } from '@/core/api/workspace'
import { appUrl } from '@/core/workspaceUrl'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'
import { Progress } from '@/components/ui/progress'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** "First steps" checklists (ModuleOnboarding): the app's, or every one the user sees. */
const props = defineProps<{ app?: string | null; workspace?: string }>()

const { t } = useI18n()
const router = useRouter()
const onboardings = ref<Onboarding[]>([])

// These steps complete by themselves once the record / setting exists; the others when opened.
const AUTO_ACTIONS = ['Create Entry', 'Update Settings', 'Take a Tour']

async function load() {
  try {
    onboardings.value = await workspaceApi.getOnboardings(props.app)
  } catch { /* silent - the checklist is a hint, not the page */ }
}
onMounted(load)

function replace(updated: Onboarding) {
  onboardings.value = onboardings.value.map((o) => (o.name === updated.name ? updated : o))
}

async function mark(o: Onboarding, step: OnboardingStep, status: OnboardingStepStatus) {
  try {
    replace(await workspaceApi.markOnboardingStep(o.name, step.step_id, status))
  } catch { /* silent */ }
}

async function hide(o: Onboarding) {
  onboardings.value = onboardings.value.filter((x) => x.name !== o.name)
  try { await workspaceApi.hideOnboarding(o.name) } catch { /* silent */ }
}

function buttonLabel(step: OnboardingStep): string {
  if (step.action_label) return step.action_label
  const labels: Record<string, string> = {
    'Create Entry': t('Create'),
    'Update Settings': t('Set up'),
    'View Report': t('View report'),
    'Read Docs': t('Read'),
    'Watch Video': t('Watch'),
    'Take a Tour': t('Take the tour'),
  }
  return labels[step.action] ?? t('Open')
}

async function run(o: Onboarding, step: OnboardingStep) {
  const target = step.target
  if (!target) return
  if (!AUTO_ACTIONS.includes(step.action)) await mark(o, step, 'Completed')
  const url = appUrl({ ...target, workspace: props.workspace })
  if (/^https?:\/\//.test(url)) window.open(url, '_blank', 'noopener')
  else router.push(url)
}
</script>

<template>
  <Card v-for="o in onboardings" :key="o.name" class="gap-4">
    <CardHeader>
      <CardTitle>{{ o.title }}</CardTitle>
      <CardDescription v-if="o.subtitle">{{ o.subtitle }}</CardDescription>
      <CardAction class="flex items-center gap-1">
        <Button v-if="o.documentation_url" variant="ghost" size="sm" as-child>
          <a :href="o.documentation_url" target="_blank" rel="noopener"><BookOpen /> {{ t('Documentation') }}</a>
        </Button>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button variant="ghost" size="icon-sm" :aria-label="t('Hide checklist')" @click="hide(o)"><X /></Button>
          </TooltipTrigger>
          <TooltipContent>{{ t('Hide checklist') }}</TooltipContent>
        </Tooltip>
      </CardAction>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
      <div class="flex items-center gap-3">
        <Progress :model-value="(o.done / o.total) * 100" class="flex-1" />
        <span class="shrink-0 text-sm text-muted-foreground tabular-nums">{{ o.done }} / {{ o.total }}</span>
      </div>

      <p v-if="o.done === o.total" class="text-sm">
        {{ o.success_message || t('All set - every step is done.') }}
      </p>

      <ItemGroup class="-mx-2 gap-0.5">
        <Item v-for="step in o.steps" :key="step.step_id" size="sm" class="group gap-3 px-2 py-2">
          <ItemMedia>
            <CircleCheck v-if="step.status === 'Completed'" class="size-5 text-success" />
            <SkipForward v-else-if="step.status === 'Skipped'" class="size-5 text-muted-foreground" />
            <CircleDashed v-else class="size-5 text-muted-foreground" />
          </ItemMedia>
          <ItemContent class="min-w-0">
            <ItemTitle :class="step.status !== 'Pending' && 'text-muted-foreground line-through'">{{ step.title }}</ItemTitle>
            <ItemDescription v-if="step.description && step.status === 'Pending'">{{ step.description }}</ItemDescription>
          </ItemContent>
          <ItemActions>
            <template v-if="step.status === 'Pending'">
              <Button variant="ghost" size="sm"
                class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
                @click="mark(o, step, 'Skipped')">
                {{ t('Skip') }}
              </Button>
              <Button v-if="step.target" variant="outline" size="sm" @click="run(o, step)">{{ buttonLabel(step) }}</Button>
            </template>
            <Tooltip v-else-if="step.status === 'Skipped' || !AUTO_ACTIONS.includes(step.action)">
              <TooltipTrigger as-child>
                <Button variant="ghost" size="icon-sm" :aria-label="t('Undo')"
                  class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
                  @click="mark(o, step, 'Pending')">
                  <Undo2 />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{{ t('Undo') }}</TooltipContent>
            </Tooltip>
          </ItemActions>
        </Item>
      </ItemGroup>
    </CardContent>
  </Card>
</template>
