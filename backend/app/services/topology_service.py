"""拓扑服务 — 节点属性(DeviceConfig) → 配置生成 / 拓扑体检 / 打包导出

设计要点:
    node.config 直接就是 DeviceConfig 的序列化结果, 生成时零转换;
    体检规则面向"拓扑才能发现的问题"(端口占用 / IP 冲突 / VLAN 未定义 / 链路两端不匹配等)。
"""

from __future__ import annotations

import io
import ipaddress
import re
import zipfile

from app.models.device import DeviceConfig, Vendor, DeviceType
from app.services.config_generator import config_service
from app.services.config_validator import validator

# DeviceConfig 允许的顶层字段
_ALLOWED_KEYS = {
    "vendor",
    "device_type",
    "hostname",
    "basic",
    "vlan",
    "routing",
    "security",
    "interface",
}

# 端口命名规则 (供"按链路生成端口配置"与体检提示使用)
PORT_RULES: dict[str, str] = {
    "huawei": "GigabitEthernet0/0/{i}",
    "h3c": "GigabitEthernet1/0/{i}",
    "ruijie": "GigabitEthernet0/{i}",
    "maipu": "GigabitEthernet0/{i}",
}


def port_name(vendor: str, index: int) -> str:
    """按厂商命名规则生成端口名"""
    tpl = PORT_RULES.get((vendor or "huawei").lower(), PORT_RULES["huawei"])
    return tpl.format(i=index)


def node_display_name(node) -> str:
    return (node.name or "").strip() or node.node_key


def default_node_config(vendor: str = "huawei", device_type: str = "switch", name: str = "") -> dict:
    """新建节点的默认属性 — 只放"一定会用上"的最小骨架, 其余交给用户按需开启"""
    return {
        "vendor": vendor,
        "device_type": device_type,
        "hostname": name or "",
        "basic": {
            "ssh": {"enable": False, "version": 2, "port": 22},
            "telnet": {"enable": False},
            "mgmt_interface": {
                "enable": True,
                "interface": "Vlanif1",
                "ip_address": "",
                "mask": "255.255.255.0",
                "gateway": "",
                "description": "Management Interface",
            },
            "dhcp_global": {"enable": False, "dns_servers": []},
            "ntp": {"enable": False, "servers": [], "timezone": "UTC+8"},
            "snmp": {"enable": False, "version": "v2c"},
        },
        "vlan": {
            "vlans": [{"id": 1, "name": "Default"}],
            "interfaces": [],
            "vlanifs": [],
            "stp": {"enable": False, "mode": "stp", "priority": 32768},
        },
    }


def build_device_config(node) -> DeviceConfig:
    """由拓扑节点构造 DeviceConfig (node.config 原样透传, 仅做字段白名单过滤)"""
    raw = dict(node.config or {})
    payload = {k: v for k, v in raw.items() if k in _ALLOWED_KEYS}

    vendor = str(payload.get("vendor") or "huawei").lower()
    payload["vendor"] = vendor if vendor in {v.value for v in Vendor} else "huawei"

    dtype = str(payload.get("device_type") or "switch").lower()
    payload["device_type"] = dtype if dtype in {d.value for d in DeviceType} else "switch"

    if not payload.get("hostname"):
        name = node_display_name(node)
        if name and name != node.node_key:
            payload["hostname"] = name

    return DeviceConfig(**payload)


def generate_for_node(node) -> dict:
    """为单个节点生成配置"""
    try:
        cfg = build_device_config(node)
    except Exception as e:
        return {
            "node_key": node.node_key,
            "name": node_display_name(node),
            "success": False,
            "message": f"属性校验失败: {e}",
            "config_text": "",
        }

    # 终端/示意类设备没有可生成的配置
    if cfg.device_type.value in {"wan", "pc", "ipc", "custom"}:
        return {
            "node_key": node.node_key,
            "name": node_display_name(node),
            "vendor": cfg.vendor.value,
            "device_type": cfg.device_type.value,
            "hostname": cfg.hostname or node_display_name(node),
            "success": True,
            "message": "终端/示意设备，无需生成配置",
            "config_text": f"# {node_display_name(node)}: 终端/示意设备({cfg.device_type.value})，无需配置\n",
            "validation": {},
            "device_id": node.device_id,
        }

    try:
        result = config_service.generate(cfg)
    except Exception as e:
        return {
            "node_key": node.node_key,
            "name": node_display_name(node),
            "success": False,
            "message": f"生成失败: {e}",
            "config_text": "",
        }

    validation = result.get("validation") or {}
    return {
        "node_key": node.node_key,
        "name": node_display_name(node),
        "vendor": result.get("vendor"),
        "device_type": result.get("device_type"),
        "hostname": result.get("hostname") or node_display_name(node),
        "success": True,
        "message": "生成成功",
        "config_text": result.get("config_text", ""),
        "validation": validation,
        "device_id": node.device_id,
    }


