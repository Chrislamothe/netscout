
let allDevices = [];
let currentFilter = 'all';
let currentView = 'list';
let sortCol = 'ip';
let sortAsc = true;
let expandedMacs = new Set();
let pollTimer = null;

async function loadInfo() {
  const r = await fetch('/api/info').then(x => x.json());
  document.getElementById('local-ip').textContent = r.local_ip;
  document.getElementById('subnet-count').textContent = r.subnets.length;
  document.getElementById('scapy-pill').innerHTML =
    r.scapy
      ? 'ENGINE <b style="color:var(--green)">SCAPY</b>'
      : 'ENGINE <b style="color:var(--yellow)">ARP FALLBACK</b>';
  document.getElementById('auto-subnet').textContent = r.subnet;
  document.getElementById('extra-subnets-input').value = (r.extra_subnets || []).join('\n');
  renderActiveSubnets(r.subnets);
}

function renderActiveSubnets(subnets) {
  document.getElementById('subnet-count').textContent = subnets.length;
  document.getElementById('active-subnets').innerHTML = subnets.map(s =>
    `<span style="font-family:var(--font-mono);font-size:11px;padding:3px 10px;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);border-radius:3px;color:var(--accent)">${s}</span>`
  ).join('');
}

function toggleSettings() {
  const p = document.getElementById('settings-panel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
}

async function saveSubnets() {
  const raw = document.getElementById('extra-subnets-input').value;
  const extra_subnets = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const r = await fetch('/api/subnets', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({extra_subnets})
  }).then(x => x.json());

  const status = document.getElementById('subnet-save-status');
  status.textContent = '✓ Saved';
  status.style.opacity = '1';
  setTimeout(() => status.style.opacity = '0', 2000);

  // Refresh info
  const info = await fetch('/api/info').then(x => x.json());
  renderActiveSubnets(info.subnets);
  document.getElementById('subnet-count').textContent = info.subnets.length;
}

async function loadDevices() {
  const r = await fetch('/api/devices').then(x => x.json());
  allDevices = r.devices;
  if (r.last_scan) {
    const d = new Date(r.last_scan);
    document.getElementById('last-scan').textContent =
      'Last scan: ' + d.toLocaleTimeString();
  }
  updateStats();
  renderDevices();
}

function updateStats() {
  const online = allDevices.filter(d => d.online).length;
  const offline = allDevices.filter(d => !d.online).length;
  const labeled = allDevices.filter(d => d.label).length;
  document.getElementById('count-online').textContent = online;
  document.getElementById('count-offline').textContent = offline;
  document.getElementById('count-labeled').textContent = labeled;
  document.getElementById('count-total').textContent = allDevices.length;
}

function setFilter(f) {
  currentFilter = f;
  ['all','online','offline','labeled'].forEach(x => {
    document.getElementById('f-' + x).classList.toggle('active', x === f);
  });
  renderDevices();
}

function ipSortKey(ip) {
  if (!ip) return [999, 999, 999, 999];
  const o = ip.split('.').map(n => parseInt(n, 10));
  if (o.length !== 4 || o.some(isNaN)) return [999, 999, 999, 999];
  return [o[3], o[0], o[1], o[2]];
}

function ipToNum(ip) {
  const k = ipSortKey(ip);
  return k[0] * 1000000 + k[1] * 10000 + k[2] * 100 + k[3];
}

function setView(v) {
  currentView = v;
  ['list','grid','table'].forEach(x => {
    const btn = document.getElementById('v-' + x);
    if (btn) btn.classList.toggle('active', x === v);
  });
  renderDevices();
}

function getFilteredDevices() {
  const q = document.getElementById('search').value.toLowerCase();
  let devices = allDevices;
  if (currentFilter === 'online')  devices = devices.filter(d => d.online);
  if (currentFilter === 'offline') devices = devices.filter(d => !d.online);
  if (currentFilter === 'labeled') devices = devices.filter(d => d.label);
  if (categoryFilter) devices = devices.filter(d => autoCategory(d) === categoryFilter);
  if (q) {
    devices = devices.filter(d =>
      (d.ip||'').includes(q) ||
      (d.mac||'').includes(q) ||
      (d.hostname||'').toLowerCase().includes(q) ||
      (d.label||'').toLowerCase().includes(q) ||
      (d.vendor_custom||d.vendor||'').toLowerCase().includes(q) ||
      (d.subnet||'').includes(q)
    );
  }
  return devices;
}

