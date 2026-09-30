'use strict';
// Tokens stay in memory and disappear when this page closes or reloads.
let session = null;
let refreshing = null;
const byId = id => document.getElementById(id);
function message(text, error = false) {
  byId('message').textContent = text;
  byId('message').classList.toggle('error', error);
}
function lock() {
  session = null;
  byId('workspace').hidden = true;
  byId('signin').hidden = false;
  byId('logout').hidden = true;
  for (const id of ['categories', 'products', 'refunds', 'plans', 'category-select']) byId(id).replaceChildren();
}
async function request(path, options = {}, retry = true) {
  const response = await fetch('/api/v1' + path, {
    method: options.method || 'GET', cache: 'no-store', credentials: 'omit',
    headers: {'Content-Type': 'application/json', ...(session ? {Authorization: 'Bearer ' + session.access_token} : {})},
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(65000),
  });
  if (response.status === 401 && session && retry) {
    refreshing ||= request('/auth/refresh', {method: 'POST', body: {refresh_token: session.refresh_token}}, false)
      .then(value => { session = value; }).catch(error => { lock(); throw error; }).finally(() => { refreshing = null; });
    await refreshing;
    return request(path, options, false);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message || `Request failed (HTTP ${response.status}).`);
  return body;
}
function table(id, rows, columns) {
  const target = byId(id);
  target.replaceChildren();
  if (!rows.length) { target.textContent = 'No records yet.'; return; }
  const wrapper = document.createElement('div'); wrapper.className = 'table-wrap';
  const grid = document.createElement('table');
  const head = grid.createTHead().insertRow();
  for (const [label] of columns) { const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = label; head.append(cell); }
  const tbody = grid.createTBody();
  for (const row of rows) { const line = tbody.insertRow(); for (const [, key] of columns) line.insertCell().textContent = String(row[key] ?? '—'); }
  wrapper.append(grid); target.append(wrapper);
}
async function load() {
  const [categories, products, refunds, plans, availability] = await Promise.all([request('/catalog/categories'), request('/catalog/products'), request('/admin/refunds'), request('/premium/plans'), request('/premium/availability')]);
  if (!session) return;
  table('categories', categories, [['Name', 'name'], ['Slug', 'slug']]);
  table('products', products, [['Name', 'name'], ['Slug', 'slug'], ['Unit', 'default_unit']]);
  table('plans', plans.map(plan => ({...plan, price: plan.currency + ' ' + plan.price_amount + '/' + plan.billing_interval, features: plan.features.join(', ')})), [['Name', 'name'], ['Code', 'code'], ['Audience', 'audience'], ['Price', 'price'], ['Features', 'features'], ['Active', 'active']]);
  byId('premium-availability').textContent = availability.subscriptions_available ? 'Subscription provider is enabled. Entitlements require provider verification.' : 'Subscription provider is unavailable. Customers can view plans but cannot start subscriptions.';
  byId('category-select').replaceChildren();
  for (const category of categories) { const option = document.createElement('option'); option.value = category.id; option.textContent = category.name; byId('category-select').append(option); }
  byId('refunds').replaceChildren();
  if (!refunds.length) byId('refunds').textContent = 'No outstanding refunds.';
  for (const refund of refunds) {
    const article = document.createElement('article');
    const title = document.createElement('h3'); title.textContent = `${refund.currency} ${refund.amount} · ${refund.state}`;
    const detail = document.createElement('p'); detail.textContent = `Refund ${refund.id} · Order ${refund.order_id} · ${refund.reason}`;
    article.append(title, detail);
    if (['manual_required', 'failed', 'pending'].includes(refund.state)) {
      const form = document.createElement('form');
      for (const [name, text, max, required] of [['reference', 'Provider refund reference', 128, true], ['note', 'Operator note', 255, false]]) {
        const label = document.createElement('label'); label.textContent = text;
        const input = document.createElement('input'); input.name = name; input.maxLength = max; input.required = required; if (required) input.minLength = 3; label.append(input); form.append(label);
      }
      const button = document.createElement('button'); button.textContent = 'Record completed refund'; form.append(button);
      form.addEventListener('submit', event => { event.preventDefault(); if (!confirm('Confirm that this refund has already been paid and the reference is correct.')) return; run(button, async () => { await request(`/admin/refunds/${encodeURIComponent(refund.id)}/complete`, {method: 'POST', body: Object.fromEntries(new FormData(form))}); await load(); message('Refund recorded.'); }); });
      article.append(form);
    }
    byId('refunds').append(article);
  }
}
async function run(button, action) {
  button.disabled = true;
  try { await action(); } catch (error) { message(error.message || 'Could not reach the server. Please retry.', true); }
  finally { button.disabled = false; }
}
byId('login').addEventListener('submit', event => {
  event.preventDefault(); const form = event.currentTarget;
  run(form.querySelector('button'), async () => {
    message('Signing in. The server may take a minute to wake up.');
    session = await request('/auth/login', {method: 'POST', body: Object.fromEntries(new FormData(form))});
    form.elements.password.value = '';
    if (!session.user.roles.includes('administrator')) {
      try { await request('/auth/logout', {method: 'POST', body: {refresh_token: session.refresh_token}}, false); } finally { lock(); }
      throw new Error('An administrator account is required.');
    }
    await load(); byId('signin').hidden = true; byId('workspace').hidden = false; byId('logout').hidden = false;
    message('Signed in. Marketplace data is up to date.');
  });
});
for (const [id, path] of [['category', '/catalog/categories'], ['product', '/catalog/products']]) {
  byId(id).addEventListener('submit', event => { event.preventDefault(); const form = event.currentTarget;
    run(form.querySelector('button'), async () => { await request(path, {method: 'POST', body: Object.fromEntries(new FormData(form))}); form.reset(); await load(); message('Catalog updated.'); });
  });
}
byId('refresh').addEventListener('click', event => run(event.currentTarget, async () => { await load(); message('Marketplace data refreshed.'); }));
byId('logout').addEventListener('click', event => run(event.currentTarget, async () => {
  try { if (session) await request('/auth/logout', {method: 'POST', body: {refresh_token: session.refresh_token}}, false); }
  finally { lock(); message('Signed out.'); }
}));
byId('plan').addEventListener('submit', event => {
  event.preventDefault(); const form = event.currentTarget;
  const fields = new FormData(form);
  const body = {...Object.fromEntries(fields), features: fields.getAll('features')};
  if (!body.features.length) { message('Choose at least one feature.', true); return; }
  run(form.querySelector('button'), async () => { await request('/premium/plans', {method: 'POST', body}); form.reset(); await load(); message('Premium plan created.'); });
});
