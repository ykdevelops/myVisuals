<template>
  <div id="app">
    <div class="header">
      <div class="container">
        <h1>AudioGiphy - Video Renderer</h1>
      </div>
    </div>

    <div class="container">
      <div class="main-content">
        <div>
          <ErrorDisplay :error="error" @dismiss="error = null" />
          <RenderForm
            :is-submitting="isSubmitting"
            @submit="handleRenderSubmit"
          />
        </div>

        <div>
          <LogDisplay
            :logs="logs"
            :status="jobStatus"
            @clear="logs = []"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { startRender, connectLogStream } from './api.js';
import RenderForm from './components/RenderForm.vue';
import LogDisplay from './components/LogDisplay.vue';
import ErrorDisplay from './components/ErrorDisplay.vue';

export default {
  name: 'App',
  components: {
    RenderForm,
    LogDisplay,
    ErrorDisplay,
  },
  data() {
    return {
      logs: [],
      error: null,
      isSubmitting: false,
      jobStatus: null,
      eventSource: null,
    };
  },
  methods: {
    async handleRenderSubmit(params) {
      // Clear previous state
      this.error = null;
      this.logs = [];
      this.jobStatus = null;
      this.isSubmitting = true;

      // Close previous event source if any
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      try {
        // Start render job
        const response = await startRender(params);
        const jobId = response.job_id;

        this.logs.push(`[cli] Render job started: ${jobId}`);
        this.jobStatus = 'queued';

        // Connect to log stream
        this.eventSource = connectLogStream(
          jobId,
          (message) => {
            this.logs.push(message);
          },
          (status, message) => {
            this.jobStatus = status;
            if (message) {
              this.logs.push(`[status] ${message}`);
            }
            if (status === 'complete') {
              this.logs.push(`[cli] Render completed successfully!`);
              this.isSubmitting = false;
            } else if (status === 'error') {
              this.error = message || 'Render failed';
              this.isSubmitting = false;
            }
          }
        );
      } catch (err) {
        this.error = err.message || 'Failed to start render job';
        this.isSubmitting = false;
        this.logs.push(`[error] ${this.error}`);
      }
    },
  },
  beforeUnmount() {
    if (this.eventSource) {
      this.eventSource.close();
    }
  },
};
</script>