function sortDevices(devices) {
  return [...devices].sort((a, b) => {
    let av, bv;
    if (sortCol === 'ip') {
      // Always sort IPs numerically regardless of sort direction
      const diff = ipToNum(a.ip) - ipToNum(b.ip);
      return sortAsc ? diff : -diff;
    }
    if (sortCol === 'online') { av = a.online ? '0' : '1'; bv = b.online ? '0' : '1'; }
    else if (sortCol === 'latency_ms') {
      av = a.latency_ms ?? 9999; bv = b.latency_ms ?? 9999;
      return sortAsc ? av - bv : bv - av;
    } else {
      av = (a[sortCol] || '').toString().toLowerCase();
      bv = (b[sortCol] || '').toString().toLowerCase();
    }
    return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
}

function setSort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  renderDevices();
}

function renderDevices() {
  if (currentView === 'list')  { renderList();  return; }
  if (currentView === 'table') { renderTable(); return; }
  // Grid view
  const devices = sortDevices(getFilteredDevices());
  if (!devices.length) {
    document.getElementById('device-container').innerHTML = `
      <div class="device-grid" id="device-grid">
        <div class="empty-state"><div class="icon">⬡</div><p>${
          allDevices.length ? 'No devices match your filter.' : 'No devices yet.<br>Run a scan to discover your network.'
        }</p></div>
      </div>`;
    return;
  }
  document.getElementById('device-container').innerHTML =
    `<div class="device-grid" id="device-grid">${devices.map((d,i) => cardHTML(d,i)).join('')}</div>`;
}

function toggleExpand(mac) {
  const detail = document.getElementById('detail-' + mac.replace(/:/g,'-'));
  const row    = document.getElementById('row-'    + mac.replace(/:/g,'-'));
  if (!detail) return;
  const isOpen = detail.classList.contains('open');
  if (isOpen) {
    detail.classList.remove('open');
    row.classList.remove('expanded');
    expandedMacs.delete(mac);
  } else {
    detail.classList.add('open');
    row.classList.add('expanded');
    expandedMacs.add(mac);
  }
}

// ── Device categories ─────────────────────────────────────────────────────────
const CATEGORIES = {
  server:  { label: 'Server / VM',    color: 'var(--cat-server)'  },
  infra:   { label: 'Infrastructure', color: 'var(--cat-infra)'   },
  iot:     { label: 'IoT Device',     color: 'var(--cat-iot)'     },
  desktop: { label: 'Desktop / User', color: 'var(--cat-desktop)' },
  unknown: { label: 'Unknown',        color: 'var(--cat-unknown)' },
};

let categoryFilter = null;

function autoCategory(d) {
  if (d.category) return d.category;
  const vendor  = (d.vendor_custom || d.vendor || '').toLowerCase();
  const os      = (d.os_guess || '').toLowerCase();
  const host    = (d.hostname || d.label || '').toLowerCase();
  const ports   = (d.open_ports || []).map(p => p.port);
  const connType = d.connection_type || '';
  if (connType === 'wireless' && d.wifi) return 'iot';
  if (os === 'network device' || os === 'router/modem' || os === 'printer') return 'infra';
  if (vendor.includes('ubiquiti') || vendor.includes('aruba') || vendor.includes('cisco')
    || vendor.includes('netgear') || vendor.includes('tp-link') || vendor.includes('zyxel')
    || vendor.includes('fortinet') || vendor.includes('hewlett packard enterp')) return 'infra';
  if (host.includes('switch') || host.includes('router') || host.includes('gateway')
    || host.includes(' ap') || host.includes('firewall')) return 'infra';
  if (os === 'iot device') return 'iot';
  if (vendor.includes('espressif') || vendor.includes('tuya') || vendor.includes('shenzhen')
    || vendor.includes('ring') || vendor.includes('amazon') || vendor.includes('philips')
    || vendor.includes('sonos') || vendor.includes('belkin') || vendor.includes('wyze')
    || vendor.includes('eero') || vendor.includes('tp-link sys')) return 'iot';
  if (host.includes('iot') || host.includes('cam') || host.includes('sensor')
    || host.includes('thermostat') || host.includes('doorbell') || host.includes('echo')) return 'iot';
  if (vendor.includes('vmware')) return 'server';
  if (ports.includes(22) && (ports.includes(80) || ports.includes(443) || ports.includes(3306)
    || ports.includes(5432) || ports.includes(6379) || ports.includes(9200))) return 'server';
  if (host.includes('server') || host.includes('-vm') || host.includes('esxi')
    || host.includes('proxmox') || host.includes('nas') || host.includes('plex')
    || host.includes('docker') || host.includes('node')) return 'server';
  if (vendor.includes('synology') || vendor.includes('qnap')) return 'server';
  if (os === 'windows' || ports.includes(3389)) return 'desktop';
  if (vendor.includes('apple') || vendor.includes('intel') || vendor.includes('dell')
    || vendor.includes('lenovo') || vendor.includes('asus') || vendor.includes('acer')
    || vendor.includes('microsoft')) return 'desktop';
  if (host.includes('macbook') || host.includes('iphone') || host.includes('ipad')
    || host.includes('pixel') || host.includes('laptop') || host.includes('desktop')) return 'desktop';
  return 'unknown';
}

function getCatColor(d) {
  return CATEGORIES[autoCategory(d)]?.color || 'var(--cat-unknown)';
}

function filterByCategory(cat) {
  categoryFilter = cat;
  Object.keys(CATEGORIES).forEach(c => {
    const el = document.getElementById('leg-' + c);
    if (el) el.classList.toggle('active', c === cat);
  });
  renderDevices();
}

async function saveCategory(mac, value) {
  await fetch(`/api/device/${encodeURIComponent(mac)}/category`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({category: value})
  });
  const dev = allDevices.find(d => d.mac === mac);
  if (dev) dev.category = value;
  renderDevices();
  toast(value ? `Category set to "${CATEGORIES[value]?.label}"` : 'Category auto-detected');
}

