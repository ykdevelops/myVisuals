<template>
  <div v-if="error" class="error-display">
    <div class="error-display-header">
      <strong>Error</strong>
      <button
        class="error-display-close"
        @click="$emit('dismiss')"
        aria-label="Dismiss error"
      >
        ×
      </button>
    </div>
    <div class="error-display-message">
      {{ error }}
    </div>
  </div>
</template>

<script>
export default {
  name: 'ErrorDisplay',
  props: {
    error: {
      type: String,
      default: null,
    },
  },
  emits: ['dismiss'],
};
</script>


