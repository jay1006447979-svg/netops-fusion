/* ============ NetOps Fusion 前端逻辑 ============ */
(function () {
  "use strict";

  /* ---------- API 封装 ---------- */
  const API = {
    async get(url) {
      const r = await fetch(url);
      return r.json();
    },
    async post(url, body) {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await r.text();
      try { return JSON.parse(text); } catch { return { _raw: text, _status: r.status }; }
    },
    async put(url, body) {
      const r = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return r.json();
    },
    async del(url) {
      const r = await fetch(url, { method: "DELETE" });
      return r.json();
    },
    async download(url, body) {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      const filename = m ? m[1] : "config.cfg";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    },
  };

  /* ---------- Toast ---------- */
  function toast(msg, type) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast show " + (type || "");
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.className = "toast"), 2600);
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  /* ---------- 配置示例模板 ---------- */
  const EXAMPLES = {
    huawei: {
      vendor: "huawei",
      device_type: "switch",
      hostname: "SW-Core-01",
      basic: {
        ssh: { enable: false, version: 2, port: 22 },
        telnet: { enable: false },
        console: { enable: false, authentication: "password", idle_timeout: 10 },
        user: { enable: false, username: "admin", password: "Admin@123", level: 15, service_types: ["terminal", "ssh", "telnet"] },
        ntp: { enable: false, servers: [{ ip: "192.168.1.1", prefer: true }], timezone: "UTC+8" },
        snmp: { enable: false, version: "v2c", community_read: "public", community_write: "private" },
      },
      vlan: {
        vlans: [
          { id: 10, name: "Mgmt" },
          { id: 20, name: "Data" },
          { id: 30, name: "Voice" },
        ],
        interfaces: [
          { interface: "GigabitEthernet0/0/1", type: "access", vlan_id: 10 },
          { interface: "GigabitEthernet0/0/2", type: "trunk", trunk_vlans: [10, 20, 30] },
        ],
        vlanifs: [{ vlan_id: 10, ip_address: "192.168.10.1", mask: "255.255.255.0" }],
        stp: { mode: "stp", priority: 32768, enable: false },
      },
    },
    h3c: {
      vendor: "h3c",
      device_type: "switch",
      hostname: "SW-Core-H3C",
      basic: {
        ssh: { enable: true, version: 2, port: 22 },
        console: { enable: false, authentication: "password", idle_timeout: 10 },
        user: { enable: true, username: "admin", password: "Admin@123", level: 15, service_types: ["terminal", "ssh", "telnet"] },
        ntp: { enable: false, servers: [{ ip: "192.168.1.1", prefer: true }], timezone: "UTC+8" },
      },
      vlan: {
        vlans: [{ id: 100, name: "User" }, { id: 200, name: "Server" }],
        interfaces: [
          { interface: "GigabitEthernet1/0/1", type: "access", vlan_id: 100 },
          { interface: "GigabitEthernet1/0/2", type: "trunk", trunk_vlans: [100, 200] },
        ],
        vlanifs: [{ vlan_id: 100, ip_address: "192.168.100.1", mask: "255.255.255.0" }],
      },
    },
  };

  /* ============================================================
     页面路由
     ============================================================ */
  const PAGE_TITLES = {
    dashboard: "仪表盘",
    config: "配置生成器",
    devices: "设备管理",
    topology: "拓扑图",
    tools: "网络工具箱",
    manual: "命令手册",
    templates: "配置模板",
    notes: "笔记",
  };

  function switchPage(name) {
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    document.querySelectorAll(".nav-item[data-page]").forEach((n) => n.classList.remove("active"));
    const page = document.getElementById("page-" + name);
    if (page) page.classList.add("active");
    const nav = document.querySelector('.nav-item[data-page="' + name + '"]');
    if (nav) nav.classList.add("active");
    document.getElementById("page-title").textContent = PAGE_TITLES[name] || name;

    if (name === "dashboard") loadDashboard();
    if (name === "devices") loadDevices();
    if (name === "manual") loadManualPage();
    if (name === "templates") loadTemplates();
    if (name === "notes") loadNotes();
    if (name === "devices") { loadDevices(); loadFileServerStatus(); }
    if (name === "topology" && window.TopologyPage) window.TopologyPage.onShow();
  }

  /* ============================================================
     仪表盘
     ============================================================ */
  async function loadDashboard() {
    try {
      const info = await API.get("/api/info");
      document.getElementById("stat-vendors").textContent = (info.vendors || []).length;
      document.getElementById("info-app").textContent = info.app || "-";
      document.getElementById("info-version").textContent = info.version || "-";

      const vl = document.getElementById("vendor-list");
      vl.innerHTML = (info.vendors || [])
        .map((v) => {
          const names = { huawei: "华为 Huawei", h3c: "H3C", ruijie: "锐捷 Ruijie", maipu: "迈普 Maipu" };
          return '<span class="badge badge-info" style="margin:2px;">' + (names[v] || v) + "</span>";
        })
        .join(" ");
    } catch (e) {
      document.getElementById("conn-status").className = "badge badge-danger";
      document.getElementById("conn-status").textContent = "● 服务离线";
    }

    try {
      const t = await API.get("/api/templates");
      document.getElementById("stat-templates").textContent = (t.templates || []).length;
    } catch {}

    try {
      const s = await API.get("/api/manual/stats");
      const stats = s.stats || {};
      const total = (stats.huawei || 0) + (stats.h3c || 0) + (stats.ruijie || 0) + (stats.maipu || 0);
      document.getElementById("stat-commands").textContent = total;
    } catch {}

    try {
      const d = await API.get("/api/devices");
      document.getElementById("stat-devices").textContent = (d.devices || []).length;
    } catch {}
  }

  /* ============================================================
     配置生成器 — 表单式
     ============================================================ */

  function switchCfgTab(name) {
    document.querySelectorAll('[data-cfg-tab]').forEach((t) => t.classList.remove('active'));
    document.querySelectorAll('.cfg-pane').forEach((p) => p.classList.remove('active'));
    document.querySelector('[data-cfg-tab="' + name + '"]').classList.add('active');
    document.getElementById('cfg-tab-' + name).classList.add('active');
  }

  function getVal(id, def) {
    const el = document.getElementById(id);
    if (!el) return def;
    const v = el.value.trim();
    if (!v) return def;
    if (el.tagName === 'SELECT') return el.value;
    if (el.type === 'number') {
      const n = parseInt(v, 10);
      return isNaN(n) ? def : n;
    }
    return v;
  }
  function getBool(id) { return getVal(id) === 'true'; }
  function getList(id) {
    const v = getVal(id, '');
    if (!v) return [];
    return v.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  }
  function getNumList(id) {
    return getList(id).map(Number).filter((n) => !isNaN(n) && n > 0);
  }

  function collectFormConfig() {
    const cfg = {
      vendor: getVal('cfg-vendor', 'huawei'),
      device_type: getVal('cfg-device-type', 'switch'),
      hostname: getVal('cfg-hostname', '') || undefined,
    };

    // Basic
    const basic = {};
    const ssh = {};
    if (getBool('cfg-ssh-enable')) { ssh.enable = true; ssh.version = getVal('cfg-ssh-version', 2); ssh.port = getVal('cfg-ssh-port', 22); ssh.timeout = getVal('cfg-ssh-timeout', 60); }
    if (Object.keys(ssh).length) basic.ssh = ssh;

    const telnet = {};
    if (getBool('cfg-telnet-enable')) { telnet.enable = true; }
    if (Object.keys(telnet).length) basic.telnet = telnet;

    // Console 认证 - 仅启用时收集
    if (getBool('cfg-console-enable')) {
      const consoleCfg = { enable: true };
      if (getVal('cfg-console-pwd')) consoleCfg.password = getVal('cfg-console-pwd');
      consoleCfg.authentication = getVal('cfg-console-auth', 'password');
      consoleCfg.idle_timeout = getVal('cfg-console-idle', 10);
      basic.console = consoleCfg;
    }

    // 用户管理 - 仅启用时收集
    if (getBool('cfg-user-enable')) {
      const user = { enable: true };
      if (getVal('cfg-user-name')) { user.username = getVal('cfg-user-name'); user.password = getVal('cfg-user-pwd', 'admin@123'); user.level = getVal('cfg-user-level', 15); user.service_types = getList('cfg-user-svc'); user.encrypted = getBool('cfg-user-enc'); }
      basic.user = user;
    }

    // NTP - 仅启用时收集
    if (getBool('cfg-ntp-enable')) {
      const ntp = { enable: true };
      if (getVal('cfg-ntp-ip')) { ntp.servers = [{ ip: getVal('cfg-ntp-ip'), prefer: true }]; }
      ntp.timezone = getVal('cfg-ntp-tz', 'UTC+8');
      ntp.broadcast_enable = getBool('cfg-ntp-bcast');
      basic.ntp = ntp;
    }

    // SNMP - 仅启用时收集
    if (getBool('cfg-snmp-enable')) {
      const snmp = { enable: true };
      snmp.version = getVal('cfg-snmp-ver', 'v2c');
      if (getVal('cfg-snmp-read')) snmp.community_read = getVal('cfg-snmp-read');
      if (getVal('cfg-snmp-write')) snmp.community_write = getVal('cfg-snmp-write');
      snmp.trap_enable = getBool('cfg-snmp-trap');
      if (getVal('cfg-snmp-trap-host')) snmp.trap_host = getVal('cfg-snmp-trap-host');
      if (getVal('cfg-snmp-sysname')) snmp.sys_name = getVal('cfg-snmp-sysname');
      if (getVal('cfg-snmp-location')) snmp.sys_location = getVal('cfg-snmp-location');
      if (getVal('cfg-snmp-contact')) snmp.sys_contact = getVal('cfg-snmp-contact');
      basic.snmp = snmp;
    }

    // DNS - 仅启用时收集
    if (getBool('cfg-dns-enable')) {
      const dns = { enable: true };
      const dnsServers = getList('cfg-dns-servers');
      if (dnsServers.length) dns.servers = dnsServers;
      if (getVal('cfg-dns-domain')) dns.domain = getVal('cfg-dns-domain');
      dns.resolve_enable = getBool('cfg-dns-resolve');
      basic.dns = dns;
    }

    // 管理接口 - 仅启用时收集
    if (getBool('cfg-mgmt-enable')) {
      const mgmt = { enable: true };
      mgmt.interface = getVal('cfg-mgmt-if', 'Vlanif1');
      if (getVal('cfg-mgmt-ip')) { mgmt.ip_address = getVal('cfg-mgmt-ip'); mgmt.mask = getVal('cfg-mgmt-mask', '255.255.255.0'); }
      if (getVal('cfg-mgmt-gw')) mgmt.gateway = getVal('cfg-mgmt-gw');
      if (getVal('cfg-mgmt-desc')) mgmt.description = getVal('cfg-mgmt-desc');
      basic.mgmt_interface = mgmt;
    }

    const banner = {};
    if (getVal('cfg-banner-motd')) banner.motd = getVal('cfg-banner-motd');
    if (getVal('cfg-banner-login')) banner.login = getVal('cfg-banner-login');
    if (Object.keys(banner).length) basic.banner = banner;

    if (Object.keys(basic).length) cfg.basic = basic;

    // VLAN
    const vlan = {};
    const vlans = [];
    document.querySelectorAll('#cfg-vlan-list .array-row').forEach((row) => {
      const id = row.querySelector('.cfg-vlan-id');
      const name = row.querySelector('.cfg-vlan-name');
      if (id && id.value) vlans.push({ id: parseInt(id.value), name: name ? name.value || undefined : undefined });
    });
    if (vlans.length) vlan.vlans = vlans;

    const ifvlans = [];
    document.querySelectorAll('#cfg-ifvlan-list .array-row').forEach((row) => {
      const ifEl = row.querySelector('.cfg-ifvlan-if');
      const type = row.querySelector('.cfg-ifvlan-type');
      const vid = row.querySelector('.cfg-ifvlan-vid');
      const trunk = row.querySelector('.cfg-ifvlan-trunk');
      if (ifEl && ifEl.value) {
        const o = { interface: ifEl.value, type: type ? type.value : 'access' };
        if (vid && vid.value) o.vlan_id = parseInt(vid.value);
        if (trunk && trunk.value) o.trunk_vlans = trunk.value.split(/[,，]/).map(Number).filter((n) => !isNaN(n) && n > 0);
        ifvlans.push(o);
      }
    });
    if (ifvlans.length) vlan.interfaces = ifvlans;

    const vlanifs = [];
    document.querySelectorAll('#cfg-vlanif-list .array-row').forEach((row) => {
      const vid = row.querySelector('.cfg-vlanif-vid');
      const ip = row.querySelector('.cfg-vlanif-ip');
      const mask = row.querySelector('.cfg-vlanif-mask');
      if (vid && vid.value && ip && ip.value) vlanifs.push({ vlan_id: parseInt(vid.value), ip_address: ip.value, mask: mask ? mask.value || '255.255.255.0' : '255.255.255.0' });
    });
    if (vlanifs.length) vlan.vlanifs = vlanifs;

    // STP - 仅启用时收集
    if (getBool('cfg-stp-enable')) {
      const stp = { enable: true };
      stp.mode = getVal('cfg-stp-mode', 'stp');
      stp.priority = getVal('cfg-stp-priority', 32768);
      vlan.stp = stp;
    }

    const voiceVlans = [];
    document.querySelectorAll('#cfg-voicevlan-list .array-row').forEach((row) => {
      const ifEl = row.querySelector('.cfg-voice-if');
      const vid = row.querySelector('.cfg-voice-vid');
      if (ifEl && ifEl.value && vid && vid.value) voiceVlans.push({ interface: ifEl.value, vlan_id: parseInt(vid.value) });
    });
    if (voiceVlans.length) vlan.voice_vlans = voiceVlans;

    if (Object.keys(vlan).length) cfg.vlan = vlan;

    // Routing
    const routing = {};
    const staticRoutes = [];
    document.querySelectorAll('#cfg-static-list .array-row').forEach((row) => {
      const dest = row.querySelector('.cfg-route-dest');
      const mask = row.querySelector('.cfg-route-mask');
      const nh = row.querySelector('.cfg-route-nh');
      const pref = row.querySelector('.cfg-route-pref');
      if (dest && dest.value && mask && mask.value) {
        const o = { dest_network: dest.value, mask: mask.value };
        if (nh && nh.value) o.next_hop = nh.value;
        if (pref && pref.value) o.preference = parseInt(pref.value);
        staticRoutes.push(o);
      }
    });
    if (staticRoutes.length) routing.static_routes = staticRoutes;

    const defRoute = {};
    if (getVal('cfg-defroute-nh')) defRoute.next_hop = getVal('cfg-defroute-nh');
    if (getVal('cfg-defroute-if')) defRoute.interface = getVal('cfg-defroute-if');
    if (Object.keys(defRoute).length) routing.default_route = defRoute;

    const ospf = {};
    ospf.process_id = getVal('cfg-ospf-pid', 1);
    if (getVal('cfg-ospf-rid')) ospf.router_id = getVal('cfg-ospf-rid');
    ospf.area_id = getVal('cfg-ospf-area', '0');
    const ospfNets = [];
    document.querySelectorAll('#cfg-ospf-net-list .array-row').forEach((row) => {
      const addr = row.querySelector('.cfg-ospf-net-addr');
      const mask = row.querySelector('.cfg-ospf-net-mask');
      const area = row.querySelector('.cfg-ospf-net-area');
      if (addr && addr.value) ospfNets.push({ address: addr.value, mask: mask ? mask.value || '0.0.0.255' : '0.0.0.255', area: area ? area.value || '0' : '0' });
    });
    if (ospfNets.length) ospf.networks = ospfNets;
    if (ospf.process_id !== 1 || ospf.router_id || ospfNets.length) routing.ospf = ospf;

    const bgp = {};
    if (getVal('cfg-bgp-as')) {
      bgp.as_number = parseInt(getVal('cfg-bgp-as'));
      if (getVal('cfg-bgp-rid')) bgp.router_id = getVal('cfg-bgp-rid');
      const peers = [];
      document.querySelectorAll('#cfg-bgp-peer-list .array-row').forEach((row) => {
        const ip = row.querySelector('.cfg-bgp-peer-ip');
        const as = row.querySelector('.cfg-bgp-peer-as');
        if (ip && ip.value && as && as.value) peers.push({ ip: ip.value, as_number: parseInt(as.value) });
      });
      if (peers.length) bgp.peers = peers;
      routing.bgp = bgp;
    }

    const rip = {};
    rip.version = getVal('cfg-rip-ver', 2);
    const ripNets = getList('cfg-rip-nets');
    if (ripNets.length) rip.networks = ripNets;
    if (rip.version !== 2 || ripNets.length) routing.rip = rip;

    if (Object.keys(routing).length) cfg.routing = routing;

    // Security
    const security = {};
    const acls = [];
    document.querySelectorAll('#cfg-acl-list > .array-row').forEach((row) => {
      const num = row.querySelector('.cfg-acl-num');
      const desc = row.querySelector('.cfg-acl-desc');
      if (!num || !num.value) return;
      const acl = { number: parseInt(num.value) };
      if (desc && desc.value) acl.description = desc.value;
      const rules = [];
      row.querySelectorAll('.cfg-acl-rules .array-row').forEach((rrow) => {
        const rid = rrow.querySelector('.cfg-acl-rule-id');
        const act = rrow.querySelector('.cfg-acl-rule-act');
        const proto = rrow.querySelector('.cfg-acl-rule-proto');
        const src = rrow.querySelector('.cfg-acl-rule-src');
        const dst = rrow.querySelector('.cfg-acl-rule-dst');
        if (rid && rid.value) {
          rules.push({
            rule_id: parseInt(rid.value),
            action: act ? act.value : 'permit',
            protocol: proto ? proto.value : 'ip',
            source: src ? src.value || 'any' : 'any',
            destination: dst ? dst.value || 'any' : 'any',
          });
        }
      });
      if (rules.length) acl.rules = rules;
      acls.push(acl);
    });
    if (acls.length) security.acls = acls;

    const portSecs = [];
    document.querySelectorAll('#cfg-portsec-list .array-row').forEach((row) => {
      const ifEl = row.querySelector('.cfg-ps-if');
      const max = row.querySelector('.cfg-ps-max');
      const act = row.querySelector('.cfg-ps-act');
      if (ifEl && ifEl.value) portSecs.push({ interface: ifEl.value, max_mac: max ? parseInt(max.value) || 1 : 1, protect_action: act ? act.value : 'protect' });
    });
    if (portSecs.length) security.port_security = portSecs;

    // DHCP Snooping - 仅启用时收集
    if (getBool('cfg-dhcp-snoop')) {
      const dhcpSnoop = { enable: true };
      const snoopVlans = getNumList('cfg-dhcp-snoop-vlans');
      if (snoopVlans.length) dhcpSnoop.vlans = snoopVlans;
      const snoopTrust = getList('cfg-dhcp-snoop-trust');
      if (snoopTrust.length) dhcpSnoop.trust_ports = snoopTrust;
      security.dhcp_snooping = dhcpSnoop;
    }

    const arpProt = {};
    const arpVlans = getNumList('cfg-arp-vlans');
    if (arpVlans.length) arpProt.vlans = arpVlans;
    const arpTrust = getList('cfg-arp-trust');
    if (arpTrust.length) arpProt.trust_ports = arpTrust;
    if (arpVlans.length || arpTrust.length) security.arp_protection = arpProt;

    const storms = [];
    document.querySelectorAll('#cfg-storm-list .array-row').forEach((row) => {
      const ifEl = row.querySelector('.cfg-storm-if');
      const bcast = row.querySelector('.cfg-storm-bcast');
      const mcast = row.querySelector('.cfg-storm-mcast');
      const ucast = row.querySelector('.cfg-storm-ucast');
      const act = row.querySelector('.cfg-storm-act');
      if (ifEl && ifEl.value) {
        const o = { interface: ifEl.value };
        if (bcast && bcast.value) o.broadcast = parseInt(bcast.value);
        if (mcast && mcast.value) o.multicast = parseInt(mcast.value);
        if (ucast && ucast.value) o.unicast = parseInt(ucast.value);
        o.action = act ? act.value : 'block';
        storms.push(o);
      }
    });
    if (storms.length) security.storm_controls = storms;

    const radius = [];
    document.querySelectorAll('#cfg-radius-list .array-row').forEach((row) => {
      const name = row.querySelector('.cfg-rad-name');
      const ip = row.querySelector('.cfg-rad-ip');
      const key = row.querySelector('.cfg-rad-key');
      const auth = row.querySelector('.cfg-rad-auth');
      const acct = row.querySelector('.cfg-rad-acct');
      if (name && name.value && ip && ip.value) {
        radius.push({
          server_name: name.value, ip_address: ip.value,
          shared_key: key ? key.value || '' : '',
          auth_port: auth ? parseInt(auth.value) || 1812 : 1812,
          acct_port: acct ? parseInt(acct.value) || 1813 : 1813,
        });
      }
    });
    if (radius.length) security.radius_servers = radius;

    // 802.1X - 仅启用时收集
    if (getBool('cfg-dot1x-enable')) {
      const dot1x = { enable: true };
      dot1x.method = getVal('cfg-dot1x-method', 'chap');
      dot1x.reauth_period = getVal('cfg-dot1x-reauth', 3600);
      security.dot1x_global = dot1x;
    }

    if (Object.keys(security).length) cfg.security = security;

    // Interface
    const iface = {};
    const ethTrunks = [];
    document.querySelectorAll('#cfg-trunk-list .array-row').forEach((row) => {
      const id = row.querySelector('.cfg-trunk-id');
      const mode = row.querySelector('.cfg-trunk-mode');
      const members = row.querySelector('.cfg-trunk-members');
      const desc = row.querySelector('.cfg-trunk-desc');
      const linkType = row.querySelector('.cfg-trunk-linktype');
      const vlans = row.querySelector('.cfg-trunk-vlans');
      const native = row.querySelector('.cfg-trunk-native');
      if (id && id.value) {
        const o = { trunk_id: parseInt(id.value), mode: mode ? mode.value : 'lacp-static' };
        if (members && members.value) o.member_ports = members.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        if (desc && desc.value) o.description = desc.value;
        o.port_link_type = linkType ? linkType.value : 'trunk';
        if (vlans && vlans.value) o.trunk_vlans = vlans.value.split(/[,，]/).map((s) => parseInt(s.trim())).filter((n) => !isNaN(n) && n > 0);
        if (native && native.value) o.native_vlan = parseInt(native.value);
        ethTrunks.push(o);
      }
    });
    if (ethTrunks.length) iface.eth_trunks = ethTrunks;

    // LACP - 仅启用时收集
    if (getBool('cfg-lacp-enable')) {
      const lacp = { enable: true };
      lacp.priority = getVal('cfg-lacp-pri', 32768);
      lacp.fast_switchover = getBool('cfg-lacp-fast');
      iface.lacp = lacp;
    }

    // LLDP - 仅启用时收集
    if (getBool('cfg-lldp-enable')) {
      const lldp = { enable: true };
      lldp.mode = getVal('cfg-lldp-mode', 'both');
      lldp.interval = getVal('cfg-lldp-int', 30);
      lldp.holdtime = getVal('cfg-lldp-hold', 120);
      iface.lldp = lldp;
    }

    // PoE - 仅启用时收集
    if (getBool('cfg-poe-enable')) {
      const poe = { enable: true };
      poe.max_power = getVal('cfg-poe-max', 74000);
      iface.poe = poe;
    }

    // 端口隔离 - 仅启用时收集
    if (getBool('cfg-isolate-enable')) {
      const isolate = { enable: true };
      isolate.group_id = getVal('cfg-isolate-gid', 1);
      const isolateIfs = getList('cfg-isolate-ifs');
      if (isolateIfs.length) isolate.interfaces = isolateIfs;
      iface.port_isolation = isolate;
    }

    // 环路检测 - 仅启用时收集
    if (getBool('cfg-loop-enable')) {
      const loop = { enable: true };
      loop.interval = getVal('cfg-loop-int', 5);
      loop.action = getVal('cfg-loop-act', 'block');
      const loopVlans = getNumList('cfg-loop-vlans');
      if (loopVlans.length) loop.vlan_ids = loopVlans;
      iface.loopback_detection = loop;
    }

    const rateLimits = [];
    document.querySelectorAll('#cfg-rate-list .array-row').forEach((row) => {
      const ifEl = row.querySelector('.cfg-rate-if');
      const rin = row.querySelector('.cfg-rate-in');
      const rout = row.querySelector('.cfg-rate-out');
      if (ifEl && ifEl.value) {
        const o = { interface: ifEl.value };
        if (rin && rin.value) o.cir_in = parseInt(rin.value);
        if (rout && rout.value) o.cir_out = parseInt(rout.value);
        rateLimits.push(o);
      }
    });
    if (rateLimits.length) iface.rate_limits = rateLimits;

    if (Object.keys(iface).length) cfg.interface = iface;

    return cfg;
  }

  function fillFormFromConfig(cfg) {
    if (!cfg) return;
    if (cfg.vendor) document.getElementById('cfg-vendor').value = cfg.vendor;
    if (cfg.device_type) document.getElementById('cfg-device-type').value = cfg.device_type;
    if (cfg.hostname) document.getElementById('cfg-hostname').value = cfg.hostname;
    const basic = cfg.basic || {};
    if (basic.ssh) { const s = basic.ssh; document.getElementById('cfg-ssh-enable').value = String(s.enable === true); if (s.version) document.getElementById('cfg-ssh-version').value = s.version; if (s.port) document.getElementById('cfg-ssh-port').value = s.port; if (s.timeout) document.getElementById('cfg-ssh-timeout').value = s.timeout; } else { document.getElementById('cfg-ssh-enable').value = 'false'; }
    if (basic.telnet) document.getElementById('cfg-telnet-enable').value = String(basic.telnet.enable === true); else document.getElementById('cfg-telnet-enable').value = 'false';
    // Console 认证
    if (basic.console) { const c = basic.console; document.getElementById('cfg-console-enable').value = String(c.enable === true); if (c.password) document.getElementById('cfg-console-pwd').value = c.password; if (c.authentication) document.getElementById('cfg-console-auth').value = c.authentication; if (c.idle_timeout) document.getElementById('cfg-console-idle').value = c.idle_timeout; } else { document.getElementById('cfg-console-enable').value = 'false'; }
    // 用户管理
    if (basic.user) { const u = basic.user; document.getElementById('cfg-user-enable').value = String(u.enable === true); if (u.username) document.getElementById('cfg-user-name').value = u.username; if (u.password) document.getElementById('cfg-user-pwd').value = u.password; if (u.level !== undefined) document.getElementById('cfg-user-level').value = u.level; if (u.service_types) document.getElementById('cfg-user-svc').value = u.service_types.join(','); document.getElementById('cfg-user-enc').value = String(u.encrypted === true); } else { document.getElementById('cfg-user-enable').value = 'false'; }
    // NTP
    if (basic.ntp) { const n = basic.ntp; document.getElementById('cfg-ntp-enable').value = String(n.enable === true); if (n.servers && n.servers.length) document.getElementById('cfg-ntp-ip').value = n.servers[0].ip; document.getElementById('cfg-ntp-tz').value = n.timezone || 'UTC+8'; document.getElementById('cfg-ntp-bcast').value = String(n.broadcast_enable || false); } else { document.getElementById('cfg-ntp-enable').value = 'false'; }
    // SNMP
    if (basic.snmp) { const s = basic.snmp; document.getElementById('cfg-snmp-enable').value = String(s.enable === true); document.getElementById('cfg-snmp-ver').value = s.version || 'v2c'; if (s.community_read) document.getElementById('cfg-snmp-read').value = s.community_read; if (s.community_write) document.getElementById('cfg-snmp-write').value = s.community_write; document.getElementById('cfg-snmp-trap').value = String(s.trap_enable || false); if (s.trap_host) document.getElementById('cfg-snmp-trap-host').value = s.trap_host; if (s.sys_name) document.getElementById('cfg-snmp-sysname').value = s.sys_name; if (s.sys_location) document.getElementById('cfg-snmp-location').value = s.sys_location; if (s.sys_contact) document.getElementById('cfg-snmp-contact').value = s.sys_contact; } else { document.getElementById('cfg-snmp-enable').value = 'false'; }
    // DNS
    if (basic.dns) { const d = basic.dns; document.getElementById('cfg-dns-enable').value = String(d.enable === true); if (d.servers) document.getElementById('cfg-dns-servers').value = d.servers.join(','); if (d.domain) document.getElementById('cfg-dns-domain').value = d.domain; document.getElementById('cfg-dns-resolve').value = String(d.resolve_enable === true); } else { document.getElementById('cfg-dns-enable').value = 'false'; }
    // 管理接口
    if (basic.mgmt_interface) { const m = basic.mgmt_interface; document.getElementById('cfg-mgmt-enable').value = String(m.enable === true); if (m.interface) document.getElementById('cfg-mgmt-if').value = m.interface; if (m.ip_address) document.getElementById('cfg-mgmt-ip').value = m.ip_address; if (m.mask) document.getElementById('cfg-mgmt-mask').value = m.mask; if (m.gateway) document.getElementById('cfg-mgmt-gw').value = m.gateway; if (m.description) document.getElementById('cfg-mgmt-desc').value = m.description; } else { document.getElementById('cfg-mgmt-enable').value = 'false'; }
    if (basic.banner) { const b = basic.banner; if (b.motd) document.getElementById('cfg-banner-motd').value = b.motd; if (b.login) document.getElementById('cfg-banner-login').value = b.login; }

    // VLAN
    if (cfg.vlan) {
      const v = cfg.vlan;
      if (v.vlans) { document.getElementById('cfg-vlan-list').innerHTML = ''; v.vlans.forEach((x) => App.addVlanRow(x.id, x.name)); }
      if (v.interfaces) { document.getElementById('cfg-ifvlan-list').innerHTML = ''; v.interfaces.forEach((x) => App.addIfVlanRow(x.interface, x.type, x.vlan_id, (x.trunk_vlans || []).join(','))); }
      if (v.vlanifs) { document.getElementById('cfg-vlanif-list').innerHTML = ''; v.vlanifs.forEach((x) => App.addVlanifRow(x.vlan_id, x.ip_address, x.mask)); }
      if (v.stp) { document.getElementById('cfg-stp-enable').value = String(v.stp.enable === true); document.getElementById('cfg-stp-mode').value = v.stp.mode || 'stp'; document.getElementById('cfg-stp-priority').value = v.stp.priority || 32768; } else { document.getElementById('cfg-stp-enable').value = 'false'; }
      if (v.voice_vlans) { document.getElementById('cfg-voicevlan-list').innerHTML = ''; v.voice_vlans.forEach((x) => App.addVoiceVlanRow(x.interface, x.vlan_id)); }
    }

    // Security
    if (cfg.security) {
      const s = cfg.security;
      if (s.dhcp_snooping) { document.getElementById('cfg-dhcp-snoop').value = String(s.dhcp_snooping.enable === true); if (s.dhcp_snooping.vlans) document.getElementById('cfg-dhcp-snoop-vlans').value = s.dhcp_snooping.vlans.join(','); if (s.dhcp_snooping.trust_ports) document.getElementById('cfg-dhcp-snoop-trust').value = s.dhcp_snooping.trust_ports.join(','); } else { document.getElementById('cfg-dhcp-snoop').value = 'false'; }
      if (s.arp_protection) { if (s.arp_protection.vlans) document.getElementById('cfg-arp-vlans').value = s.arp_protection.vlans.join(','); if (s.arp_protection.trust_ports) document.getElementById('cfg-arp-trust').value = s.arp_protection.trust_ports.join(','); }
      if (s.dot1x_global) { document.getElementById('cfg-dot1x-enable').value = String(s.dot1x_global.enable === true); document.getElementById('cfg-dot1x-method').value = s.dot1x_global.method || 'chap'; document.getElementById('cfg-dot1x-reauth').value = s.dot1x_global.reauth_period || 3600; } else { document.getElementById('cfg-dot1x-enable').value = 'false'; }
      if (s.acls) { document.getElementById('cfg-acl-list').innerHTML = ''; s.acls.forEach((x) => App.addAclRowWithData(x)); }
      if (s.port_security) { document.getElementById('cfg-portsec-list').innerHTML = ''; s.port_security.forEach((x) => App.addPortSecRow(x.interface, x.max_mac, x.protect_action)); }
      if (s.storm_controls) { document.getElementById('cfg-storm-list').innerHTML = ''; s.storm_controls.forEach((x) => App.addStormRow(x.interface, x.broadcast, x.multicast, x.unicast, x.action)); }
      if (s.radius_servers) { document.getElementById('cfg-radius-list').innerHTML = ''; s.radius_servers.forEach((x) => App.addRadiusRow(x.server_name, x.ip_address, x.shared_key, x.auth_port, x.acct_port)); }
    }

    // Interface
    if (cfg.interface) {
      const i = cfg.interface;
      if (i.eth_trunks) { document.getElementById('cfg-trunk-list').innerHTML = ''; i.eth_trunks.forEach((x) => App.addEthTrunkRow(x.trunk_id, x.mode, (x.member_ports || []).join(','), x.description, x.port_link_type, (x.trunk_vlans || []).join(','), x.native_vlan)); }
      if (i.lacp) { document.getElementById('cfg-lacp-enable').value = String(i.lacp.enable === true); document.getElementById('cfg-lacp-pri').value = i.lacp.priority || 32768; document.getElementById('cfg-lacp-fast').value = String(i.lacp.fast_switchover === true); } else { document.getElementById('cfg-lacp-enable').value = 'false'; }
      if (i.lldp) { document.getElementById('cfg-lldp-enable').value = String(i.lldp.enable === true); document.getElementById('cfg-lldp-mode').value = i.lldp.mode || 'both'; document.getElementById('cfg-lldp-int').value = i.lldp.interval || 30; document.getElementById('cfg-lldp-hold').value = i.lldp.holdtime || 120; } else { document.getElementById('cfg-lldp-enable').value = 'false'; }
      if (i.poe) { document.getElementById('cfg-poe-enable').value = String(i.poe.enable === true); document.getElementById('cfg-poe-max').value = i.poe.max_power || 74000; } else { document.getElementById('cfg-poe-enable').value = 'false'; }
      if (i.port_isolation) { document.getElementById('cfg-isolate-enable').value = String(i.port_isolation.enable === true); document.getElementById('cfg-isolate-gid').value = i.port_isolation.group_id || 1; if (i.port_isolation.interfaces) document.getElementById('cfg-isolate-ifs').value = i.port_isolation.interfaces.join(','); } else { document.getElementById('cfg-isolate-enable').value = 'false'; }
      if (i.loopback_detection) { document.getElementById('cfg-loop-enable').value = String(i.loopback_detection.enable === true); document.getElementById('cfg-loop-int').value = i.loopback_detection.interval || 5; document.getElementById('cfg-loop-act').value = i.loopback_detection.action || 'block'; if (i.loopback_detection.vlan_ids) document.getElementById('cfg-loop-vlans').value = i.loopback_detection.vlan_ids.join(','); } else { document.getElementById('cfg-loop-enable').value = 'false'; }
      if (i.rate_limits) { document.getElementById('cfg-rate-list').innerHTML = ''; i.rate_limits.forEach((x) => App.addRateLimitRow(x.interface, x.cir_in, x.cir_out)); }
    }

    // Routing
    if (cfg.routing) {
      const r = cfg.routing;
      if (r.static_routes) { document.getElementById('cfg-static-list').innerHTML = ''; r.static_routes.forEach((x) => App.addStaticRouteRowWithData(x)); }
      if (r.default_route) { if (r.default_route.next_hop) document.getElementById('cfg-defroute-nh').value = r.default_route.next_hop; if (r.default_route.interface) document.getElementById('cfg-defroute-if').value = r.default_route.interface; }
      if (r.ospf) { document.getElementById('cfg-ospf-pid').value = r.ospf.process_id || 1; if (r.ospf.router_id) document.getElementById('cfg-ospf-rid').value = r.ospf.router_id; document.getElementById('cfg-ospf-area').value = r.ospf.area_id || '0'; if (r.ospf.networks) { document.getElementById('cfg-ospf-net-list').innerHTML = ''; r.ospf.networks.forEach((x) => App.addOspfNetRow(x.address, x.mask, x.area)); } }
      if (r.bgp) { if (r.bgp.as_number) document.getElementById('cfg-bgp-as').value = r.bgp.as_number; if (r.bgp.router_id) document.getElementById('cfg-bgp-rid').value = r.bgp.router_id; if (r.bgp.peers) { document.getElementById('cfg-bgp-peer-list').innerHTML = ''; r.bgp.peers.forEach((x) => App.addBgpPeerRow(x.ip, x.as_number)); } }
      if (r.rip) { document.getElementById('cfg-rip-ver').value = r.rip.version || 2; if (r.rip.networks) document.getElementById('cfg-rip-nets').value = r.rip.networks.join(','); }
    }
  }

  function loadExample(vendor) {
    const ex = EXAMPLES[vendor] || EXAMPLES.huawei;
    fillFormFromConfig(ex);
    toast('已载入 ' + vendor + ' 示例', 'success');
  }

  function resetConfigForm() {
    // 清空主机名
    document.getElementById('cfg-hostname').value = '';
    // 所有 enable 下拉框设为 false
    ['cfg-ssh-enable','cfg-telnet-enable','cfg-console-enable','cfg-user-enable','cfg-ntp-enable','cfg-snmp-enable','cfg-dns-enable','cfg-mgmt-enable','cfg-stp-enable','cfg-dhcp-snoop','cfg-dot1x-enable','cfg-lacp-enable','cfg-lldp-enable','cfg-poe-enable','cfg-isolate-enable','cfg-loop-enable'].forEach((id) => { const el = document.getElementById(id); if (el) el.value = 'false'; });
    // 清空数组行列表
    ['cfg-vlan-list','cfg-ifvlan-list','cfg-vlanif-list','cfg-voicevlan-list','cfg-acl-list','cfg-portsec-list','cfg-storm-list','cfg-radius-list','cfg-trunk-list','cfg-rate-list','cfg-static-list','cfg-ospf-net-list','cfg-bgp-peer-list'].forEach((id) => { const el = document.getElementById(id); if (el) el.innerHTML = ''; });
    // 每个列表添加一行空白行供用户输入
    addVlanRow(); addIfVlanRow(); addVlanifRow();
    // 清空预览
    document.getElementById('config-output').textContent = '';
    document.getElementById('config-meta').style.display = 'none';
    document.getElementById('config-hint').textContent = '';
  }

  async function generateConfig() {
    const cfg = collectFormConfig();
    document.getElementById('config-hint').textContent = '生成中...';
    try {
      const r = await API.post('/api/config/generate', cfg);
      if (r.success) {
        document.getElementById('config-output').textContent = r.config_text || '';
        document.getElementById('config-meta').style.display = 'flex';
        document.getElementById('meta-vendor').textContent = '厂商: ' + (r.vendor || '-');
        document.getElementById('meta-hostname').textContent = '主机名: ' + (r.hostname || '-');
        document.getElementById('meta-lines').textContent = (r.config_text || '').split('\n').length + ' 行';
        // 显示推送区并加载设备列表
        lastGenVendor = r.vendor || null;
        showPushSection();
        toast('配置生成成功', 'success');
      } else {
        toast(r.error || r.message || '生成失败', 'error');
        document.getElementById('config-output').textContent = JSON.stringify(r, null, 2);
      }
    } catch (e) {
      toast('请求失败: ' + e.message, 'error');
    } finally {
      document.getElementById('config-hint').textContent = '';
    }
  }

  async function validateConfig() {
    const cfg = collectFormConfig();
    try {
      const r = await API.post('/api/config/validate', cfg);
      const out = document.getElementById('config-output');
      if (r.success) { out.textContent = '✓ 校验通过\n\n' + JSON.stringify(r, null, 2); toast('校验通过', 'success'); }
      else { out.textContent = '✗ 校验失败\n\n' + JSON.stringify(r, null, 2); toast('校验未通过', 'error'); }
    } catch (e) { toast('请求失败: ' + e.message, 'error'); }
  }

  async function exportConfig() {
    const cfg = collectFormConfig();
    try { await API.download('/api/config/export', cfg); toast('已导出配置文件', 'success'); }
    catch (e) { toast('导出失败: ' + e.message, 'error'); }
  }

  /* ---------- 数组行添加 ---------- */
  function makeRow(html) { const d = document.createElement('div'); d.innerHTML = html; return d.firstElementChild; }
  function addVlanRow(id, name) {
    const list = document.getElementById('cfg-vlan-list');
    const row = makeRow('<div class="array-row"><input type="number" placeholder="VLAN ID" class="cfg-vlan-id" min="1" max="4094" value="' + (id || '') + '"/><input type="text" placeholder="名称" class="cfg-vlan-name" value="' + (name || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addIfVlanRow(iface, type, vid, trunk) {
    const list = document.getElementById('cfg-ifvlan-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="接口名" class="cfg-ifvlan-if" value="' + (iface || '') + '"/><select class="cfg-ifvlan-type"><option value="access"' + (type === 'access' ? ' selected' : '') + '>access</option><option value="trunk"' + (type === 'trunk' ? ' selected' : '') + '>trunk</option><option value="hybrid"' + (type === 'hybrid' ? ' selected' : '') + '>hybrid</option></select><input type="number" placeholder="VLAN ID" class="cfg-ifvlan-vid" value="' + (vid || '') + '"/><input type="text" placeholder="Trunk VLANs" class="cfg-ifvlan-trunk" value="' + (trunk || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addVlanifRow(vid, ip, mask) {
    const list = document.getElementById('cfg-vlanif-list');
    const row = makeRow('<div class="array-row"><input type="number" placeholder="VLAN ID" class="cfg-vlanif-vid" value="' + (vid || '') + '"/><input type="text" placeholder="IP 地址" class="cfg-vlanif-ip" value="' + (ip || '') + '"/><input type="text" placeholder="掩码" class="cfg-vlanif-mask" value="' + (mask || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addVoiceVlanRow(iface, vid) {
    const list = document.getElementById('cfg-voicevlan-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="接口" class="cfg-voice-if" value="' + (iface || '') + '"/><input type="number" placeholder="VLAN ID" class="cfg-voice-vid" value="' + (vid || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addStaticRouteRow() {
    const list = document.getElementById('cfg-static-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="目标网段" class="cfg-route-dest"/><input type="text" placeholder="掩码" class="cfg-route-mask"/><input type="text" placeholder="下一跳" class="cfg-route-nh"/><input type="number" placeholder="优先级" class="cfg-route-pref"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addStaticRouteRowWithData(r) {
    const list = document.getElementById('cfg-static-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="目标网段" class="cfg-route-dest" value="' + (r.dest_network || '') + '"/><input type="text" placeholder="掩码" class="cfg-route-mask" value="' + (r.mask || '') + '"/><input type="text" placeholder="下一跳" class="cfg-route-nh" value="' + (r.next_hop || '') + '"/><input type="number" placeholder="优先级" class="cfg-route-pref" value="' + (r.preference || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addOspfNetRow(addr, mask, area) {
    const list = document.getElementById('cfg-ospf-net-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="网段" class="cfg-ospf-net-addr" value="' + (addr || '') + '"/><input type="text" placeholder="反掩码" class="cfg-ospf-net-mask" value="' + (mask || '0.0.0.255') + '"/><input type="text" placeholder="Area" class="cfg-ospf-net-area" value="' + (area || '0') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addBgpPeerRow(ip, as) {
    const list = document.getElementById('cfg-bgp-peer-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="IP" class="cfg-bgp-peer-ip" value="' + (ip || '') + '"/><input type="number" placeholder="AS 号" class="cfg-bgp-peer-as" value="' + (as || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addAclRow() {
    const list = document.getElementById('cfg-acl-list');
    const row = makeRow('<div class="array-row" style="flex-direction:column;align-items:stretch;gap:6px;padding:10px;border:1px solid var(--border);border-radius:6px;"><div class="form-grid" style="grid-template-columns: repeat(3,1fr);"><div class="form-field"><label>ACL 编号</label><input type="number" class="cfg-acl-num" placeholder="2000-5999"/></div><div class="form-field"><label>描述</label><input type="text" class="cfg-acl-desc"/></div><div class="form-field"><label></label><button class="btn btn-sm btn-ghost" style="color:#dc2626;align-self:flex-end;" onclick="this.closest(\'.array-row\').remove()">删除 ACL</button></div></div><div class="form-section-subtitle">规则</div><div class="cfg-acl-rules" style="display:flex;flex-direction:column;gap:6px;"><div class="array-row"><input type="number" placeholder="规则ID" class="cfg-acl-rule-id" style="width:80px;"/><select class="cfg-acl-rule-act"><option value="permit">permit</option><option value="deny">deny</option></select><select class="cfg-acl-rule-proto"><option value="ip">ip</option><option value="tcp">tcp</option><option value="udp">udp</option><option value="icmp">icmp</option></select><input type="text" placeholder="源" class="cfg-acl-rule-src" value="any"/><input type="text" placeholder="目的" class="cfg-acl-rule-dst" value="any"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div></div><button class="btn btn-sm btn-ghost" onclick="App.addAclRule(this)">+ 添加规则</button></div>');
    list.appendChild(row);
  }
  function addAclRowWithData(a) {
    const list = document.getElementById('cfg-acl-list');
    const rulesHtml = (a.rules || []).map((r) => '<div class="array-row"><input type="number" placeholder="规则ID" class="cfg-acl-rule-id" style="width:80px;" value="' + (r.rule_id || '') + '"/><select class="cfg-acl-rule-act"><option value="permit"' + (r.action === 'permit' ? ' selected' : '') + '>permit</option><option value="deny"' + (r.action === 'deny' ? ' selected' : '') + '>deny</option></select><select class="cfg-acl-rule-proto"><option value="ip"' + (r.protocol === 'ip' ? ' selected' : '') + '>ip</option><option value="tcp"' + (r.protocol === 'tcp' ? ' selected' : '') + '>tcp</option><option value="udp"' + (r.protocol === 'udp' ? ' selected' : '') + '>udp</option><option value="icmp"' + (r.protocol === 'icmp' ? ' selected' : '') + '>icmp</option></select><input type="text" placeholder="源" class="cfg-acl-rule-src" value="' + (r.source || 'any') + '"/><input type="text" placeholder="目的" class="cfg-acl-rule-dst" value="' + (r.destination || 'any') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>').join('');
    const row = makeRow('<div class="array-row" style="flex-direction:column;align-items:stretch;gap:6px;padding:10px;border:1px solid var(--border);border-radius:6px;"><div class="form-grid" style="grid-template-columns: repeat(3,1fr);"><div class="form-field"><label>ACL 编号</label><input type="number" class="cfg-acl-num" placeholder="2000-5999" value="' + (a.number || '') + '"/></div><div class="form-field"><label>描述</label><input type="text" class="cfg-acl-desc" value="' + (a.description || '') + '"/></div><div class="form-field"><label></label><button class="btn btn-sm btn-ghost" style="color:#dc2626;align-self:flex-end;" onclick="this.closest(\'.array-row\').remove()">删除 ACL</button></div></div><div class="form-section-subtitle">规则</div><div class="cfg-acl-rules" style="display:flex;flex-direction:column;gap:6px;">' + (rulesHtml || '<div class="array-row"><input type="number" placeholder="规则ID" class="cfg-acl-rule-id" style="width:80px;"/><select class="cfg-acl-rule-act"><option value="permit">permit</option><option value="deny">deny</option></select><select class="cfg-acl-rule-proto"><option value="ip">ip</option><option value="tcp">tcp</option><option value="udp">udp</option><option value="icmp">icmp</option></select><input type="text" placeholder="源" class="cfg-acl-rule-src" value="any"/><input type="text" placeholder="目的" class="cfg-acl-rule-dst" value="any"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>') + '</div><button class="btn btn-sm btn-ghost" onclick="App.addAclRule(this)">+ 添加规则</button></div>');
    list.appendChild(row);
  }
  function addAclRule(btn) {
    const rules = btn.previousElementSibling;
    const row = makeRow('<div class="array-row"><input type="number" placeholder="规则ID" class="cfg-acl-rule-id" style="width:80px;"/><select class="cfg-acl-rule-act"><option value="permit">permit</option><option value="deny">deny</option></select><select class="cfg-acl-rule-proto"><option value="ip">ip</option><option value="tcp">tcp</option><option value="udp">udp</option><option value="icmp">icmp</option></select><input type="text" placeholder="源" class="cfg-acl-rule-src" value="any"/><input type="text" placeholder="目的" class="cfg-acl-rule-dst" value="any"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    rules.appendChild(row);
  }
  function addPortSecRow(iface, max, act) {
    const list = document.getElementById('cfg-portsec-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="接口" class="cfg-ps-if" value="' + (iface || '') + '"/><input type="number" placeholder="最大 MAC" class="cfg-ps-max" value="' + (max || 1) + '"/><select class="cfg-ps-act"><option value="protect"' + (act === 'protect' ? ' selected' : '') + '>protect</option><option value="restrict"' + (act === 'restrict' ? ' selected' : '') + '>restrict</option><option value="shutdown"' + (act === 'shutdown' ? ' selected' : '') + '>shutdown</option></select><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addStormRow(iface, bcast, mcast, ucast, act) {
    const list = document.getElementById('cfg-storm-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="接口" class="cfg-storm-if" value="' + (iface || '') + '"/><input type="number" placeholder="广播" class="cfg-storm-bcast" value="' + (bcast || '') + '"/><input type="number" placeholder="组播" class="cfg-storm-mcast" value="' + (mcast || '') + '"/><input type="number" placeholder="单播" class="cfg-storm-ucast" value="' + (ucast || '') + '"/><select class="cfg-storm-act"><option value="block"' + (act === 'block' ? ' selected' : '') + '>block</option><option value="shutdown"' + (act === 'shutdown' ? ' selected' : '') + '>shutdown</option></select><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addRadiusRow(name, ip, key, auth, acct) {
    const list = document.getElementById('cfg-radius-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="名称" class="cfg-rad-name" value="' + (name || '') + '"/><input type="text" placeholder="IP" class="cfg-rad-ip" value="' + (ip || '') + '"/><input type="text" placeholder="共享密钥" class="cfg-rad-key" value="' + (key || '') + '"/><input type="number" placeholder="认证端口" class="cfg-rad-auth" value="' + (auth || 1812) + '"/><input type="number" placeholder="计费端口" class="cfg-rad-acct" value="' + (acct || 1813) + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addEthTrunkRow(id, mode, members, desc, linkType, vlans, native) {
    const list = document.getElementById('cfg-trunk-list');
    const row = makeRow('<div class="array-row" style="flex-wrap:wrap;gap:6px;">'
      + '<input type="number" placeholder="Trunk ID" class="cfg-trunk-id" style="width:90px;" value="' + (id || '') + '"/>'
      + '<select class="cfg-trunk-mode"><option value="lacp-static"' + (mode === 'lacp-static' ? ' selected' : '') + '>lacp-static</option><option value="lacp-dynamic"' + (mode === 'lacp-dynamic' ? ' selected' : '') + '>lacp-dynamic</option><option value="manual"' + (mode === 'manual' ? ' selected' : '') + '>manual</option></select>'
      + '<input type="text" placeholder="成员端口(逗号分隔)" class="cfg-trunk-members" style="min-width:200px;" value="' + (members || '') + '"/>'
      + '<input type="text" placeholder="描述" class="cfg-trunk-desc" style="min-width:150px;" value="' + (desc || '') + '"/>'
      + '<select class="cfg-trunk-linktype"><option value="trunk"' + (linkType === 'access' ? '' : ' selected') + '>trunk</option><option value="access"' + (linkType === 'access' ? ' selected' : '') + '>access</option></select>'
      + '<input type="text" placeholder="Trunk VLANs (如 10,20,30)" class="cfg-trunk-vlans" style="min-width:180px;" value="' + (vlans || '') + '"/>'
      + '<input type="number" placeholder="Native VLAN" class="cfg-trunk-native" style="width:120px;" value="' + (native || '') + '"/>'
      + '<button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }
  function addRateLimitRow(iface, rin, rout) {
    const list = document.getElementById('cfg-rate-list');
    const row = makeRow('<div class="array-row"><input type="text" placeholder="接口" class="cfg-rate-if" value="' + (iface || '') + '"/><input type="number" placeholder="CIR 入(Kbps)" class="cfg-rate-in" value="' + (rin || '') + '"/><input type="number" placeholder="CIR 出(Kbps)" class="cfg-rate-out" value="' + (rout || '') + '"/><button class="btn btn-sm btn-ghost" style="color:#dc2626;" onclick="this.parentElement.remove()">✕</button></div>');
    list.appendChild(row);
  }

  /* ============================================================
     设备管理
     ============================================================ */
  let editingDeviceId = null;

  // 连接测试状态: { [deviceId]: { state: 'testing'|'ok'|'fail', message, elapsed } }
  const deviceTestStates = {};

  function statusChipHtml(id) {
    const ts = deviceTestStates[id];
    if (!ts) {
      return '<span class="status-chip status-unknown" title="尚未测试">未测</span>';
    }
    if (ts.state === "testing") {
      return '<span class="status-chip status-testing">测试中…</span>';
    }
    if (ts.state === "ok") {
      return '<span class="status-chip status-online" title="' + escapeHtml(ts.message || "") + ' · ' + ts.elapsed + ' ms">在线 ' + ts.elapsed + 'ms</span>';
    }
    return '<span class="status-chip status-offline" title="' + escapeHtml(ts.message || "连接失败") + '">离线</span>';
  }

  function renderDeviceStatus(id) {
    const td = document.getElementById("dev-status-" + id);
    if (td) td.innerHTML = statusChipHtml(id);
  }

  async function testDeviceQuiet(id) {
    deviceTestStates[id] = { state: "testing" };
    renderDeviceStatus(id);
    try {
      const r = await API.post("/api/devices/" + id + "/test", {});
      deviceTestStates[id] = {
        state: r.success ? "ok" : "fail",
        message: r.message || "",
        elapsed: r.elapsed_ms || null,
      };
    } catch (e) {
      deviceTestStates[id] = { state: "fail", message: e.message, elapsed: null };
    }
    renderDeviceStatus(id);
    return deviceTestStates[id];
  }

  async function testDevice(id, name) {
    const label = name ? "「" + name + "」" : "设备";
    toast("正在测试 " + label + " 连接...");
    const st = await testDeviceQuiet(id);
    if (st.state === "ok") {
      toast("✅ " + label + " 连接成功 (" + st.elapsed + " ms)", "success");
    } else {
      toast("❌ " + label + " 连接失败: " + (st.message || "未知原因"), "error");
    }
  }

  async function testAllDevices() {
    const btn = document.getElementById("btn-test-all");
    if (btn) { btn.disabled = true; btn.textContent = "⚡ 测试中..."; }
    try {
      const r = await API.get("/api/devices");
      const list = r.devices || [];
      if (!list.length) { toast("暂无设备", "error"); return; }
      let ok = 0, fail = 0;
      for (const d of list) {
        const st = await testDeviceQuiet(d.id);
        if (st.state === "ok") ok++; else fail++;
      }
      const msg = "批量测试完成: " + ok + " 台在线, " + fail + " 台失败";
      toast(msg, fail === 0 ? "success" : "error");
    } catch (e) {
      toast("批量测试失败: " + e.message, "error");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "⚡ 批量测试"; }
    }
  }

  async function loadDevices() {
    try {
      const r = await API.get("/api/devices");
      const tbody = document.getElementById("device-tbody");
      const empty = document.getElementById("device-empty");
      const list = r.devices || [];
      if (!list.length) {
        tbody.innerHTML = "";
        empty.style.display = "block";
        return;
      }
      empty.style.display = "none";
      const vendorNames = { huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" };
      const typeNames = { switch: "交换机", router: "路由器", ap: "AP" };
      tbody.innerHTML = list
        .map((d) =>
          '<tr>' +
          '<td>' + escapeHtml(d.name) + "</td>" +
          '<td><span class="badge badge-info">' + (vendorNames[d.vendor] || d.vendor) + "</span></td>" +
          "<td>" + (typeNames[d.device_type] || d.device_type) + "</td>" +
          '<td><span class="badge" style="background:#6366f1;color:#fff">' + (d.connection_type === "telnet" ? "Telnet" : "SSH") + "</span></td>" +
          "<td>" + escapeHtml(d.host || "-") + "</td>" +
          "<td>" + (d.port || "-") + "</td>" +
          "<td>" + escapeHtml(d.location || "-") + "</td>" +
          "<td>" + (d.created_at ? d.created_at.replace("T", " ").slice(0, 19) : "-") + "</td>" +
          '<td id="dev-status-' + d.id + '">' + statusChipHtml(d.id) + "</td>" +
          '<td class="actions">' +
            '<button class="btn btn-sm btn-ghost" onclick="App.testDevice(\'' + d.id + "','" + escapeHtml(d.name) + "')\">测试</button>" +
            '<button class="btn btn-sm btn-ghost" onclick="App.openPushModal(\'' + d.id + "','" + escapeHtml(d.name) + "','" + (d.vendor || "huawei") + "')\">推送</button>" +
            '<button class="btn btn-sm btn-ghost" style="color:#2563eb" onclick="App.backupDevice(\'' + d.id + "','" + escapeHtml(d.name) + "')\">历史</button>" +
            '<button class="btn btn-sm btn-ghost" onclick="App.editDevice(\'' + d.id + "')\">编辑</button>" +
            '<button class="btn btn-sm btn-ghost" style="color:#dc2626" onclick="App.deleteDevice(\'' + d.id + "','" + escapeHtml(d.name) + "')\">删除</button>" +
          "</td>" +
          "</tr>"
        )
        .join("");
    } catch (e) {
      toast("加载设备失败: " + e.message, "error");
    }
  }

  function openDeviceModal(id) {
    editingDeviceId = id || null;
    document.getElementById("device-modal-title").textContent = id ? "编辑设备" : "添加设备";
    if (!id) {
      ["dev-name","dev-host","dev-username","dev-password","dev-enable","dev-location","dev-remark"].forEach(x => document.getElementById(x).value = "");
      document.getElementById("dev-vendor").value = "huawei";
      document.getElementById("dev-type").value = "switch";
      document.getElementById("dev-conn-type").value = "ssh";
      document.getElementById("dev-port").value = 22;
    }
    document.getElementById("device-modal").classList.add("show");
  }

  function closeDeviceModal() {
    document.getElementById("device-modal").classList.remove("show");
  }

  async function editDevice(id) {
    const r = await API.get("/api/devices");
    const d = (r.devices || []).find((x) => x.id === id);
    if (!d) { toast("设备不存在", "error"); return; }
    openDeviceModal(id);
    document.getElementById("dev-name").value = d.name || "";
    document.getElementById("dev-vendor").value = d.vendor || "huawei";
    document.getElementById("dev-type").value = d.device_type || "switch";
    document.getElementById("dev-conn-type").value = d.connection_type || "ssh";
    document.getElementById("dev-host").value = d.host || "";
    document.getElementById("dev-port").value = d.port || (d.connection_type === "telnet" ? 23 : 22);
    document.getElementById("dev-location").value = d.location || "";
    document.getElementById("dev-remark").value = d.remark || "";
  }

  async function saveDevice() {
    const name = document.getElementById("dev-name").value.trim();
    if (!name) { toast("请输入设备名称", "error"); return; }
    const body = {
      name,
      vendor: document.getElementById("dev-vendor").value,
      device_type: document.getElementById("dev-type").value,
      connection_type: document.getElementById("dev-conn-type").value,
      host: document.getElementById("dev-host").value.trim() || null,
      port: parseInt(document.getElementById("dev-port").value) || (document.getElementById("dev-conn-type").value === "telnet" ? 23 : 22),
      username: document.getElementById("dev-username").value.trim() || null,
      password: document.getElementById("dev-password").value || null,
      enable_password: document.getElementById("dev-enable").value || null,
      location: document.getElementById("dev-location").value.trim() || null,
      remark: document.getElementById("dev-remark").value.trim() || null,
    };
    try {
      if (editingDeviceId) {
        await API.put("/api/devices/" + editingDeviceId, body);
        toast("设备已更新", "success");
      } else {
        const r = await API.post("/api/devices", body);
        if (r.auto_backup_started) {
          toast("设备已添加，正在后台自动备份配置...", "success");
        } else {
          toast(r.message || "设备已添加", "success");
        }
      }
      closeDeviceModal();
      loadDevices();
    } catch (e) {
      toast("保存失败: " + e.message, "error");
    }
  }

  async function deleteDevice(id, name) {
    if (!confirm("确定删除设备「" + name + "」？")) return;
    try {
      await API.del("/api/devices/" + id);
      toast("已删除", "success");
      loadDevices();
    } catch (e) {
      toast("删除失败: " + e.message, "error");
    }
  }

  /* ---------- 配置备份 ---------- */
  let backupDeviceId = null;

  function backupDevice(id, name) {
    backupDeviceId = id;
    document.getElementById("backup-device-name").textContent = name || id;
    document.getElementById("backup-panel").style.display = "block";
    document.getElementById("backup-info").style.display = "none";
    document.getElementById("backup-info").innerHTML = "";
    // 仅加载历史记录, 不自动触发备份 — 需要备份时点面板内"立即备份"
    loadBackups();
  }

  function closeBackupPanel() {
    document.getElementById("backup-panel").style.display = "none";
  }

  async function execBackup() {
    if (!backupDeviceId) { toast("请先选择设备", "error"); return; }
    const btn = document.getElementById("btn-backup-now");
    const info = document.getElementById("backup-info");
    btn.disabled = true;
    btn.textContent = "备份中...";
    info.style.display = "block";
    info.innerHTML = '<span style="color:#2563eb">正在连接设备获取运行配置...</span>';
    try {
      const r = await API.post("/api/devices/" + backupDeviceId + "/backup", {});
      if (r.success) {
        info.innerHTML = '<span class="badge badge-success">✓ ' + escapeHtml(r.message) + '</span> (版本 ' + escapeHtml(r.version_label || "-") + ')';
        toast("备份成功", "success");
        loadBackups();
      } else {
        info.innerHTML = '<span class="badge" style="background:#dc2626;color:#fff">✗ ' + escapeHtml(r.message || "备份失败") + '</span>';
        toast("备份失败: " + (r.message || ""), "error");
      }
    } catch (e) {
      info.innerHTML = '<span class="badge" style="background:#dc2626;color:#fff">✗ ' + escapeHtml(e.message) + '</span>';
      toast("备份失败: " + e.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "📦 立即备份";
    }
  }

  async function loadBackups() {
    if (!backupDeviceId) return;
    const tbody = document.getElementById("backup-tbody");
    const empty = document.getElementById("backup-empty");
    try {
      const r = await API.get("/api/devices/" + backupDeviceId + "/backups");
      const list = r.backups || [];
      tbody.innerHTML = "";
      if (!list.length) {
        empty.style.display = "block";
        return;
      }
      empty.style.display = "none";
      tbody.innerHTML = list
        .map((b) => {
          const missing = b.file_exists === false;
          const fileCell = missing
            ? "<code style='font-size:12px;color:#9ca3af;text-decoration:line-through;'>" + escapeHtml(b.file_path || "-") + "</code> " +
              "<span class='badge' style='background:#fef3c7;color:#b45309;' title='磁盘上的 .cfg 文件已不存在, 配置内容仍保存在数据库中'>⚠ 文件缺失</span>"
            : "<code style='font-size:12px;'>" + escapeHtml(b.file_path || "-") + "</code>";
          const restoreBtn = missing
            ? '<button class="btn btn-sm btn-ghost" style="color:#b45309" onclick="App.restoreBackupFile(\'' + b.id + "')\">恢复文件</button>"
            : "";
          return (
          '<tr' + (missing ? ' style="background:#fffbeb;"' : "") + '>' +
          "<td>" + escapeHtml(b.version_label || "backup") + "</td>" +
          "<td>" + (b.created_at ? b.created_at.replace("T", " ").slice(0, 19) : "-") + "</td>" +
          "<td>" + fmtSize(b.size || 0) + "</td>" +
          "<td>" + (b.lines || 0) + "</td>" +
          "<td>" + fileCell + "</td>" +
          '<td class="actions">' +
            '<button class="btn btn-sm btn-ghost" onclick="App.viewBackup(\'' + b.id + "')\">查看</button>" +
            '<button class="btn btn-sm btn-ghost" onclick="App.downloadBackup(\'' + b.id + "')\">下载</button>" +
            restoreBtn +
            '<button class="btn btn-sm btn-ghost" style="color:#dc2626" onclick="App.deleteBackup(\'' + b.id + "')\">删除</button>" +
          "</td>" +
          "</tr>"
          );
        })
        .join("");
    } catch (e) {
      toast("加载备份失败: " + e.message, "error");
    }
  }

  async function viewBackup(configId) {
    if (!backupDeviceId) return;
    try {
      const r = await API.get("/api/devices/" + backupDeviceId + "/backups/" + configId);
      const b = r.backup || {};
      document.getElementById("backup-view-label").textContent = b.version_label || "backup";
      document.getElementById("backup-view-time").textContent = "时间: " + (b.created_at ? b.created_at.replace("T", " ").slice(0, 19) : "-");
      document.getElementById("backup-view-size").textContent = "大小: " + fmtSize((b.config_text || "").length);
      document.getElementById("backup-view-content").textContent = b.config_text || "(空配置)";
      window._backupViewConfigId = configId;
      document.getElementById("backup-view-modal").classList.add("show");
    } catch (e) {
      toast("查看备份失败: " + e.message, "error");
    }
  }

  function closeBackupView() {
    document.getElementById("backup-view-modal").classList.remove("show");
  }

  function copyBackup() {
    const el = document.getElementById("backup-view-content");
    const text = el.textContent || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("已复制", "success")).catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("已复制", "success"); } catch (e) { toast("复制失败", "error"); }
    document.body.removeChild(ta);
  }

  function downloadBackup(configId) {
    const el = document.getElementById("backup-view-content");
    const text = el.textContent || "";
    const label = (document.getElementById("backup-view-label").textContent || "backup").replace(/[\\/:*?"<>|]/g, "_");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = label + ".txt";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function deleteBackup(configId) {
    if (!confirm("确定删除这条备份？将同时删除数据库记录和磁盘上的 .cfg 文件, 不可恢复。")) return;
    try {
      const r = await API.del("/api/devices/" + backupDeviceId + "/backups/" + configId);
      if (r && r.file_deleted === false && r.file_message) {
        toast("记录已删除 (" + r.file_message + ")", "success");
      } else {
        toast("备份已删除 (含 .cfg 文件)", "success");
      }
      loadBackups();
    } catch (e) {
      toast("删除失败: " + e.message, "error");
    }
  }

  async function restoreBackupFile(configId) {
    try {
      const r = await API.post("/api/devices/" + backupDeviceId + "/backups/" + configId + "/restore-file", {});
      if (r.success && r.restored) {
        toast("文件已恢复: " + (r.message || "OK"), "success");
      } else {
        toast(r.message || "恢复失败", "error");
      }
      loadBackups();
    } catch (e) {
      toast("恢复失败: " + e.message, "error");
    }
  }

  function fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(2) + " MB";
  }

  /* ---------- 批量备份 ---------- */
  async function backupAllDevices() {
    if (!confirm("确定批量备份所有设备吗？将逐台连接并抓取配置。")) return;
    const btn = document.getElementById("btn-backup-all");
    const panel = document.getElementById("batch-backup-panel");
    const summary = document.getElementById("batch-backup-summary");
    const list = document.getElementById("batch-backup-list");
    btn.disabled = true;
    btn.textContent = "备份中...";
    panel.style.display = "block";
    summary.innerHTML = '<span style="color:#2563eb">⏳ 正在逐台备份，请稍候...</span>';
    list.innerHTML = "";
    try {
      const r = await API.post("/api/devices/backup-all", {});
      const results = r.results || [];
      summary.innerHTML = '<span class="badge badge-success">成功 ' + (r.ok || 0) + "</span> " +
        '<span class="badge" style="background:#dc2626;color:#fff">失败 ' + (r.failed || 0) + "</span> " +
        '<span class="hint">共 ' + (r.total || 0) + " 台设备</span>";
      list.innerHTML = results.map((x) =>
        '<div style="padding:6px 0;border-bottom:1px dashed var(--border);">' +
        (x.success
          ? '<span class="badge badge-success">✓</span> <b>' + escapeHtml(x.device_name || x.device_id) + "</b> — " + escapeHtml(x.file || "")
          : '<span class="badge" style="background:#dc2626;color:#fff">✗</span> <b>' + escapeHtml(x.device_name || x.device_id) + "</b> — " + escapeHtml(x.message || "失败")) +
        "</div>"
      ).join("");
    } catch (e) {
      summary.innerHTML = '<span class="badge" style="background:#dc2626;color:#fff">✗ ' + escapeHtml(e.message) + "</span>";
    } finally {
      btn.disabled = false;
      btn.textContent = "📦 批量备份";
    }
  }

  function closeBatchBackupPanel() {
    document.getElementById("batch-backup-panel").style.display = "none";
  }

  /* ---------- TFTP/FTP 文件服务 ---------- */
  function renderFileServerStatus(st) {
    const rootEl = document.getElementById("fileserver-root");
    if (rootEl) rootEl.textContent = st.root || "-";
    const tftp = st.tftp || {};
    const ftp = st.ftp || {};
    const tState = document.getElementById("tftp-state");
    tState.textContent = tftp.running ? "运行中 :" + tftp.port : "停止";
    tState.className = "badge " + (tftp.running ? "badge-success" : "");
    tState.style.background = tftp.running ? "" : "#94a3b8";
    tState.style.color = tftp.running ? "" : "#fff";
    const fState = document.getElementById("ftp-state");
    fState.textContent = ftp.running ? "运行中 :" + ftp.port : "停止";
    fState.className = "badge " + (ftp.running ? "badge-success" : "");
    fState.style.background = ftp.running ? "" : "#94a3b8";
    fState.style.color = ftp.running ? "" : "#fff";
    const badge = document.getElementById("fileserver-status");
    const any = tftp.running || ftp.running;
    badge.textContent = any ? "● 服务已开启" : "未启动";
    badge.className = "badge " + (any ? "badge-success" : "badge-info");
    // TFTP 传输日志 (始终显示, 便于随时点刷新)
    const logEl = document.getElementById("tftp-log");
    if (logEl) {
      const log = tftp.transfer_log || [];
      logEl.style.display = "block";
      const header =
        '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">' +
        '<span style="font-weight:600;">📡 最近传输记录（最新在上）</span>' +
        '<button class="btn btn-sm btn-ghost" onclick="App.loadFileServerStatus()">🔄 刷新</button>' +
        "</div>";
      if (!log.length) {
        logEl.innerHTML = header +
          '<div style="font-size:12px; color:var(--text-secondary,#6b7280); padding:6px 0;">暂无传输记录，进行 TFTP 上传/下载后可点"刷新"查看。</div>';
      } else {
        logEl.innerHTML = header +
          '<table style="width:100%; font-size:12px; border-collapse:collapse;">' +
          "<thead><tr>" +
          ['时间', '方向', '客户端', '请求文件', '结果'].map((h) =>
            '<th style="text-align:left; padding:2px 8px; border-bottom:1px solid var(--border,#e5e7eb);">' + h + "</th>").join("") +
          "</tr></thead><tbody>" +
          log.map((t) =>
            "<tr>" +
            '<td style="padding:2px 8px;">' + escapeHtml(t.time) + "</td>" +
            "<td>" + (t.op === "读" ? "⬇ 下载" : "⬆ 上传") + "</td>" +
            "<td>" + escapeHtml(t.client) + "</td>" +
            "<td><code>" + escapeHtml(t.filename) + "</code></td>" +
            '<td style="color:' + (t.ok ? "#16a34a" : "#dc2626") + ';">' + (t.ok ? "✓ " : "✗ ") + escapeHtml(t.detail) + "</td>" +
            "</tr>").join("") +
          "</tbody></table>";
      }
    }
  }

  async function loadFileServerStatus() {
    try {
      renderFileServerStatus(await API.get("/api/fileservers/status"));
    } catch (e) { /* 静默 */ }
  }

  async function toggleFileServer(kind, start) {
    const port = document.getElementById(kind + "-port").value;
    try {
      const r = await API.post("/api/fileservers/" + kind + "/" + (start ? "start" : "stop"), { port: parseInt(port) || null });
      toast(r.message || (start ? "已启动" : "已停止"), r.success ? "success" : "error");
      renderFileServerStatus(r);
    } catch (e) {
      toast("操作失败: " + e.message, "error");
    }
  }

  /* ---------- 推送配置 ---------- */
  let pushDeviceId = null;
  let lastGenVendor = null; // 最近一次生成配置的厂商，用于预览区推送

  function openPushModal(id, name, vendor) {
    pushDeviceId = id;
    document.getElementById("push-device-name").textContent = name;
    document.getElementById("push-vendor").value = vendor || "huawei";
    document.getElementById("push-config-text").value = "";
    document.getElementById("push-result").innerHTML = "";
    document.getElementById("push-modal").classList.add("show");
  }

  function closePushModal() {
    document.getElementById("push-modal").classList.remove("show");
  }

  async function execPush() {
    const text = document.getElementById("push-config-text").value.trim();
    if (!text) { toast("请输入配置文本", "error"); return; }
    const vendor = document.getElementById("push-vendor").value;
    const resultEl = document.getElementById("push-result");
    resultEl.innerHTML = '<div class="hint">推送中，逐条下发并监控回滚...</div>';
    try {
      const r = await API.post("/api/devices/" + pushDeviceId + "/push", {
        config_text: text,
        vendor,
      });
      renderPushResult(r);
    } catch (e) {
      resultEl.innerHTML = '<div class="badge badge-danger">请求失败: ' + escapeHtml(e.message) + "</div>";
    }
  }

  function renderPushResult(r, targetId) {
    const el = document.getElementById(targetId || "push-result");
    if (r.success) {
      el.innerHTML =
        '<div class="push-info">' +
          '<div class="info-box ok"><div class="num">' + (r.commands_success || 0) + "/" + (r.commands_total || 0) + '</div><div class="lbl">成功/总命令</div></div>' +
          '<div class="info-box ' + (r.rollback_performed ? "fail" : "ok") + '"><div class="num">' + (r.rollback_commands || 0) + '</div><div class="lbl">回滚命令</div></div>' +
        "</div>" +
        '<div class="badge badge-success">推送成功</div> ' + escapeHtml(r.message || "") +
        '<pre class="log-area" style="margin-top:10px;">' + escapeHtml(r.output || "无输出") + "</pre>";
      toast("推送成功", "success");
    } else {
      el.innerHTML =
        '<div class="push-info">' +
          '<div class="info-box fail"><div class="num">' + (r.commands_success || 0) + "/" + (r.commands_total || 0) + '</div><div class="lbl">成功/总命令</div></div>' +
          '<div class="info-box fail"><div class="num">' + (r.rollback_commands || 0) + '</div><div class="lbl">已回滚</div></div>' +
        "</div>" +
        '<div class="badge badge-danger">推送失败 — 已执行命令级回滚</div> ' + escapeHtml(r.message || "") +
        '<pre class="log-area" style="margin-top:10px;">' + escapeHtml(r.output || "无输出") + "</pre>";
      toast("推送失败，已回滚", "error");
    }
  }

  /* ---------- 预览区直接推送 ---------- */
  const VENDOR_LABELS = { huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" };

  // 显示预览区下方的推送区块，并加载设备列表
  async function showPushSection() {
    const sec = document.getElementById("push-section");
    if (!sec) return;
    sec.style.display = "block";
    const hint = document.getElementById("push-vendor-hint");
    if (hint) {
      hint.textContent = lastGenVendor
        ? "当前配置厂商: " + (VENDOR_LABELS[lastGenVendor] || lastGenVendor)
        : "尚未生成配置";
    }
    await loadPushDeviceList();
  }

  // 加载设备列表到预览区推送下拉框
  async function loadPushDeviceList() {
    const sel = document.getElementById("push-target-device");
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">选择目标设备…</option>';
    try {
      const r = await API.get("/api/devices");
      const devices = Array.isArray(r) ? r : r.devices || r.data || [];
      devices.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.name + " (" + (VENDOR_LABELS[d.vendor] || d.vendor || "?") + ")";
        opt.dataset.vendor = d.vendor || "";
        sel.appendChild(opt);
      });
      if (cur) sel.value = cur;
      if (devices.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "暂无设备，请先在「设备管理」添加";
        opt.disabled = true;
        sel.appendChild(opt);
      }
    } catch (e) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "设备列表加载失败";
      opt.disabled = true;
      sel.appendChild(opt);
    }
  }

  // 从预览区推送当前生成的配置
  async function pushFromPreview() {
    const text = (document.getElementById("config-output").textContent || "").trim();
    if (!text || text.startsWith("点击「生成配置」")) {
      toast("请先生成配置", "error");
      return;
    }
    const sel = document.getElementById("push-target-device");
    const deviceId = sel ? sel.value : "";
    if (!deviceId) {
      toast("请选择目标设备", "error");
      return;
    }
    // 优先用生成配置的厂商，其次用设备自身厂商
    const vendor =
      lastGenVendor ||
      (sel.selectedOptions[0] && sel.selectedOptions[0].dataset.vendor) ||
      "huawei";
    const resultEl = document.getElementById("push-preview-result");
    resultEl.innerHTML = '<div class="hint">推送中，逐条下发并监控回滚…</div>';
    const btn = document.getElementById("btn-push-from-preview");
    if (btn) btn.disabled = true;
    try {
      const r = await API.post("/api/devices/" + deviceId + "/push", {
        config_text: text,
        vendor,
      });
      renderPushResult(r, "push-preview-result");
    } catch (e) {
      resultEl.innerHTML =
        '<div class="badge badge-danger">请求失败: ' + escapeHtml(e.message) + "</div>";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  /* ============================================================
     网络工具箱
     ============================================================ */
  function switchTool(name) {
    document.querySelectorAll("#tool-tabs .tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tool-pane").forEach((p) => p.classList.remove("active"));
    document.querySelector('#tool-tabs .tab[data-tool="' + name + '"]').classList.add("active");
    document.querySelector('.tool-pane[data-tool="' + name + '"]').classList.add("active");
  }

  function showResult(id, data) {
    const el = document.getElementById(id);
    el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  }

  // 渲染 HTML 到输出区
  function renderToolHtml(outId, html) {
    const el = document.getElementById(outId);
    if (el) el.innerHTML = html;
  }

  async function runTool(url, body, outId, label) {
    showResult(outId, label + " 中...");
    try {
      const r = body ? await API.post(url, body) : await API.get(url);
      const renderer = TOOL_RENDERERS[outId];
      if (renderer) {
        renderToolHtml(outId, renderer(r));
      } else {
        showResult(outId, r);
      }
    } catch (e) {
      showResult(outId, "错误: " + e.message);
    }
  }

  /* ============================================================
     工具结果渲染器 — 把 JSON 转成普通人可读的信息
     ============================================================ */
  function tiHeader(title, ok) {
    return '<div class="ti-header ' + (ok ? "ok" : "fail") + '">' + escapeHtml(title) + "</div>";
  }
  function tiRow(label, value, cls) {
    return '<div class="ti-row"><span class="ti-label">' + escapeHtml(label) +
      '</span><span class="ti-val ' + (cls || "") + '">' +
      escapeHtml(value === undefined || value === null ? "" : String(value)) + "</span></div>";
  }
  function tiBadge(text, cls) {
    return '<span class="ti-badge ' + (cls || "info") + '">' + escapeHtml(text) + "</span>";
  }
  function tiEmpty(msg) {
    return '<div class="ti-empty">' + escapeHtml(msg) + "</div>";
  }
  function tiTable(headers, rows) {
    let h = '<table class="ti-table"><thead><tr>';
    headers.forEach((x) => (h += "<th>" + escapeHtml(x) + "</th>"));
    h += "</tr></thead><tbody>";
    rows.forEach((r) => {
      h += "<tr>";
      r.forEach((c) => (h += "<td>" + c + "</td>"));
      h += "</tr>";
    });
    return h + "</tbody></table>";
  }

  // 子网计算
  function renderSubnetCalc(r) {
    const res = r && r.result;
    if (!res) return tiHeader("子网计算失败", false) + tiEmpty("无返回数据");
    if (res.error) return tiHeader("子网计算失败", false) + tiRow("错误", res.error, "bad");
    return tiHeader("子网计算结果", true) +
      tiRow("网络地址", res.network) +
      tiRow("子网掩码", res.mask + " (/" + res.prefix_length + ")") +
      tiRow("反掩码", res.wildcard) +
      tiRow("广播地址", res.broadcast) +
      tiRow("可用主机数", res.num_hosts, "good") +
      tiRow("主机范围", res.first_host + " - " + res.last_host) +
      tiRow("地址总数", res.num_addresses) +
      tiRow("是否私有网段", res.is_private ? "是" : "否", res.is_private ? "warn" : "good");
  }

  // 子网划分
  function renderSubnetDivide(r) {
    const subs = r && r.subnets;
    if (!subs || !subs.length) return tiHeader("子网划分失败", false) + tiEmpty("无划分结果");
    if (subs[0] && subs[0].error) return tiHeader("子网划分失败", false) + tiRow("错误", subs[0].error, "bad");
    const rows = subs.map((s, i) => [
      i + 1, escapeHtml(s.network), escapeHtml(s.mask), escapeHtml(s.broadcast),
      escapeHtml(s.range), s.num_hosts,
    ]);
    return tiHeader("子网划分结果（共 " + subs.length + " 个子网）", true) +
      tiTable(["序号", "网络地址", "子网掩码", "广播地址", "主机范围", "可用主机"], rows);
  }

  // Ping
  function renderPing(r) {
    const p = r && r.result;
    if (!p) return tiHeader("Ping 失败", false) + tiEmpty("无返回数据");
    const ok = p.loss < 100;
    let html = tiHeader("Ping " + p.host + " 结果", ok);
    html += '<div style="margin:6px 0 10px;">' +
      tiBadge("发送 " + p.count, "info") + " " +
      tiBadge("成功 " + p.success, ok ? "ok" : "bad") + " " +
      tiBadge("丢包率 " + p.loss + "%", p.loss === 0 ? "ok" : "bad") +
      "</div>";
    if (ok) {
      html += tiRow("最小延迟", p.min_rtt + " ms", "good");
      html += tiRow("最大延迟", p.max_rtt + " ms");
      html += tiRow("平均延迟", p.avg_rtt + " ms", "good");
    }
    const rows = (p.results || []).map((it) => [
      it.seq,
      it.success ? tiBadge("成功", "ok") : tiBadge("失败", "bad"),
      it.success ? it.rtt + " ms" : "-",
      escapeHtml(it.error || ""),
    ]);
    html += '<div class="ti-section"></div>';
    html += tiTable(["序号", "结果", "延迟", "说明"], rows);
    return html;
  }

  // Ping 扫描
  function renderPingScan(r) {
    const list = r && r.results;
    if (!list) return tiHeader("扫描失败", false) + tiEmpty("无返回数据");
    if (list[0] && list[0].error) return tiHeader("扫描失败", false) + tiRow("错误", list[0].error, "bad");
    const alive = list.filter((x) => x.alive);
    let html = tiHeader("Ping 扫描结果", true);
    html += '<div style="margin:6px 0 10px;">' +
      tiBadge("扫描 " + list.length + " 台", "info") + " " +
      tiBadge("存活 " + alive.length + " 台", "ok") + "</div>";
    const rows = list.map((x) => [
      escapeHtml(x.host),
      x.alive ? tiBadge("存活", "ok") : tiBadge("未响应", "bad"),
    ]);
    return html + tiTable(["IP 地址", "状态"], rows);
  }

  // 端口范围扫描
  function renderPortScan(r) {
    const ports = r && r.open_ports;
    if (!ports) return tiHeader("端口扫描失败", false) + tiEmpty("无返回数据");
    let html = tiHeader("端口扫描结果", true);
    if (!ports.length) return html + tiEmpty("扫描范围内未发现开放端口");
    html += '<div style="margin:6px 0 10px;">' + tiBadge("开放端口 " + ports.length + " 个", "ok") + "</div>";
    const rows = ports.map((p) => [
      p.port, tiBadge("开放", "ok"), escapeHtml(p.service || "未知"),
    ]);
    return html + tiTable(["端口", "状态", "服务"], rows);
  }

  // 端口测试
  function renderPortTest(r) {
    const p = r && r.result;
    if (!p) return tiHeader("端口测试失败", false) + tiEmpty("无返回数据");
    const ok = !!p.open;
    return tiHeader("端口测试结果", ok) +
      tiRow("端口", p.port) +
      tiRow("状态", ok ? "开放" : "关闭/被过滤", ok ? "good" : "bad") +
      tiRow("服务", p.service || "未知");
  }

  // 路由跟踪
  function renderTraceroute(r) {
    const hops = r && r.hops;
    if (!hops) return tiHeader("路由跟踪失败", false) + tiEmpty("无返回数据");
    let html = tiHeader("路由跟踪结果（共 " + hops.length + " 跳）", true);
    const rows = hops.map((h) => [
      h.hop,
      escapeHtml(h.ip || "*"),
      h.rtt ? h.rtt + " ms" : "-",
      h.reached ? tiBadge("到达目标", "ok") : tiBadge("中转", "info"),
    ]);
    return html + tiTable(["跳数", "IP 地址", "延迟", "状态"], rows);
  }

  // DNS 查询
  function renderDns(r) {
    const list = r && r.results;
    if (!list) return tiHeader("DNS 查询失败", false) + tiEmpty("无返回数据");
    let html = tiHeader("DNS 查询结果", true);
    if (!list.length) return html + tiEmpty("未找到记录");
    const rows = list.map((v, i) => {
      const isError = typeof v === "string" && v.toLowerCase().startsWith("error");
      return [i + 1, '<span class="ti-val ' + (isError ? "bad" : "good") + '">' + escapeHtml(v) + "</span>"];
    });
    return html + tiTable(["序号", "记录值"], rows);
  }

  // 反向 DNS
  function renderReverseDns(r) {
    const list = r && r.results;
    if (!list) return tiHeader("反向 DNS 查询失败", false) + tiEmpty("无返回数据");
    let html = tiHeader("反向 DNS 查询结果", true);
    if (!list.length) return html + tiEmpty("未找到 PTR 记录");
    const rows = list.map((v, i) => {
      const isError = typeof v === "string" && v.toLowerCase().startsWith("error");
      return [i + 1, '<span class="ti-val ' + (isError ? "bad" : "good") + '">' + escapeHtml(v) + "</span>"];
    });
    return html + tiTable(["序号", "主机名"], rows);
  }

  // Whois
  function renderWhois(r) {
    const text = r && r.result;
    if (!text) return tiHeader("Whois 查询失败", false) + tiEmpty("无返回数据");
    return tiHeader("Whois 查询结果", true) + '<div class="ti-code">' + escapeHtml(text) + "</div>";
  }

  // 本机 IP
  function renderLocalIp(r) {
    const info = r && r.info;
    if (!info) return tiHeader("获取失败", false) + tiEmpty("无返回数据");
    return tiHeader("本机网络信息", true) +
      tiRow("主机名", info.hostname) +
      tiRow("主 IP 地址", info.local_ip, "good") +
      tiRow("全部 IP", (info.all_ips || []).join("、") || "无");
  }

  // 公网 IP
  function renderPublicIp(r) {
    const info = r && r.info;
    if (!info) return tiHeader("获取失败", false) + tiEmpty("无返回数据");
    if (info.error) return tiHeader("公网 IP 获取失败", false) + tiRow("错误", info.error, "bad");
    return tiHeader("公网 IP 信息", true) + tiRow("公网 IP", info.ip || JSON.stringify(info), "good");
  }

  // 配置对比
  function renderCompare(r) {
    const res = r && r.result;
    if (!res) return tiHeader("配置对比失败", false) + tiEmpty("无返回数据");
    let html = tiHeader("配置对比结果", res.identical);
    html += '<div style="margin:6px 0 10px;">' +
      tiBadge("新增 " + res.added + " 行", res.added ? "ok" : "info") + " " +
      tiBadge("删除 " + res.removed + " 行", res.removed ? "bad" : "info") + " " +
      tiBadge(res.identical ? "完全相同" : "存在差异", res.identical ? "ok" : "bad") + "</div>";
    if (res.identical) return html + tiEmpty("两份配置内容完全一致");
    const lines = (res.text_diff || "").split("\n");
    let diff = '<div class="ti-section ti-code">';
    lines.forEach((l) => {
      if (l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@")) {
        diff += '<div class="ti-diff-hunk">' + escapeHtml(l) + "</div>";
      } else if (l.startsWith("+")) {
        diff += '<div class="ti-diff-add">' + escapeHtml(l) + "</div>";
      } else if (l.startsWith("-")) {
        diff += '<div class="ti-diff-del">' + escapeHtml(l) + "</div>";
      } else {
        diff += "<div>" + escapeHtml(l) + "</div>";
      }
    });
    return html + diff + "</div>";
  }

  // 命令转换
  function renderConvert(r) {
    const text = r && r.result;
    if (!text) return tiHeader("命令转换失败", false) + tiEmpty("无返回数据");
    return tiHeader("命令转换结果", true) + '<div class="ti-code">' + escapeHtml(text) + "</div>";
  }

  // 渲染器映射表：key = 输出元素 id
  const TOOL_RENDERERS = {
    "subnet-output": renderSubnetCalc,
    "divide-output": renderSubnetDivide,
    "ping-output": renderPing,
    "scan-output": renderPingScan,
    "port-output": renderPortScan,
    "ptest-output": renderPortTest,
    "trace-output": renderTraceroute,
    "dns-output": renderDns,
    "rdns-output": renderReverseDns,
    "whois-output": renderWhois,
    "localip-output": renderLocalIp,
    "publicip-output": renderPublicIp,
    "compare-output": renderCompare,
    "convert-output": renderConvert,
  };

  /* ============================================================
     命令手册
     ============================================================ */
  async function loadManualPage() {
    try {
      const v = await API.get("/api/manual/vendors");
      const sel = document.getElementById("manual-vendor");
      const cur = sel.value;
      sel.innerHTML = '<option value="">全部厂商</option>' +
        (v.vendors || []).map((x) => '<option value="' + x + '">' + ({ huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" }[x] || x) + "</option>").join("");
      sel.value = cur;

      const s = await API.get("/api/manual/stats");
      const stats = s.stats || {};
      const parts = Object.entries(stats).map(([k, n]) => ({ huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" }[k] || k) + " " + n + " 条");
      document.getElementById("manual-stats").textContent = "手册统计: " + parts.join(" · ");
    } catch {}
    searchManual();
    loadManualCases();
  }

  async function searchManual() {
    const kw = document.getElementById("manual-search").value.trim();
    const vendor = document.getElementById("manual-vendor").value;
    const url = "/api/manual/search?keyword=" + encodeURIComponent(kw) + (vendor ? "&vendor=" + vendor : "");
    try {
      const r = await API.get(url);
      const list = r.results || [];
      const el = document.getElementById("manual-results");
      if (!list.length) {
        el.innerHTML = '<div class="empty-state">未找到匹配命令</div>';
        return;
      }
      const vendorNames = { huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" };
      const sourceLabels = {
        generator: { text: "生成器验证", cls: "src-generator" },
        official_doc: { text: "官方文档", cls: "src-official" },
        netops_toolkit: { text: "NetOps-toolkit", cls: "src-toolkit" },
        ai_knowledge: { text: "AI知识·待验证", cls: "src-ai" },
      };

      // 按 category 分组
      const groups = {};
      list.forEach((c) => {
        const cat = c.category || "其他";
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(c);
      });

      // 渲染分类折叠面板（默认折叠）
      let html = "";
      Object.keys(groups).sort().forEach((catName) => {
        const cmds = groups[catName];
        const catId = "cat-" + catName.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, "_");
        html +=
          '<div class="manual-category collapsed" data-cat="' + catId + '">' +
            '<div class="manual-cat-header" onclick="toggleManualCat(this)">' +
              '<span class="cat-title">' +
                '<span class="cat-arrow">▼</span>' +
                '<span>' + escapeHtml(catName) + '</span>' +
                '<span class="cat-count">' + cmds.length + ' 条</span>' +
              '</span>' +
            '</div>' +
            '<div class="manual-cat-body">' +
              cmds
                .map((c) => {
                  const src = sourceLabels[c.source];
                  const srcBadge = src
                    ? '<span class="src-badge ' + src.cls + '" title="命令来源">' + src.text + "</span>"
                    : "";
                  return (
                  '<div class="manual-item">' +
                    '<div class="cmd-vendor">' +
                      '<span class="badge badge-info">' + (vendorNames[c.vendor] || c.vendor) + "</span>" +
                      srcBadge +
                    "</div>" +
                    '<div class="cmd-syntax">' + escapeHtml(c.syntax || c.command || "") + "</div>" +
                    '<div class="cmd-desc">' + escapeHtml(c.description || c.desc || "") + "</div>" +
                    (c.example ? '<div class="cmd-cat-tag" style="margin-top:4px;">示例: <code>' + escapeHtml(c.example) + "</code></div>" : "") +
                  "</div>"
                  );
                })
                .join("") +
            "</div>" +
          "</div>";
      });
      el.innerHTML = html;
    } catch (e) {
      toast("搜索失败: " + e.message, "error");
    }
  }

  // 加载配置案例
  async function loadManualCases() {
    const vendor = document.getElementById("manual-vendor").value;
    const el = document.getElementById("manual-cases");
    const cntEl = document.getElementById("manual-case-count");
    const vendorNames = { huawei: "华为", h3c: "H3C", ruijie: "锐捷", maipu: "迈普" };
    try {
      const vendors = vendor ? [vendor] : (await API.get("/api/manual/vendors")).vendors || [];
      let allCases = [];
      for (const v of vendors) {
        const r = await API.get("/api/manual/" + v + "/cases");
        (r.cases || []).forEach((c) => allCases.push({ ...c, vendor: v }));
      }
      if (!allCases.length) {
        el.innerHTML = '<div class="empty-state">暂无配置案例</div>';
        cntEl.textContent = "";
        return;
      }
      cntEl.textContent = "共 " + allCases.length + " 个案例" + (vendor ? "" : "（当前显示全部厂商）");
      el.innerHTML = allCases
        .map((c, i) => {
          const caseId = "case-" + i;
          return (
            '<div class="manual-category collapsed" data-cat="' + caseId + '">' +
              '<div class="manual-cat-header" onclick="toggleManualCat(this)">' +
                '<span class="cat-title">' +
                  '<span class="cat-arrow">▼</span>' +
                  '<span class="badge badge-info">' + (vendorNames[c.vendor] || c.vendor) + "</span>" +
                  '<span>' + escapeHtml(c.title || "未命名案例") + "</span>" +
                '</span>' +
              '</div>' +
              '<div class="manual-cat-body">' +
                (c.description ? '<div class="cmd-desc" style="margin-bottom:8px;">' + escapeHtml(c.description) + "</div>" : "") +
                '<pre class="case-config">' + escapeHtml((c.steps || []).join("\n")) + "</pre>" +
              "</div>" +
            "</div>"
          );
        })
        .join("");
    } catch (e) {
      el.innerHTML = '<div class="empty-state">案例加载失败: ' + escapeHtml(e.message) + "</div>";
    }
  }

  // 切换分类面板展开/折叠
  window.toggleManualCat = function (header) {
    const panel = header.closest(".manual-category");
    panel.classList.toggle("collapsed");
  };

  /* ============================================================
     配置模板
     ============================================================ */
  async function loadTemplates() {
    try {
      const r = await API.get("/api/templates");
      const list = r.templates || [];
      const el = document.getElementById("template-list");
      if (!list.length) {
        el.innerHTML = '<div class="empty-state">暂无模板</div>';
        return;
      }
      el.innerHTML = list
        .map((t) =>
          '<div class="template-item" onclick="App.viewTemplate(\'' + (t.id || t.name) + "','" + escapeHtml(t.name || t.id) + "')\">" +
            "<strong>" + escapeHtml(t.name || t.id) + "</strong>" +
            "<small>" + escapeHtml(t.description || "") + " · " + (t.vendor || "通用") + "</small>" +
          "</div>"
        )
        .join("");
    } catch (e) {
      toast("加载模板失败: " + e.message, "error");
    }
  }

  async function viewTemplate(id, name) {
    document.querySelectorAll(".template-item").forEach((x) => x.classList.remove("active"));
    try {
      const r = await API.get("/api/templates/" + id + "/config");
      const el = document.getElementById("template-detail");
      if (r.success) {
        el.textContent = JSON.stringify(r.config, null, 2);
        el._config = r.config;
        toast("已加载模板: " + name, "success");
      } else {
        el.textContent = r.error || "加载失败";
      }
    } catch (e) {
      toast("加载失败: " + e.message, "error");
    }
  }

  function templateToConfig() {
    const el = document.getElementById("template-detail");
    if (!el._config) { toast("请先选择模板", "error"); return; }
    fillFormFromConfig(el._config);
    switchPage("config");
    toast("已载入到配置生成器", "success");
  }

  /* ============================================================
     初始化
     ============================================================ */
  function init() {
    // 深链接: 支持 /?page=topology 直达指定页面
    const wanted = new URLSearchParams(location.search).get("page");
    if (wanted && document.getElementById("page-" + wanted)) {
      switchPage(wanted);
    }

    // 导航
    document.querySelectorAll(".nav-item[data-page]").forEach((n) => {
      n.addEventListener("click", (e) => {
        e.preventDefault();
        switchPage(n.dataset.page);
      });
    });
    document.querySelectorAll(".quick-link[data-page]").forEach((n) => {
      n.addEventListener("click", (e) => {
        e.preventDefault();
        switchPage(n.dataset.page);
      });
    });

    // 配置生成器 Tab
    document.querySelectorAll('[data-cfg-tab]').forEach((t) => {
      t.addEventListener('click', () => switchCfgTab(t.dataset.cfgTab));
    });

    // 配置生成器 — 初始化为空白表单
    resetConfigForm();
    document.getElementById("btn-load-template").addEventListener("click", () => {
      loadExample(document.getElementById("config-vendor-quick").value);
    });
    document.getElementById("config-vendor-quick").addEventListener("change", (e) => loadExample(e.target.value));
    document.getElementById("btn-generate").addEventListener("click", generateConfig);
    document.getElementById("btn-validate").addEventListener("click", validateConfig);
    document.getElementById("btn-export").addEventListener("click", exportConfig);
    document.getElementById("btn-copy-config").addEventListener("click", () => {
      const t = document.getElementById("config-output").textContent;
      navigator.clipboard.writeText(t).then(() => toast("已复制", "success"));
    });

    // 设备管理
    document.getElementById("btn-add-device").addEventListener("click", () => openDeviceModal(null));
    document.getElementById("btn-test-all").addEventListener("click", testAllDevices);
    document.getElementById("btn-refresh-devices").addEventListener("click", loadDevices);
    document.getElementById("btn-save-device").addEventListener("click", saveDevice);
    document.getElementById("btn-cancel-device").addEventListener("click", closeDeviceModal);
    document.getElementById("btn-close-modal").addEventListener("click", closeDeviceModal);

    // 连接方式切换 — 自动改端口
    document.getElementById("dev-conn-type").addEventListener("change", (e) => {
      const portEl = document.getElementById("dev-port");
      const currentPort = parseInt(portEl.value) || 0;
      if (e.target.value === "telnet" && currentPort === 22) portEl.value = 23;
      if (e.target.value === "ssh" && currentPort === 23) portEl.value = 22;
    });

    // 推送
    document.getElementById("btn-close-push-modal").addEventListener("click", closePushModal);
    document.getElementById("btn-push-exec").addEventListener("click", execPush);

    // 配置备份
    document.getElementById("btn-backup-now").addEventListener("click", execBackup);
    document.getElementById("btn-refresh-backups").addEventListener("click", loadBackups);
    document.getElementById("btn-close-backup").addEventListener("click", closeBackupPanel);
    document.getElementById("btn-close-backup-view").addEventListener("click", closeBackupView);
    document.getElementById("btn-backup-copy").addEventListener("click", copyBackup);
    document.getElementById("btn-backup-download").addEventListener("click", () => downloadBackup(window._backupViewConfigId));

    // 预览区推送
    const btnPushPreview = document.getElementById("btn-push-from-preview");
    const btnRefreshPush = document.getElementById("btn-refresh-push-devices");
    if (btnPushPreview) btnPushPreview.addEventListener("click", pushFromPreview);
    if (btnRefreshPush) btnRefreshPush.addEventListener("click", loadPushDeviceList);

    // 工具标签
    document.querySelectorAll("#tool-tabs .tab").forEach((t) => {
      t.addEventListener("click", () => switchTool(t.dataset.tool));
    });

    // 子网
    document.getElementById("btn-subnet-calc").addEventListener("click", () => {
      runTool("/api/tools/subnet/calculate", {
        ip: val("subnet-ip"), mask: val("subnet-mask"),
      }, "subnet-output", "计算中");
    });
    document.getElementById("btn-subnet-divide").addEventListener("click", () => {
      runTool("/api/tools/subnet/divide", {
        ip: val("divide-ip"), prefix: +val("divide-prefix"), new_prefix: +val("divide-new"),
      }, "divide-output", "划分中");
    });

    // Ping
    document.getElementById("btn-ping").addEventListener("click", () => {
      runTool("/api/tools/ping", {
        host: val("ping-host"), count: +val("ping-count"), timeout: +val("ping-timeout"),
      }, "ping-output", "Ping 中");
    });
    document.getElementById("btn-ping-scan").addEventListener("click", () => {
      runTool("/api/tools/ping/scan", {
        network: val("scan-net"), timeout: +val("scan-timeout"),
      }, "scan-output", "扫描中");
    });

    // 端口
    document.getElementById("btn-port-scan").addEventListener("click", () => {
      runTool("/api/tools/port-scan/range", {
        host: val("port-host"), start: +val("port-start"), end: +val("port-end"),
      }, "port-output", "扫描中");
    });
    document.getElementById("btn-port-test").addEventListener("click", () => {
      runTool("/api/tools/port-test", {
        host: val("ptest-host"), port: +val("ptest-port"),
      }, "ptest-output", "测试中");
    });

    // 路由跟踪
    document.getElementById("btn-trace").addEventListener("click", () => {
      runTool("/api/tools/traceroute", {
        host: val("trace-host"), max_hops: +val("trace-hops"),
      }, "trace-output", "跟踪中");
    });

    // DNS
    document.getElementById("btn-dns").addEventListener("click", () => {
      runTool("/api/tools/dns/" + encodeURIComponent(val("dns-domain")) + "?record_type=" + encodeURIComponent(val("dns-type")), null, "dns-output", "查询中");
    });
    document.getElementById("btn-rdns").addEventListener("click", () => {
      runTool("/api/tools/reverse-dns/" + encodeURIComponent(val("rdns-ip")), null, "rdns-output", "查询中");
    });
    document.getElementById("btn-whois").addEventListener("click", () => {
      runTool("/api/tools/whois/" + encodeURIComponent(val("whois-domain")), null, "whois-output", "查询中");
    });

    // 网络信息
    document.getElementById("btn-local-ip").addEventListener("click", () => {
      runTool("/api/tools/network-info/local", null, "localip-output", "获取中");
    });
    document.getElementById("btn-public-ip").addEventListener("click", () => {
      runTool("/api/tools/network-info/public-ip", null, "publicip-output", "获取中");
    });

    // 配置对比
    document.getElementById("btn-compare").addEventListener("click", () => {
      runTool("/api/tools/config-compare", {
        config1: val("cmp-1"), config2: val("cmp-2"), context: +val("cmp-ctx"),
      }, "compare-output", "对比中");
    });

    // 命令转换
    document.getElementById("btn-convert").addEventListener("click", () => {
      runTool("/api/tools/config-convert", {
        config: val("conv-input"),
        from_vendor: val("conv-from"),
        to_vendor: val("conv-to"),
      }, "convert-output", "转换中");
    });

    // 手册
    document.getElementById("btn-manual-search").addEventListener("click", searchManual);
    document.getElementById("manual-search").addEventListener("keypress", (e) => {
      if (e.key === "Enter") searchManual();
    });
    document.getElementById("manual-vendor").addEventListener("change", () => {
      searchManual();
      loadManualCases();
    });

    // 模板
    document.getElementById("btn-template-to-config").addEventListener("click", templateToConfig);

    // 笔记
    document.getElementById("btn-note-new").addEventListener("click", () => openNoteEditor(null));
    document.getElementById("btn-note-search").addEventListener("click", () => {
      const kw = document.getElementById("note-search").value.trim();
      if (!kw) { toast("请输入搜索关键词", "error"); return; }
      loadNotes(kw);
    });
    document.getElementById("note-search").addEventListener("keypress", (e) => {
      if (e.key === "Enter") document.getElementById("btn-note-search").click();
    });
    document.getElementById("btn-note-clear").addEventListener("click", () => {
      document.getElementById("note-search").value = "";
      loadNotes(null);
    });
    document.getElementById("btn-save-note").addEventListener("click", saveNote);
    document.getElementById("btn-cancel-note").addEventListener("click", () => {
      document.getElementById("note-edit-modal").classList.remove("show");
    });
    document.getElementById("btn-close-note-edit").addEventListener("click", () => {
      document.getElementById("note-edit-modal").classList.remove("show");
    });
    document.getElementById("btn-close-note-view").addEventListener("click", () => {
      document.getElementById("note-view-modal").classList.remove("show");
    });
    document.getElementById("btn-note-view-edit").addEventListener("click", () => {
      document.getElementById("note-view-modal").classList.remove("show");
      openNoteEditor(viewingNoteId);
    });

    // 批量备份 / 文件服务
    document.getElementById("btn-backup-all").addEventListener("click", backupAllDevices);
    document.getElementById("btn-close-batch-backup").addEventListener("click", closeBatchBackupPanel);
    document.getElementById("btn-tftp-start").addEventListener("click", () => toggleFileServer("tftp", true));
    document.getElementById("btn-tftp-stop").addEventListener("click", () => toggleFileServer("tftp", false));
    document.getElementById("btn-ftp-start").addEventListener("click", () => toggleFileServer("ftp", true));
    document.getElementById("btn-ftp-stop").addEventListener("click", () => toggleFileServer("ftp", false));

    // 弹窗背景关闭
    document.querySelectorAll(".modal").forEach((m) => {
      m.addEventListener("click", (e) => { if (e.target === m) m.classList.remove("show"); });
    });

    loadDashboard();
  }

  function val(id) { return document.getElementById(id).value; }

  /* ============================================================
     笔记
     ============================================================ */
  let notesCache = [];
  let editingNoteId = null;
  let viewingNoteId = null;

  function fmtTime(iso) {
    if (!iso) return "-";
    return iso.replace("T", " ").slice(0, 19);
  }

  async function loadNotes(keyword) {
    try {
      const url = "/api/notes" + (keyword ? "?keyword=" + encodeURIComponent(keyword) : "");
      const data = await API.get(url);
      notesCache = data.notes || [];
      const clearBtn = document.getElementById("btn-note-clear");
      clearBtn.style.display = keyword ? "" : "none";
      document.getElementById("note-count").textContent =
        (keyword ? "搜索到 " : "共 ") + notesCache.length + " 条笔记";
      const list = document.getElementById("note-list");
      if (!notesCache.length) {
        list.innerHTML = '<div class="note-empty">' +
          (keyword ? "没有匹配的笔记" : "暂无笔记，点击右上角「新建笔记」开始记录") + "</div>";
        return;
      }
      list.innerHTML = notesCache.map((n) => {
        const preview = (n.content || "").replace(/\s+/g, " ").trim().slice(0, 120);
        return '<div class="note-card" data-id="' + n.id + '">' +
          '<div class="note-card-head">' +
            '<div class="note-card-title" onclick="App.viewNote(\'' + n.id + '\')">' + escapeHtml(n.title) + "</div>" +
            '<div class="note-card-actions">' +
              '<button class="btn btn-sm btn-ghost" onclick="App.editNote(\'' + n.id + '\')">编辑</button>' +
              '<button class="btn btn-sm btn-danger" onclick="App.deleteNote(\'' + n.id + '\')">删除</button>' +
            "</div>" +
          "</div>" +
          (preview ? '<div class="note-card-preview" onclick="App.viewNote(\'' + n.id + '\')">' + escapeHtml(preview) + (n.content && n.content.length > 120 ? "..." : "") + "</div>" : '<div class="note-card-preview note-card-empty-body">（无内容）</div>') +
          '<div class="note-card-meta">更新于 ' + fmtTime(n.updated_at) + "</div>" +
        "</div>";
      }).join("");
    } catch (e) {
      toast("加载笔记失败: " + e.message, "error");
    }
  }

  function openNoteEditor(noteId) {
    editingNoteId = noteId || null;
    const modal = document.getElementById("note-edit-modal");
    const input = document.getElementById("note-edit-input");
    const content = document.getElementById("note-edit-content");
    if (noteId) {
      const n = notesCache.find((x) => x.id === noteId);
      document.getElementById("note-edit-title").textContent = "编辑笔记";
      input.value = n ? n.title : "";
      content.value = n ? (n.content || "") : "";
    } else {
      document.getElementById("note-edit-title").textContent = "新建笔记";
      input.value = "";
      content.value = "";
    }
    modal.classList.add("show");
    setTimeout(() => input.focus(), 50);
  }

  async function saveNote() {
    const title = document.getElementById("note-edit-input").value.trim();
    const content = document.getElementById("note-edit-content").value;
    if (!title) { toast("请输入笔记标题", "error"); return; }
    try {
      if (editingNoteId) {
        await API.put("/api/notes/" + editingNoteId, { title, content });
        toast("笔记已更新");
      } else {
        await API.post("/api/notes", { title, content });
        toast("笔记已保存");
      }
      document.getElementById("note-edit-modal").classList.remove("show");
      loadNotes(document.getElementById("note-search").value.trim() || null);
    } catch (e) {
      toast("保存失败: " + e.message, "error");
    }
  }

  function viewNote(noteId) {
    const n = notesCache.find((x) => x.id === noteId);
    if (!n) return;
    viewingNoteId = noteId;
    document.getElementById("note-view-title").textContent = n.title;
    document.getElementById("note-view-content").textContent = n.content || "（无内容）";
    document.getElementById("note-view-created").textContent = "创建: " + fmtTime(n.created_at);
    document.getElementById("note-view-updated").textContent = "更新: " + fmtTime(n.updated_at);
    document.getElementById("note-view-modal").classList.add("show");
  }

  async function deleteNote(noteId) {
    const n = notesCache.find((x) => x.id === noteId);
    if (!n) return;
    if (!confirm('确定删除笔记「' + n.title + '」吗？删除后不可恢复。')) return;
    try {
      await API.del("/api/notes/" + noteId);
      toast("笔记已删除");
      loadNotes(document.getElementById("note-search").value.trim() || null);
    } catch (e) {
      toast("删除失败: " + e.message, "error");
    }
  }

  /* ---------- 暴露给 onclick ---------- */
  window.App = {
    testDevice, openPushModal, editDevice, deleteDevice, viewTemplate,
    backupDevice, execBackup, loadBackups, viewBackup, deleteBackup, restoreBackupFile, downloadBackup, closeBackupPanel,
    addVlanRow, addIfVlanRow, addVlanifRow, addVoiceVlanRow,
    addStaticRouteRow, addOspfNetRow, addBgpPeerRow,
    addAclRow, addAclRule,
    addPortSecRow, addStormRow, addRadiusRow,
    addEthTrunkRow, addRateLimitRow,
    switchCfgTab, generateConfig, validateConfig, exportConfig,
    pushFromPreview, loadPushDeviceList,
    viewNote, editNote: openNoteEditor, deleteNote,
    backupAllDevices,
    loadFileServerStatus,
    toast, escapeHtml,
  };

  document.addEventListener("DOMContentLoaded", init);
})();