function categorySelectHTML(mac) {
  const dev = allDevices.find(d => d.mac === mac);
  const current = dev?.category || '';
  return `<select class="cat-select" onchange="saveCategory('${mac}', this.value)">
    <option value="">Auto-detect</option>
    ${Object.entries(CATEGORIES).map(([k,v]) =>
      `<option value="${k}" ${current===k?'selected':''}>${v.label}</option>`
    ).join('')}
  </select>`;
}

function renderList() {
  // List view always sorts by IP numerically
  const saved = sortCol;
  const savedAsc = sortAsc;
  sortCol = 'ip';
  sortAsc = true;
  const devices = sortDevices(getFilteredDevices());
  sortCol = saved;
  sortAsc = savedAsc;
  const container = document.getElementById('device-container');

  if (!devices.length) {
    container.innerHTML = `
      <div class="device-grid">
        <div class="empty-state"><div class="icon">⬡</div><p>${
          allDevices.length ? 'No devices match your filter.' : 'No devices yet.<br>Run a scan to discover your network.'
        }</p></div>
      </div>`;
    return;
  }

  const rows = devices.map(d => {
    const macDash = d.mac.replace(/:/g,'-');
    const name    = displayName(d);
    const vendor  = d.vendor_custom || d.vendor || '—';
    const isOpen  = expandedMacs.has(d.mac);
    const portBadge = d.connection_type === 'wireless' && d.wifi
      ? `<span style="color:var(--accent2);font-size:10px">📶 ${escHtml(d.wifi.ssid)}</span>`
      : d.switch_port
        ? `<span style="color:var(--accent);font-size:10px">${escHtml(d.switch_port.port)}</span>`
        : (d.latency_ms != null
            ? `<span style="color:${d.latency_ms < 5 ? 'var(--green)' : d.latency_ms < 20 ? 'var(--yellow)' : 'var(--red)'}; font-size:10px">${d.latency_ms}ms</span>`
            : '');
    const osLabel = d.os_guess && d.os_guess !== 'Unknown'
      ? `<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">${escHtml(d.os_guess)}</span>`
      : '';

    return `
<div class="list-row ${d.online ? '' : 'offline'} ${isOpen ? 'expanded' : ''}"
     id="row-${macDash}" onclick="toggleExpand('${d.mac}')">
  <span class="cat-bar" style="background:${getCatColor(d)}"></span>
  <span style="width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;background:${d.online ? 'var(--green)' : 'var(--text-dim)'};box-shadow:${d.online ? '0 0 5px var(--green)' : 'none'}"></span>
  <span class="list-ip">${d.ip || '—'}</span>
  <span class="list-name">${escHtml(name)} ${osLabel}</span>
  <span class="list-vendor">${escHtml(vendor)}</span>
  <span class="list-port">${portBadge}</span>
  <span class="list-chevron">▶</span>
</div>
<div class="list-detail ${isOpen ? 'open' : ''}" id="detail-${macDash}">
  ${cardHTML(d, 0)}
</div>`;
  }).join('');

  container.innerHTML = `
<div class="device-list">
  <div class="list-row list-header">
    <span></span>
    <span></span>
    <span class="list-col-hdr">IP</span>
    <span class="list-col-hdr">Name / OS</span>
    <span class="list-col-hdr">Vendor</span>
    <span class="list-col-hdr">Port / Latency</span>
    <span></span>
  </div>
  ${rows}
</div>`;
}