def generate_topology(nodes: list, only_keys: list[str] | None = None) -> dict:
    """为整张拓扑(或指定节点)生成配置"""
    results = []
    for n in nodes:
        if only_keys and n.node_key not in only_keys:
            continue
        results.append(generate_for_node(n))

    ok = sum(1 for r in results if r["success"])
    return {
        "success": ok == len(results) and len(results) > 0,
        "total": len(results),
        "ok": ok,
        "failed": len(results) - ok,
        "results": results,
    }


def export_zip(topology, nodes: list, links: list) -> bytes:
    """把整张拓扑的配置打包为 zip (每台一个 .cfg + 拓扑清单)"""
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in nodes:
            r = generate_for_node(n)
            base = (r.get("hostname") or node_display_name(n)).replace("/", "_")
            fname = f"{base}.cfg"
            i = 1
            while fname in used:
                fname = f"{base}_{i}.cfg"
                i += 1
            used.add(fname)
            body = r["config_text"] if r["success"] else f"# 生成失败: {r['message']}\n"
            zf.writestr(fname, body)

        # 拓扑清单 — 节点与链路关系, 便于人工核对
        lines = [f"# 拓扑: {topology.name}", ""]
        lines.append("[节点]")
        for n in nodes:
            cfg = n.config or {}
            vendor = cfg.get("vendor", "-")
            dtype = cfg.get("device_type", "-")
            mgmt = ((cfg.get("basic") or {}).get("mgmt_interface") or {}).get("ip_address") or "-"
            lines.append(f"{node_display_name(n)}\t{vendor}\t{dtype}\t管理IP={mgmt}\tnode={n.node_key}")
        lines.append("")
        lines.append("[链路]")
        for l in links:
            lines.append(
                f"{l.src_node_key}({l.src_port or '-'}) <--> "
                f"{l.dst_node_key}({l.dst_port or '-'}) [{l.link_type}]"
            )
        zf.writestr("_topology.txt", "\n".join(lines) + "\n")
    return buf.getvalue()


# --------------------------------------------------------------------------
# 拓扑体检
# --------------------------------------------------------------------------

def _mgmt_ip(cfg: dict) -> str | None:
    basic = cfg.get("basic") or {}
    mgmt = basic.get("mgmt_interface") or {}
    ip = (mgmt.get("ip_address") or "").strip()
    return ip or None


def _all_ips(cfg: dict) -> list[tuple[str, str]]:
    """收集节点配置里的所有 IP: [(ip, 来源描述)]"""
    out: list[tuple[str, str]] = []
    basic = cfg.get("basic") or {}
    mgmt = basic.get("mgmt_interface") or {}
    if (mgmt.get("ip_address") or "").strip():
        out.append((mgmt["ip_address"].strip(), "管理接口"))
    vlan = cfg.get("vlan") or {}
    for v in vlan.get("vlanifs") or []:
        ip = (v.get("ip_address") or "").strip()
        if ip:
            out.append((ip, f"Vlanif{v.get('vlan_id')}"))
    return out


