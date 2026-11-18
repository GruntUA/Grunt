<script setup lang="ts">
import { computed } from 'vue'
import { RouterView } from 'vue-router'
import { ConfigProvider } from 'reka-ui'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import GruntDialog from '@/components/desk/GruntDialog.vue'
import TaskProgressPanel from '@/components/desk/TaskProgressPanel.vue'
import ServerErrorModal from '@/components/debug/ServerErrorModal.vue'
import FolderPickerDialog from '@/components/files/FolderPickerDialog.vue'
import AppToaster from '@/components/layout/AppToaster.vue'
import CommandPalette from '@/components/layout/CommandPalette.vue'
import LinkPreview from '@/components/layout/LinkPreview.vue'
import OfflineIndicator from '@/components/layout/OfflineIndicator.vue'
import PWAInstallPrompt from '@/components/pwa/PWAInstallPrompt.vue'
import { TooltipProvider } from '@/components/ui/tooltip'
import { localeTag } from '@/core/datetime'

// The UI language for every reka-ui component: date pickers start the week on the
// language's first day (uk - Monday) and name months and weekdays in it.
const locale = computed(() => localeTag())
</script>

<template>
  <ConfigProvider :locale="locale">
  <TooltipProvider>
    <ErrorBoundary>
      <RouterView />

      <CommandPalette />
      <LinkPreview />
      <PWAInstallPrompt />
    </ErrorBoundary>

    <!-- Outside the boundary: errors, dialogs, notices and offline sync must survive a crashed page. -->
    <ServerErrorModal />
    <GruntDialog />
    <FolderPickerDialog />
    <TaskProgressPanel />
    <OfflineIndicator />
    <AppToaster />
  </TooltipProvider>
  </ConfigProvider>
</template>
