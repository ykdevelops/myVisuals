<template>
  <div class="panel">
    <h2>Render Settings</h2>
    <form @submit.prevent="handleSubmit">
      <div class="form-group">
        <label for="audio">Audio File Path</label>
        <input
          id="audio"
          v-model="form.audio"
          type="text"
          placeholder="mixes/88_to_134_mix.wav"
          required
        />
      </div>

      <div class="form-group">
        <label for="gif-folder">Video Folder (MP4s)</label>
        <input
          id="gif-folder"
          v-model="form.gif_folder"
          type="text"
          placeholder="bank"
          required
        />
      </div>

      <div class="form-group">
        <label for="duration">Duration (seconds)</label>
        <input
          id="duration"
          v-model.number="form.duration_seconds"
          type="number"
          min="1"
          required
        />
      </div>

      <div class="form-group">
        <label for="output">Output Path</label>
        <input
          id="output"
          v-model="form.output"
          type="text"
          placeholder="renders/test_60s.mp4"
          required
        />
      </div>

      <div class="form-group">
        <label>Resolution</label>
        <div class="form-row">
          <div>
            <label for="width" style="font-size: 12px;">Width</label>
            <input
              id="width"
              v-model.number="form.width"
              type="number"
              min="1"
            />
          </div>
          <div>
            <label for="height" style="font-size: 12px;">Height</label>
            <input
              id="height"
              v-model.number="form.height"
              type="number"
              min="1"
            />
          </div>
        </div>
      </div>

      <div class="form-group">
        <label for="seed">Seed (optional)</label>
        <input
          id="seed"
          v-model.number="form.seed"
          type="number"
          placeholder="Leave empty for random"
        />
      </div>

      <button
        type="submit"
        class="btn btn-primary"
        :disabled="isSubmitting"
      >
        {{ isSubmitting ? 'Starting...' : 'Start Render' }}
      </button>
    </form>
  </div>
</template>

<script>
export default {
  name: 'RenderForm',
  props: {
    isSubmitting: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['submit'],
  data() {
    return {
      form: {
        audio: 'mixes/88_to_134_mix.wav',
        gif_folder: 'bank',
        duration_seconds: 60,
        output: 'renders/test_60s.mp4',
        width: 1080,
        height: 1920,
        seed: null,
      },
    };
  },
  methods: {
    handleSubmit() {
      const params = {
        ...this.form,
        seed: this.form.seed || undefined,
      };
      this.$emit('submit', params);
    },
  },
};
</script>