function renderTable() {
  const devices = sortDevices(getFilteredDevices());

  if (!devices.length) {
    document.getElementById('device-container').innerHTML = `
      <div class="device-grid" id="device-grid">
        <div class="empty-state"><div class="icon">⬡</div><p>${
          allDevices.length ? 'No devices match your filter.' : 'No devices yet.<br>Run a scan to discover your network.'
        }</p></div>
      </div>`;
    return;
  }

  const arrow = col => `<span class="sort-arrow">${sortCol===col ? (sortAsc?'▲':'▼') : '⇅'}</span>`;
  const th = (col, label) =>
    `<th class="${sortCol===col?'sorted':''}" onclick="setSort('${col}')">${label}${arrow(col)}</th>`;

  const rows = devices.map(d => {
    const mac = d.mac.replace(/:/g, '-');
    const name = displayName(d);
    const vendor = escHtml(d.vendor_custom || d.vendor || '—');
    const hasCustomVendor = !!d.vendor_custom;
    return `
<tr class="${d.online ? '' : 'offline'}">
  <td><span class="tbl-dot ${d.online?'':'off'}"></span></td>
  <td class="tbl-name">
    ${escHtml(name)}
    ${d.label ? '<span class="tbl-custom">[custom]</span>' : ''}
  </td>
  <td>${d.ip || '—'}</td>
  <td style="font-family:var(--font-mono);font-size:11px">${d.mac || '—'}</td>
  <td>
    ${vendor}${hasCustomVendor ? ' <span style="font-size:9px;color:var(--accent2)">[custom]</span>' : ''}
  </td>
  <td style="font-size:11px">${escHtml(d.os_guess || '—')}</td>
  <td style="font-family:var(--font-mono);font-size:11px">${d.latency_ms != null ? `<span style="color:${d.latency_ms < 5 ? 'var(--green)' : d.latency_ms < 20 ? 'var(--yellow)' : 'var(--red)'}">${d.latency_ms}ms</span>` : '—'}</td>
  <td style="font-size:10px">${d.open_ports && d.open_ports.length ? d.open_ports.map(p=>`<span title="${p.service}" style="padding:1px 4px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);border-radius:2px;margin-right:2px">${p.port}</span>`).join('') : '—'}</td>
  <td style="font-size:11px">${d.switch_port ? `<span style="color:var(--text-dim)">${escHtml(d.switch_port.switch)}</span> <span style="color:var(--accent)">${escHtml(d.switch_port.port)}</span>${d.switch_port.port_desc ? `<br><span style="color:var(--text-dim);font-size:10px">${escHtml(d.switch_port.port_desc)}</span>` : ''}` : '—'}</td>
  <td>${escHtml(d.subnet || '—')}</td>
  <td>${escHtml(d.hostname || '—')}</td>
  <td>
    <input class="tbl-input" id="tbl-lbl-${mac}" value="${escHtml(d.label||'')}" placeholder="Set name…"
      onkeydown="if(event.key==='Enter') saveLabel('${d.mac}','${mac}')">
    <button class="tbl-save" onclick="saveLabel('${d.mac}','${mac}')">Name</button>
  </td>
  <td>
    <input class="tbl-input" id="tbl-ven-${mac}" value="${escHtml(d.vendor_custom||'')}" placeholder="Override vendor…"
      onkeydown="if(event.key==='Enter') saveVendorFrom('tbl-ven-','${d.mac}','${mac}')">
    <button class="tbl-save vendor" onclick="saveVendorFrom('tbl-ven-','${d.mac}','${mac}')">Vendor</button>
    <button class="tbl-clear" onclick="clearVendorFrom('tbl-ven-','${d.mac}','${mac}')">↺</button>
  </td>
</tr>`;
  }).join('');

  document.getElementById('device-container').innerHTML = `
<div class="device-table-wrap">
  <table class="device-table">
    <thead><tr>
      ${th('online','●')}
      ${th('label','Name')}
      ${th('ip','IP')}
      ${th('mac','MAC')}
      ${th('vendor','Vendor')}
      ${th('os_guess','OS')}
      ${th('latency_ms','Latency')}
      <th>Ports</th>
      <th>Switch Port</th>
      ${th('subnet','Subnet')}
      ${th('hostname','Hostname')}
      <th>Set Name</th>
      <th>Set Vendor</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
</div>`;
}

function displayName(d) {
  return d.label || d.hostname || d.ip || d.mac;
}

