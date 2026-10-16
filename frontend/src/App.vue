<script setup lang="ts">
import { RouterView } from 'vue-router'
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
</script>

<template>
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
</template>
