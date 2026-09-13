/* Native WebMCP adapter. All data, validation and URL construction stay in Django. */
(() => {
  'use strict';
  const script = document.currentScript;
  const manifestURL = script?.dataset.manifest;
  let lifecycle;

  function status(message) {
    const element = document.getElementById('webmcp-status');
    if (element) element.textContent = message;
  }

  async function request(endpoint, arguments_, signal) {
    const url = new URL(endpoint, window.location.origin);
    if (url.origin !== window.location.origin) throw new Error('Only Eligius endpoints are allowed.');
    const options = {credentials: 'omit', signal, headers: {Accept: 'application/json'}};
    if (arguments_ !== undefined) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(arguments_);
    }
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Eligius query unavailable.');
    return data;
  }

  function executionSignal(lifetime, invocation) {
    // Use both cancellation scopes without depending on AbortSignal.any().
    const controller = new AbortController();
    const abort = () => controller.abort();
    const signals = [lifetime, invocation].filter(Boolean);
    for (const signal of signals) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener('abort', abort, {once: true});
    }
    return {signal: controller.signal, cleanup() {
      for (const signal of signals) signal.removeEventListener('abort', abort);
    }};
  }

  async function start() {
    if (lifecycle || !manifestURL) return;
    const modelContext = document.modelContext;
    if (typeof modelContext?.registerTool !== 'function') {
      status('In diesem Browser ist WebMCP nicht verfügbar. Sie können Eligius wie gewohnt nutzen.');
      return;
    }
    const controller = new AbortController();
    lifecycle = controller;
    try {
      const manifest = await request(manifestURL, undefined, controller.signal);
      for (const definition of [...manifest.data_tools, ...manifest.ui_tools]) {
        if (controller.signal.aborted) return;
        const isData = manifest.data_tools.some(tool => tool.name === definition.name);
        await modelContext.registerTool({
          name: definition.name,
          description: definition.description + (definition.name === 'search_objects' ? '\n' + manifest.instructions : ''),
          inputSchema: definition.inputSchema,
          annotations: definition.annotations,
          async execute(arguments_ = {}, options = {}) {
            const execution = executionSignal(controller.signal, options.signal);
            try {
              if (definition.name === 'get_current_context') {
                if (Object.keys(arguments_).length) throw new Error('This tool takes no arguments.');
                // Read location at invocation time, including history/URL changes.
                const endpoint = new URL(definition.endpoint, window.location.origin);
                const query = new URLSearchParams(window.location.search);
                const allowed = new Set(manifest.filter_names);
                for (const key of [...query.keys()]) if (!allowed.has(key)) query.delete(key);
                endpoint.searchParams.set('url', window.location.pathname + (query.size ? '?' + query : ''));
                return await request(endpoint, undefined, execution.signal);
              }
              const result = await request(definition.endpoint, arguments_, execution.signal);
              if (isData) return result;
              const target = new URL(result.url, window.location.origin);
              if (target.origin !== window.location.origin || !result.url.startsWith('/') || result.url.startsWith('//')) {
                throw new Error('Invalid Eligius navigation target.');
              }
              if (execution.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
              // Return the tool result before unloading this document.
              setTimeout(() => {
                if (!controller.signal.aborted && !options.signal?.aborted) window.location.assign(target.href);
              }, 0);
              return {navigating_to: target.pathname + target.search};
            } finally {
              execution.cleanup();
            }
          },
        }, {signal: controller.signal});
      }
      status('WebMCP ist in diesem Browser aktiv. Ihr Browser-Assistent kann Eligius erkunden.');
    } catch (error) {
      controller.abort(); // Remove only this adapter's registrations, including partial setup.
      if (lifecycle === controller) lifecycle = undefined;
      if (error.name !== 'AbortError') status('WebMCP ist momentan nicht verfügbar. Eligius bleibt wie gewohnt nutzbar.');
    }
  }

  window.addEventListener('pagehide', () => {
    lifecycle?.abort();
    lifecycle = undefined;
  });
  window.addEventListener('pageshow', event => { if (event.persisted) void start(); });
  void start();
})();