function cardHTML(d, idx) {
  const mac = d.mac.replace(/:/g, '-');
  const name = displayName(d);
  const hasLabel = !!d.label;
  const hasCustomVendor = !!d.vendor_custom;
  const lastSeen = d.last_seen ? new Date(d.last_seen).toLocaleString() : '—';
  return `
<div class="device-card ${d.online ? '' : 'offline'}" style="animation-delay:${idx * 30}ms">
  <div class="status-dot"></div>
  <div class="device-name">
    ${escHtml(name)}
    ${hasLabel ? '<span class="custom-tag">custom</span>' : ''}
  </div>
  <div class="device-meta">
    <b>IP</b> ${d.ip || '—'}<br>
    <b>MAC</b> ${d.mac || '—'}<br>
    <b>Vendor</b> ${escHtml(d.vendor_custom || d.vendor || '—')}${hasCustomVendor ? ' <span style="font-size:9px;color:var(--accent2)">[custom]</span>' : ''}<br>
    ${d.hostname ? `<b>Host</b> ${escHtml(d.hostname)}<br>` : ''}
    ${d.os_guess ? `<b>OS</b> ${escHtml(d.os_guess)}${d.ttl ? ` <span style="color:var(--text-dim);font-size:10px">(TTL ${d.ttl})</span>` : ''}<br>` : ''}
    ${d.latency_ms != null ? `<b>Latency</b> <span style="color:${d.latency_ms < 5 ? 'var(--green)' : d.latency_ms < 20 ? 'var(--yellow)' : 'var(--red)'}">${d.latency_ms}ms</span><br>` : ''}
    ${d.connection_type === 'wireless' && d.wifi
      ? `<b>WiFi</b> 📶 ${escHtml(d.wifi.ssid)} <span style="color:var(--text-dim);font-size:10px">${escHtml(d.wifi.band)}</span><br>
         <b>AP</b> ${escHtml(d.wifi.ap)}<br>`
      : d.switch_port
        ? `<b>Switch</b> ${escHtml(d.switch_port.switch)} / <span style="color:var(--accent)">${escHtml(d.switch_port.port)}</span>${d.switch_port.port_desc ? ` <span style="color:var(--text-dim);font-size:10px">${escHtml(d.switch_port.port_desc)}</span>` : ''}<br>`
        : ''}
    ${d.open_ports && d.open_ports.length ? `<b>Ports</b> ${d.open_ports.map(p => `<span title="${p.service}" style="font-size:10px;padding:1px 5px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);border-radius:3px;margin-right:2px">${p.port}</span>`).join('')}<br>` : ''}
    ${d.first_seen ? `<b>First seen</b> ${new Date(d.first_seen).toLocaleDateString()}<br>` : ''}
    <b>Last seen</b> ${lastSeen}
  </div>
  <div style="margin-top:8px">
    <span onclick="toggleVendorEdit('${mac}')"
      style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);cursor:pointer;user-select:none;letter-spacing:0.5px"
      id="vendor-toggle-${mac}">▶ override vendor</span>
    <div id="vendor-row-${mac}" style="display:none;margin-top:6px">
      <div class="edit-row">
        <input class="label-input" id="ven-${mac}" type="text"
          placeholder="Override vendor…"
          value="${escHtml(d.vendor_custom || '')}"
          onkeydown="if(event.key==='Enter') saveVendor('${d.mac}', '${mac}')">
        <button class="save-btn" style="background:var(--accent);color:var(--bg)" onclick="saveVendor('${d.mac}', '${mac}')">Save</button>
        <button class="del-btn" title="Clear custom vendor" onclick="clearVendor('${d.mac}', '${mac}')">↺</button>
      </div>
    </div>
  </div>
  <div style="margin-top:6px">
    <span onclick="toggleRename('${mac}')"
      style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);cursor:pointer;user-select:none;letter-spacing:0.5px"
      id="rename-toggle-${mac}">▶ rename device</span>
    <div id="rename-row-${mac}" style="display:none;margin-top:6px">
      <div class="edit-row">
        <input class="label-input" id="lbl-${mac}" type="text"
          placeholder="Name this device…"
          value="${escHtml(d.label || '')}"
          onkeydown="if(event.key==='Enter') saveLabel('${d.mac}', '${mac}')">
        <button class="save-btn" onclick="saveLabel('${d.mac}', '${mac}')">Save</button>
        <button class="del-btn" title="Remove from list" onclick="deleteDevice('${d.mac}')">✕</button>
      </div>
    </div>
  </div>
  <div style="margin-top:8px;display:flex;align-items:center;gap:8px">
    <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">Category:</span>
    ${categorySelectHTML(d.mac)}
    <span style="width:8px;height:8px;border-radius:50%;background:${getCatColor(d)};display:inline-block;box-shadow:0 0 4px ${getCatColor(d)}"></span>
  </div>
</div>`;
}

function toggleVendorEdit(mac) {
  const row = document.getElementById('vendor-row-' + mac);
  const toggle = document.getElementById('vendor-toggle-' + mac);
  const open = row.style.display === 'none';
  row.style.display = open ? 'block' : 'none';
  toggle.textContent = (open ? '▼' : '▶') + ' override vendor';
  if (open) document.getElementById('ven-' + mac).focus();
}

