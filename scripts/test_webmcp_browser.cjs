// Adapter boundary tests in Node's isolated VM, never a browser polyfill.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../slg/static/js/eligius-webmcp.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function harness({supported = true, failRegistration = false} = {}) {
  const registered = new Map(), calls = [], events = {}, navigations = [], timers = [];
  const dataNames = ['search_objects', 'get_object', 'get_facets', 'get_distribution', 'get_statistics'];
  const uiNames = ['navigate_to_object', 'navigate_to_coin_type', 'open_collection', 'set_browse_filters', 'clear_browse_filters', 'get_current_context'];
  const definition = name => ({name, description: name, inputSchema: {type: 'object', properties: {}},
    annotations: {readOnlyHint: dataNames.includes(name)}, endpoint: '/api/webmcp/' + name + '/'});
  const manifest = {data_tools: dataNames.map(definition), ui_tools: uiNames.map(definition),
    filter_names: ['Slg', 'Praegeherren', 'unbestimmt'], instructions: 'Shared filter instructions'};
  const status = {textContent: ''};
  const document = {currentScript: {dataset: {manifest: '/api/webmcp/manifest/'}},
    getElementById: () => status};
  if (supported) document.modelContext = {async registerTool(tool, options) {
    if (failRegistration && registered.size === 1) throw new Error('Registration unavailable');
    assert.ok(!registered.has(tool.name), 'No duplicate registration');
    registered.set(tool.name, tool);
    options.signal.addEventListener('abort', () => registered.delete(tool.name), {once: true});
  }};
  const window = {location: {origin: 'https://example.test', pathname: '/browse/', search: '?Slg=2',
    assign(url) { navigations.push(url); }}, addEventListener(name, fn) { events[name] = fn; }};
  const state = {reply: {total: 7, results: []}};
  const fetch = async (url, options) => {
    calls.push({url: url.toString(), options});
    if (options.signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    return {ok: true, async json() { return url.pathname === '/api/webmcp/manifest/' ? manifest : state.reply; }};
  };
  vm.runInNewContext(source, {document, window, fetch, URL, URLSearchParams, AbortController, DOMException,
    setTimeout(fn) { timers.push(fn); }});
  await tick();
  return {registered, calls, events, navigations, timers, state, window, manifest, status};
}

test('unsupported browsers perform no fetch or registration', async () => {
  const h = await harness({supported: false});
  assert.equal(h.calls.length, 0);
  assert.equal(h.registered.size, 0);
  assert.match(h.status.textContent, /nicht verfügbar/);
});

test('native API registers eleven tools and preserves shared schemas', async () => {
  const h = await harness();
  assert.equal(h.registered.size, 11);
  assert.equal(h.calls.length, 1, 'Only metadata is fetched automatically');
  for (const definition of h.manifest.data_tools) {
    assert.equal(h.registered.get(definition.name).inputSchema, definition.inputSchema);
  }
});

test('data tools forward parameters unchanged and return bounded server output', async () => {
  const h = await harness();
  const args = {filters: {Praegeherren: ['Valens'], Slg: [2]}, page: 3, page_size: 25};
  const result = await h.registered.get('search_objects').execute(args);
  assert.equal(result, h.state.reply);
  assert.deepEqual(JSON.parse(h.calls.at(-1).options.body), args);
  assert.equal(h.calls.at(-1).options.credentials, 'omit');
  assert.equal(h.navigations.length, 0);
});

test('all navigation actions use only validated same-origin server URLs', async () => {
  const h = await harness();
  for (const [name, args, url] of [
    ['navigate_to_object', {object_id: 46736}, '/objekt/46736/'],
    ['navigate_to_coin_type', {type_id: 12}, '/typ/12/'],
    ['open_collection', {collection_id: 2}, '/slg/2/'],
    ['set_browse_filters', {filters: {Praegeherren: ['Valens'], unbestimmt: true}}, '/browse/?Praegeherren=Valens&unbestimmt=True'],
    ['clear_browse_filters', {}, '/browse/'],
  ]) {
    h.state.reply = {url};
    const result = await h.registered.get(name).execute(args);
    assert.equal(result.navigating_to, url);
    assert.deepEqual(JSON.parse(h.calls.at(-1).options.body), args);
    h.timers.shift()();
    assert.equal(h.navigations.at(-1), 'https://example.test' + url);
  }
  h.state.reply = {url: 'https://evil.example/'};
  await assert.rejects(h.registered.get('navigate_to_object').execute({object_id: 1}), /Invalid Eligius/);
  assert.equal(h.timers.length, 0);
});

test('context reads live location rather than initial page state', async () => {
  const h = await harness();
  h.window.location.pathname = '/objekt/46736/';
  h.window.location.search = '';
  await h.registered.get('get_current_context').execute();
  assert.equal(new URL(h.calls.at(-1).url).searchParams.get('url'), '/objekt/46736/');
  h.window.location.pathname = '/browse/';
  h.window.location.search = '?Slg=2&auth_token=SECRET&page=4';
  await h.registered.get('get_current_context').execute();
  assert.equal(new URL(h.calls.at(-1).url).searchParams.get('url'), '/browse/?Slg=2');
});

test('pagehide unregisters tools and BFCache restore registers once', async () => {
  const h = await harness();
  h.events.pagehide({});
  assert.equal(h.registered.size, 0);
  h.events.pageshow({persisted: true});
  h.events.pageshow({persisted: true});
  await tick();
  assert.equal(h.registered.size, 11);
  assert.equal(h.calls.length, 2);
});

test('partial registration failure removes own tools without breaking page', async () => {
  const h = await harness({failRegistration: true});
  assert.equal(h.registered.size, 0);
  assert.match(h.status.textContent, /momentan nicht verfügbar/);
});

test('cancelled invocation cannot navigate', async () => {
  const h = await harness();
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(h.registered.get('open_collection').execute({collection_id: 2}, {signal: controller.signal}), /Cancelled/);
  assert.equal(h.timers.length, 0);
});
