/* ============================================================
   拓扑图页面 — 表单式建网 + 静态 SVG 展示
   ------------------------------------------------------------
   交互模型（参考锐捷 WEB 网管）:
     · 新建设备 → 表单填写(厂家/类型/名称/端口数/管理IP) → 放置图形
     · 添加链路 → 选本端端口 + 对端端口 → 画线并点亮两端端口
     · 画布只做展示: 拖动设备调位置 / 滚轮缩放 / 空白处拖动平移
   性能设计:
     · 无实时连线交互 → 无路由计算、无命中吸附
     · 每台设备 = 1 个 data-URI 图标 + 2 行文字, 每条链路 = 1 条线 + 2 个端口点
     · 事件用根节点委托(仅 4 个监听器), 不随元素数量增长
   数据流不变: 节点属性(DeviceConfig) 直接存后端 topology_nodes.config
   ============================================================ */
(function () {
  "use strict";

  const API_BASE = "/api/topologies";
  const SVGNS = "http://www.w3.org/2000/svg";

  /* 厂商配色 — 与整体视觉保持一致 */
  const VENDOR_STYLE = {
    huawei: { fill: "#E6F1FB", stroke: "#185FA5", text: "#0C447C", short: "华为" },
    h3c: { fill: "#E1F5EE", stroke: "#0F6E56", text: "#085041", short: "H3C" },
    ruijie: { fill: "#FAEEDA", stroke: "#854F0B", text: "#633806", short: "锐捷" },
    maipu: { fill: "#EEEDFE", stroke: "#534AB7", text: "#3C3489", short: "迈普" },
  };

  /* 端口命名规则 — 与后端 topology_service.PORT_RULES 保持一致 */
  const PORT_RULE = {
    huawei: (i) => "GigabitEthernet0/0/" + i,
    h3c: (i) => "GigabitEthernet1/0/" + i,
    ruijie: (i) => "GigabitEthernet0/" + i,
    maipu: (i) => "GigabitEthernet0/" + i,
  };

  /* 设备类型元数据: label=图标左侧缩写 name=中文名 defaultPorts=新建设备默认端口数 */
  const TYPE_META = {
    switch: { label: "SW",  name: "交换机",   defaultPorts: 24 },
    router: { label: "R",   name: "路由器",   defaultPorts: 8 },
    ap:     { label: "AP",  name: "无线AP",   defaultPorts: 2 },
    ac:     { label: "AC",  name: "无线AC",   defaultPorts: 8 },
    wan:    { label: "Internet", name: "互联网", defaultPorts: 2 },
    pc:     { label: "PC",  name: "PC终端",   defaultPorts: 1 },
    ipc:    { label: "IPC", name: "摄像头",   defaultPorts: 1 },
    custom: { label: "自定义", name: "自定义设备", defaultPorts: 4 },
  };
  const TYPE_NAME = {
    switch: "交换机", router: "路由器", ap: "无线AP", ac: "无线AC",
    wan: "互联网", pc: "PC终端", ipc: "摄像头", custom: "自定义设备",
  };
  function typeLabelOf(node) {
    const t = (node.config || {}).device_type || "switch";
    if (t === "custom") {
      return String((node.config || {}).custom_label || "").trim() || "自定义";
    }
    return (TYPE_META[t] || TYPE_META.switch).label;
  }
  function typeNameOf(node) {
    const t = (node.config || {}).device_type || "switch";
    return TYPE_NAME[t] || "设备";
  }
  /* 终端/示意类设备: 不参与配置生成 */
  const TERMINAL_TYPES = { wan: 1, pc: 1, ipc: 1, custom: 1 };

  /* ---------- 状态 ---------- */
  let svg = null;
  let world = null;
  let gLinks = null;
  let gNodes = null;
  let vp = { x: 0, y: 0, k: 1 };           /* 视口: 平移 + 缩放 */
  let topoId = null;
  let topoList = [];
  let nodeMap = {};        // node_key -> 后端节点对象
  let linkMap = {};        // link_id  -> 后端链路对象
  let nodeEls = {};        // node_key -> {g}
  let linkEls = {};        // link_id  -> {g}
  let selectedNodeKey = null;
  let selectedLinkId = null;
  let genResults = {};
  let devices = [];
  let inited = false;
  let labelOffs = {};      // link_id -> { s:{x,y}, d:{x,y} } 端口标注拖拽偏移(按拓扑持久化)

  function loadLabelOffs() {
    try { return JSON.parse(localStorage.getItem("topo_label_offs") || "{}") || {}; } catch (e) { return {}; }
  }
  function saveLabelOffs() {
    try {
      const all = loadLabelOffs();
      all[topoId] = labelOffs;
      localStorage.setItem("topo_label_offs", JSON.stringify(all));
    } catch (e) { /* 存储不可用时忽略, 仅本次会话生效 */ }
  }

  /* ---------- 小工具 ---------- */
  function toast(msg, type) {
    if (window.App && typeof App.toast === "function") return App.toast(msg, type);
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast show " + (type || "");
  }

  function esc(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function val(id) {
    const el = document.getElementById(id);
    return el ? String(el.value || "").trim() : "";
  }

  function setVal(id, v) {
    const el = document.getElementById(id);
    if (el) el.value = v == null ? "" : v;
  }

  function status(msg) {
    const el = document.getElementById("topo-status");
    if (el) el.textContent = msg || "";
  }

  function splitList(s) {
    return String(s || "").split(/[,，\s]+/).map((x) => x.trim()).filter(Boolean);
  }

  /* ---------- 后端接口 ---------- */
  async function apiGet(url) {
    const r = await fetch(url);
    const t = await r.text();
    try { return JSON.parse(t); } catch (e) { return { success: false, message: t.slice(0, 200) }; }
  }

  async function apiSend(method, url, body) {
    const r = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const t = await r.text();
    try { return JSON.parse(t); } catch (e) { return { success: false, message: t.slice(0, 200), _status: r.status }; }
  }

  const apiPost = (url, body) => apiSend("POST", url, body);
  const apiPut = (url, body) => apiSend("PUT", url, body);
  const apiDel = (url) => apiSend("DELETE", url);

  /* ============================================================
     静态 SVG 画布
     ============================================================ */
  function ensureSvg() {
    if (svg) return true;
    const container = document.getElementById("topo-canvas");
    if (!container) return false;
    svg = document.createElementNS(SVGNS, "svg");
    svg.innerHTML =
      '<defs><pattern id="tp-grid" width="28" height="28" patternUnits="userSpaceOnUse">' +
      '<circle cx="1.5" cy="1.5" r="1.2" fill="#e2e6f0"/></pattern>' +
      '<filter id="tp-shadow" x="-30%" y="-30%" width="160%" height="160%">' +
      '<feDropShadow dx="0" dy="1.5" stdDeviation="1.6" flood-color="#64748b" flood-opacity="0.32"/></filter>' +
      "</defs>";
    world = document.createElementNS(SVGNS, "g");
    world.innerHTML =
      '<rect x="-20000" y="-20000" width="60000" height="60000" fill="url(#tp-grid)"/>' +
      '<g id="tp-links"></g><g id="tp-nodes"></g>';
    gLinks = world.querySelector("#tp-links");
    gNodes = world.querySelector("#tp-nodes");
    svg.appendChild(world);
    container.innerHTML = "";
    container.appendChild(svg);
    bindSvgEvents();
    return true;
  }

  function applyView() {
    if (world) {
      world.setAttribute("transform", "translate(" + vp.x + "," + vp.y + ") scale(" + vp.k + ")");
    }
  }

  function clientToWorld(cx, cy) {
    const rect = svg.getBoundingClientRect();
    return { x: (cx - rect.left - vp.x) / vp.k, y: (cy - rect.top - vp.y) / vp.k };
  }

  function fitView() {
    const entries = Object.values(dispMap);
    const container = document.getElementById("topo-canvas");
    if (!svg || !container) return;
    if (!entries.length) {
      if (!Object.keys(nodeMap).length) { vp = { x: 0, y: 0, k: 1 }; applyView(); return; }
      renderAll();
    }
    const list = Object.values(dispMap);
    if (!list.length) { vp = { x: 0, y: 0, k: 1 }; applyView(); return; }
    let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
    list.forEach((d) => {
      minx = Math.min(minx, d.x); miny = Math.min(miny, d.y - 12);
      maxx = Math.max(maxx, d.x + d.w); maxy = Math.max(maxy, d.y + d.h + 35);
    });
    const rect = container.getBoundingClientRect();
    const pad = 60;
    const bw = maxx - minx + pad * 2, bh = maxy - miny + pad * 2;
    const k = Math.min(1.2, Math.max(0.15, Math.min(rect.width / bw, rect.height / bh)));
    vp.k = k;
    vp.x = (rect.width - (maxx - minx) * k) / 2 - minx * k;
    vp.y = (rect.height - (maxy - miny) * k) / 2 - miny * k;
    applyView();
  }

  /* ---------- 几何: 基于显示节点(dispMap)的边界交点 ---------- */
  function centerOfDisp(d) { return { x: d.x + d.w / 2, y: d.y + d.h / 2 }; }

  function boundaryPoint(fromD, toD) {
    const c1 = centerOfDisp(fromD), c2 = centerOfDisp(toD);
    const dx = c2.x - c1.x, dy = c2.y - c1.y;
    let t = Infinity;
    if (dx > 0) t = Math.min(t, (fromD.x + fromD.w - c1.x) / dx);
    else if (dx < 0) t = Math.min(t, (fromD.x - c1.x) / dx);
    if (dy > 0) t = Math.min(t, (fromD.y + fromD.h - c1.y) / dy);
    else if (dy < 0) t = Math.min(t, (fromD.y - c1.y) / dy);
    if (!isFinite(t) || t < 0) t = 0;
    return { x: c1.x + dx * t, y: c1.y + dy * t };
  }

  /* 链路端点: 有对应端口方块时从端口中心出发(相对坐标, 随设备移动), 否则用节点边界 */
  function anchorPoint(d, port, otherD) {
    if (port && d.portPos) {
      const p = d.portPos[String(port).toLowerCase()];
      if (p) return { x: d.x + p.rx, y: d.y + p.ry };
    }
    return boundaryPoint(d, otherD);
  }

  /* 圆角折线: 途经 points, 拐角用二次贝塞尔圆滑 */
  function roundedPath(pts, r) {
    r = r || 8;
    let dStr = "M " + pts[0].x + " " + pts[0].y;
    for (let i = 1; i < pts.length - 1; i++) {
      const p = pts[i], prev = pts[i - 1], next = pts[i + 1];
      const l1 = Math.hypot(p.x - prev.x, p.y - prev.y) || 1;
      const l2 = Math.hypot(next.x - p.x, next.y - p.y) || 1;
      const rr = Math.min(r, l1 / 2, l2 / 2);
      const u1 = { x: (p.x - prev.x) / l1, y: (p.y - prev.y) / l1 };
      const u2 = { x: (next.x - p.x) / l2, y: (next.y - p.y) / l2 };
      const a = { x: p.x - u1.x * rr, y: p.y - u1.y * rr };
      const b = { x: p.x + u2.x * rr, y: p.y + u2.y * rr };
      dStr += " L " + a.x.toFixed(1) + " " + a.y.toFixed(1) +
        " Q " + p.x.toFixed(1) + " " + p.y.toFixed(1) + " " + b.x.toFixed(1) + " " + b.y.toFixed(1);
    }
    const last = pts[pts.length - 1];
    dStr += " L " + last.x + " " + last.y;
    return dStr;
  }

  /* ---------- 设备图标(仿网管平台立体风格, data-URI, 每台设备 1 个 image) ---------- */
  /* 图标绘制区 64x48: 浅灰机身 + 底部投影, 细节按类型 */
  function svgIcon(vendor, type) {
    const body = [];
    const box = (x, y, w, h, rx) =>
      '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="' + rx + '" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.4"/>' +
      '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + (h * 0.42) + '" rx="' + rx + '" fill="#ffffff"/>' +
      '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="' + rx + '" fill="none" stroke="#64748b" stroke-width="1.2"/>';
    if (type === "switch") {
      body.push(box(6, 14, 52, 22, 3));
      for (let i = 0; i < 8; i++)
        body.push('<rect x="' + (11 + i * 6) + '" y="26" width="4" height="6" rx="0.8" fill="' + (i % 3 === 2 ? "#f59e0b" : "#10b981") + '"/>');
      body.push('<circle cx="12" cy="20.5" r="1.6" fill="#10b981"/>');
      body.push('<rect x="20" y="19" width="14" height="3" rx="1.5" fill="#cbd5e1"/>');
    } else if (type === "router") {
      body.push(box(6, 14, 52, 22, 3));
      body.push('<circle cx="22" cy="25" r="8.5" fill="none" stroke="#64748b" stroke-width="1.6"/>');
      body.push('<path d="M18 23 h6 m-2.4 -2.4 L24.4 23 M26 27 h-6 m2.4 2.4 L19.6 27" stroke="#64748b" stroke-width="1.5" fill="none" stroke-linecap="round"/>');
      body.push('<circle cx="40" cy="21" r="1.6" fill="#10b981"/><circle cx="46" cy="21" r="1.6" fill="#f59e0b"/>');
      body.push('<rect x="36" y="27" width="14" height="4" rx="1" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="0.8"/>');
    } else if (type === "ac") {
      body.push(box(6, 10, 52, 26, 3));
      body.push('<rect x="12" y="16" width="8" height="5" rx="1" fill="#10b981"/>');
      body.push('<rect x="23" y="16" width="8" height="5" rx="1" fill="#cbd5e1"/>');
      body.push('<path d="M40 20 a5 5 0 0 1 8 0 M42 23 a3 3 0 0 1 4 0" stroke="#64748b" stroke-width="1.5" fill="none" stroke-linecap="round"/>');
      body.push('<rect x="10" y="27" width="44" height="4" rx="1" fill="#e2e8f0"/>');
    } else if (type === "wan") {
      body.push('<circle cx="32" cy="24" r="19" fill="#2f7de1" stroke="#1e5fb8" stroke-width="1.5"/>');
      body.push('<ellipse cx="32" cy="24" rx="9" ry="19" fill="none" stroke="#bcd7f7" stroke-width="1.4"/>');
      body.push('<path d="M13.5 18 h37 M13.5 30 h37" stroke="#bcd7f7" stroke-width="1.4" fill="none"/>');
      body.push('<circle cx="32" cy="24" r="19" fill="none" stroke="#1e5fb8" stroke-width="1.5"/>');
    } else if (type === "pc") {
      body.push('<rect x="16" y="8" width="32" height="22" rx="2.5" fill="#f8fafc" stroke="#64748b" stroke-width="1.4"/>');
      body.push('<rect x="19" y="11" width="26" height="16" rx="1" fill="#dbeafe"/>');
      body.push('<path d="M11 32 h42 l5 7 a2 2 0 0 1 -2 3 H8 a2 2 0 0 1 -2 -3 Z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.3"/>');
      body.push('<rect x="26" y="34.5" width="12" height="3" rx="1.5" fill="#cbd5e1"/>');
    } else if (type === "ipc") {
      body.push('<rect x="28" y="5" width="8" height="6" rx="1.5" fill="#94a3b8"/>');
      body.push('<path d="M18 18 a14 14 0 0 1 28 0 l-2 6 H20 Z" fill="#f8fafc" stroke="#64748b" stroke-width="1.4"/>');
      body.push('<circle cx="32" cy="19" r="6.5" fill="#334155"/>');
      body.push('<circle cx="30" cy="17" r="2" fill="#93c5fd"/>');
      body.push('<path d="M22 32 h20" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"/>');
      body.push('<path d="M48 12 q6 3 5 9" stroke="#94a3b8" stroke-width="1.4" fill="none" stroke-linecap="round"/>');
    } else if (type === "ap") {
      body.push('<rect x="12" y="12" width="40" height="26" rx="6" fill="#f8fafc" stroke="#64748b" stroke-width="1.4"/>');
      body.push('<circle cx="32" cy="25" r="6" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.2"/>');
      body.push('<circle cx="32" cy="25" r="2" fill="#64748b"/>');
      body.push('<path d="M20 20 a14 14 0 0 1 24 0 M24 24 a9 9 0 0 1 16 0" stroke="#94a3b8" stroke-width="1.3" fill="none" stroke-linecap="round"/>');
    } else { /* custom: 通用机箱 + 齿轮 */
      body.push(box(6, 12, 52, 26, 3));
      body.push('<circle cx="32" cy="25" r="7" fill="none" stroke="#64748b" stroke-width="1.6"/>');
      body.push('<circle cx="32" cy="25" r="2.4" fill="#64748b"/>');
      for (let i = 0; i < 8; i++) {
        const a = (Math.PI / 4) * i;
        body.push('<line x1="' + (32 + Math.cos(a) * 7).toFixed(1) + '" y1="' + (25 + Math.sin(a) * 7).toFixed(1) +
          '" x2="' + (32 + Math.cos(a) * 10).toFixed(1) + '" y2="' + (25 + Math.sin(a) * 10).toFixed(1) +
          '" stroke="#64748b" stroke-width="1.6"/>');
      }
    }
    const svgStr = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" viewBox="0 0 64 48">' + body.join("") + "</svg>";
    return "data:image/svg+xml;utf8," + encodeURIComponent(svgStr);
  }

  /* ---------- 节点尺寸/端口排布局(纯计算, 供绘制与几何共用) ---------- */
  const TYPE_LABEL_W = 40;   /* 类型标签区宽度(SW/R/AC...) */
  const NODE_ICON_W = 64;
  const PORT_STEP = 11;      /* 端口方块步距 */
  const PORT_MAX_LAMPS = 32; /* 最多画 32 个端口(2 行 x 16) */
  const CARD_TYPES = { switch: 1, router: 1, ac: 1, wan: 1 }; /* 卡片式: 白底卡+类型标签+端口排 */

  function nodeLayout(node) {
    const t = (node.config || {}).device_type || "switch";
    if (!CARD_TYPES[t]) {
      /* 图标式终端设备(AP/PC/IPC/自定义): 仅图标, 不画端口排 */
      return { w: NODE_ICON_W + 8, h: 52, ports: [], perRow: 0, rows: 0 };
    }
    const itfs = nodePorts(node);
    const count = Math.min(itfs.length, PORT_MAX_LAMPS);
    const perRow = count > 12 ? Math.ceil(count / 2) : count;
    const rows = count > 12 ? 2 : (count ? 1 : 0);
    const portsW = count ? perRow * PORT_STEP - (PORT_STEP - 8) + 4 : 0;
    return {
      w: TYPE_LABEL_W + 4 + portsW + 6,
      h: 52,
      ports: itfs.slice(0, PORT_MAX_LAMPS),
      perRow: Math.max(perRow, 1),
      rows: rows,
    };
  }

  /* 白底圆角卡片(带浅阴影) */
  function cardRect(w) {
    return '<rect class="tp-card" x="0" y="0" width="' + w + '" height="52" rx="7" fill="#ffffff" stroke="#dde3ea" stroke-width="1.2" filter="url(#tp-shadow)"/>';
  }

  /* 端口小盾牌(仿参考图中的端口灯) */
  function shieldPath(x, y) {
    return "M" + x + " " + (y + 3) + " L" + (x + 4) + " " + y + " L" + (x + 8) + " " + (y + 3) +
      " L" + (x + 8) + " " + (y + 11) + " L" + x + " " + (y + 11) + " Z";
  }

  /* ---------- 绘制: 节点(折叠按钮 + 类型标签 + 端口排/图标) ---------- */
  function drawDispNode(d) {
    const g = document.createElementNS(SVGNS, "g");
    if (d.real) {
      const node = d.node;
      const type = (node.config || {}).device_type || "switch";
      const isCard = !!CARD_TYPES[type];
      g.setAttribute("class", "tp-node");
      g.setAttribute("data-key", node.node_key);
      g.setAttribute("transform", "translate(" + d.x + "," + d.y + ")");
      let html = '<rect class="tp-halo" x="-4" y="-4" width="' + (d.w + 8) + '" height="' + (d.h + 8) + '" rx="9" fill="none" stroke="transparent" stroke-width="2"/>';
      if (isCard) {
        html += cardRect(d.w);
        const lbl = typeLabelOf(node);
        html += '<text class="tp-typelabel" x="8" y="33" font-size="' + (lbl.length > 3 ? 11 : 15) + '" font-weight="700" fill="#1f2937">' + esc(lbl) + "</text>";
        /* 右侧端口排(小盾牌) */
        const px0 = TYPE_LABEL_W + 4;
        d.ports.forEach((p, i) => {
          const row = d.perRow > 0 && i >= d.perRow ? 1 : 0;
          const col = row === 0 ? i : i - d.perRow;
          const lx = px0 + col * PORT_STEP;
          const ly = row === 0 ? 7 : 29;
          html += '<path class="tp-port" data-port="' + esc(p.toLowerCase()) + '" data-key="' + esc(node.node_key) +
            '" d="' + shieldPath(lx, ly) + '" fill="#49556a" stroke="#333f52" stroke-width="0.8" stroke-linejoin="round"/>';
          d.portPos[p.toLowerCase()] = { rx: lx + 4, ry: ly + 6 };
        });
        if ((nodePorts(node).length || 0) > PORT_MAX_LAMPS) {
          html += '<text class="tp-portmore" x="' + (d.w - 2) + '" y="24" font-size="9" fill="#94a3b8">+</text>';
        }
      } else {
        const href = svgIcon(node.config && node.config.vendor, type);
        html += '<image href="' + href + '" x="4" y="2" width="' + NODE_ICON_W + '" height="48"/>';
      }
      html +=
        '<text class="tp-name" x="' + (d.w / 2) + '" y="66" text-anchor="middle" font-size="12" font-weight="600" fill="#1f2937" stroke="#fbfcfe" stroke-width="3" paint-order="stroke">' + esc(node.name || node.node_key) + "</text>" +
        '<text class="tp-ip" x="' + (d.w / 2) + '" y="82" text-anchor="middle" font-size="10" fill="#94a3b8" stroke="#fbfcfe" stroke-width="3" paint-order="stroke">' + esc(node.mgmt_ip || "") + "</text>";
      g.innerHTML = html;
    } else {
      /* 下级设备折叠组节点(样式与真实设备一致): 点击任意处展开(折叠按钮画在连线上) */
      const t = d.gtype;
      const rep = d.members[0] || {};
      const isCard = !!CARD_TYPES[t];
      const meta = TYPE_META[t] || TYPE_META.custom;
      const lbl = t === "custom" ? (String((rep.config || {}).custom_label || "").trim() || "自定义") : meta.label;
      g.setAttribute("class", "tp-node tp-group");
      g.setAttribute("data-gkey", d.key);
      g.setAttribute("data-pfold", d.pfold);
      g.setAttribute("transform", "translate(" + d.x + "," + d.y + ")");
      let html = '<rect class="tp-halo" x="-4" y="-4" width="' + (d.w + 8) + '" height="' + (d.h + 8) + '" rx="9" fill="none" stroke="transparent" stroke-width="2"/>';
      if (isCard) {
        html += cardRect(d.w);
        html += '<text class="tp-typelabel" x="8" y="33" font-size="' + (lbl.length > 3 ? 11 : 15) + '" font-weight="700" fill="#1f2937">' + esc(lbl) + "</text>";
        /* 端口排(与真实设备一致, 灰色不可点亮) */
        const px0 = TYPE_LABEL_W + 4;
        d.ports.forEach((p, i) => {
          const row = d.perRow > 0 && i >= d.perRow ? 1 : 0;
          const col = row === 0 ? i : i - d.perRow;
          html += '<path class="tp-port" d="' + shieldPath(px0 + col * PORT_STEP, row === 0 ? 7 : 29) +
            '" fill="#49556a" stroke="#333f52" stroke-width="0.8" stroke-linejoin="round"/>';
        });
      } else {
        const href = svgIcon(rep.config && rep.config.vendor, t);
        html += '<image href="' + href + '" x="4" y="2" width="' + NODE_ICON_W + '" height="48"/>';
      }
      html += '<g class="tp-badge"><rect x="' + (d.w - 30) + '" y="-9" width="26" height="16" rx="8" fill="#10b981"/>' +
        '<text x="' + (d.w - 17) + '" y="3" text-anchor="middle" font-size="10" font-weight="700" fill="#ffffff">×' + d.members.length + "</text></g>" +
        '<text class="tp-name" x="' + (d.w / 2) + '" y="66" text-anchor="middle" font-size="12" font-weight="600" fill="#1f2937" stroke="#fbfcfe" stroke-width="3" paint-order="stroke">' + esc((meta.name || "设备") + " ×" + d.members.length) + "</text>";
      g.innerHTML = html;
    }
    gNodes.appendChild(g);
    nodeEls[d.key] = { g: g, d: d };
    return g;
  }

  function updateNodeVisual(node) {
    const wrap = nodeEls[node.node_key];
    /* 视觉重建最稳妥(端口排/标签都可能变化) */
    if (wrap && dispMap[node.node_key]) {
      renderAll();
      return;
    }
    drawNode(node);
  }

  /* 兼容旧调用: 画单台真实设备(当前视图中) */
  function drawNode(node) {
    if (!dispMap[node.node_key]) {
      const lay = nodeLayout(node);
      dispMap[node.node_key] = {
        key: node.node_key, real: true, node: node, type: (node.config || {}).device_type || "switch",
        x: node.x, y: node.y, w: lay.w, h: lay.h, ports: lay.ports, perRow: lay.perRow, rows: lay.rows, portPos: {},
      };
    }
    return drawDispNode(dispMap[node.node_key]);
  }

  function setNodeHalo(nodeKey, on) {
    if (!nodeKey) return;
    const d = dispOf(nodeKey);
    const wrap = d && nodeEls[d.key];
    if (wrap) {
      wrap.g.querySelector(".tp-halo").setAttribute("stroke", on ? "#2563eb" : "transparent");
      wrap.g.classList.toggle("sel", !!on);
    }
  }

  /* ---------- 折叠: 把某设备的下级设备"按类型"折叠成组 ---------- */
  let collapsedGroups = {}; // "parentKey|type" -> true (type=* 表示该上级的全部可折叠类型)
  let groupOffs = {};       // 组 visKey -> {dx,dy}: 手工拖动折叠组的偏移
  let badgeEls = {};        // 折叠按钮: "foldall:<pk>" / "expand:<visKey>" -> <g>
  let dispMap = {};         // visKey -> 显示节点(真实 or 下级类型组)
  let childHidden = {};     // childKey -> 组visKey(被折叠隐藏)

  const GROUP_ALL = "*";
  const foldKeyOf = (pk, t) => pk + "|" + t;
  const visKeyOf = (pk, t) => "pfold:" + pk + ":" + t;

  function loadFoldState() {
    try {
      const all = JSON.parse(localStorage.getItem("topo_fold_groups") || "{}") || {};
      collapsedGroups = all[topoId] || {};
    } catch (e) { collapsedGroups = {}; }
    /* 兼容早期"按上级整体折叠"的本地记录 */
    try {
      const oldAll = JSON.parse(localStorage.getItem("topo_fold_parents") || "{}") || {};
      const old = oldAll[topoId];
      if (old) Object.keys(old).forEach((pk) => { if (old[pk]) collapsedGroups[foldKeyOf(pk, GROUP_ALL)] = true; });
    } catch (e) { /* 忽略 */ }
  }
  function saveFoldState() {
    try {
      const all = JSON.parse(localStorage.getItem("topo_fold_groups") || "{}") || {};
      all[topoId] = collapsedGroups;
      localStorage.setItem("topo_fold_groups", JSON.stringify(all));
    } catch (e) { /* 忽略 */ }
  }
  function loadGroupPos() {
    try { return JSON.parse(localStorage.getItem("topo_group_pos") || "{}") || {}; }
    catch (e) { return {}; }
  }
  function saveGroupPos() {
    try {
      const all = loadGroupPos();
      all[topoId] = groupOffs;
      localStorage.setItem("topo_group_pos", JSON.stringify(all));
    } catch (e) { /* 忽略 */ }
  }

  /* 设备中心 y(布局高度固定 52) */
  const cyOf = (n) => n.y + 26;

  /* 某设备的"下级"设备: 通过链路相连且位于其下方 */
  function childrenOf(parentKey) {
    const p = nodeMap[parentKey];
    if (!p) return [];
    const out = [];
    Object.values(linkMap).forEach((l) => {
      [[l.src_node_key, l.dst_node_key], [l.dst_node_key, l.src_node_key]].forEach(([a, b]) => {
        if (a !== parentKey) return;
        const n = nodeMap[b];
        if (n && cyOf(n) > cyOf(p) + 10) out.push(b);
      });
    });
    return [...new Set(out)];
  }

  /* 下级设备按类型分组: {type: [nodeKey, ...]} */
  function childrenByType(parentKey) {
    const out = {};
    childrenOf(parentKey).forEach((k) => {
      const n = nodeMap[k];
      if (!n) return;
      const t = (n.config || {}).device_type || "switch";
      (out[t] = out[t] || []).push(k);
    });
    return out;
  }

  /* 可折叠的类型: 该上级同类型下级 >= 2 台(单个设备不需要折叠) */
  function foldableTypes(pk) {
    const byType = childrenByType(pk);
    return Object.keys(byType).filter((t) => byType[t].length >= 2);
  }

  /* 该上级当前被折叠的类型集合 */
  function collapsedTypesOf(pk) {
    const byType = childrenByType(pk);
    const out = new Set();
    if (collapsedGroups[foldKeyOf(pk, GROUP_ALL)]) {
      Object.keys(byType).forEach((t) => { if (byType[t].length >= 2) out.add(t); });
      return out;
    }
    Object.keys(byType).forEach((t) => { if (collapsedGroups[foldKeyOf(pk, t)]) out.add(t); });
    return out;
  }

  function clearFoldStateOf(pk) {
    Object.keys(collapsedGroups).forEach((k) => {
      if (k.split("|")[0] === pk) delete collapsedGroups[k];
    });
  }

  /* 折叠该上级的全部可折叠类型(单台下级不动) */
  function foldAllGroups(pk) {
    const ts = foldableTypes(pk);
    if (!ts.length) return;
    clearFoldStateOf(pk);
    ts.forEach((t) => { collapsedGroups[foldKeyOf(pk, t)] = true; });
    saveFoldState();
    if (selectedNodeKey && childHidden[selectedNodeKey]) selectNode(null);
    renderAll();
  }

  /* 主干线按钮: 一键折叠 / 一键展开(同一位置切换) */
  function toggleFoldAll(pk) {
    if (collapsedTypesOf(pk).size) expandAllGroups(pk);
    else foldAllGroups(pk);
  }

  /* 一键展开该上级的全部折叠组:
     本来就不重叠的组原样保留(不打扰手工布局);
     拥挤重叠的组统一铺成水平带——每组一条带、带内以组卡片为中心居中铺开,
     带与带从上到下依次排开, 并避开图内其他设备与已就位的组 */
  function expandAllGroups(pk) {
    const vis = Object.keys(dispMap).filter((k) => {
      const d = dispMap[k];
      return d && !d.real && d.pfold === pk && (d.members || []).length >= 2;
    });
    if (!vis.length) {
      clearFoldStateOf(pk);
      saveFoldState();
      renderAll();
      return;
    }
    const PAD = 12;
    const BAND_GAP = 40;   /* 重排时组带之间的垂直间距 */
    const staticObs = Object.values(dispMap)
      .filter((o) => vis.indexOf(o.key) < 0)
      .map((o) => ({ x: o.x, y: o.y, w: o.w, h: o.h + TEXT_H }));

    /* 各组的自然位置框(折叠前成员的位置) */
    const prep = vis.map((k) => {
      const gd = dispMap[k];
      const members = gd.members.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
      const lays = members.map((m) => nodeLayout(m));
      return { key: k, cx: gd.x + gd.w / 2,
        members: members, lays: lays,
        nat: members.map((m, i) => ({ x: m.x, y: m.y, w: lays[i].w, h: 52 })) };
    });
    const clash = (b, obs) => obs.some((o) =>
      b.x < o.x + o.w + PAD && b.x + b.w + PAD > o.x &&
      b.y < o.y + o.h + PAD && b.y + b.h + TEXT_H + PAD > o.y);
    const pairClash = (a, b) =>
      a.x < b.x + b.w + PAD && a.x + a.w + PAD > b.x &&
      a.y < b.y + b.h + PAD && a.y + a.h + PAD > b.y;

    /* 干净组(自然位置与设备、其他组、本组成员都不冲突)原样保留 */
    const dirty = [];
    const placed = [];
    prep.forEach((g) => {
      const others = prep.filter((o) => o !== g);
      const bad = g.nat.some((b) => clash(b, staticObs)) ||
        g.nat.some((a, i) => g.nat.some((b2, j) => j > i && pairClash(a, b2))) ||
        g.nat.some((a) => others.some((o) => o.nat.some((b2) => pairClash(a, b2))));
      if (bad) dirty.push(g);
      else g.nat.forEach((b) => placed.push(b));
    });

    /* 拥挤组从上到下铺成水平带, 起点取各组自然位置的最上沿 */
    const moved = [];
    dirty.sort((a, b) =>
      (Math.min(...a.nat.map((x) => x.y)) - Math.min(...b.nat.map((x) => x.y))));
    if (dirty.length) {
      let y0 = Math.min(...dirty.map((g) => Math.min(...g.nat.map((x) => x.y))));
      dirty.forEach((g) => {
        let touched = false;
        for (let pass = 0; pass < 24; pass++) {
          const boxes = memberBoxes(g.members, g.lays, 0, y0, g.cx);
          const bad = boxes.some((b) => clash(b, staticObs) || clash(b, placed));
          if (!bad || pass === 23) {
            g.members.forEach((m, i) => {
              const b = boxes[i];
              if (m.x !== b.x || m.y !== b.y) { m.x = b.x; m.y = b.y; moved.push(m); touched = true; }
            });
            boxes.forEach((b) => placed.push(b));
            if (touched) delete groupOffs[g.key];
            y0 = Math.max(...boxes.map((b) => b.y)) + 52 + BAND_GAP;
            break;
          }
          y0 = Math.round(y0 + 96 + PAD + 10);
        }
      });
    }

    clearFoldStateOf(pk);
    saveFoldState();
    saveGroupPos();
    if (selectedNodeKey && childHidden[selectedNodeKey]) selectNode(null);
    renderAll();
    persistMovedNodes(moved);
    if (vis.length) {
      status("已展开 " + vis.length + " 个设备组" + (moved.length ? "，自动重排 " + moved.length + " 台设备" : ""));
    }
  }

  /* 只展开指定的一个组, 同上级其他已折叠的组保持不变 */
  function expandGroup(visKey) {
    if (!visKey || visKey.indexOf("pfold:") !== 0) return;
    const rest = visKey.slice(6);
    const i = rest.lastIndexOf(":");
    if (i < 0) return;
    const pk = rest.slice(0, i), t = rest.slice(i + 1);
    const keep = collapsedTypesOf(pk);
    keep.delete(t);
    const moved = reflowGroupMembers(visKey);   /* 展开前先把成员落位算好, 避免展开后重叠 */
    clearFoldStateOf(pk);
    keep.forEach((x) => { collapsedGroups[foldKeyOf(pk, x)] = true; });
    saveFoldState();
    saveGroupPos();
    renderAll();
    persistMovedNodes(moved);
    if (moved.length) status("已展开设备组，自动重排 " + moved.length + " 台设备");
  }

  /* ---------- 展开时的自动重排(设备 / 端口连线标注都不重叠) ---------- */
  const GROUP_GAP = 26;        /* 展开后成员之间的水平间距 */
  const GROUP_ROW_MAX = 1180;  /* 单行最大宽度, 超出自动折行 */
  const TEXT_H = 36;           /* 名称/IP 文字占位(判重叠时一并计入) */

  /* 成员排布: 从 x0 起按各设备实际宽度铺开, 超宽折行;
     传入 centerX 时每行以该横坐标为中心居中铺开(展开组对齐到组卡片正下方) */
  function memberBoxes(members, lays, x0, y0, centerX) {
    const rows = [];
    let cur = [], curW = 0;
    lays.forEach((l, i) => {
      if (!cur.length) { cur = [i]; curW = l.w; return; }
      if (curW + GROUP_GAP + l.w > GROUP_ROW_MAX) { rows.push(cur); cur = [i]; curW = l.w; return; }
      cur.push(i); curW += GROUP_GAP + l.w;
    });
    if (cur.length) rows.push(cur);
    const boxes = [];
    rows.forEach((row, ri) => {
      const rowW = row.reduce((s, i) => s + lays[i].w, 0) + (row.length - 1) * GROUP_GAP;
      let x = (typeof centerX === "number")
        ? Math.max(20, Math.round(centerX - rowW / 2))
        : Math.round(x0);
      row.forEach((i) => {
        boxes[i] = { x: x, y: Math.round(y0) + ri * 96, w: lays[i].w, h: 52 };
        x += lays[i].w + GROUP_GAP;
      });
    });
    return boxes;
  }

  /* 把折叠组成员就地铺开(有重叠才重排, 布局本身没问题就不打扰用户):
     与图内其他设备逐轮避让, 保证展开后设备/文字不压在一起 */
  function reflowGroupMembers(gkey, extraObs) {
    const gd = dispMap[gkey];
    if (!gd || gd.real || !gd.pfold) return [];
    const members = (gd.members || []).slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
    if (members.length < 2) return [];
    const lays = members.map((m) => nodeLayout(m));
    const obstacles = Object.values(dispMap)
      .filter((o) => o.key !== gkey)
      .map((o) => ({ x: o.x, y: o.y, w: o.w, h: o.h + TEXT_H }))
      .concat(extraObs || []);
    const PAD = 12;
    const boxClash = (b) => obstacles.some((o) =>
      b.x < o.x + o.w + PAD && b.x + b.w + PAD > o.x &&
      b.y < o.y + o.h + PAD && b.y + b.h + TEXT_H + PAD > o.y);
    const pairClash = (a, b) =>
      a.x < b.x + b.w + PAD && a.x + a.w + PAD > b.x &&
      a.y < b.y + b.h + PAD && a.y + a.h + PAD > b.y;

    /* 先按原位置检查: 成员之间、成员与其他设备之间都没有重叠 → 保持原布局 */
    const nat = members.map((m, i) => ({ x: m.x, y: m.y, w: lays[i].w, h: 52 }));
    const dirty = nat.some(boxClash) ||
      nat.some((a, i) => nat.some((b, j) => j > i && pairClash(a, b)));
    if (!dirty) return [];

    const x0 = Math.min(...members.map((m) => m.x));
    let y0 = Math.min(...members.map((m) => m.y));
    for (let pass = 0; pass < 16; pass++) {
      const boxes = memberBoxes(members, lays, x0, y0);
      const hit = boxes.find(boxClash);
      if (!hit) {
        const moved = [];
        members.forEach((m, i) => {
          const b = boxes[i];
          if (m.x !== b.x || m.y !== b.y) { m.x = b.x; m.y = b.y; moved.push(m); }
        });
        if (moved.length) delete groupOffs[gkey];
        return moved;
      }
      y0 = Math.round(hit.y + hit.h + PAD + 10);
    }
    return [];
  }

  function persistMovedNodes(moved) {
    if (!topoId || !moved || !moved.length) return;
    moved.forEach((m) => { apiPut(API_BASE + "/" + topoId + "/nodes/" + m.id, { x: m.x, y: m.y }); });
  }

  function buildDispMap() {
    dispMap = {};
    childHidden = {};
    badgeEls = {};
    Object.values(nodeMap).forEach((n) => {
      const t = (n.config || {}).device_type || "switch";
      const lay = nodeLayout(n);
      dispMap[n.node_key] = {
        key: n.node_key, real: true, node: n, type: t,
        x: n.x, y: n.y, w: lay.w, h: lay.h, ports: lay.ports,
        perRow: lay.perRow, rows: lay.rows, portPos: {},
      };
    });
    const parents = new Set();
    Object.keys(collapsedGroups).forEach((k) => parents.add(k.split("|")[0]));
    parents.forEach((pk) => {
      if (!nodeMap[pk] || !dispMap[pk]) return; /* 上级不存在或已被上层折叠隐藏 */
      const ctypes = collapsedTypesOf(pk);
      if (!ctypes.size) return;
      const byType = childrenByType(pk);
      ctypes.forEach((t) => {
        const keys = (byType[t] || []).filter((k) => dispMap[k]);
        if (!keys.length) return;
        const members = keys.map((k) => dispMap[k].node);
        const gkey = visKeyOf(pk, t);
        const o = groupOffs[gkey] || { dx: 0, dy: 0 };
        keys.forEach((k) => { delete dispMap[k]; childHidden[k] = gkey; });
        const lay = nodeLayout(members[0]);
        const baseX = Math.round(members.reduce((s, m) => s + m.x, 0) / members.length);
        const baseY = Math.round(members.reduce((s, m) => s + m.y, 0) / members.length);
        dispMap[gkey] = {
          key: gkey, real: false, pfold: pk, gtype: t, members: members,
          baseX: baseX, baseY: baseY,
          x: baseX + (o.dx || 0), y: baseY + (o.dy || 0),
          w: lay.w, h: lay.h, ports: lay.ports,
          perRow: lay.perRow, rows: lay.rows, portPos: {},
        };
      });
    });
  }

  function dispOf(nodeKey) {
    if (childHidden[nodeKey]) return dispMap[childHidden[nodeKey]] || null;
    return dispMap[nodeKey] || null;
  }

  /* ---------- 绘制: 链路(绿色正交折线 + 端口标注; 点亮在设备端口排上) ---------- */
  function drawLink(link) {
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("class", "tp-link" + (link.link_type === "access" ? " tp-access" : ""));
    g.setAttribute("data-id", link.id);
    g.innerHTML =
      '<path class="tp-hit" fill="none" stroke="transparent" stroke-width="14"/>' +
      '<path class="tp-line" fill="none" stroke-width="1.8"/>' +
      '<text class="tp-pl" font-size="9" fill="#6b7280" text-anchor="middle" stroke="#fbfcfe" stroke-width="3" paint-order="stroke"></text>' +
      '<text class="tp-pl" font-size="9" fill="#6b7280" text-anchor="middle" stroke="#fbfcfe" stroke-width="3" paint-order="stroke"></text>';
    gLinks.appendChild(g);
    linkEls[link.id] = { g: g };
    updateLinkGeom(link.id);
    return g;
  }

  /* 同一对设备(不区分方向)之间的链路分组：返回本链路在组内的序号与组大小 */
  function linkGroupOf(link) {
    const key = [link.src_node_key, link.dst_node_key].sort().join("|");
    const group = Object.values(linkMap).filter(
      (l) => [l.src_node_key, l.dst_node_key].sort().join("|") === key
    );
    group.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
    return { idx: group.indexOf(link), count: group.length };
  }

  /* 总线 Y: 以上级设备 pd 为上端的所有下级链路共用一条水平总线 */
  function busYFor(svKey, pd) {
    const pbY = pd.y + pd.h;
    let minTop = Infinity;
    Object.values(linkMap).forEach((l) => {
      let other = null;
      const s = dispOf(l.src_node_key), d = dispOf(l.dst_node_key);
      if (!s || !d) return;
      if (s.key === svKey) other = d;
      else if (d.key === svKey) other = s;
      if (!other || other.key === svKey) return;
      if (centerOfDisp(other).y > centerOfDisp(pd).y + 10) minTop = Math.min(minTop, other.y);
    });
    return isFinite(minTop) ? (pbY + minTop) / 2 : pbY + 40;
  }

  /* 上方总线 Y: 以上级设备 pd 为下端的所有上方链路共用一条水平总线(镜像 busYFor) */
  function busYAboveFor(svKey, pd) {
    const pTop = pd.y;
    let maxBottom = -Infinity;
    Object.values(linkMap).forEach((l) => {
      let other = null;
      const s = dispOf(l.src_node_key), d = dispOf(l.dst_node_key);
      if (!s || !d) return;
      if (s.key === svKey) other = d;
      else if (d.key === svKey) other = s;
      if (!other || other.key === svKey) return;
      if (centerOfDisp(other).y < centerOfDisp(pd).y - 10) maxBottom = Math.max(maxBottom, other.y + other.h);
    });
    return isFinite(maxBottom) ? (pTop + maxBottom) / 2 : pTop - 40;
  }

  function updateLinkGeom(linkId) {
    const link = linkMap[linkId];
    const wrap = linkEls[linkId];
    if (!link || !wrap) return;
    const sv = dispOf(link.src_node_key), dv = dispOf(link.dst_node_key);
    if (!sv || !dv || sv.key === dv.key) { wrap.g.style.display = "none"; return; }
    wrap.g.style.display = "";
    const t1 = wrap.g.children[2], t2 = wrap.g.children[3];
    const o = labelOffs[linkId] || {};
    const os = o.s || { x: 0, y: 0 }, od = o.d || { x: 0, y: 0 };
    const sC = centerOfDisp(sv), dC = centerOfDisp(dv);
    const dyC = dC.y - sC.y;
    let pts, p1, p2;

    if (sv.pfold || dv.pfold) {
      /* 折叠链路: 上级 → 类型组, 走"主干线 + 水平总线 + 垂直落线"(与真实下级共用一条总线),
         同组的多条链路完全重叠, 看起来只有一根线; 不画端口标注 */
      if (sv.pfold && dv.pfold && sv.pfold === dv.pfold) {
        /* 同一折叠子树内部两组之间的链路: 隐藏 */
        wrap.g.style.display = "none";
        return;
      }
      const pd = sv.pfold ? dv : sv, gd = sv.pfold ? sv : dv;
      p1 = { x: pd.x + pd.w / 2, y: pd.y + pd.h };
      p2 = { x: gd.x + gd.w / 2, y: gd.y };
      if (p2.y > p1.y + 4) {
        /* 组在上级下方: 底部引出 → 共用总线 → 落到组顶 */
        const busY = busYFor(pd.key, pd);
        pts = [p1, { x: p1.x, y: busY }, { x: p2.x, y: busY }, p2];
      } else if (p2.y + gd.h < p1.y - 4) {
        /* 组在上级上方: 顶部引出 → 上方共用总线 → 落到组底(镜像, 保持正交风格一致) */
        const q1 = { x: pd.x + pd.w / 2, y: pd.y };
        const q2 = { x: gd.x + gd.w / 2, y: gd.y + gd.h };
        const busY = busYAboveFor(pd.key, pd);
        pts = [q1, { x: q1.x, y: busY }, { x: q2.x, y: busY }, q2];
      } else {
        pts = [p1, p2];
      }
      t1.textContent = ""; t2.textContent = "";
    } else if (dyC > 40) {
      /* src 是上级: 底部中心引出主干 → 共用总线 → 垂直落到 dst 顶部中心 */
      p1 = { x: sv.x + sv.w / 2, y: sv.y + sv.h };
      p2 = { x: dv.x + dv.w / 2, y: dv.y };
      const group = linkGroupOf(link);
      const busY = busYFor(sv.key, sv) + (group.count > 1 ? (group.idx - (group.count - 1) / 2) * 12 : 0);
      pts = [p1, { x: p1.x, y: busY }, { x: p2.x, y: busY }, p2];
      /* 端口标注沿落线段分布(仿参考图): src 靠总线, dst 靠设备, 同对多链路错开 */
      t1.setAttribute("text-anchor", "start");
      t1.setAttribute("x", p2.x + 5 + os.x);
      t1.setAttribute("y", busY + 13 + group.idx * 14 + os.y);
      t1.textContent = link.src_port || "";
      t2.setAttribute("text-anchor", "start");
      t2.setAttribute("x", p2.x + 5 + od.x);
      t2.setAttribute("y", p2.y - 8 - (group.count - 1 - group.idx) * 14 + od.y);
      t2.textContent = link.dst_port || "";
    } else if (dyC < -40) {
      /* dst 是上级: src 顶部 ← 总线 ← dst 底部 */
      p1 = { x: sv.x + sv.w / 2, y: sv.y };
      p2 = { x: dv.x + dv.w / 2, y: dv.y + dv.h };
      const group = linkGroupOf(link);
      const busY = busYFor(dv.key, dv) + (group.count > 1 ? (group.idx - (group.count - 1) / 2) * 12 : 0);
      pts = [p1, { x: p1.x, y: busY }, { x: p2.x, y: busY }, p2];
      t1.setAttribute("text-anchor", "start");
      t1.setAttribute("x", p1.x + 5 + os.x);
      t1.setAttribute("y", p1.y - 8 - (group.count - 1 - group.idx) * 14 + os.y);
      t1.textContent = link.src_port || "";
      t2.setAttribute("text-anchor", "start");
      t2.setAttribute("x", p2.x + 5 + od.x);
      t2.setAttribute("y", busY + 13 + group.idx * 14 + od.y);
      t2.textContent = link.dst_port || "";
    } else {
      /* 同层设备: 侧向正交折线 */
      p1 = anchorPoint(sv, link.src_port, dv);
      p2 = anchorPoint(dv, link.dst_port, sv);
      const group = linkGroupOf(link);
      const gOff = (group.idx - (group.count - 1) / 2) * 12;
      const dx = p2.x - p1.x, dy = p2.y - p1.y;
      if (Math.abs(dx) >= Math.abs(dy)) {
        const midX = (p1.x + p2.x) / 2 + gOff;
        pts = [p1, { x: midX, y: p1.y }, { x: midX, y: p2.y }, p2];
      } else {
        const midY = (p1.y + p2.y) / 2 + gOff;
        pts = [p1, { x: p1.x, y: midY }, { x: p2.x, y: midY }, p2];
      }
      t1.setAttribute("text-anchor", "middle");
      t2.setAttribute("text-anchor", "middle");
      t1.setAttribute("x", p1.x + (p2.x > p1.x ? 20 : -20) + os.x);
      t1.setAttribute("y", p1.y - 4 + os.y);
      t1.textContent = link.src_port || "";
      t2.setAttribute("x", p2.x + (p2.x > p1.x ? -20 : 20) + od.x);
      t2.setAttribute("y", p2.y - 4 + od.y);
      t2.textContent = link.dst_port || "";
    }
    const dStr = roundedPath(pts, 8);
    wrap.g.children[0].setAttribute("d", dStr);
    wrap.g.children[1].setAttribute("d", dStr);
    /* 记下"未错开"的基准 y: 端口标注防重叠时以此为准, 保证可反复计算 */
    [t1, t2].forEach((el) => {
      const yv = parseFloat(el.getAttribute("y"));
      el.__baseY = isNaN(yv) ? 0 : yv;
    });
  }

  /* 端口连线标注防重叠: 渲染后统一算一遍, 相互压住的向下错开(不改写用户的拖动偏移) */
  function resolveLabelOverlaps() {
    const items = [];
    Object.keys(linkEls).forEach((id) => {
      const wrap = linkEls[id];
      if (!wrap || wrap.g.style.display === "none") return;
      [2, 3].forEach((i) => {
        const el = wrap.g.children[i];
        if (!el || !el.textContent) return;
        let b = null;
        try { b = el.getBBox(); } catch (e) { return; }
        if (!b || !b.width || !b.height) return;
        items.push({ el: el, baseY: el.__baseY || 0, x: b.x, y: b.y, w: b.width, h: b.height });
      });
    });
    if (items.length < 2) return;
    items.sort((a, b) => a.y - b.y);
    const placed = [];
    items.forEach((it) => {
      let y = it.y;
      for (let pass = 0; pass < 24; pass++) {
        const hit = placed.find((p) =>
          y < p.y + p.h + 2 && y + it.h + 2 > p.y &&
          it.x < p.x + p.w + 4 && it.x + it.w + 4 > p.x);
        if (!hit) break;
        y = hit.y + hit.h + 3;
      }
      const dy = y - it.y;
      const ny = it.baseY + dy;
      if (Math.abs(parseFloat(it.el.getAttribute("y")) - ny) > 0.1) it.el.setAttribute("y", ny.toFixed(1));
      placed.push({ x: it.x, y: y, w: it.w, h: it.h });
    });
  }

  /* 端口点亮: 遍历链路, 点亮两端设备端口排中对应方块 */
  function refreshPortLamps() {
    Object.values(nodeEls).forEach((wrap) => {
      if (wrap.d && wrap.d.real) {
        wrap.g.querySelectorAll(".tp-port.lit").forEach((el) => el.classList.remove("lit"));
      }
    });
    Object.values(linkMap).forEach((l) => {
      [[l.src_node_key, l.src_port], [l.dst_node_key, l.dst_port]].forEach(([key, port]) => {
        if (!key || !port) return;
        const wrap = nodeEls[key];
        if (!wrap) return;
        const lamp = wrap.g.querySelector('.tp-port[data-port="' + CSS.escape(String(port).toLowerCase()) + '"]');
        if (lamp) {
          lamp.classList.add("lit");
          if (l.link_type === "access") lamp.classList.add("acc");
        }
      });
    });
  }

  function setLinkSel(linkId, on) {
    if (!linkId) return;
    const wrap = linkEls[linkId];
    if (wrap) wrap.g.classList.toggle("sel", !!on);
    if (on) applyLinkHighlight(linkId);
    else clearLinkHighlight();
  }

  /* ---------- 编辑链路时高亮两端端口标注 + 设备上对应端口灯 ---------- */
  const PL_SRC = 2, PL_DST = 3;   /* tp-link 子元素: 0=hit 1=line 2=源端口标注 3=目的端口标注 */
  let phActive = false;           /* 是否插入了"自动"占位文本(取消高亮时还原) */

  function linkLabelEl(wrap, end) {
    return wrap && wrap.g ? wrap.g.children[end === 1 ? PL_DST : PL_SRC] : null;
  }

  function portLampEl(nodeKey, port) {
    const nw = nodeEls[nodeKey];
    if (!nw || !port) return null;
    try {
      return nw.g.querySelector('.tp-port[data-port="' + CSS.escape(String(port).toLowerCase()) + '"]');
    } catch (e) { return null; }
  }

  /* 只摘掉高亮类, 不还原文本(内部用) */
  function stripHiClasses() {
    if (gNodes) gNodes.querySelectorAll(".tp-port.hi").forEach((el) => el.classList.remove("hi"));
    if (gLinks) gLinks.querySelectorAll(".tp-pl.hi").forEach((el) => el.classList.remove("hi", "ph"));
  }

  /* 还原"自动"占位文本: 直接按链路模型回填, 不用整图重算 */
  function clearPhPlaceholders() {
    if (!phActive) return;
    phActive = false;
    if (!gLinks) return;
    gLinks.querySelectorAll(".tp-pl.ph").forEach((el) => {
      const g = el.parentNode;
      const lk = g && g.getAttribute ? linkMap[g.getAttribute("data-id")] : null;
      el.textContent = lk ? ((el === g.children[PL_DST] ? lk.dst_port : lk.src_port) || "") : "";
    });
  }

  function clearLinkHighlight() {
    clearPhPlaceholders();   /* 先还原占位文本(依赖 .ph 类), 再摘高亮类 */
    stripHiClasses();
  }

  /* 高亮: 标注加粗变蓝(端口为空则显示"自动"占位) + 两端设备上对应端口灯描蓝圈 */
  function applyLinkHighlight(linkId) {
    clearPhPlaceholders();
    stripHiClasses();
    if (!gLinks) return;
    const link = linkId ? linkMap[linkId] : null;
    const wrap = linkId ? linkEls[linkId] : null;
    if (!link || !wrap || wrap.g.style.display === "none") return;
    [{ key: link.src_node_key, port: link.src_port }, { key: link.dst_node_key, port: link.dst_port }]
      .forEach((e, i) => {
        const el = linkLabelEl(wrap, i);
        if (el) {
          if (!String(el.textContent || "").trim()) {
            el.textContent = "自动";
            el.classList.add("ph");
            phActive = true;
          }
          el.classList.add("hi");
        }
        const lamp = portLampEl(e.key, e.port);
        if (lamp) lamp.classList.add("hi");
      });
    resolveLabelOverlaps();
  }

  /* 编辑表单实时预览: 输入端口时同步更新对应标注(仅预览, 失焦/保存后按模型重算) */
  function previewLinkLabel(end, value) {
    if (!selectedLinkId) return;
    const wrap = linkEls[selectedLinkId];
    if (!wrap || wrap.g.style.display === "none") return;
    const el = linkLabelEl(wrap, end);
    if (!el) return;
    const txt = String(value == null ? "" : value).trim();
    el.classList.add("hi");
    if (!txt) { el.textContent = "自动"; el.classList.add("ph"); phActive = true; }
    else { el.textContent = txt; el.classList.remove("ph"); }
    resolveLabelOverlaps();
  }

  function removeNodeEl(nodeKey) {
    const wrap = nodeEls[nodeKey];
    if (wrap) { wrap.g.remove(); delete nodeEls[nodeKey]; }
  }

  function removeLinkEl(linkId) {
    const wrap = linkEls[linkId];
    if (wrap) { wrap.g.remove(); delete linkEls[linkId]; }
  }

  function renderAll() {
    if (!world) return;
    buildDispMap();
    gLinks.innerHTML = "";
    gNodes.innerHTML = "";
    nodeEls = {};
    linkEls = {};
    Object.values(dispMap).forEach((d) => drawDispNode(d));
    Object.values(linkMap).forEach((l) => drawLink(l));
    refreshPortLamps();
    resolveLabelOverlaps();
    drawFoldBadges();
  }

  /* ---------- 连线上的折叠按钮 ---------- */
  function createFoldBadge(badgeKey, expand) {
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("class", "tp-fold tp-foldbadge");
    g.setAttribute("data-badge", badgeKey);
    g.setAttribute("data-state", expand ? "expand" : "fold");
    g.innerHTML = foldBadgeInner(expand);
    g.__expand = !!expand;
    gNodes.appendChild(g);
    return g;
  }

  /* 折叠按钮状态: expand=false 箭头朝下(可折叠) / true 箭头朝上(可展开) */
  function setFoldBadgeGlyph(g, expand) {
    expand = !!expand;
    if (g.__expand === expand) return;
    g.__expand = expand;
    g.setAttribute("data-state", expand ? "expand" : "fold");
    g.innerHTML = foldBadgeInner(expand);
  }
  function foldBadgeInner(expand) {
    const glyph = expand
      ? '<path d="M4.5 9.5 L8 6 L11.5 9.5" fill="none" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
      : '<path d="M4.5 6.5 L8 10 L11.5 6.5" fill="none" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>';
    return '<rect x="0" y="0" width="16" height="16" rx="5" fill="#10b981" stroke="#0d9488" stroke-width="1"/>' + glyph;
  }

  /* 稳定总线 Y: 只用真实节点坐标推算(不随折叠状态、折叠组拖动变化),
     让主干线上的折叠按钮位置固定 —— 折叠/展开来回切换时不用重新找按钮 */
  function stableBusYFor(pk, pd) {
    const pbY = pd.y + pd.h;
    const p = nodeMap[pk];
    if (!p) return pbY + 40;
    let minTop = Infinity;
    Object.values(linkMap).forEach((l) => {
      let other = null;
      if (l.src_node_key === pk) other = nodeMap[l.dst_node_key];
      else if (l.dst_node_key === pk) other = nodeMap[l.src_node_key];
      if (!other) return;
      if (cyOf(other) > cyOf(p) + 10) minTop = Math.min(minTop, other.y);
    });
    return isFinite(minTop) ? (pbY + minTop) / 2 : pbY + 40;
  }

  /* 按钮位置: foldall:<pk> 在上级主干线上(位置固定); expand:<visKey> 在该组落线上 */
  function foldBadgePos(badgeKey) {
    if (badgeKey.indexOf("foldall:") === 0) {
      const pd = dispMap[badgeKey.slice(8)];
      if (!pd) return null;
      const pbY = pd.y + pd.h;
      const busY = stableBusYFor(pd.key, pd);
      return { x: pd.x + pd.w / 2 - 8, y: pbY + Math.max(4, (busY - pbY) / 2 - 8) };
    }
    const gd = dispMap[badgeKey.slice(7)];
    if (!gd || gd.real || !gd.pfold) return null;
    const pd = dispMap[gd.pfold];
    if (!pd) return null;
    if (centerOfDisp(gd).y < centerOfDisp(pd).y) {
      /* 组在上级上方: 按钮放上方总线与组底之间 */
      const busY = busYAboveFor(pd.key, pd);
      return { x: gd.x + gd.w / 2 - 8, y: (busY + gd.y + gd.h) / 2 - 8 };
    }
    const busY = busYFor(pd.key, pd);
    return { x: gd.x + gd.w / 2 - 8, y: (busY + gd.y) / 2 - 8 };
  }

  /* 期望的按钮集合: foldall=有 >=2 台同类型下级的上级(单个设备不需要折叠)
     主干线按钮常驻(折叠后不消失、不换位置), 箭头方向随状态变化, 点击即切换折叠/展开 */
  function wantedFoldBadges() {
    const want = {};
    Object.values(nodeMap).forEach((n) => {
      const pk = n.node_key;
      if (!dispMap[pk]) return;                 /* 自身被上层折叠隐藏 */
      if (!foldableTypes(pk).length) return;    /* 无 >=2 台同类型下级: 不需要折叠按钮 */
      want["foldall:" + pk] = collapsedTypesOf(pk).size > 0;
    });
    Object.values(dispMap).forEach((gd) => {
      if (gd.real || !gd.pfold || !dispMap[gd.pfold]) return;
      want["expand:" + gd.key] = true;
    });
    return want;
  }

  function drawFoldBadges() {
    const want = wantedFoldBadges();
    Object.keys(badgeEls).forEach((k) => {
      if (!want[k]) { badgeEls[k].remove(); delete badgeEls[k]; }
    });
    Object.keys(want).forEach((k) => {
      const p = foldBadgePos(k);
      if (!p) {
        if (badgeEls[k]) { badgeEls[k].remove(); delete badgeEls[k]; }
        return;
      }
      if (!badgeEls[k]) badgeEls[k] = createFoldBadge(k, want[k]);
      setFoldBadgeGlyph(badgeEls[k], want[k]);
      badgeEls[k].setAttribute("transform", "translate(" + p.x + "," + p.y + ")");
    });
  }

  /* 拖动设备/折叠组时, 只更新已有按钮的位置(不重建 DOM) */
  function updateFoldBadgeGeom() {
    Object.keys(badgeEls).forEach((k) => {
      const p = foldBadgePos(k);
      if (p) badgeEls[k].setAttribute("transform", "translate(" + p.x + "," + p.y + ")");
    });
  }
  /* ---------- 画布交互(委托, 仅 4 个监听器) ---------- */
  let panState = null;
  let suppressClick = false;
  let multiSel = new Set();  // 框选的多选 node_key 集合

  function clearMulti() {
    if (!multiSel.size) return;
    multiSel.clear();
    refreshMultiHalo();
    updateAlignButtons();
  }

  function refreshMultiHalo() {
    Object.keys(nodeEls).forEach((k) => {
      const wrap = nodeEls[k];
      if (wrap && wrap.d && wrap.d.real) wrap.g.classList.toggle("mul", multiSel.has(k));
    });
  }

  function updateAlignButtons() {
    const on = multiSel.size >= 2;
    ["btn-topo-align-left", "btn-topo-align-right", "btn-topo-align-top", "btn-topo-align-bottom"].forEach((id) => {
      const b = document.getElementById(id);
      if (b) b.disabled = !on;
    });
  }

  /* 框选矩形(world 坐标, 画在 world 顶层) */
  function marqueeRectEl() {
    let el = document.getElementById("tp-marquee");
    if (!el) {
      el = document.createElementNS(SVGNS, "rect");
      el.setAttribute("id", "tp-marquee");
      el.setAttribute("class", "tp-marquee");
      world.appendChild(el);
    }
    return el;
  }

  /* 对齐: 框选的设备按方向对齐并持久化 */
  async function alignNodes(dir) {
    const keys = [...multiSel].filter((k) => dispMap[k] && dispMap[k].real);
    if (keys.length < 2) { toast("请先框选至少 2 台设备", "error"); return; }
    const ds = keys.map((k) => dispMap[k]);
    const nameOf = { left: "左对齐", right: "右对齐", top: "上对齐", bottom: "下对齐" };
    beginHistory("对齐 " + keys.length + " 台设备");
    let target;
    if (dir === "left") target = Math.min(...ds.map((d) => d.x));
    else if (dir === "right") target = Math.max(...ds.map((d) => d.x + d.w));
    else if (dir === "top") target = Math.min(...ds.map((d) => d.y));
    else target = Math.max(...ds.map((d) => d.y + d.h));
    keys.forEach((k) => {
      const d = dispMap[k], n = nodeMap[k];
      if (!d || !n) return;
      if (dir === "left") { d.x = target; n.x = target; }
      else if (dir === "right") { d.x = Math.round(target - d.w); n.x = d.x; }
      else if (dir === "top") { d.y = target; n.y = target; }
      else { d.y = Math.round(target - d.h); n.y = d.y; }
    });
    renderAll();
    refreshMultiHalo();
    if (topoId) {
      await Promise.all(keys.map((k) => {
        const n = nodeMap[k];
        return apiPut(API_BASE + "/" + topoId + "/nodes/" + n.id, { x: n.x, y: n.y });
      }));
    }
    toast("已" + (nameOf[dir] || "对齐") + " " + keys.length + " 台设备", "success");
    status("已" + (nameOf[dir] || "对齐") + " " + keys.length + " 台设备");
  }

  function bindSvgEvents() {
    svg.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      /* 端口标注拖拽 */
      const tg = e.target.closest(".tp-pl");
      if (tg) {
        const lg = tg.closest(".tp-link");
        if (lg) {
          const linkId = lg.getAttribute("data-id");
          if (linkMap[linkId]) {
            const isDst = tg === lg.children[3];
            const o = (labelOffs[linkId] = labelOffs[linkId] || {});
            const cur = o[isDst ? "d" : "s"] = o[isDst ? "d" : "s"] || { x: 0, y: 0 };
            panState = { mode: "label", linkId: linkId, end: isDst ? "d" : "s",
              sx: e.clientX, sy: e.clientY, bx: cur.x, by: cur.y, moved: false };
            e.preventDefault();
            return;
          }
        }
      }
      const ng = e.target.closest(".tp-node");
      if (ng) {
        /* 折叠组卡片: 可整体拖动 */
        const gk = ng.getAttribute("data-gkey");
        if (gk && dispMap[gk]) {
          const gd = dispMap[gk];
          panState = { mode: "group", gkey: gk, sx: e.clientX, sy: e.clientY, ox: gd.x, oy: gd.y, moved: false };
          ng.classList.add("dragging");
          e.preventDefault();
          return;
        }
        const key = ng.getAttribute("data-key");
        const n = nodeMap[key];
        if (!n) { e.preventDefault(); return; }
        /* 多选整体拖动: 起点按住的是选中集合中的设备 */
        let multi = null;
        if (multiSel.has(key) && multiSel.size > 1) {
          multi = {};
          multiSel.forEach((k) => { const m = nodeMap[k]; if (m) multi[k] = { x: m.x, y: m.y }; });
        }
        panState = { mode: "node", key: key, multi: multi, sx: e.clientX, sy: e.clientY, ox: n.x, oy: n.y, moved: false,
          snap: snapshotGraph() };   /* 拖动前抓快照, mouseup 时若真移动过才入撤销栈 */
        ng.classList.add("dragging");
      } else if (e.button === 1 || e.button === 2) {
        /* 右/中键拖拽 = 平移画布 */
        panState = { mode: "pan", sx: e.clientX, sy: e.clientY, ox: vp.x, oy: vp.y, moved: false };
        svg.classList.add("panning");
      } else {
        /* 空白左键拖拽 = 框选 */
        const w = clientToWorld(e.clientX, e.clientY);
        panState = { mode: "marquee", sx: e.clientX, sy: e.clientY, wx: w.x, wy: w.y, wx2: w.x, wy2: w.y, moved: false };
      }
      e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
      if (!panState) return;
      const dx = e.clientX - panState.sx, dy = e.clientY - panState.sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) panState.moved = true;
      if (panState.mode === "pan") {
        vp.x = panState.ox + dx;
        vp.y = panState.oy + dy;
        applyView();
      } else if (panState.mode === "marquee") {
        const w2 = clientToWorld(e.clientX, e.clientY);
        panState.wx2 = w2.x; panState.wy2 = w2.y;
        const el = marqueeRectEl();
        el.setAttribute("x", Math.min(panState.wx, w2.x));
        el.setAttribute("y", Math.min(panState.wy, w2.y));
        el.setAttribute("width", Math.abs(w2.x - panState.wx));
        el.setAttribute("height", Math.abs(w2.y - panState.wy));
        el.style.display = "";
      } else if (panState.mode === "label") {
        if (!linkMap[panState.linkId]) return;
        const o = labelOffs[panState.linkId];
        const cur = o && o[panState.end];
        if (!cur) return;
        cur.x = panState.bx + dx / vp.k;
        cur.y = panState.by + dy / vp.k;
        updateLinkGeom(panState.linkId);
      } else if (panState.mode === "group") {
        /* 拖动折叠组卡片 */
        const gd = dispMap[panState.gkey];
        if (!gd) return;
        gd.x = Math.round(panState.ox + dx / vp.k);
        gd.y = Math.round(panState.oy + dy / vp.k);
        const gwrap = nodeEls[panState.gkey];
        if (gwrap) gwrap.g.setAttribute("transform", "translate(" + gd.x + "," + gd.y + ")");
        Object.keys(linkMap).forEach((id) => {
          const l = linkMap[id];
          const s = dispOf(l.src_node_key), d = dispOf(l.dst_node_key);
          if ((s && s.key === panState.gkey) || (d && d.key === panState.gkey)) updateLinkGeom(id);
        });
        updateFoldBadgeGeom();
      } else {
        const dxw = dx / vp.k, dyw = dy / vp.k;
        if (panState.multi) {
          /* 多选整体拖动 */
          Object.keys(panState.multi).forEach((k) => {
            const n = nodeMap[k];
            if (!n) return;
            const o = panState.multi[k];
            n.x = Math.round(o.x + dxw);
            n.y = Math.round(o.y + dyw);
            const wrap = nodeEls[k];
            if (wrap && wrap.d) { wrap.d.x = n.x; wrap.d.y = n.y; }
            if (wrap) wrap.g.setAttribute("transform", "translate(" + n.x + "," + n.y + ")");
            Object.keys(linkMap).forEach((id) => {
              const l = linkMap[id];
              if (l.src_node_key === k || l.dst_node_key === k) updateLinkGeom(id);
            });
          });
          updateFoldBadgeGeom();
          return;
        }
        const n = nodeMap[panState.key];
        if (!n) return;
        n.x = Math.round(panState.ox + dxw);
        n.y = Math.round(panState.oy + dyw);
        const wrap = nodeEls[panState.key];
        if (wrap && wrap.d) { wrap.d.x = n.x; wrap.d.y = n.y; }
        if (wrap) wrap.g.setAttribute("transform", "translate(" + n.x + "," + n.y + ")");
        /* 只重算与该设备相连的链路 — 其余不动 */
        Object.keys(linkMap).forEach((id) => {
          const l = linkMap[id];
          if (l.src_node_key === panState.key || l.dst_node_key === panState.key) updateLinkGeom(id);
        });
        updateFoldBadgeGeom();
      }
    });

    window.addEventListener("mouseup", () => {
      if (!panState) return;
      const st = panState;
      panState = null;
      svg.classList.remove("panning");
      if (st.mode === "group") {
        const gwrap = nodeEls[st.gkey];
        if (gwrap) gwrap.g.classList.remove("dragging");
        if (st.moved && dispMap[st.gkey]) {
          /* 记录相对成员中心的偏移并持久化(折叠组位置是视图状态) */
          const gd = dispMap[st.gkey];
          groupOffs[st.gkey] = { dx: Math.round(gd.x - (gd.baseX || 0)), dy: Math.round(gd.y - (gd.baseY || 0)) };
          saveGroupPos();
        }
      }
      if (st.mode === "node") {
        const wrap = nodeEls[st.key];
        if (wrap) wrap.g.classList.remove("dragging");
        if (st.moved && topoId) {
          const n = nodeMap[st.key];
          if (n) apiPut(API_BASE + "/" + topoId + "/nodes/" + n.id, { x: n.x, y: n.y });
          const label = (st.multi && st.multi[st.key])
            ? "移动 " + Object.keys(st.multi).length + " 台设备"
            : "移动设备 " + ((n && n.name) || st.key);
          commitHistory(st.snap, label, st.key, null);
        }
      }
      if (st.mode === "label" && st.moved && topoId) saveLabelOffs();
      /* 拖动设备/标注会重算链路几何并回填标注文本, 重新贴一次编辑高亮 */
      if (selectedLinkId && (st.mode === "label" || st.mode === "node")) applyLinkHighlight(selectedLinkId);
      if (st.mode === "marquee") {
        const el = document.getElementById("tp-marquee");
        if (el) el.remove();
        if (st.moved) {
          const x1 = Math.min(st.wx, st.wx2), x2 = Math.max(st.wx, st.wx2);
          const y1 = Math.min(st.wy, st.wy2), y2 = Math.max(st.wy, st.wy2);
          selectNode(null);
          multiSel = new Set();
          Object.values(dispMap).forEach((d) => {
            if (!d.real) return;
            if (d.x < x2 && d.x + d.w > x1 && d.y < y2 && d.y + d.h > y1) multiSel.add(d.key);
          });
          refreshMultiHalo();
          updateAlignButtons();
          if (multiSel.size) {
            suppressClick = true;
            setTimeout(() => { suppressClick = false; }, 0);
            status("已框选 " + multiSel.size + " 台设备（整体拖动 / Delete 删除 / 对齐按钮）");
          }
        }
      }
      if (st.mode === "node" && st.multi && st.moved && topoId) {
        /* 多选整体拖动后批量持久化 */
        Object.keys(st.multi).forEach((k) => {
          const n = nodeMap[k];
          if (n) apiPut(API_BASE + "/" + topoId + "/nodes/" + n.id, { x: n.x, y: n.y });
        });
      }
      if (st.moved) {
        resolveLabelOverlaps();   /* 拖动结束后重排端口标注, 避免压在一起 */
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0);
      }
    });

    svg.addEventListener("click", (e) => {
      if (suppressClick) { suppressClick = false; return; }
      /* 连线上的折叠/展开按钮 */
      const fold = e.target.closest(".tp-fold");
      if (fold) {
        const bk = fold.getAttribute("data-badge") || "";
        if (bk.indexOf("foldall:") === 0) { toggleFoldAll(bk.slice(8)); return; }
        if (bk.indexOf("expand:") === 0) { expandGroup(bk.slice(7)); return; }
      }
      const ng = e.target.closest(".tp-node");
      if (ng) {
        /* 点击折叠组: 只展开该组, 同上级其他折叠组保持不变 */
        const gk = ng.getAttribute("data-gkey");
        if (gk) { expandGroup(gk); return; }
        const key = ng.getAttribute("data-key");
        if (!key) return;
        clearMulti();
        selectNode(key);
        return;
      }
      const lg = e.target.closest(".tp-link");
      if (lg) { clearMulti(); selectLink(lg.getAttribute("data-id")); return; }
      clearMulti();
      selectNode(null);
    });

    svg.addEventListener("contextmenu", (e) => e.preventDefault());

    svg.addEventListener("dblclick", (e) => {
      /* 双击端口标注: 复位到默认位置 */
      const tg = e.target.closest(".tp-pl");
      if (tg) {
        const lg = tg.closest(".tp-link");
        if (lg) {
          const linkId = lg.getAttribute("data-id");
          const o = labelOffs[linkId];
          if (o) {
            const isDst = tg === lg.children[3];
            delete o[isDst ? "d" : "s"];
            if (!o.s && !o.d) delete labelOffs[linkId];
            saveLabelOffs();
            updateLinkGeom(linkId);
          }
          e.preventDefault();
          return;
        }
      }
      const ng = e.target.closest(".tp-node");
      if (ng && !ng.isConnected) { e.preventDefault(); return; } /* 单击已展开并移除, 忽略 */
      if (ng) {
        /* 双击设备组: 只展开对应的设备组(单击已展开, 这里做兜底) */
        const gk = ng.getAttribute("data-gkey");
        if (gk) { expandGroup(gk); return; }
        selectNode(ng.getAttribute("data-key"));
      }
    });

    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const nk = Math.min(3, Math.max(0.15, vp.k * factor));
      const wx = (cx - vp.x) / vp.k, wy = (cy - vp.y) / vp.k;
      vp.x = cx - wx * nk;
      vp.y = cy - wy * nk;
      vp.k = nk;
      applyView();
    }, { passive: false });
  }

  /* 键盘: Delete 删除选中项 / Ctrl+Z 撤销 / Ctrl+Y(Ctrl+Shift+Z) 重做 */
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    const typing = !!(t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable));
    const mod = e.ctrlKey || e.metaKey;
    if (mod && (e.key === "z" || e.key === "Z")) {
      if (typing) return;                  /* 输入框里让系统原生撤销生效 */
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
      return;
    }
    if (mod && (e.key === "y" || e.key === "Y")) {
      if (typing) return;
      e.preventDefault();
      redo();
      return;
    }
    if (e.key !== "Delete" && e.key !== "Backspace") return;
    if (typing) return;
    if (multiSel.size > 1) { deleteMultiNodes(); return; }
    if (selectedLinkId) deleteLink(selectedLinkId);
    else if (selectedNodeKey) deleteNode(selectedNodeKey);
  });

  /* ============================================================
     端口工具
     ============================================================ */
  function nodePorts(node) {
    const itfs = ((node.config || {}).vlan || {}).interfaces || [];
    const seen = new Set();
    const out = [];
    itfs.forEach((i) => {
      const n = String((i && i.interface) || "").trim();
      const k = n.toLowerCase();
      if (!n || seen.has(k)) return;
      seen.add(k);
      out.push(n);
    });
    return out;
  }

  function usedPorts(nodeKey) {
    const used = new Set();
    Object.values(linkMap).forEach((l) => {
      if (l.src_node_key === nodeKey && l.src_port) used.add(l.src_port.toLowerCase());
      if (l.dst_node_key === nodeKey && l.dst_port) used.add(l.dst_port.toLowerCase());
    });
    return used;
  }

  /* ============================================================
     属性面板 — DeviceConfig ⇄ 表单
     ============================================================ */
  function selectNode(nodeKey) {
    setNodeHalo(selectedNodeKey, false);
    if (selectedLinkId) setLinkSel(selectedLinkId, false);
    selectedLinkId = null;
    selectedNodeKey = nodeKey || null;
    setNodeHalo(selectedNodeKey, true);
    const form = document.getElementById("topo-props-form");
    const linkForm = document.getElementById("topo-link-form");
    const empty = document.getElementById("topo-props-empty");
    const title = document.getElementById("topo-props-title");

    if (!nodeKey) {
      form.style.display = "none";
      linkForm.style.display = "none";
      empty.style.display = "block";
      title.textContent = "设备属性";
      renderPanel();
      return;
    }
    const node = nodeMap[nodeKey];
    if (!node) { renderPanel(); return; }
    linkForm.style.display = "none";
    empty.style.display = "none";
    form.style.display = "block";
    title.textContent = "设备属性 — " + (node.name || nodeKey);
    fillNodeForm(node);
    renderPanel();
  }

  function selectLink(linkId) {
    setNodeHalo(selectedNodeKey, false);
    if (selectedLinkId) setLinkSel(selectedLinkId, false);
    selectedNodeKey = null;
    selectedLinkId = linkId || null;
    setLinkSel(selectedLinkId, true);
    const form = document.getElementById("topo-props-form");
    const linkForm = document.getElementById("topo-link-form");
    const empty = document.getElementById("topo-props-empty");
    const title = document.getElementById("topo-props-title");

    if (!linkId) {
      linkForm.style.display = "none";
      empty.style.display = "block";
      title.textContent = "设备属性";
      renderPanel();
      return;
    }
    const link = linkMap[linkId];
    if (!link) { renderPanel(); return; }
    form.style.display = "none";
    empty.style.display = "none";
    linkForm.style.display = "block";
    title.textContent = "链路属性";
    const s = nodeMap[link.src_node_key], d = nodeMap[link.dst_node_key];
    document.getElementById("topo-l-path").textContent =
      (s ? s.name : link.src_node_key) + "  ←→  " + (d ? d.name : link.dst_node_key);
    setVal("topo-l-srcport", link.src_port || "");
    setVal("topo-l-dstport", link.dst_port || "");
    setVal("topo-l-type", link.link_type || "trunk");
    setVal("topo-l-desc", link.description || "");
    renderPanel();
  }

  function fmtVlans(vlans) {
    return (vlans || []).map((v) => v.id + (v.name ? "," + v.name : "")).join("\n");
  }

  function fmtItfs(itfs) {
    return (itfs || []).map((i) => {
      if ((i.type || "access") === "trunk") {
        return i.interface + ",trunk:" + (i.trunk_vlans || []).join(",");
      }
      return i.interface + ",access:" + (i.vlan_id == null ? "" : i.vlan_id);
    }).join("\n");
  }

  function fillNodeForm(node) {
    const cfg = node.config || {};
    const basic = cfg.basic || {};
    const mgmt = basic.mgmt_interface || {};
    const vlan = cfg.vlan || {};
    const dhcp = basic.dhcp_global || {};
    const ntp = basic.ntp || {};
    const snmp = basic.snmp || {};

    setVal("topo-f-name", node.name || "");
    setVal("topo-f-vendor", cfg.vendor || "huawei");
    setVal("topo-f-type", cfg.device_type || "switch");
    setVal("topo-f-clabel", cfg.custom_label || "");
    syncPropTypeUI();
    setVal("topo-f-hostname", cfg.hostname || "");

    setVal("topo-f-mgmt-ip", mgmt.ip_address || "");
    setVal("topo-f-mgmt-mask", mgmt.mask || "255.255.255.0");
    setVal("topo-f-mgmt-gw", mgmt.gateway || "");
    setVal("topo-f-mgmt-itf", mgmt.interface || "Vlanif1");

    const dev = devices.find((d) => d.id === node.device_id);
    setVal("topo-f-conn", dev ? (dev.connection_type || "telnet") : "telnet");
    setVal("topo-f-conn-port", dev ? (dev.port || 23) : 23);
    /* 设备列表接口不返回凭据, 这里留空表示"不修改"(避免误清空设备账号密码) */
    setVal("topo-f-user", "");
    setVal("topo-f-pass", "");

    setVal("topo-f-portcount", (vlan.interfaces || []).length || 24);
    setVal("topo-f-portstart", 1);
    setVal("topo-f-portvlan", ((vlan.vlans || [])[0] || {}).id || 1);
    setVal("topo-f-vlans", fmtVlans(vlan.vlans));
    setVal("topo-f-itfs", fmtItfs(vlan.interfaces));

    setVal("topo-f-dhcp", dhcp.enable ? "true" : "false");
    setVal("topo-f-dns", (dhcp.dns_servers || []).join(","));
    setVal("topo-f-ntp", ntp.enable ? "true" : "false");
    setVal("topo-f-ntp-server", ((ntp.servers || [])[0] || {}).ip || "");
    setVal("topo-f-snmp", snmp.enable ? "true" : "false");
    setVal("topo-f-snmp-ro", snmp.community_read || "public");

    setVal("topo-f-device", node.device_id || "");
  }

  function parseVlans(text) {
    const out = [];
    String(text || "").split(/\r?\n/).forEach((line) => {
      const s = line.trim();
      if (!s) return;
      const m = s.split(/[,，\s]+/);
      const id = parseInt(m[0], 10);
      if (!id || id < 1 || id > 4094) return;
      out.push({ id: id, name: m[1] || null });
    });
    return out;
  }

  function parseItfs(text) {
    const out = [];
    String(text || "").split(/\r?\n/).forEach((line) => {
      const s = line.trim();
      if (!s) return;
      const parts = s.split(/,|，/);
      const name = (parts[0] || "").trim();
      if (!name) return;
      const rest = parts.slice(1).join(",").trim();
      const m = rest.match(/^(access|trunk)\s*:\s*(.*)$/i);
      const type = m ? m[1].toLowerCase() : "access";
      const vlist = (m ? m[2] : rest).split(/[\s,，]+/).map((x) => parseInt(x, 10)).filter((x) => !isNaN(x));
      if (type === "trunk") {
        out.push({ interface: name, type: "trunk", trunk_vlans: vlist });
      } else {
        out.push({ interface: name, type: "access", vlan_id: vlist[0] == null ? null : vlist[0] });
      }
    });
    return out;
  }

  function collectConfig() {
    const node = nodeMap[selectedNodeKey] || {};
    const cfg = JSON.parse(JSON.stringify(node.config || {}));
    const vendor = val("topo-f-vendor") || "huawei";
    const dtype = val("topo-f-type") || "switch";

    cfg.vendor = vendor;
    cfg.device_type = dtype;
    if (dtype === "custom") {
      cfg.custom_label = val("topo-f-clabel").trim() || "自定义";
    } else {
      delete cfg.custom_label;
    }
    cfg.hostname = val("topo-f-hostname") || val("topo-f-name") || "";

    cfg.basic = cfg.basic || {};
    const mgmtItf = val("topo-f-mgmt-itf") || "Vlanif1";
    const mgmtIp = val("topo-f-mgmt-ip");
    cfg.basic.mgmt_interface = {
      enable: true,
      interface: mgmtItf,
      ip_address: mgmtIp,
      mask: val("topo-f-mgmt-mask") || "255.255.255.0",
      gateway: val("topo-f-mgmt-gw"),
      description: "Management Interface",
    };
    cfg.basic.dhcp_global = {
      enable: val("topo-f-dhcp") === "true",
      dns_servers: splitList(val("topo-f-dns")),
    };
    const ntpServer = val("topo-f-ntp-server");
    cfg.basic.ntp = {
      enable: val("topo-f-ntp") === "true",
      servers: ntpServer ? [{ ip: ntpServer, prefer: true }] : [],
      timezone: "UTC+8",
    };
    cfg.basic.snmp = {
      enable: val("topo-f-snmp") === "true",
      version: "v2c",
      community_read: val("topo-f-snmp-ro") || "public",
    };

    cfg.vlan = cfg.vlan || {};
    cfg.vlan.vlans = parseVlans(val("topo-f-vlans"));
    cfg.vlan.interfaces = parseItfs(val("topo-f-itfs"));

    /* 管理接口若是 VlanifN, 自动补一条三层接口(IP 才能下发) */
    const mm = mgmtItf.match(/^vlanif\s*(\d+)$/i);
    const vlanifs = [];
    if (mm && mgmtIp) {
      vlanifs.push({
        vlan_id: parseInt(mm[1], 10),
        ip_address: mgmtIp,
        mask: val("topo-f-mgmt-mask") || "255.255.255.0",
        description: "Management Interface",
      });
    }
    const vlanIds = new Set(cfg.vlan.vlans.map((v) => v.id));
    if (mm && !vlanIds.has(parseInt(mm[1], 10))) {
      cfg.vlan.vlans.push({ id: parseInt(mm[1], 10), name: "Mgmt" });
    }
    cfg.vlan.vlanifs = vlanifs.length ? vlanifs : (cfg.vlan.vlanifs || []);

    return cfg;
  }

  async function saveNode() {
    if (!topoId || !selectedNodeKey) { toast("请先选中一个节点", "error"); return; }
    const node = nodeMap[selectedNodeKey];
    if ((val("topo-f-type") || "switch") === "custom" && !val("topo-f-clabel").trim()) {
      toast("请输入自定义类型标签", "error"); return;
    }
    const cfg = collectConfig();
    const deviceId = val("topo-f-device");
    const payload = {
      name: val("topo-f-name") || node.name,
      config: cfg,
    };
    if (deviceId) payload.device_id = deviceId;
    else payload.clear_device = true;

    const before = snapNode(node);
    const h = beginHistory("修改设备属性 " + (payload.name || node.name));
    const r = await apiPut(API_BASE + "/" + topoId + "/nodes/" + node.id, payload);
    if (!r.success) { dropHistory(h); toast(r.message || "保存失败", "error"); return; }
    if (sameSnap(before, snapNode(r.node))) dropHistory(h);   /* 没改任何东西, 不占撤销步 */
    nodeMap[r.node.node_key] = r.node;
    updateNodeVisual(r.node);
    document.getElementById("topo-props-title").textContent = "设备属性 — " + r.node.name;
    await syncDeviceBinding(r.node);
    renderPanel();
    status("已保存属性: " + r.node.name);
    toast("属性已保存", "success");
  }

  /* 绑定设备时, 把变化的连接信息同步到设备管理表(保证备份/下发可用)
     安全约定: 只提交"确实变化"的字段; 用户名/密码留空表示不修改, 绝不回写空值 */
  async function syncDeviceBinding(node) {
    if (!node.device_id) return;
    const dev = devices.find((d) => d.id === node.device_id);
    if (!dev) return;
    const cfg = node.config || {};
    const payload = {};

    const wantHost = val("topo-f-mgmt-ip") || dev.host || "";
    if (wantHost && wantHost !== (dev.host || "")) payload.host = wantHost;

    const wantConn = val("topo-f-conn") || dev.connection_type || "telnet";
    if (wantConn !== (dev.connection_type || "")) payload.connection_type = wantConn;

    const wantPort = parseInt(val("topo-f-conn-port"), 10);
    if (wantPort && wantPort !== dev.port) payload.port = wantPort;

    const user = val("topo-f-user");
    if (user) payload.username = user;
    const pass = val("topo-f-pass");
    if (pass) payload.password = pass;

    if (cfg.vendor && cfg.vendor !== dev.vendor) payload.vendor = cfg.vendor;

    if (!Object.keys(payload).length) return;
    const r = await apiPut("/api/devices/" + node.device_id, payload);
    if (r && r.success) {
      Object.assign(dev, payload);
      if (payload.host) status("已同步管理地址到设备记录: " + payload.host);
    }
  }

  async function saveLink() {
    if (!topoId || !selectedLinkId) return;
    const before = snapLink(linkMap[selectedLinkId]);
    const h = beginHistory("修改链路属性");
    const r = await apiPut(API_BASE + "/" + topoId + "/links/" + selectedLinkId, {
      src_port: val("topo-l-srcport"),
      dst_port: val("topo-l-dstport"),
      link_type: val("topo-l-type") || "trunk",
      description: val("topo-l-desc"),
    });
    if (!r.success) { dropHistory(h); toast(r.message || "保存失败", "error"); return; }
    if (sameSnap(before, snapLink(r.link))) dropHistory(h);   /* 没改任何东西, 不占撤销步 */
    linkMap[r.link.id] = r.link;
    updateLinkGeom(r.link.id);
    refreshPortLamps();
    resolveLabelOverlaps();
    selectLink(r.link.id);
    toast("链路已保存", "success");
  }

  function genPortsForForm() {
    const vendor = val("topo-f-vendor") || "huawei";
    const rule = PORT_RULE[vendor] || PORT_RULE.huawei;
    const count = Math.min(96, Math.max(1, parseInt(val("topo-f-portcount"), 10) || 24));
    const start = Math.max(1, parseInt(val("topo-f-portstart"), 10) || 1);
    const vlan = Math.max(1, parseInt(val("topo-f-portvlan"), 10) || 1);
    const exist = parseItfs(val("topo-f-itfs"));
    const names = new Set(exist.map((i) => (i.interface || "").toLowerCase()));
    for (let i = start; i < start + count; i++) {
      const name = rule(i);
      if (names.has(name.toLowerCase())) continue;
      exist.push({ interface: name, type: "access", vlan_id: vlan });
    }
    setVal("topo-f-itfs", fmtItfs(exist));
    toast("已生成 " + count + " 个端口（access，加入 VLAN " + vlan + "）", "success");
  }

  /* ============================================================
     新建设备(表单式) / 添加链路(端口选择式)
     ============================================================ */
  /* ---------- 新建设备: 记住上次选择(厂家/类型/端口数/掩码/网关) ---------- */
  function loadDevPrefs() {
    try { return JSON.parse(localStorage.getItem("topo_adddev_prefs") || "{}") || {}; } catch (e) { return {}; }
  }
  function saveDevPrefs() {
    try {
      localStorage.setItem("topo_adddev_prefs", JSON.stringify({
        vendor: val("ta-vendor") || "huawei",
        type: val("ta-type") || "switch",
        clabel: val("ta-clabel").trim(),
        portcount: parseInt(val("ta-portcount"), 10) || null,
        mask: val("ta-mask") || "",
        gw: val("ta-gw") || "",
      }));
    } catch (e) { /* 忽略 */ }
  }

  function openAddDevModal() {
    if (!topoId) { toast("请先新建或选择一张拓扑图", "error"); return; }
    const p = loadDevPrefs();
    const dt = (p.type && TYPE_META[p.type]) ? p.type : "switch";
    setVal("ta-name", "");
    setVal("ta-vendor", p.vendor || "huawei");
    setVal("ta-type", dt);
    setVal("ta-clabel", p.clabel || "");
    setVal("ta-portcount", p.portcount || TYPE_META[dt].defaultPorts);
    setVal("ta-batch", 1);
    setVal("ta-ip", "");
    setVal("ta-mask", p.mask || "255.255.255.0");
    setVal("ta-gw", p.gw || "");
    syncAddDevTypeUI();
    document.getElementById("ta-name").focus();
    document.getElementById("topo-adddev-modal").classList.add("show");
  }

  function syncAddDevTypeUI() {
    const t = val("ta-type") || "switch";
    const row = document.getElementById("ta-clabel-row");
    if (row) row.style.display = t === "custom" ? "" : "none";
  }

  function syncPropTypeUI() {
    const t = val("topo-f-type") || "switch";
    const row = document.getElementById("topo-f-clabel-row");
    if (row) row.style.display = t === "custom" ? "" : "none";
  }

  /* 管理 IP 末段自动递增: 192.168.1.10 + 1 -> 192.168.1.11（溢出回到 .1） */
  function nextMgmtIp(ip, step) {
    if (!ip || step === 0) return ip;
    const m = /^(\d{1,3}(?:\.\d{1,3}){2}\.)(\d{1,3})$/.exec(ip);
    if (!m) return "";
    const last = (parseInt(m[2], 10) - 1 + step) % 254 + 1;
    return m[1] + last;
  }

  async function submitAddDevice() {
    if (!topoId) return;
    const vendor = val("ta-vendor") || "huawei";
    const dtype = val("ta-type") || "switch";
    const clabel = val("ta-clabel").trim();
    if (dtype === "custom" && !clabel) { toast("请输入自定义类型标签", "error"); return; }
    const meta = TYPE_META[dtype] || TYPE_META.switch;
    const count = Math.min(96, Math.max(1, parseInt(val("ta-portcount"), 10) || meta.defaultPorts));
    const batch = Math.min(24, Math.max(1, parseInt(val("ta-batch"), 10) || 1));
    const nameInput = val("ta-name").trim();
    const ip0 = val("ta-ip").trim();
    const mask = val("ta-mask") || "255.255.255.0";
    const gw = val("ta-gw");

    /* 组装 DeviceConfig 用的公共部分: 厂商端口命名规则 */
    const rule = PORT_RULE[vendor] || PORT_RULE.huawei;
    const itfs = [];
    for (let i = 1; i <= count; i++) {
      itfs.push({ interface: rule(i), type: "access", vlan_id: 1 });
    }

    const h = beginHistory(batch > 1 ? "批量新建 " + batch + " 台设备" : "新建设备");
    let created = 0, lastNode = null;
    for (let b = 0; b < batch; b++) {
      const n = Object.keys(nodeMap).length;
      /* 名称: 手填 + 批量时加序号; 留空则按 厂商缩写-类型-序号 自动命名 */
      const name = nameInput
        ? (batch > 1 ? nameInput + "-" + (b + 1) : nameInput)
        : (VENDOR_STYLE[vendor].short + "-" + (clabel || meta.name) + "-" + (n + 1));
      const ip = batch > 1 ? nextMgmtIp(ip0, b) : ip0;

      /* 位置: 网格找空位; 之后可拖动微调或自动布局 */
      const x = 80 + (n % 5) * 240;
      const y = 80 + Math.floor(n / 5) * 150;

      const cfg = {
        vendor: vendor,
        device_type: dtype,
        hostname: name,
        basic: {
          mgmt_interface: {
            enable: true,
            interface: "Vlanif1",
            ip_address: ip,
            mask: mask,
            gateway: gw,
            description: "Management Interface",
          },
        },
        vlan: {
          vlans: [{ id: 1, name: ip ? "Mgmt" : "Default" }],
          interfaces: itfs,
          vlanifs: ip ? [{ vlan_id: 1, ip_address: ip, mask: mask, description: "Management Interface" }] : [],
        },
      };
      if (dtype === "custom") cfg.custom_label = clabel;

      const r = await apiPost(API_BASE + "/" + topoId + "/nodes", {
        name: name,
        vendor: vendor,
        device_type: dtype,
        x: x,
        y: y,
        config: cfg,
      });
      if (!r.success) {
        if (created === 0) { dropHistory(h); toast(r.message || "添加失败", "error"); return; }
        toast("已创建 " + created + " 台，其余失败: " + (r.message || "未知错误"), "error");
        break;
      }
      nodeMap[r.node.node_key] = r.node;
      drawNode(r.node);
      lastNode = r.node;
      created++;
    }
    if (!created) { dropHistory(h); return; }

    saveDevPrefs();
    fitView();
    resolveLabelOverlaps();
    renderPanel();
    selectNode(lastNode.node_key);
    document.getElementById("topo-adddev-modal").classList.remove("show");
    status(created > 1
      ? "已批量添加 " + created + " 台设备（" + count + " 端口/台）"
      : "已添加设备: " + lastNode.name + "（" + count + " 端口）");
    toast(created > 1 ? "已批量添加 " + created + " 台设备" : "设备已添加", "success");
  }

  /* ---------- 添加链路: 记住上次选择的两端设备与链路类型 ---------- */
  function loadLinkPrefs() {
    try { return JSON.parse(localStorage.getItem("topo_addlink_prefs") || "{}") || {}; } catch (e) { return {}; }
  }
  function saveLinkPrefs(src, dst, type) {
    try {
      localStorage.setItem("topo_addlink_prefs", JSON.stringify({ src: src, dst: dst, type: type }));
    } catch (e) { /* 忽略 */ }
  }

  function openAddLinkModal() {
    if (!topoId) { toast("请先新建或选择一张拓扑图", "error"); return; }
    const keys = Object.keys(nodeMap);
    if (keys.length < 2) { toast("至少需要两台设备才能连线", "error"); return; }
    const opts = keys.map((k) =>
      '<option value="' + esc(k) + '">' + esc(nodeMap[k].name) + "</option>"
    ).join("");
    const s1 = document.getElementById("tal-src");
    const s2 = document.getElementById("tal-dst");
    s1.innerHTML = opts;
    s2.innerHTML = opts;
    /* 恢复上次选择: 两端设备仍存在才回填, 否则回落默认 */
    const p = loadLinkPrefs();
    s1.value = p.src && nodeMap[p.src] ? p.src : keys[0];
    s2.value = p.dst && nodeMap[p.dst] ? p.dst : (keys[1] || keys[0]);
    if (s1.value === s2.value && keys.length > 1) s2.value = keys.find((k) => k !== s1.value);
    setVal("tal-type", p.type === "access" ? "access" : "trunk");
    setVal("tal-desc", "");
    refreshPortSelect("tal-srcport", "tal-src");
    refreshPortSelect("tal-dstport", "tal-dst");
    /* 连续连线场景: 本端保持, 焦点直接落到对端设备选择框 */
    document.getElementById("tal-dst").focus();
    document.getElementById("topo-addlink-modal").classList.add("show");
  }

  function refreshPortSelect(portSelId, devSelId) {
    const key = val(devSelId);
    const node = nodeMap[key];
    const sel = document.getElementById(portSelId);
    if (!sel) return;
    const used = usedPorts(key);
    const ports = node ? nodePorts(node) : [];
    sel.innerHTML = '<option value="">自动分配</option>' + ports.map((p) => {
      const occ = used.has(p.toLowerCase());
      return '<option value="' + esc(p) + '"' + (occ ? " disabled" : "") + ">" +
        esc(p) + (occ ? "（已占用）" : "") + "</option>";
    }).join("");
  }

  async function submitAddLink() {
    if (!topoId) return;
    const src = val("tal-src"), dst = val("tal-dst");
    if (!src || !dst) { toast("请选择两端设备", "error"); return; }
    if (src === dst) { toast("两端不能是同一台设备", "error"); return; }
    const nm = (k) => (nodeMap[k] || {}).name || k;
    const h = beginHistory("添加链路 " + nm(src) + " ↔ " + nm(dst));
    const r = await apiPost(API_BASE + "/" + topoId + "/links", {
      src_node_key: src,
      dst_node_key: dst,
      src_port: val("tal-srcport") || null,
      dst_port: val("tal-dstport") || null,
      link_type: val("tal-type") || "trunk",
      description: val("tal-desc"),
    });
    if (!r.success) { dropHistory(h); toast(r.message || "创建链路失败", "error"); return; }
    /* 后端可能自动补全端口并写回接口配置 */
    (r.nodes || []).forEach((nd) => { nodeMap[nd.node_key] = nd; updateNodeVisual(nd); });
    linkMap[r.link.id] = r.link;
    saveLinkPrefs(src, dst, val("tal-type") || "trunk");
    drawLink(r.link);
    refreshPortLamps();
    resolveLabelOverlaps();
    document.getElementById("topo-addlink-modal").classList.remove("show");
    renderPanel();
    selectLink(r.link.id);
    const s = nodeMap[src], d = nodeMap[dst];
    status("链路已创建: " + (s ? s.name : src) + " ↔ " + (d ? d.name : dst));
    toast(r.message || "链路已创建，两端端口已点亮", r.message && r.message.indexOf("占满") >= 0 ? "error" : "success");
  }

  /* ============================================================
     删除 / 自动布局
     ============================================================ */
  async function deleteNode(nodeKey, skipConfirm) {
    const node = nodeMap[nodeKey];
    if (!topoId || !node) return;
    const linked = Object.values(linkMap).filter(
      (l) => l.src_node_key === nodeKey || l.dst_node_key === nodeKey
    ).length;
    if (!skipConfirm && !confirm("删除设备 “" + node.name + "” ？" + (linked ? "将同时删除 " + linked + " 条链路。" : ""))) return;
    const h = beginHistory("删除设备 " + node.name);
    const r = await apiDel(API_BASE + "/" + topoId + "/nodes/" + node.id);
    if (!r.success) { dropHistory(h); toast(r.message || "删除失败", "error"); return; }
    Object.values(linkMap).forEach((l) => {
      if (l.src_node_key === nodeKey || l.dst_node_key === nodeKey) {
        removeLinkEl(l.id);
        delete linkMap[l.id];
        delete labelOffs[l.id];
      }
    });
    saveLabelOffs();
    delete nodeMap[nodeKey];
    selectNode(null);
    renderAll();
    renderPanel();
    toast(r.message || "设备已删除", "success");
  }

  /* 框选多选的批量删除(Delete 键): 逐台调 API, 一次入撤销栈 */
  async function deleteMultiNodes() {
    if (!topoId || !multiSel.size) return;
    const keys = [...multiSel].filter((k) => nodeMap[k]);
    if (!keys.length) { clearMulti(); return; }
    const linkedCount = new Set();
    keys.forEach((k) => {
      Object.values(linkMap).forEach((l) => {
        if (l.src_node_key === k || l.dst_node_key === k) linkedCount.add(l.id);
      });
    });
    const label = "删除 " + keys.length + " 台设备" + (linkedCount.size ? "（含 " + linkedCount.size + " 条链路）" : "");
    if (!confirm("删除框选的 " + keys.length + " 台设备？" + (linkedCount.size ? "将同时删除 " + linkedCount.size + " 条链路。" : ""))) return;
    const h = beginHistory(label);
    let fail = 0;
    for (const k of keys) {
      const n = nodeMap[k];
      if (!n) continue;
      const r = await apiDel(API_BASE + "/" + topoId + "/nodes/" + n.id);
      if (!r.success) { fail++; continue; }
      Object.values(linkMap).forEach((l) => {
        if (l.src_node_key === k || l.dst_node_key === k) {
          removeLinkEl(l.id);
          delete linkMap[l.id];
          delete labelOffs[l.id];
        }
      });
      removeNodeEl(k);
      delete nodeMap[k];
    }
    saveLabelOffs();
    clearMulti();
    selectNode(null);
    renderAll();
    renderPanel();
    if (fail) toast(fail + " 台设备删除失败", "error");
    else { toast(label, "success"); status(label); }
  }

  async function deleteLink(linkId) {
    const link = linkMap[linkId];
    if (!topoId || !link) return;
    if (!confirm("删除这条链路？")) return;
    const h = beginHistory("删除链路 " + ((nodeMap[link.src_node_key] || {}).name || link.src_node_key) +
      " ↔ " + ((nodeMap[link.dst_node_key] || {}).name || link.dst_node_key));
    const r = await apiDel(API_BASE + "/" + topoId + "/links/" + link.id);
    if (!r.success) { dropHistory(h); toast(r.message || "删除失败", "error"); return; }
    removeLinkEl(link.id);
    delete linkMap[link.id];
    delete labelOffs[link.id];
    saveLabelOffs();
    refreshPortLamps();
    resolveLabelOverlaps();
    selectLink(null);
    renderPanel();
    toast("链路已删除", "success");
  }

  /* ============================================================
     撤销 / 重做 (快照式历史)
     —— 增删设备/链路、改属性、拖位置、对齐、自动布局、端口补全 在动手前压一份整图快照,
        Ctrl+Z 时用快照整体覆盖回后端(一次 PUT /graph, 按 id/node_key 对齐, 绑定关系不丢)
     —— 不下发、不生成: 那两项对真实设备有副作用, 撤不回来
     ============================================================ */
  const UNDO_MAX = 40;
  let undoStack = [], redoStack = [], historyBusy = false;

  function snapNode(n) {
    return {
      id: n.id, node_key: n.node_key, name: n.name, x: n.x, y: n.y,
      device_id: n.device_id || null, config: n.config || {},
    };
  }
  function snapLink(l) {
    return {
      id: l.id, src_node_key: l.src_node_key, src_port: l.src_port || null,
      dst_node_key: l.dst_node_key, dst_port: l.dst_port || null,
      link_type: l.link_type || "trunk", description: l.description || null,
    };
  }
  function snapshotGraph() {
    return { nodes: Object.values(nodeMap).map(snapNode), links: Object.values(linkMap).map(snapLink) };
  }
  function sameSnap(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function updateHistoryButtons() {
    const u = document.getElementById("btn-topo-undo");
    const r = document.getElementById("btn-topo-redo");
    if (u) {
      u.disabled = !undoStack.length;
      u.title = undoStack.length
        ? "撤销：" + undoStack[undoStack.length - 1].label + "（Ctrl+Z）"
        : "没有可撤销的操作";
    }
    if (r) {
      r.disabled = !redoStack.length;
      r.title = redoStack.length
        ? "重做：" + redoStack[redoStack.length - 1].label + "（Ctrl+Y / Ctrl+Shift+Z）"
        : "没有可重做的操作";
    }
  }

  function resetHistory() {
    undoStack = []; redoStack = [];
    updateHistoryButtons();
  }

  /* 动手前调用: 记录当前状态(返回句柄, 便于"实际没改动"时丢弃) */
  function beginHistory(label) {
    if (!topoId || historyBusy) return null;
    const entry = { label: label, snap: snapshotGraph(), selN: selectedNodeKey, selL: selectedLinkId };
    undoStack.push(entry);
    if (undoStack.length > UNDO_MAX) undoStack.shift();
    redoStack.length = 0;
    updateHistoryButtons();
    return entry;
  }

  /* 拖动类操作: 位移在 mousemove 中就已改完, 需要拿 mousedown 时抓的快照入栈 */
  function commitHistory(snap, label, selN, selL) {
    if (!topoId || historyBusy || !snap) return;
    if (sameSnap(snap, snapshotGraph())) return;   /* 位置没实际变化 */
    undoStack.push({ label: label, snap: snap, selN: selN || null, selL: selL || null });
    if (undoStack.length > UNDO_MAX) undoStack.shift();
    redoStack.length = 0;
    updateHistoryButtons();
  }

  function dropHistory(entry) {
    if (!entry) return;
    const i = undoStack.lastIndexOf(entry);
    if (i >= 0) undoStack.splice(i, 1);
    updateHistoryButtons();
  }

  /* 用服务端返回的整图替换本地状态并重绘 */
  function adoptGraph(nodes, links) {
    nodeMap = {}; linkMap = {};
    (nodes || []).forEach((n) => { nodeMap[n.node_key] = n; });
    (links || []).forEach((l) => { linkMap[l.id] = l; });
    Object.keys(labelOffs).forEach((id) => { if (!linkMap[id]) delete labelOffs[id]; });
    Object.keys(groupOffs).forEach((k) => { if (!nodeMap[k]) delete groupOffs[k]; });
    saveLabelOffs();
    saveGroupPos();
    renderAll();
    renderPanel();
  }

  async function applyHistory(entry, verb) {
    historyBusy = true;
    let r = null;
    try {
      r = await apiPut(API_BASE + "/" + topoId + "/graph",
        { nodes: entry.snap.nodes, links: entry.snap.links, label: entry.label });
    } finally { historyBusy = false; }
    if (!r || !r.success) { toast((r && r.message) || verb + "失败", "error"); return false; }
    selectedNodeKey = null; selectedLinkId = null;
    adoptGraph(r.nodes, r.links);
    if (entry.selN && nodeMap[entry.selN]) selectNode(entry.selN);
    else if (entry.selL && linkMap[entry.selL]) selectLink(entry.selL);
    else selectNode(null);
    toast(verb + "：" + entry.label, "success");
    status(verb + "：" + entry.label);
    return true;
  }

  async function undo() {
    if (!topoId || historyBusy || !undoStack.length) return;
    if (!onTopologyPage()) return;
    const entry = undoStack.pop();
    const redoEntry = { label: entry.label, snap: snapshotGraph(), selN: selectedNodeKey, selL: selectedLinkId };
    updateHistoryButtons();
    if (await applyHistory(entry, "已撤销")) {
      redoStack.push(redoEntry);
      if (redoStack.length > UNDO_MAX) redoStack.shift();
    } else {
      undoStack.push(entry);
    }
    updateHistoryButtons();
  }

  async function redo() {
    if (!topoId || historyBusy || !redoStack.length) return;
    if (!onTopologyPage()) return;
    const entry = redoStack.pop();
    const undoEntry = { label: entry.label, snap: snapshotGraph(), selN: selectedNodeKey, selL: selectedLinkId };
    updateHistoryButtons();
    if (await applyHistory(entry, "已重做")) {
      undoStack.push(undoEntry);
      if (undoStack.length > UNDO_MAX) undoStack.shift();
    } else {
      redoStack.push(entry);
    }
    updateHistoryButtons();
  }

  function onTopologyPage() {
    const p = document.getElementById("page-topology");
    return !!(p && p.classList.contains("active"));
  }

  /* 按连通性分层 — 供自动布局与下发顺序共用 */
  function layeredOrder() {
    const keys = Object.keys(nodeMap);
    if (!keys.length) return [];
    const adj = {};
    keys.forEach((k) => { adj[k] = []; });
    Object.values(linkMap).forEach((l) => {
      if (adj[l.src_node_key] && adj[l.dst_node_key]) {
        adj[l.src_node_key].push(l.dst_node_key);
        adj[l.dst_node_key].push(l.src_node_key);
      }
    });
    const degree = keys.map((k) => ({ k, d: adj[k].length, router: ((nodeMap[k].config || {}).device_type === "router") ? 1 : 0 }))
      .sort((a, b) => (b.router - a.router) || (b.d - a.d));
    const root = degree[0].k;
    const layer = {};
    const queue = [root];
    layer[root] = 0;
    while (queue.length) {
      const cur = queue.shift();
      adj[cur].forEach((nb) => {
        if (layer[nb] == null) { layer[nb] = layer[cur] + 1; queue.push(nb); }
      });
    }
    keys.forEach((k) => { if (layer[k] == null) layer[k] = 0; });
    const byLayer = {};
    keys.forEach((k) => {
      (byLayer[layer[k]] = byLayer[layer[k]] || []).push(k);
    });
    const ordered = [];
    Object.keys(byLayer).map(Number).sort((a, b) => a - b).forEach((lv) => {
      byLayer[lv].forEach((k) => ordered.push({ key: k, layer: lv, index: byLayer[lv].indexOf(k) }));
    });
    return ordered;
  }

  async function autoLayout() {
    if (!Object.keys(nodeMap).length) { toast("还没有设备", "error"); return; }
    const h = beginHistory("自动布局");
    const ordered = layeredOrder();
    const byLayer = {};
    ordered.forEach((item) => {
      (byLayer[item.layer] = byLayer[item.layer] || []).push(item);
    });
    const LAYER_H = 150, GAP = 34, X0 = 80, Y0 = 60;
    const updates = [];
    Object.keys(byLayer).forEach((lay) => {
      const row = byLayer[lay];
      /* 按每台设备的实际卡片宽度铺开, 避免宽设备(端口多)互相压住 */
      const ws = row.map((it) => nodeLayout(nodeMap[it.key]).w);
      const rowWidth = ws.reduce((s, w) => s + w, 0) + GAP * Math.max(0, row.length - 1);
      let x = Math.max(20, Math.round(X0 - rowWidth / 2));
      row.forEach((item, idx) => {
        const y = Y0 + Number(lay) * LAYER_H;
        const node = nodeMap[item.key];
        node.x = x; node.y = y;
        x += ws[idx] + GAP;
        const wrap = nodeEls[item.key];
        if (wrap) wrap.g.setAttribute("transform", "translate(" + node.x + "," + y + ")");
        updates.push(apiPut(API_BASE + "/" + topoId + "/nodes/" + node.id, { x: node.x, y: y }));
      });
    });
    Object.keys(linkMap).forEach((id) => updateLinkGeom(id));
    await Promise.all(updates);
    fitView();
    resolveLabelOverlaps();
    toast("已按连通层级自动布局", "success");
  }

  /* ============================================================
     左侧列表面板(设备 / 链路)
     ============================================================ */
  function renderPanel() {
    const dl = document.getElementById("topo-dev-list");
    const ll = document.getElementById("topo-link-list");
    if (!dl || !ll) return;
    const keys = Object.keys(nodeMap);
    dl.innerHTML = keys.length ? keys.map((k) => {
      const nd = nodeMap[k];
      const st = VENDOR_STYLE[(nd.config || {}).vendor] || VENDOR_STYLE.huawei;
      return '<div class="topo-list-item' + (k === selectedNodeKey ? " sel" : "") + '" data-key="' + esc(k) + '">' +
        '<span class="dot" style="background:' + st.stroke + '"></span>' + esc(nd.name) +
        (nd.mgmt_ip ? '<span class="topo-hint">' + esc(nd.mgmt_ip) + "</span>" : "") +
        "</div>";
    }).join("") : '<div class="topo-tip">暂无设备，点击"＋ 新建设备"</div>';

    const links = Object.values(linkMap);
    ll.innerHTML = links.length ? links.map((l) => {
      const s = nodeMap[l.src_node_key], d = nodeMap[l.dst_node_key];
      const ports = (l.src_port || l.dst_port)
        ? '<span class="topo-hint">' + esc((l.src_port || "?") + " ↔ " + (l.dst_port || "?")) + "</span>" : "";
      return '<div class="topo-list-item' + (l.id === selectedLinkId ? " sel" : "") + '" data-lid="' + esc(l.id) + '">' +
        '<span class="dot" style="background:#8fa3b0"></span>' +
        esc((s ? s.name : "?") + " ←→ " + (d ? d.name : "?")) + ports +
        "</div>";
    }).join("") : '<div class="topo-tip">暂无链路，点击"🔗 添加链路"</div>';
  }

  function bindPanelClicks() {
    const dl = document.getElementById("topo-dev-list");
    const ll = document.getElementById("topo-link-list");
    if (dl) dl.addEventListener("click", (e) => {
      const item = e.target.closest(".topo-list-item");
      if (item && item.getAttribute("data-key")) selectNode(item.getAttribute("data-key"));
    });
    if (ll) ll.addEventListener("click", (e) => {
      const item = e.target.closest(".topo-list-item");
      if (item && item.getAttribute("data-lid")) selectLink(item.getAttribute("data-lid"));
    });
  }

  /* ============================================================
     生成 / 体检 / 导出 / 下发
     ============================================================ */
  async function generate(nodeKeys, scopeLabel) {
    if (!topoId) { toast("请先选择拓扑图", "error"); return; }
    const body = nodeKeys && nodeKeys.length ? { node_keys: nodeKeys } : {};
    const r = await apiPost(API_BASE + "/" + topoId + "/generate", body);
    if (!r.results) { toast(r.message || "生成失败", "error"); return; }

    genResults = {};
    (r.results || []).forEach((x) => { genResults[x.node_key] = x; });

    document.getElementById("topo-gen-scope").textContent = scopeLabel || "整图";
    document.getElementById("topo-gen-summary").textContent =
      "成功 " + r.ok + " / 共 " + r.total + (r.failed ? "（失败 " + r.failed + "）" : "");
    const sel = document.getElementById("topo-gen-node-select");
    sel.innerHTML = (r.results || []).map((x) =>
      '<option value="' + esc(x.node_key) + '">' + esc(x.name) + (x.success ? "" : "（失败）") + "</option>"
    ).join("");
    showGenResult();
    document.getElementById("topo-gen-modal").classList.add("show");
  }

  function showGenResult() {
    const key = document.getElementById("topo-gen-node-select").value;
    const res = genResults[key];
    const pre = document.getElementById("topo-gen-content");
    const msg = document.getElementById("topo-gen-msg");
    if (!res) { pre.textContent = ""; msg.textContent = ""; return; }
    pre.textContent = res.success ? res.config_text : "# 生成失败\n# " + (res.message || "");
    const v = res.validation || {};
    msg.textContent = res.success
      ? "厂商 " + (res.vendor || "-") + " · 类型 " + (res.device_type || "-") + " · 大小 " + (res.config_text || "").length + " 字符" +
        (v.errors && v.errors.length ? " · 校验错误 " + v.errors.length : "")
      : (res.message || "生成失败");
  }

  function downloadCurrentConfig() {
    const key = document.getElementById("topo-gen-node-select").value;
    const res = genResults[key];
    if (!res) return;
    downloadText((res.hostname || res.name || "config") + ".cfg", res.success ? res.config_text : "# 生成失败");
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function exportZip() {
    if (!topoId) { toast("请先选择拓扑图", "error"); return; }
    const r = await fetch(API_BASE + "/" + topoId + "/export");
    if (!r.ok) {
      const t = await r.text();
      let msg = "导出失败";
      try { msg = JSON.parse(t).detail || msg; } catch (e) { /* 忽略 */ }
      toast(msg, "error");
      return;
    }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="([^"]+)"/);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = m ? m[1] : "topology_configs.zip";
    a.click();
    URL.revokeObjectURL(a.href);
    toast("已导出整图配置 ZIP", "success");
  }

  async function checkTopology() {
    if (!topoId) { toast("请先选择拓扑图", "error"); return; }
    const r = await apiPost(API_BASE + "/" + topoId + "/check", {});
    const s = r.summary || { error: 0, warn: 0, info: 0 };
    document.getElementById("topo-check-error").textContent = "错误 " + (s.error || 0);
    document.getElementById("topo-check-warn").textContent = "警告 " + (s.warn || 0);
    document.getElementById("topo-check-info").textContent = "提示 " + (s.info || 0);

    const color = { error: "#dc2626", warn: "#d97706", info: "#2563eb" };
    const label = { error: "错误", warn: "警告", info: "提示" };
    const list = document.getElementById("topo-check-list");
    const issues = r.issues || [];
    if (!issues.length) {
      list.innerHTML = '<div class="topo-tip">未发现问题，拓扑配置一致 ✔</div>';
    } else {
      list.innerHTML = issues.map((i) =>
        '<div class="topo-issue" style="border-left:3px solid ' + (color[i.level] || "#94a3b8") + '">' +
        '<span class="badge" style="background:' + (color[i.level] || "#94a3b8") + ';color:#fff;">' + (label[i.level] || i.level) + "</span> " +
        (i.node ? "<b>" + esc(i.node) + "</b> " : "") + esc(i.message) +
        (i.hint ? '<div class="topo-issue-hint">→ ' + esc(i.hint) + "</div>" : "") +
        "</div>"
      ).join("");
    }
    document.getElementById("topo-check-modal").classList.add("show");
    status("体检完成: 错误 " + (s.error || 0) + " / 警告 " + (s.warn || 0) + " / 提示 " + (s.info || 0));
  }

  async function autofillPorts() {
    if (!topoId) { toast("请先选择拓扑图", "error"); return; }
    const h = beginHistory("按链路补全端口");
    const r = await apiPost(API_BASE + "/" + topoId + "/autofill-ports", {});
    if (!r.success) { dropHistory(h); toast(r.message || "补全失败", "error"); return; }
    (r.nodes || []).forEach((nd) => { nodeMap[nd.node_key] = nd; updateNodeVisual(nd); });
    (r.links || []).forEach((l) => { linkMap[l.id] = l; updateLinkGeom(l.id); });
    resolveLabelOverlaps();
    if (selectedNodeKey) fillNodeForm(nodeMap[selectedNodeKey]);
    if (selectedLinkId) selectLink(selectedLinkId);
    toast(r.message || "端口已补全", r.message && r.message.indexOf("占满") >= 0 ? "error" : "success");
    status(r.message || "");
  }

  /* ---------- 下发 ---------- */
  function openPushModal() {
    const targets = orderedNodeKeysForPush();
    if (!targets.length) { toast("没有可下发的设备（需先绑定受管设备）", "error"); return; }
    const list = document.getElementById("topo-push-list");
    list.innerHTML = targets.map((t, i) =>
      '<div class="topo-push-row" data-key="' + esc(t.key) + '">' +
      '<span class="topo-push-idx">' + (i + 1) + "</span>" +
      "<span>" + esc(t.name) + "</span>" +
      '<span class="topo-hint">' + esc(t.deviceName) + "</span>" +
      '<span class="topo-push-state">待执行</span>' +
      "</div>"
    ).join("");
    document.getElementById("topo-push-modal").classList.add("show");
  }

  function orderedNodeKeysForPush() {
    const ordered = layeredOrder();
    const out = [];
    ordered.forEach((item) => {
      const nd = nodeMap[item.key];
      if (!nd || !nd.device_id) return;
      const dev = devices.find((d) => d.id === nd.device_id);
      out.push({ key: item.key, name: nd.name, device_id: nd.device_id, deviceName: dev ? dev.name : nd.device_id, layer: item.layer });
    });
    return out;
  }

  function setPushState(nodeKey, text, color) {
    const el = document.querySelector('.topo-push-row[data-key="' + nodeKey + '"] .topo-push-state');
    if (el) {
      el.textContent = text;
      el.style.color = color || "";
    }
  }

  async function execPushAll() {
    const targets = orderedNodeKeysForPush();
    if (!targets.length) { toast("没有可下发的设备", "error"); return; }
    const doBackup = document.getElementById("topo-push-backup").checked;
    if (!confirm("将按顺序下发 " + targets.length + " 台设备的配置" + (doBackup ? "（先备份现状）" : "") + "，失败即停。继续？")) return;

    const btn = document.getElementById("btn-topo-push-exec");
    btn.disabled = true;
    btn.textContent = "下发中...";
    const report = [];

    try {
      for (const t of targets) {
        setPushState(t.key, "生成中…", "#2563eb");
        const gen = await apiPost(API_BASE + "/" + topoId + "/generate", { node_keys: [t.key] });
        const res = (gen.results || [])[0];
        if (!res || !res.success) {
          setPushState(t.key, "生成失败", "#dc2626");
          report.push(t.name + ": 生成失败 - " + ((res && res.message) || "未知错误"));
          break;
        }

        if (doBackup) {
          setPushState(t.key, "备份中…", "#2563eb");
          const bk = await apiPost("/api/devices/" + t.device_id + "/backup", {});
          if (!bk.success) {
            setPushState(t.key, "备份失败, 已中止", "#dc2626");
            report.push(t.name + ": 备份失败 - " + (bk.message || ""));
            break;
          }
        }

        setPushState(t.key, "下发中…", "#2563eb");
        const push = await apiPost("/api/devices/" + t.device_id + "/push", {
          config_text: res.config_text,
          vendor: res.vendor || "huawei",
        });
        if (push.success) {
          setPushState(t.key, "✔ 成功", "#16a34a");
          report.push(t.name + ": 成功 (" + push.commands_success + "/" + push.commands_total + " 条命令)");
        } else {
          setPushState(t.key, push.rollback_performed ? "✗ 失败(已回滚)" : "✗ 失败", "#dc2626");
          report.push(t.name + ": 失败 - " + (push.message || ""));
          break;
        }
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "开始下发";
    }
    status("整图下发结束：" + report.length + " 台已处理");
    toast(report.length ? "下发结束, 详见面板" : "未执行任何下发", "success");
  }

  async function pushSingleNode() {
    if (!selectedNodeKey) return;
    const node = nodeMap[selectedNodeKey];
    if (!node.device_id) { toast("该节点未绑定受管设备, 无法下发", "error"); return; }
    const gen = await apiPost(API_BASE + "/" + topoId + "/generate", { node_keys: [selectedNodeKey] });
    const res = (gen.results || [])[0];
    if (!res || !res.success) { toast("生成失败: " + ((res && res.message) || ""), "error"); return; }
    const dev = devices.find((d) => d.id === node.device_id);
    if (!confirm("推送 " + res.config_text.split("\n").length + " 行配置到设备 “" + (dev ? dev.name : node.device_id) + "”？")) return;
    const bk = await apiPost("/api/devices/" + node.device_id + "/backup", {});
    if (!bk.success && !confirm("下发前备份失败（" + (bk.message || "") + "）。仍要继续下发？")) return;
    const push = await apiPost("/api/devices/" + node.device_id + "/push", {
      config_text: res.config_text,
      vendor: res.vendor || "huawei",
    });
    toast(push.success ? "下发成功" : "下发失败: " + (push.message || ""), push.success ? "success" : "error");
    status(push.message || "");
  }

  /* ============================================================
     拓扑图管理 / PNG 导出 / 初始化
     ============================================================ */
  async function createTopology() {
    const name = prompt("拓扑图名称", "园区网拓扑 " + new Date().toLocaleDateString());
    if (!name) return;
    const r = await apiPost(API_BASE, { name: name });
    if (!r.success) { toast(r.message || "创建失败", "error"); return; }
    await loadTopologyList(false);
    document.getElementById("topo-select").value = r.id;
    await openTopology(r.id);
    toast("拓扑图已创建", "success");
  }

  async function renameTopology() {
    if (!topoId) return;
    const cur = (topoList.find((t) => t.id === topoId) || {}).name || "";
    const name = prompt("修改拓扑图名称", cur);
    if (!name) return;
    await apiPut(API_BASE + "/" + topoId, { name: name });
    await loadTopologyList(true);
    toast("已改名", "success");
  }

  async function deleteTopology() {
    if (!topoId) return;
    const cur = (topoList.find((t) => t.id === topoId) || {}).name || "";
    if (!confirm("删除拓扑图 “" + cur + "”？设备与链路会一并删除，不可恢复。")) return;
    const r = await apiDel(API_BASE + "/" + topoId);
    if (!r.success) { toast(r.message || "删除失败", "error"); return; }
    topoId = null;
    resetHistory();
    await loadTopologyList(false);
    toast("拓扑图已删除", "success");
  }

  async function openTopology(id) {
    if (!ensureSvg()) return;
    const r = await apiGet(API_BASE + "/" + id);
    if (!r.success) { toast(r.message || "加载拓扑失败", "error"); return; }

    topoId = id;
    topoList.forEach((t) => { if (t.id === id) { t.name = r.topology.name; } });
    setVal("topo-select", id);
    labelOffs = loadLabelOffs()[id] || {};
    loadFoldState();
    groupOffs = loadGroupPos()[id] || {};
    clearMulti();
    updateAlignButtons();
    resetHistory();     /* 换图 → 历史不跨图(快照只对当前拓扑有效) */

    nodeMap = {};
    linkMap = {};
    selectNode(null);
    selectLink(null);

    (r.nodes || []).forEach((nd) => { nodeMap[nd.node_key] = nd; });
    (r.links || []).forEach((l) => { linkMap[l.id] = l; });
    renderAll();
    fitView();
    renderPanel();

    document.getElementById("topo-empty").style.display = "none";
    status("已加载 " + (r.nodes || []).length + " 台设备 / " + (r.links || []).length + " 条链路");
  }

  async function loadTopologyList(keepCurrent) {
    const r = await apiGet(API_BASE);
    topoList = (r.topologies || []);
    const sel = document.getElementById("topo-select");
    sel.innerHTML = topoList.length
      ? topoList.map((t) => '<option value="' + t.id + '">' + esc(t.name) +
          " (" + t.node_count + "节点/" + t.link_count + "链路)</option>").join("")
      : '<option value="">（尚无拓扑图）</option>';

    if (keepCurrent && topoId && topoList.some((t) => t.id === topoId)) {
      sel.value = topoId;
      return;
    }
    if (topoList.length) {
      await openTopology(topoList[0].id);
    } else {
      topoId = null;
      if (world) { gLinks.innerHTML = ""; gNodes.innerHTML = ""; nodeEls = {}; linkEls = {}; }
      renderPanel();
      resetHistory();
      document.getElementById("topo-empty").style.display = "block";
      status("");
    }
  }

  /* PNG 导出: 序列化 SVG → Canvas → PNG */
  function exportPng() {
    if (!svg || !Object.keys(nodeMap).length) { toast("还没有设备", "error"); return; }
    buildDispMap();
    let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
    Object.values(dispMap).forEach((d) => {
      minx = Math.min(minx, d.x); miny = Math.min(miny, d.y - 12);
      maxx = Math.max(maxx, d.x + d.w); maxy = Math.max(maxy, d.y + d.h + 35);
    });
    const pad = 30;
    minx -= pad; miny -= pad; maxx += pad; maxy += pad;
    const w = Math.ceil(maxx - minx), h = Math.ceil(maxy - miny);

    /* 导出的是"干净"的图: 先摘掉链路编辑高亮(含"自动"占位), 克隆后再还原 */
    const prevSel = selectedLinkId;
    if (prevSel) clearLinkHighlight();
    const clone = svg.cloneNode(true);
    /* 把 CSS 类样式内联, 保证独立 SVG 渲染一致 */
    const cssMap = [
      [".tp-line", ["stroke", "stroke-width", "stroke-dasharray", "stroke-linejoin", "stroke-linecap"]],
      [".tp-pl", ["fill", "font-size", "font-weight", "stroke", "stroke-width", "paint-order"]],
      [".tp-port", ["fill", "stroke", "stroke-width"]],
      [".tp-fold rect", ["fill", "stroke"]],
      [".tp-typelabel", ["fill", "font-size", "font-weight"]],
      [".tp-name", ["fill", "font-size", "font-weight", "stroke", "stroke-width", "paint-order"]],
      [".tp-ip", ["fill", "font-size", "stroke", "stroke-width", "paint-order"]],
    ];
    cssMap.forEach(([sel, props]) => {
      const src = svg.querySelectorAll(sel), dst = clone.querySelectorAll(sel);
      for (let i = 0; i < dst.length; i++) {
        const cs = getComputedStyle(src[i]);
        dst[i].setAttribute("style", props.map((p) => p + ":" + cs.getPropertyValue(p)).join(";"));
      }
    });
    const cw = clone.querySelector("g");
    if (cw) cw.removeAttribute("transform");
    clone.setAttribute("width", w);
    clone.setAttribute("height", h);
    clone.setAttribute("viewBox", minx + " " + miny + " " + w + " " + h);
    clone.querySelectorAll(".tp-halo").forEach((r) => r.setAttribute("stroke", "transparent"));
    clone.querySelectorAll(".tp-marquee, .tp-foldbadge").forEach((el) => el.remove());
    clone.querySelectorAll(".tp-link.sel").forEach((g) => g.classList.remove("sel"));
    clone.querySelectorAll(".tp-node.sel, .tp-node.mul").forEach((g) => g.classList.remove("sel", "mul"));

    const xml = new XMLSerializer().serializeToString(clone);
    if (prevSel) applyLinkHighlight(prevSel);   /* 还原屏幕上的高亮 */
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = w * 2; cv.height = h * 2;
      const ctx = cv.getContext("2d");
      ctx.scale(2, 2);
      ctx.fillStyle = "#fbfcfe";
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0);
      const a = document.createElement("a");
      a.href = cv.toDataURL("image/png");
      a.download = ((topoList.find((t) => t.id === topoId) || {}).name || "topology") + ".png";
      a.click();
      toast("已导出 PNG", "success");
    };
    img.onerror = () => toast("导出失败", "error");
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  }

  async function loadDevices() {
    try {
      const r = await apiGet("/api/devices");
      devices = r.devices || [];
      const sel = document.getElementById("topo-f-device");
      if (sel) {
        sel.innerHTML = '<option value="">不绑定</option>' + devices.map((d) =>
          '<option value="' + d.id + '">' + esc(d.name) + " (" + esc(d.host || "无地址") + ")</option>"
        ).join("");
      }
    } catch (e) { /* 静默 */ }
  }

  function bindToolbar() {
    document.getElementById("topo-select").addEventListener("change", (e) => {
      if (e.target.value) openTopology(e.target.value);
    });
    document.getElementById("btn-topo-new").addEventListener("click", createTopology);
    document.getElementById("btn-topo-rename").addEventListener("click", renameTopology);
    document.getElementById("btn-topo-delete").addEventListener("click", deleteTopology);
    document.getElementById("btn-topo-adddev").addEventListener("click", openAddDevModal);
    document.getElementById("btn-topo-addlink").addEventListener("click", openAddLinkModal);
    document.getElementById("btn-topo-layout").addEventListener("click", autoLayout);
    document.getElementById("btn-topo-align-left").addEventListener("click", () => alignNodes("left"));
    document.getElementById("btn-topo-align-right").addEventListener("click", () => alignNodes("right"));
    document.getElementById("btn-topo-align-top").addEventListener("click", () => alignNodes("top"));
    document.getElementById("btn-topo-align-bottom").addEventListener("click", () => alignNodes("bottom"));
    document.getElementById("btn-topo-autofill").addEventListener("click", autofillPorts);
    document.getElementById("btn-topo-check").addEventListener("click", checkTopology);
    document.getElementById("btn-topo-generate").addEventListener("click", () => generate(null, "整图"));
    document.getElementById("btn-topo-export").addEventListener("click", exportZip);
    document.getElementById("btn-topo-png").addEventListener("click", exportPng);
    document.getElementById("btn-topo-push").addEventListener("click", openPushModal);

    /* 新建设备弹窗 */
    document.getElementById("btn-ta-submit").addEventListener("click", submitAddDevice);
    document.getElementById("btn-ta-cancel").addEventListener("click", () =>
      document.getElementById("topo-adddev-modal").classList.remove("show"));
    document.getElementById("btn-close-ta").addEventListener("click", () =>
      document.getElementById("topo-adddev-modal").classList.remove("show"));
    document.getElementById("ta-type").addEventListener("change", () => {
      syncAddDevTypeUI();
      const t = val("ta-type") || "switch";
      setVal("ta-portcount", (TYPE_META[t] || TYPE_META.switch).defaultPorts);
    });

    /* 添加链路弹窗 */
    document.getElementById("tal-src").addEventListener("change", () => refreshPortSelect("tal-srcport", "tal-src"));
    document.getElementById("tal-dst").addEventListener("change", () => refreshPortSelect("tal-dstport", "tal-dst"));
    document.getElementById("btn-tal-submit").addEventListener("click", submitAddLink);
    document.getElementById("btn-tal-cancel").addEventListener("click", () =>
      document.getElementById("topo-addlink-modal").classList.remove("show"));
    document.getElementById("btn-close-tal").addEventListener("click", () =>
      document.getElementById("topo-addlink-modal").classList.remove("show"));

    /* 属性面板 */
    document.getElementById("topo-f-type").addEventListener("change", syncPropTypeUI);
    document.getElementById("btn-topo-gen-ports").addEventListener("click", genPortsForForm);
    document.getElementById("btn-topo-save-node").addEventListener("click", saveNode);
    document.getElementById("btn-topo-gen-node").addEventListener("click", () => {
      if (!selectedNodeKey) return;
      generate([selectedNodeKey], nodeMap[selectedNodeKey].name);
    });
    document.getElementById("btn-topo-download-node").addEventListener("click", () => {
      if (!selectedNodeKey) return;
      generate([selectedNodeKey], nodeMap[selectedNodeKey].name).then(() => {
        setTimeout(downloadCurrentConfig, 350);
      });
    });
    document.getElementById("btn-topo-push-node").addEventListener("click", pushSingleNode);
    document.getElementById("btn-topo-del-node").addEventListener("click", () => {
      if (selectedNodeKey) deleteNode(selectedNodeKey);
    });

    document.getElementById("btn-topo-save-link").addEventListener("click", saveLink);
    document.getElementById("btn-topo-del-link").addEventListener("click", () => {
      if (selectedLinkId) deleteLink(selectedLinkId);
    });
    const undoBtn = document.getElementById("btn-topo-undo");
    if (undoBtn) undoBtn.addEventListener("click", undo);
    const redoBtn = document.getElementById("btn-topo-redo");
    if (redoBtn) redoBtn.addEventListener("click", redo);
    /* 链路属性编辑: 输入时实时高亮/预览对应端口标注, 失焦或保存后按模型重算 */
    [["topo-l-srcport", 0], ["topo-l-dstport", 1]].forEach(([id, end]) => {
      const inp = document.getElementById(id);
      if (!inp) return;
      inp.addEventListener("input", () => previewLinkLabel(end, inp.value));
      inp.addEventListener("focus", () => {
        if (!selectedLinkId) return;
        applyLinkHighlight(selectedLinkId);
        previewLinkLabel(end, inp.value);
      });
      inp.addEventListener("blur", () => {
        if (!selectedLinkId) return;
        updateLinkGeom(selectedLinkId);
        applyLinkHighlight(selectedLinkId);
      });
    });
    const ltypeSel = document.getElementById("topo-l-type");
    if (ltypeSel) ltypeSel.addEventListener("change", () => {
      const wrap = selectedLinkId ? linkEls[selectedLinkId] : null;
      if (wrap) wrap.g.classList.toggle("tp-access", ltypeSel.value === "access");
    });

    document.getElementById("btn-close-topo-gen").addEventListener("click", () =>
      document.getElementById("topo-gen-modal").classList.remove("show"));
    document.getElementById("btn-close-topo-check").addEventListener("click", () =>
      document.getElementById("topo-check-modal").classList.remove("show"));
    document.getElementById("btn-close-topo-push").addEventListener("click", () =>
      document.getElementById("topo-push-modal").classList.remove("show"));
    document.getElementById("topo-gen-node-select").addEventListener("change", showGenResult);
    document.getElementById("btn-topo-gen-copy").addEventListener("click", () => {
      const text = document.getElementById("topo-gen-content").textContent || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => toast("已复制", "success")).catch(() => toast("复制失败", "error"));
      }
    });
    document.getElementById("btn-topo-gen-download").addEventListener("click", downloadCurrentConfig);
    document.getElementById("btn-topo-gen-zip").addEventListener("click", exportZip);
    document.getElementById("btn-topo-push-exec").addEventListener("click", execPushAll);

    bindPanelClicks();
  }

  /* ---------- 面板宽度调节(拖动分隔条, localStorage 持久化) ---------- */
  function initPanelResizers() {
    const body = document.querySelector(".topo-body");
    if (!body) return;
    const MIN = 140, MAX = 620;
    let leftW = 168, rightW = 296;
    try {
      const saved = JSON.parse(localStorage.getItem("topo_panel_widths") || "null");
      if (saved) {
        leftW = Math.min(MAX, Math.max(MIN, parseInt(saved.left, 10) || leftW));
        rightW = Math.min(MAX, Math.max(MIN, parseInt(saved.right, 10) || rightW));
      }
    } catch (e) { /* 忽略 */ }
    apply();

    function apply() {
      body.style.gridTemplateColumns = leftW + "px 8px minmax(0, 1fr) 8px " + rightW + "px";
    }
    function save() {
      try { localStorage.setItem("topo_panel_widths", JSON.stringify({ left: leftW, right: rightW })); } catch (e) { /* 忽略 */ }
    }

    [["topo-div-left", 1], ["topo-div-right", -1]].forEach(([id, dir]) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        el.classList.add("active");
        const startX = e.clientX, startL = leftW, startR = rightW;
        function onMove(ev) {
          const dx = ev.clientX - startX;
          if (dir === 1) {
            /* 左分隔条: 向右拖 -> 左面板变宽 */
            leftW = Math.min(MAX, Math.max(MIN, Math.round(startL + dx)));
          } else {
            /* 右分隔条: 向左拖 -> 右面板变宽 */
            rightW = Math.min(MAX, Math.max(MIN, Math.round(startR - dx)));
          }
          apply();
        }
        function onUp() {
          el.classList.remove("active");
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          document.body.style.cursor = "";
          save();
        }
        document.body.style.cursor = "col-resize";
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    });
  }

  function init() {
    if (inited) return;
    inited = true;
    bindToolbar();
    initPanelResizers();
  }

  async function onShow() {
    init();
    if (!ensureSvg()) return;
    await loadDevices();
    await loadTopologyList(true);
  }

  window.TopologyPage = {
    init,
    onShow,
    exportPng,
    checkTopology,
    autoLayout,
    autofillPorts,
    undo,
    redo,
    /* 供自动化测试/调试查看历史栈 */
    historyInfo: () => ({
      undo: undoStack.map((e) => e.label),
      redo: redoStack.map((e) => e.label),
    }),
  };
})();