function toggleRename(mac) {
  const row = document.getElementById('rename-row-' + mac);
  const toggle = document.getElementById('rename-toggle-' + mac);
  const open = row.style.display === 'none';
  row.style.display = open ? 'block' : 'none';
  toggle.textContent = (open ? '▼' : '▶') + ' rename device';
  if (open) document.getElementById('lbl-' + mac).focus();
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function saveLabel(mac, macDash) {
  // Works for both card (lbl-) and table (tbl-lbl-) inputs
  const input = document.getElementById('lbl-' + macDash)
             || document.getElementById('tbl-lbl-' + macDash);
  const label = input ? input.value.trim() : '';
  await fetch(`/api/device/${encodeURIComponent(mac)}/label`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({label})
  });
  const dev = allDevices.find(d => d.mac === mac);
  if (dev) dev.label = label;
  updateStats();
  renderDevices();
  toast(label ? `Labeled as "${label}"` : 'Label cleared');
}

async function saveVendorFrom(prefix, mac, macDash, applyAll = false) {
  const input = document.getElementById(prefix + macDash);
  const vendor_custom = input ? input.value.trim() : '';
  const r = await fetch(`/api/device/${encodeURIComponent(mac)}/vendor`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({vendor_custom, apply_all: applyAll})
  }).then(x => x.json());

  // Update local state for all affected MACs
  if (r.updated_macs) {
    r.updated_macs.forEach(m => {
      const dev = allDevices.find(d => d.mac === m);
      if (dev) dev.vendor_custom = vendor_custom;
    });
  } else {
    const dev = allDevices.find(d => d.mac === mac);
    if (dev) dev.vendor_custom = vendor_custom;
  }

  renderDevices();

  // If there are other devices with the same OUI and we haven't already applied all,
  // prompt the user to apply to all
  if (!applyAll && vendor_custom && r.oui_matches > 0) {
    const noun = r.oui_matches === 1 ? '1 other device shares' : `${r.oui_matches} other devices share`;
    const apply = confirm(`${noun} the same OUI prefix (${r.oui_prefix}).\n\nApply "${vendor_custom}" to all of them?`);
    if (apply) {
      await saveVendorFrom(prefix, mac, macDash, true);
      return;
    }
  }

  if (vendor_custom) {
    const total = applyAll ? r.updated_count : 1;
    toast(total > 1 ? `Vendor set to "${vendor_custom}" for ${total} devices` : `Vendor set to "${vendor_custom}"`);
  } else {
    toast('Vendor override cleared');
  }
}

async function clearVendorFrom(prefix, mac, macDash) {
  const input = document.getElementById(prefix + macDash);
  if (input) input.value = '';
  await saveVendorFrom(prefix, mac, macDash);
}

async function saveVendor(mac, macDash) {
  await saveVendorFrom('ven-', mac, macDash);
}

async function clearVendor(mac, macDash) {
  await clearVendorFrom('ven-', mac, macDash);
}

async function saveVendor(mac, macDash) {
  const input = document.getElementById('ven-' + macDash);
  const vendor_custom = input.value.trim();
  await fetch(`/api/device/${encodeURIComponent(mac)}/vendor`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({vendor_custom})
  });
  const dev = allDevices.find(d => d.mac === mac);
  if (dev) dev.vendor_custom = vendor_custom;
  renderDevices();
  toast(vendor_custom ? `Vendor set to "${vendor_custom}"` : 'Vendor override cleared');
}

async function clearVendor(mac, macDash) {
  document.getElementById('ven-' + macDash).value = '';
  await saveVendor(mac, macDash);
}

async function deleteDevice(mac) {
  if (!confirm('Remove this device from the list?')) return;
  await fetch(`/api/device/${encodeURIComponent(mac)}`, {method:'DELETE'});
  allDevices = allDevices.filter(d => d.mac !== mac);
  updateStats();
  renderDevices();
  toast('Device removed');
}

async function startScan() {
  const btn = document.getElementById('scan-btn');
  const r = await fetch('/api/scan', {method:'POST'});
  if (!r.ok) { toast('Scan already running'); return; }
  btn.textContent = '⬡ Scanning…';
  btn.classList.add('scanning');
  btn.disabled = true;
  document.getElementById('progress-wrap').classList.add('visible');
  pollScan();
}

function pollScan() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    const s = await fetch('/api/scan/status').then(x => x.json());
    document.getElementById('progress-bar').style.width = s.progress + '%';
    document.getElementById('scan-status').textContent =
      s.running ? '● ' + s.status : '';

    if (!s.running) {
      await loadDevices();
      const btn = document.getElementById('scan-btn');
      btn.textContent = '⬡ Scan Network';
      btn.classList.remove('scanning');
      btn.disabled = false;
      document.getElementById('progress-wrap').classList.remove('visible');
      document.getElementById('progress-bar').style.width = '0%';
      toast('Scan complete');
    } else {
      pollScan();
    }
  }, 800);
}

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2800);
}