def check_topology(nodes: list, links: list, managed_hosts: set[str] | None = None) -> dict:
    """拓扑体检 — 返回问题清单

    规则:
        error 同节点端口被多条链路占用 / IP 冲突 / 同一节点内 VLAN 定义冲突
        warn  接口引用未定义 VLAN / 链路两端 trunk VLAN 不一致 / 未配置管理 IP / 与受管设备 IP 重复
        info  孤立节点 / 未绑定受管设备
    """
    issues: list[dict] = []
    managed_hosts = {h for h in (managed_hosts or set()) if h}
    by_key = {n.node_key: n for n in nodes}

    def add(level: str, msg: str, node_key: str | None = None, hint: str = ""):
        issues.append(
            {
                "level": level,
                "node_key": node_key,
                "node": node_display_name(by_key[node_key]) if node_key in by_key else None,
                "message": msg,
                "hint": hint,
            }
        )

    # ---- 1. 端口占用冲突 (拓扑才能发现) ----
    port_use: dict[tuple[str, str], list[str]] = {}
    for l in links:
        for key, port in ((l.src_node_key, l.src_port), (l.dst_node_key, l.dst_port)):
            if not port:
                continue
            port_use.setdefault((key, port.strip().lower()), []).append(
                f"{l.src_node_key}({l.src_port or '-'})<->{l.dst_node_key}({l.dst_port or '-'})"
            )
    for (key, port), users in port_use.items():
        if len(users) > 1:
            add(
                "error",
                f"端口 {port} 被 {len(users)} 条链路同时占用",
                key,
                "同一物理端口只能连接一条链路, 请修改链路端口",
            )

    # ---- 2. IP 冲突 ----
    ip_map: dict[str, list[str]] = {}
    for n in nodes:
        for ip, src in _all_ips(n.config or {}):
            ip_map.setdefault(ip, []).append(f"{node_display_name(n)}({src})")
    for ip, users in ip_map.items():
        if len(users) > 1:
            add("error", f"IP {ip} 被多处使用: {', '.join(users)}", None, "请为各节点分配唯一 IP")

    # ---- 3. VLAN 引用未定义 / 定义重复 ----
    for n in nodes:
        cfg = n.config or {}
        vlan = cfg.get("vlan") or {}
        defined = [v.get("id") for v in (vlan.get("vlans") or []) if v.get("id")]
        defined_set = set(defined)
        dup = {v for v in defined if defined.count(v) > 1}
        for d in dup:
            add("error", f"VLAN {d} 重复定义", n.node_key, "同一 VLAN 只能定义一次")
        for itf in vlan.get("interfaces") or []:
            refs: list[int] = []
            if itf.get("vlan_id"):
                refs.append(itf["vlan_id"])
            refs += list(itf.get("trunk_vlans") or [])
            if itf.get("pvid"):
                refs.append(itf["pvid"])
            refs += list(itf.get("untagged_vlans") or [])
            refs += list(itf.get("tagged_vlans") or [])
            for r in sorted(set(refs)):
                if r not in defined_set:
                    add(
                        "warn",
                        f"接口 {itf.get('interface')} 引用了未定义的 VLAN {r}",
                        n.node_key,
                        "请在 VLAN 列表中补充该 VLAN",
                    )
        for v in vlan.get("vlanifs") or []:
            if v.get("vlan_id") and v["vlan_id"] not in defined_set:
                add(
                    "warn",
                    f"Vlanif{v['vlan_id']} 对应的 VLAN 未定义",
                    n.node_key,
                    "三层接口的 VLAN 需先在 VLAN 列表定义",
                )

    # ---- 4. 链路两端 VLAN 不一致 / 端口未在节点配置中定义 ----
    def node_interfaces(node) -> dict[str, dict]:
        cfg = node.config or {}
        vlan = cfg.get("vlan") or {}
        out: dict[str, dict] = {}
        for itf in vlan.get("interfaces") or []:
            key = (itf.get("interface") or "").strip().lower()
            if key:
                out[key] = itf
        return out

    def trunk_vlans(node, port) -> set[int]:
        itf = node_interfaces(node).get((port or "").strip().lower())
        return set(itf.get("trunk_vlans") or []) if itf else set()

    for l in links:
        a, b = by_key.get(l.src_node_key), by_key.get(l.dst_node_key)
        if not a or not b:
            continue
        for node, port, other in ((a, l.src_port, b), (b, l.dst_port, a)):
            if port and (port.strip().lower() not in node_interfaces(node)):
                add(
                    "warn",
                    f"链路端口 {port} 未在节点 {node_display_name(node)} 的接口配置中定义",
                    node.node_key,
                    "该端口不会被生成到配置中, 可用“按链路生成端口配置”补全",
                )
        if (l.link_type or "trunk") != "trunk":
            continue
        va, vb = trunk_vlans(a, l.src_port), trunk_vlans(b, l.dst_port)
        if va and vb and va != vb:
            add(
                "warn",
                f"链路 {l.src_port or '?'} ←→ {l.dst_port or '?'} 两端 trunk 放通 VLAN 不一致: "
                f"{sorted(va)} vs {sorted(vb)}",
                l.src_node_key,
                "VLAN 未放通会导致业务不通",
            )

    # ---- 5. 节点级检查 ----
    names: dict[str, list[str]] = {}
    linked_keys = {l.src_node_key for l in links} | {l.dst_node_key for l in links}
    for n in nodes:
        nm = node_display_name(n)
        names.setdefault(nm, []).append(n.node_key)
        cfg = n.config or {}
        if not _mgmt_ip(cfg):
            add("warn", "未配置管理 IP", n.node_key, "无管理地址将无法自动备份/下发")
        else:
            ip = _mgmt_ip(cfg)
            if ip in managed_hosts:
                add(
                    "warn",
                    f"管理 IP {ip} 与已有受管设备重复",
                    n.node_key,
                    "可能指向同一台设备, 请确认是否需要合并",
                )
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                add("error", f"管理 IP {ip} 格式不正确", n.node_key, "请填写合法的 IPv4 地址")
        if not n.device_id:
            add("info", "未绑定受管设备", n.node_key, "绑定后可一键备份与下发")
        if n.node_key not in linked_keys:
            add("info", "节点没有任何链路", n.node_key, "孤立节点可能无法通信, 或仅作示意")

    for nm, keys in names.items():
        if len(keys) > 1:
            add("warn", f"存在 {len(keys)} 个同名节点 “{nm}”", keys[0], "重名会让配置归档难以区分")

    # ---- 6. 链路端口未在节点配置中体现 ----
    for l in links:
        for key, port in ((l.src_node_key, l.src_port), (l.dst_node_key, l.dst_port)):
            if not port:
                add(
                    "warn",
                    f"链路未指定端口: {l.src_node_key}({l.src_port or '-'}) <-> "
                    f"{l.dst_node_key}({l.dst_port or '-'})",
                    key,
                    "可用“按链路生成端口配置”自动补全",
                )

    summary = {
        "error": sum(1 for i in issues if i["level"] == "error"),
        "warn": sum(1 for i in issues if i["level"] == "warn"),
        "info": sum(1 for i in issues if i["level"] == "info"),
    }
    return {"success": True, "issues": issues, "summary": summary}


