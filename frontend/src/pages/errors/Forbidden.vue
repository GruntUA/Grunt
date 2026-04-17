<script setup lang="ts">
import ErrorLayout from './ErrorLayout.vue'
</script>

<template>
  <ErrorLayout 
    code="403" 
    title="Access denied" 
    message="You don't have permission to access this page."
    :showHomeButton="true"
    :showBackButton="true"
  />
</template>
