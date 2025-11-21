/**
 * API client for AudioGiphy backend.
 */

const API_BASE = import.meta.env.DEV ? '' : '/api';

/**
 * Start a render job.
 * @param {Object} params - Render parameters
 * @returns {Promise<Object>} Job response with job_id
 */
export async function startRender(params) {
  const response = await fetch(`${API_BASE}/api/render`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Connect to log stream using Server-Sent Events.
 * @param {string} jobId - Job ID
 * @param {Function} onLog - Callback for log messages
 * @param {Function} onStatus - Callback for status updates
 * @returns {EventSource} EventSource instance
 */
export function connectLogStream(jobId, onLog, onStatus) {
  const eventSource = new EventSource(`${API_BASE}/api/logs/${jobId}`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.type === 'log') {
        onLog(data.message);
      } else if (data.type === 'status') {
        onStatus(data.status, data.message);
        if (data.status === 'complete' || data.status === 'error') {
          eventSource.close();
        }
      }
    } catch (e) {
      console.error('Failed to parse SSE message:', e);
    }
  };

  eventSource.onerror = (error) => {
    console.error('SSE error:', error);
    eventSource.close();
  };

  return eventSource;
}

/**
 * Get job status.
 * @param {string} jobId - Job ID
 * @returns {Promise<Object>} Job status
 */
export async function getStatus(jobId) {
  const response = await fetch(`${API_BASE}/api/status/${jobId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}