def autofill_link_ports(nodes: list, links: list, apply_config: bool = True) -> dict:
    """按链路自动补全端口名, 并(可选)把端口写进节点 VLAN 接口配置

    分配规则:
        - "占用"只统计链路: 配置里已有的端口条目只是端口定义, 不算被占用;
        - 优先从设备接口配置中已定义的端口池内分配(编号从小到大),
          保证分配结果不会超出设备的端口数量, 也不会新增端口条目;
        - 设备没有接口定义时(旧数据), 退回按厂商规则向后编号(不设上限)。

    会就地修改传入的 link 对象(node_key/端口属性)与 node 对象(config);
    若为 ORM 实例, 调用方只需 flush 即可持久化。

    Returns:
        {link_updates: [{id, src_port, dst_port}], changed: n,
         failures: [{id, side, node, message}]}
    """
    by_key = {n.node_key: n for n in nodes}
    used: dict[str, set[str]] = {n.node_key: set() for n in nodes}   # 仅链路占用

    for l in links:
        if l.src_port:
            used.setdefault(l.src_node_key, set()).add(l.src_port.strip().lower())
        if l.dst_port:
            used.setdefault(l.dst_node_key, set()).add(l.dst_port.strip().lower())

    # 每台设备的候选端口池: 接口配置中已定义的端口名(按编号升序)
    pool: dict[str, list[str]] = {}
    for n in nodes:
        vlan = (n.config or {}).get("vlan") or {}
        names = [
            (itf.get("interface") or "").strip()
            for itf in vlan.get("interfaces") or []
            if (itf.get("interface") or "").strip()
        ]
        pool[n.node_key] = sorted(set(names), key=lambda s: (_port_sort_key(s), s))

    def alloc(key: str) -> str | None:
        """为节点分配一个未被链路占用的端口; 无可用端口返回 None"""
        taken = used.setdefault(key, set())
        node = by_key.get(key)
        vendor = ((node.config or {}).get("vendor") or "huawei") if node else "huawei"
        for name in pool.get(key) or []:
            if name.lower() not in taken:
                return name
        if pool.get(key):
            return None  # 端口池已满, 不越界分配
        idx = 1
        while port_name(vendor, idx).lower() in taken:
            idx += 1
        return port_name(vendor, idx)

    link_updates = []
    failures: list[dict] = []
    for l in links:
        upd = {"id": l.id, "src_port": l.src_port, "dst_port": l.dst_port}
        for side in ("src", "dst"):
            key = getattr(l, f"{side}_node_key")
            port = getattr(l, f"{side}_port")
            if port:
                continue
            new_port = alloc(key)
            if not new_port:
                node = by_key.get(key)
                failures.append(
                    {
                        "id": l.id,
                        "side": side,
                        "node": node_display_name(node) if node else key,
                        "message": f"{node_display_name(node) if node else key} 的端口已被链路占满",
                    }
                )
                continue
            used.setdefault(key, set()).add(new_port.lower())
            upd[f"{side}_port"] = new_port
        if upd["src_port"] != l.src_port or upd["dst_port"] != l.dst_port:
            link_updates.append(upd)
            # 就地写回链路对象
            l.src_port = upd["src_port"]
            l.dst_port = upd["dst_port"]
            # 同步到节点配置
            if apply_config:
                for side in ("src", "dst"):
                    key = getattr(l, f"{side}_node_key")
                    node = by_key.get(key)
                    port = upd[f"{side}_port"]
                    if not node or not port:
                        continue
                    node.config = _sync_link_port(node.config or {}, port, l.link_type or "trunk")

    return {"link_updates": link_updates, "changed": len(link_updates), "failures": failures}


