(() => {
  'use strict';
  const nodes = {
    servers: document.getElementById('servers'),
    empty: document.getElementById('empty'),
    search: document.getElementById('search'),
    region: document.getElementById('region'),
    state: document.getElementById('state'),
    sort: document.getElementById('sort'),
    summary: document.getElementById('summary'),
    updated: document.getElementById('updated'),
    verified: document.getElementById('verified-count'),
  };
  let catalog = { servers: [], stats: {} };
  const latencies = new Map();

  function canonical(value) {
    if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
    if (value && typeof value === 'object') {
      return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
    }
    return JSON.stringify(value);
  }

  function decodeBase64(value) {
    const raw = atob(value);
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  }

  function hex(bytes) {
    return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, '0')).join('');
  }

  async function verifyServer(server) {
    if (!window.crypto?.subtle || server.schemaVersion !== 'dash-public-directory-entry/v1') throw new Error('browser signature verification unavailable');
    const signature = server.signature || {};
    const signingKey = server.signingKey || {};
    if (signature.algorithm !== 'Ed25519' || signingKey.algorithm !== 'Ed25519') throw new Error('unsupported listing signature');
    const { signature: ignored, ...unsigned } = server;
    void ignored;
    const payload = new TextEncoder().encode(canonical(unsigned));
    const digest = await crypto.subtle.digest('SHA-256', payload);
    if (hex(digest) !== signature.payloadSha256) throw new Error('listing digest mismatch');
    const publicDer = decodeBase64(signingKey.publicKeyDerBase64);
    const identity = await crypto.subtle.digest('SHA-256', publicDer);
    if (`dash-${hex(identity)}` !== server.serverId) throw new Error('listing identity mismatch');
    const key = await crypto.subtle.importKey('spki', publicDer, { name: 'Ed25519' }, false, ['verify']);
    const valid = await crypto.subtle.verify({ name: 'Ed25519' }, key, decodeBase64(signature.valueBase64), payload);
    if (!valid) throw new Error('listing signature invalid');
    const now = Date.now();
    const generated = Date.parse(server.generatedAt);
    const expires = Date.parse(server.expiresAt);
    if (!Number.isFinite(generated) || !Number.isFinite(expires) || generated > now + 300000 || expires <= now || expires - generated < 60000 || expires - generated > 900000) throw new Error('listing freshness invalid');
    return server;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function link(label, href) {
    const node = element('a', '', label);
    node.href = href;
    node.target = '_blank';
    node.rel = 'noopener noreferrer';
    return node;
  }

  function telemetry(label, value) {
    const box = element('div');
    box.append(element('dt', '', label), element('dd', '', value));
    return box;
  }

  function latencyLabel(id) {
    const value = latencies.get(id);
    if (value === undefined) return 'scanning';
    if (value === null) return 'unreachable';
    return `${value} ms`;
  }

  function renderCard(server) {
    const card = element('article', 'contact');
    const head = element('div', 'contact-head');
    const state = element('span', `state ${server.status.state}`, server.status.state === 'degraded' ? 'warming' : server.status.state);
    const latency = element('span', 'latency', latencyLabel(server.serverId));
    latency.dataset.latencyFor = server.serverId;
    head.append(state, latency);

    const title = element('h2', '', server.profile.name);
    const region = element('p', 'region', server.profile.region);
    const description = element('p', 'description', server.profile.description || 'Public Dune: Awakening community server.');
    const stats = element('dl', 'telemetry');
    stats.append(
      telemetry('Players', `${server.status.playersOnline}/${server.status.capacity}`),
      telemetry('Sietches', String(server.status.sietches)),
      telemetry('Maps live', `${server.status.maps.online}/${server.status.maps.total}`),
    );
    const actions = element('div', 'actions');
    actions.append(link('Open server', server.profile.websiteUrl));
    if (server.profile.discordInvite) actions.append(link('Discord', server.profile.discordInvite));
    const identity = element('span', 'identity', `signed ${server.serverId.slice(5, 17)}`);
    card.append(head, title, region, description, stats, actions, identity);
    return card;
  }

  function visibleServers() {
    const query = nodes.search.value.trim().toLocaleLowerCase();
    const region = nodes.region.value;
    const state = nodes.state.value;
    const rows = catalog.servers.filter((server) => {
      const text = `${server.profile.name} ${server.profile.description} ${server.profile.region}`.toLocaleLowerCase();
      return (!query || text.includes(query)) && (!region || server.profile.region === region) && (!state || server.status.state === state);
    });
    rows.sort((a, b) => {
      if (nodes.sort.value === 'name') return a.profile.name.localeCompare(b.profile.name);
      if (nodes.sort.value === 'players') return b.status.playersOnline - a.status.playersOnline || a.profile.name.localeCompare(b.profile.name);
      const rank = { online: 0, degraded: 1, offline: 2 };
      const stateOrder = rank[a.status.state] - rank[b.status.state];
      if (stateOrder) return stateOrder;
      const left = latencies.get(a.serverId);
      const right = latencies.get(b.serverId);
      return (left ?? Number.MAX_SAFE_INTEGER) - (right ?? Number.MAX_SAFE_INTEGER) || a.profile.name.localeCompare(b.profile.name);
    });
    return rows;
  }

  function render() {
    const rows = visibleServers();
    nodes.servers.replaceChildren(...rows.map(renderCard));
    nodes.empty.hidden = rows.length !== 0;
    nodes.summary.textContent = `${rows.length} of ${catalog.servers.length} verified contacts in band`;
  }

  async function measure(server) {
    const start = performance.now();
    try {
      const separator = server.sourceUrl.includes('?') ? '&' : '?';
      await fetch(`${server.sourceUrl}${separator}signal=${Date.now()}`, { mode: 'no-cors', cache: 'no-store' });
      latencies.set(server.serverId, Math.max(1, Math.round(performance.now() - start)));
    } catch (_) {
      latencies.set(server.serverId, null);
    }
    const node = document.querySelector(`[data-latency-for="${CSS.escape(server.serverId)}"]`);
    if (node) node.textContent = latencyLabel(server.serverId);
  }

  async function load() {
    try {
      const response = await fetch('directory.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`directory HTTP ${response.status}`);
      const data = await response.json();
      if (data.schemaVersion !== 'dash-public-directory-catalog/v1' || !Array.isArray(data.servers)) throw new Error('directory schema is invalid');
      const verified = await Promise.allSettled(data.servers.map(verifyServer));
      const servers = verified.filter((row) => row.status === 'fulfilled').map((row) => row.value);
      catalog = { ...data, servers };
      nodes.verified.textContent = String(servers.length);
      nodes.updated.textContent = `catalog ${new Date(data.generatedAt).toLocaleString()}`;
      const regions = [...new Set(servers.map((server) => server.profile.region))].sort();
      nodes.region.append(...regions.map((value) => {
        const option = element('option', '', value);
        option.value = value;
        return option;
      }));
      render();
      servers.forEach((server) => { void measure(server); });
    } catch (error) {
      nodes.summary.textContent = `Directory unavailable: ${error.message}`;
      nodes.empty.hidden = false;
      nodes.empty.querySelector('h2').textContent = 'The signed catalog is unavailable.';
    }
  }

  [nodes.search, nodes.region, nodes.state, nodes.sort].forEach((node) => node.addEventListener('input', render));
  void load();
})();
