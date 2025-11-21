<template>
  <div class="panel">
    <div class="log-controls">
      <h2 style="margin: 0; flex: 1;">Logs</h2>
      <span v-if="status" class="status-badge" :class="status">
        {{ statusText }}
      </span>
      <button
        v-if="logs.length > 0"
        class="btn btn-secondary"
        @click="clearLogs"
        style="padding: 6px 12px; font-size: 12px;"
      >
        Clear
      </button>
    </div>
    <div
      ref="logContainer"
      class="log-display"
      :style="{ minHeight: status ? '200px' : '400px' }"
    >
      <div v-if="logs.length === 0" class="empty-state">
        <p>No logs yet. Start a render job to see progress.</p>
      </div>
      <div
        v-for="(log, index) in logs"
        :key="index"
        class="log-line"
        :data-tag="getLogTag(log)"
      >
        {{ log }}
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'LogDisplay',
  props: {
    logs: {
      type: Array,
      default: () => [],
    },
    status: {
      type: String,
      default: null,
    },
  },
  watch: {
    logs() {
      this.$nextTick(() => {
        this.scrollToBottom();
      });
    },
  },
  computed: {
    statusText() {
      const statusMap = {
        queued: 'Queued',
        running: 'Running',
        complete: 'Complete',
        error: 'Error',
      };
      return statusMap[this.status] || this.status;
    },
  },
  methods: {
    getLogTag(log) {
      if (log.includes('[error]')) return 'error';
      if (log.startsWith('[audio]')) return 'audio';
      if (log.startsWith('[visual]')) return 'visual';
      if (log.startsWith('[render]')) return 'render';
      if (log.startsWith('[ffmpeg]')) return 'ffmpeg';
      if (log.startsWith('[cli]')) return 'cli';
      return '';
    },
    scrollToBottom() {
      const container = this.$refs.logContainer;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    },
    clearLogs() {
      this.$emit('clear');
    },
  },
};
</script>


