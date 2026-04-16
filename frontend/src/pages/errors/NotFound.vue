<script setup lang="ts">
import ErrorLayout from './ErrorLayout.vue'
</script>

<template>
  <ErrorLayout 
    code="404" 
    title="Page not found" 
    message="The page you're looking for doesn't exist or has been moved."
    :showHomeButton="true"
  />
</template>
