<script setup lang="ts">
import type { TabsListProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { TabsList } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<TabsListProps & {
  class?: HTMLAttributes["class"]
  variant?: 'pill' | 'underline'
}>()

const delegatedProps = reactiveOmit(props, "class", "variant")
</script>

<template>
  <TabsList
    v-bind="delegatedProps"
    :class="cn(
      variant === 'underline'
        ? 'flex items-center justify-start rounded-none bg-transparent p-0 border-b border-border'
        : 'inline-flex items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground',
      props.class,
    )"
  >
    <slot />
  </TabsList>
</template>
