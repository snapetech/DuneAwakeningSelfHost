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
    scan: document.getElementById('scan'),
  };
  let catalog = { servers: [], stats: {} };
  const latencies = new Map();
  const regions = new Set(['Africa', 'Asia', 'Europe', 'Middle East', 'North America', 'Oceania', 'South America']);

  function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function hasExactKeys(value, keys) {
    return isRecord(value) && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0');
  }

  function boundedInteger(value, low, high) {
    return Number.isInteger(value) && value >= low && value <= high;
  }

  function boundedText(value, limit, required = false) {
    return typeof value === 'string' && value.length <= limit && (!required || value.trim().length > 0) && !/[\u0000-\u001f]/u.test(value);
  }

  function safeHttps(value, discord = false) {
    if (value === '' && discord) return true;
    if (typeof value !== 'string') return false;
    try {
      const parsed = new URL(value);
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port || parsed.search || parsed.hash) return false;
      const host = parsed.hostname.toLocaleLowerCase().replace(/\.$/u, '');
      if (!host || host === 'localhost' || host.endsWith('.local') || /^\d{1,3}(?:\.\d{1,3}){3}$/u.test(host) || host.includes(':')) return false;
      if (!discord) return parsed.hostname.length > 0;
      return /^(discord\.gg\/[A-Za-z0-9_-]{2,100}|(?:www\.)?discord\.com\/invite\/[A-Za-z0-9_-]{2,100})$/u.test(`${parsed.hostname}${parsed.pathname}`);
    } catch (_) {
      return false;
    }
  }

  function validateServerShape(server) {
    const entryKeys = ['schemaVersion', 'serverId', 'generatedAt', 'expiresAt', 'sourceUrl', 'profile', 'status', 'signingKey', 'signature'];
    const profileKeys = ['name', 'description', 'region', 'websiteUrl', 'discordInvite', 'game', 'software', 'features'];
    const statusKeys = ['state', 'playersOnline', 'capacity', 'build', 'sietches', 'maps'];
    if (!hasExactKeys(server, entryKeys) || !/^dash-[0-9a-f]{64}$/u.test(server.serverId) || !safeHttps(server.sourceUrl)) return false;
    if (!hasExactKeys(server.profile, profileKeys) || !boundedText(server.profile.name, 120, true) || !boundedText(server.profile.description, 500)) return false;
    if (!regions.has(server.profile.region) || server.profile.game !== 'Dune: Awakening' || !['DASH', 'Dune Docker Console', 'Other'].includes(server.profile.software)) return false;
    if (!safeHttps(server.profile.websiteUrl) || !safeHttps(server.profile.discordInvite, true)) return false;
    if (!Array.isArray(server.profile.features) || server.profile.features.length > 32 || server.profile.features.some((value) => typeof value !== 'string' || !/^[a-z0-9-]{1,64}$/u.test(value))) return false;
    if (!hasExactKeys(server.status, statusKeys) || !['online', 'degraded', 'offline'].includes(server.status.state) || !boundedText(server.status.build, 120, true)) return false;
    if (!boundedInteger(server.status.capacity, 1, 1000) || !boundedInteger(server.status.playersOnline, 0, server.status.capacity) || !boundedInteger(server.status.sietches, 0, 1000)) return false;
    if (!hasExactKeys(server.status.maps, ['online', 'warming', 'onDemand', 'offline', 'total']) || Object.values(server.status.maps).some((value) => !boundedInteger(value, 0, 1000))) return false;
    if (!hasExactKeys(server.signingKey, ['algorithm', 'publicKeyDerBase64']) || !hasExactKeys(server.signature, ['algorithm', 'payloadSha256', 'valueBase64'])) return false;
    return /^[A-Za-z0-9+/]{1,1368}={0,2}$/u.test(server.signingKey.publicKeyDerBase64)
      && /^[A-Za-z0-9+/]{1,1368}={0,2}$/u.test(server.signature.valueBase64)
      && /^[0-9a-f]{64}$/u.test(server.signature.payloadSha256);
  }

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
    if (!window.crypto?.subtle) throw new Error('browser signature verification unavailable');
    if (server?.schemaVersion !== 'dash-public-directory-entry/v1' || !validateServerShape(server)) throw new Error('listing schema is invalid');
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
    if (value === undefined) return 'not scanned';
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
      if (!hasExactKeys(data, ['schemaVersion', 'generatedAt', 'refreshAfter', 'stats', 'servers', 'rejected']) || data.schemaVersion !== 'dash-public-directory-catalog/v1' || !Array.isArray(data.servers)) throw new Error('directory schema is invalid');
      const generated = Date.parse(data.generatedAt);
      if (!Number.isFinite(generated) || generated > Date.now() + 300000) throw new Error('directory timestamp is invalid');
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
      nodes.scan.hidden = servers.length === 0;
    } catch (error) {
      nodes.summary.textContent = `Directory unavailable: ${error.message}`;
      nodes.empty.hidden = false;
      nodes.empty.querySelector('h2').textContent = 'The signed catalog is unavailable.';
    }
  }

  [nodes.search, nodes.region, nodes.state, nodes.sort].forEach((node) => node.addEventListener('input', render));
  nodes.scan.addEventListener('click', async () => {
    nodes.scan.disabled = true;
    nodes.scan.textContent = 'Scanning…';
    try {
      await Promise.all(catalog.servers.map(measure));
      render();
    } finally {
      nodes.scan.disabled = false;
      nodes.scan.textContent = 'Measure again';
    }
  });
  void load();
})();
