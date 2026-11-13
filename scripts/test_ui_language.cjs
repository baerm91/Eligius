const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');

test('language switch returns to the current filters and fragment', () => {
  const listeners = {};
  const form = {elements: {next: {value: '/browse/?q=old'}},
    addEventListener(name, fn) { listeners[name] = fn; }};
  const window = {location: {pathname: '/browse/', search: '?q=new&Nominal=Pfennig', hash: '#results'}};
  const document = {addEventListener(name, fn) { fn(); }, querySelectorAll() { return [form]; }};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'slg/static/js/eligius-i18n.js'), 'utf8'),
    {window, document, gettext: value => value});
  listeners.submit();
  assert.equal(form.elements.next.value, '/browse/?q=new&Nominal=Pfennig#results');
});

test('Search applies the new term synchronously and keeps selected facets', () => {
  const template = fs.readFileSync(path.join(root, 'slg/templates/slg/facet-lists.html'), 'utf8');
  const search = template.slice(template.indexOf('  function writeSearchToUrl()'),
    template.indexOf('  /***************** Event Binding'));
  const historyUpdate = template.slice(template.indexOf('  function updateHistoryForBfcache('), template.lastIndexOf('</script>'));
  const location = {pathname: '/browse/', search: '?q=old&Nominal=Pfennig', hash: '#results'};
  const history = {replaceState(state, title, target) {
    const url = new URL(target, 'http://localhost');
    location.search = url.search;
  }};
  const $ = selector => selector === '#searchInput'
    ? {attr: () => 'q', val: () => 'new'} : {val: () => 'False'};
  vm.runInNewContext(search + historyUpdate + '\nexecuteSearch();',
    {window: {location}, history, $, URLSearchParams});
  const result = new URL(location.href, 'http://localhost');
  assert.equal(result.searchParams.get('q'), 'new');
  assert.equal(result.searchParams.get('Nominal'), 'Pfennig');
  assert.equal(result.searchParams.get('unbestimmt'), 'False');
});
