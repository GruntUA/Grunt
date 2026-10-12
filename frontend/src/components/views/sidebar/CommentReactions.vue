<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { SmilePlus } from '@lucide/vue'
import { docsApi, type CommentReaction } from '@/core/api/docs'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

// `reply` - sits in a reply (group/reply), so the add button shows on that row's hover only.
const props = defineProps<{ comment: string; reply?: boolean }>()
const reactions = defineModel<CommentReaction[]>({ default: () => [] })
const { t } = useI18n()

// One request per page load - the choices are site settings.
let choicesRequest: Promise<string[]> | null = null
const choices = ref<string[]>([])
const pickerOpen = ref(false)
const busy = ref(false)

onMounted(async () => {
  choicesRequest ??= docsApi.getReactionChoices().catch(() => [])
  choices.value = await choicesRequest
})

async function toggle(emoji: string) {
  pickerOpen.value = false
  if (busy.value) return
  busy.value = true
  try {
    reactions.value = await docsApi.toggleReaction(props.comment, emoji)
  } catch { /* silent */ }
  finally { busy.value = false }
}
</script>

<template>
  <div v-if="choices.length" class="flex flex-wrap items-center gap-1">
    <Tooltip v-for="r in reactions" :key="r.emoji">
      <TooltipTrigger as-child>
        <Button variant="outline" size="xs" class="rounded-full px-2 tabular-nums"
          :class="r.mine && 'border-primary/40 bg-primary/10'"
          :aria-pressed="r.mine" :disabled="busy" @click="toggle(r.emoji)">
          {{ r.emoji }} {{ r.count }}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{{ r.users.join(', ') }}</TooltipContent>
    </Tooltip>
    <Popover v-model:open="pickerOpen">
      <PopoverTrigger as-child>
        <Button variant="ghost" size="icon-xs" :aria-label="t('Add reaction')"
          :class="!reactions.length && [
            'opacity-0 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(hover:none)]:opacity-100',
            reply ? 'group-hover/reply:opacity-100' : 'group-hover:opacity-100',
          ]">
          <SmilePlus />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" class="flex w-auto gap-0.5 p-1">
        <Button v-for="e in choices" :key="e" variant="ghost" size="icon-sm" class="text-base" @click="toggle(e)">
          {{ e }}
        </Button>
      </PopoverContent>
    </Popover>
  </div>
</template>