async function loadOuiStatus() {
  const r = await fetch('/api/oui/status').then(x => x.json());
  const el = document.getElementById('oui-status');
  if (r.loaded > 0) {
    el.innerHTML = `<span style="color:var(--green)">✓ ${r.loaded.toLocaleString()} vendors loaded</span> &nbsp;·&nbsp; updated ${r.file_date}`;
  } else if (r.file_exists) {
    el.textContent = 'File found but not loaded';
  } else {
    el.innerHTML = `<span style="color:var(--yellow)">⚠ No database — click Download</span>`;
  }
}

async function updateOui() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⬇ Downloading…';
  const status = document.getElementById('oui-update-status');
  status.textContent = 'Downloading IEEE OUI database…';
  status.style.opacity = '1';

  await fetch('/api/oui/update', {method:'POST'});

  // Poll until done (DB size increases)
  let prev = 0;
  const poll = setInterval(async () => {
    const r = await fetch('/api/oui/status').then(x => x.json());
    if (r.loaded > prev && r.loaded > 0) {
      clearInterval(poll);
      btn.disabled = false;
      btn.textContent = '⬇ Download / Update OUI DB';
      status.textContent = `✓ ${r.loaded.toLocaleString()} vendors loaded — re-scan to update device cards`;
      loadOuiStatus();
      // Reload devices to show updated vendor names
      loadDevices();
    }
    prev = r.loaded;
  }, 2000);
}

// ── Enrichment ────────────────────────────────────────────────────────────────
let enrichPollTimer = null;

function showEnrichModal() {
  document.getElementById('enrich-modal').style.display = 'flex';
  // Show/hide custom ports input
  document.querySelectorAll('input[name="profile"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('custom-ports-wrap').style.display =
        r.value === 'custom' && r.checked ? 'block' : 'none';
    });
  });
}

function hideEnrichModal() {
  document.getElementById('enrich-modal').style.display = 'none';
}

async function startEnrich() {
  const profile = document.querySelector('input[name="profile"]:checked')?.value || 'top20';
  const customRaw = document.getElementById('custom-ports-input').value;
  const custom_ports = customRaw.split(',').map(p => parseInt(p.trim())).filter(n => !isNaN(n));

  const r = await fetch('/api/enrich', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({profile, custom_ports})
  });
  if (!r.ok) { toast('Enrichment already running'); hideEnrichModal(); return; }

  hideEnrichModal();
  document.getElementById('enrich-btn').textContent = '⬡ Enriching…';
  document.getElementById('enrich-btn').style.color = 'var(--yellow)';
  document.getElementById('enrich-btn').style.borderColor = 'var(--yellow)';
  document.getElementById('enrich-progress-wrap').style.display = 'block';
  pollEnrich();
}

function pollEnrich() {
  clearTimeout(enrichPollTimer);
  enrichPollTimer = setTimeout(async () => {
    const s = await fetch('/api/enrich/status').then(x => x.json());
    document.getElementById('enrich-bar').style.width = s.progress + '%';
    document.getElementById('enrich-status-text').textContent = s.running ? '● ' + s.status : '';
    document.getElementById('enrich-count-text').textContent =
      s.total > 0 ? `${s.done} / ${s.total} devices` : '';

    if (!s.running) {
      document.getElementById('enrich-btn').textContent = '⬡ Enrich';
      document.getElementById('enrich-btn').style.color = 'var(--accent2)';
      document.getElementById('enrich-btn').style.borderColor = 'var(--accent2)';
      setTimeout(() => {
        document.getElementById('enrich-progress-wrap').style.display = 'none';
        document.getElementById('enrich-bar').style.width = '0%';
      }, 3000);
      await loadDevices();
      toast(s.status);
    } else {
      // Refresh device list progressively as enrichment runs
      await loadDevices();
      pollEnrich();
    }
  }, 1500);
}

// Check if enrichment is already running on page load
async function checkEnrichStatus() {
  const s = await fetch('/api/enrich/status').then(x => x.json());
  if (s.running) {
    document.getElementById('enrich-btn').textContent = '⬡ Enriching…';
    document.getElementById('enrich-progress-wrap').style.display = 'block';
    pollEnrich();
  }
}

// ── AP management ─────────────────────────────────────────────────────────────
let apConfig = [];

async function loadAPs() {
  const r = await fetch('/api/aps').then(x => x.json());
  apConfig = r.aps || [];
  renderApList();
}