def _port_sort_key(name: str):
    """端口名排序键: 按名称末尾编号排序(GE0/0/2 < GE0/0/10), 无编号的排最后"""
    m = re.search(r"(\d+)$", (name or "").strip())
    return (0, int(m.group(1))) if m else (1, 0)


def _sync_link_port(cfg: dict, port: str, link_type: str) -> dict:
    """把链路端口同步进节点配置: 已有该端口条目则类型与链路对齐, 没有则追加"""
    known = [int(v.get("id")) for v in ((cfg.get("vlan") or {}).get("vlans") or []) if v.get("id")]
    cfg = dict(cfg)
    vlan = dict(cfg.get("vlan") or {})
    itfs = list(vlan.get("interfaces") or [])
    existing = next(
        (i for i in itfs if (i.get("interface") or "").strip().lower() == port.strip().lower()),
        None,
    )
    if existing is not None:
        if link_type == "trunk":
            existing["type"] = "trunk"
            existing.pop("vlan_id", None)
            if not existing.get("trunk_vlans"):
                existing["trunk_vlans"] = known or None
        else:
            existing["type"] = "access"
            existing.pop("trunk_vlans", None)
            if existing.get("vlan_id") is None:
                existing["vlan_id"] = known[0] if known else None
    else:
        entry: dict = {"interface": port, "type": link_type}
        if link_type == "trunk":
            entry["trunk_vlans"] = known or None
        else:
            entry["vlan_id"] = known[0] if known else None
        itfs.append(entry)
    vlan["interfaces"] = itfs
    cfg["vlan"] = vlan
    return cfg


def node_summary(node, vendor_names: dict | None = None) -> dict:
    """节点摘要 — 供体检/生成面板展示"""
    cfg = node.config or {}
    port_count = 0
    vlan = cfg.get("vlan") or {}
    defined = len(vlan.get("vlans") or [])
    configured = len(vlan.get("interfaces") or [])
    mgmt = cfg.get("basic") or {}
    dhcp = mgmt.get("dhcp_global") or {}
    return {
        "node_key": node.node_key,
        "name": node_display_name(node),
        "vendor": cfg.get("vendor", "-"),
        "device_type": cfg.get("device_type", "-"),
        "mgmt_ip": _mgmt_ip(cfg) or "",
        "device_id": node.device_id,
        "vlan_count": defined,
        "interface_count": configured,
        "dhcp_enable": bool(dhcp.get("enable")),
        "port_count": port_count,
    }