function renderApList() {
  const list = document.getElementById('ap-list');
  if (!list) return;
  if (!apConfig.length) {
    list.innerHTML = '<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-dim)">No APs configured.</div>';
    return;
  }
  list.innerHTML = apConfig.map((ap, i) => `
<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
  <input class="label-input" style="width:130px" placeholder="IP" value="${escHtml(ap.ip)}"
    onchange="apConfig[${i}].ip=this.value">
  <input class="label-input" style="width:110px" placeholder="Community" value="${escHtml(ap.community)}"
    onchange="apConfig[${i}].community=this.value">
  <input class="label-input" style="width:120px" placeholder="Name" value="${escHtml(ap.name||'')}"
    onchange="apConfig[${i}].name=this.value">
  <button class="save-btn" style="padding:4px 10px;font-size:10px;background:var(--surface2);color:var(--accent2);border:1px solid var(--accent2)"
    onclick="testAP(${i})">Test</button>
  <button class="del-btn" style="padding:4px 8px" onclick="removeAP(${i})">✕</button>
  <span id="ap-test-${i}" style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)"></span>
</div>`).join('');
}

function addApRow() {
  apConfig.push({ip:'', community:'netscout', name:''});
  renderApList();
}

function removeAP(i) {
  apConfig.splice(i, 1);
  renderApList();
}

async function testAP(i) {
  const ap = apConfig[i];
  const el = document.getElementById(`ap-test-${i}`);
  el.textContent = 'Testing…';
  el.style.color = 'var(--text-dim)';
  const r = await fetch('/api/aps/test', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ip: ap.ip, community: ap.community})
  }).then(x => x.json());
  el.textContent = r.ok ? '✓ ' + r.description : '✗ ' + r.description;
  el.style.color = r.ok ? 'var(--green)' : 'var(--red)';
}

async function saveAPs() {
  const r = await fetch('/api/aps', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({aps: apConfig})
  }).then(x => x.json());
  const el = document.getElementById('ap-save-status');
  el.textContent = `✓ Saved ${r.aps.length} AP(s)`;
  el.style.opacity = '1';
  setTimeout(() => el.style.opacity = '0', 2500);
}

async function pollAPs() {
  await fetch('/api/aps/poll', {method:'POST'});
  toast('AP poll started — refreshing in 5s…');
  setTimeout(loadDevices, 5000);
}

// ── Switch management ─────────────────────────────────────────────────────────
let switchConfig = [];

async function loadSwitches() {
  const r = await fetch('/api/switches').then(x => x.json());
  switchConfig = r.switches || [];
  renderSwitchList();
}

function renderSwitchList() {
  const list = document.getElementById('switch-list');
  if (!list) return;
  if (!switchConfig.length) {
    list.innerHTML = '<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-dim)">No switches configured.</div>';
    return;
  }
  list.innerHTML = switchConfig.map((sw, i) => `
<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
  <input class="label-input" style="width:130px" placeholder="IP" value="${escHtml(sw.ip)}"
    onchange="switchConfig[${i}].ip=this.value">
  <input class="label-input" style="width:110px" placeholder="Community" value="${escHtml(sw.community)}"
    onchange="switchConfig[${i}].community=this.value">
  <input class="label-input" style="width:110px" placeholder="Name" value="${escHtml(sw.name||'')}"
    onchange="switchConfig[${i}].name=this.value">
  <button class="save-btn" style="padding:4px 10px;font-size:10px;background:var(--surface2);color:var(--accent);border:1px solid var(--accent)"
    onclick="testSwitch(${i})">Test</button>
  <button class="del-btn" style="padding:4px 8px" onclick="removeSwitch(${i})">✕</button>
  <span id="sw-test-${i}" style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)"></span>
</div>`).join('');
}

function addSwitchRow() {
  switchConfig.push({ip:'', community:'netscout', name:''});
  renderSwitchList();
}

function removeSwitch(i) {
  switchConfig.splice(i, 1);
  renderSwitchList();
}

async function testSwitch(i) {
  const sw = switchConfig[i];
  const el = document.getElementById(`sw-test-${i}`);
  el.textContent = 'Testing…';
  el.style.color = 'var(--text-dim)';
  const r = await fetch('/api/switches/test', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ip: sw.ip, community: sw.community})
  }).then(x => x.json());
  if (r.ok) {
    el.textContent = '✓ ' + r.description.substring(0, 50);
    el.style.color = 'var(--green)';
  } else {
    el.textContent = '✗ ' + r.description;
    el.style.color = 'var(--red)';
  }
}

async function saveSwitches() {
  const r = await fetch('/api/switches', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({switches: switchConfig})
  }).then(x => x.json());
  const el = document.getElementById('switch-save-status');
  el.textContent = `✓ Saved ${r.switches.length} switch(es)`;
  el.style.opacity = '1';
  setTimeout(() => el.style.opacity = '0', 2500);
}

async function pollSwitchPorts() {
  await fetch('/api/switches/poll', {method:'POST'});
  toast('Switch port poll started — refreshing in 5s…');
  setTimeout(loadDevices, 5000);
}

// Init
loadInfo();
loadDevices();
loadOuiStatus();
loadSwitches();
loadAPs();
checkEnrichStatus();
