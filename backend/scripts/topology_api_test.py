"""拓扑功能端到端 API 测试 — 直接打真实 HTTP 服务

用法:
    python scripts/topology_api_test.py [base_url]      # 默认 http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
FAILS: list[str] = []


def call(method: str, path: str, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return json.loads(raw)
            return {"_binary": len(raw), "_ctype": ct, "_cd": r.headers.get("Content-Disposition", "")}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return {"success": False, "detail": json.loads(raw).get("detail"), "_status": e.code}
        except Exception:
            return {"success": False, "detail": raw[:200], "_status": e.code}


def check(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        FAILS.append(msg)


def main() -> int:
    print(f"目标服务: {BASE}")

    print("[1] 新建拓扑图")
    r = call("POST", "/api/topologies", {"name": "__e2e_拓扑测试", "description": "自动化测试"})
    check(r.get("success"), "创建拓扑成功")
    tid = r.get("id")
    check(bool(tid), f"返回拓扑 id {tid}")
    if not tid:
        return 1

    print("[2] 添加 3 台设备")
    nodes = {}
    plan = [
        ("SW-Core", "huawei", "switch", "192.168.10.1"),
        ("SW-Acc", "huawei", "switch", "192.168.10.2"),
        ("AP-01", "h3c", "ap", "192.168.10.3"),
    ]
    for i, (name, vendor, dtype, ip) in enumerate(plan):
        r = call("POST", f"/api/topologies/{tid}/nodes",
                 {"name": name, "vendor": vendor, "device_type": dtype, "x": 60 + i * 220, "y": 60})
        ok = r.get("success")
        check(ok, f"添加节点 {name}")
        if not ok:
            continue
        node = r["node"]
        nodes[name] = node
        cfg = node["config"]
        cfg["basic"]["mgmt_interface"]["ip_address"] = ip
        cfg["vlan"]["vlans"] = [{"id": 1, "name": "Default"}, {"id": 10, "name": "Mgmt"}, {"id": 20, "name": "Data"}]
        cfg["vlan"]["interfaces"] = [
            {"interface": "GigabitEthernet0/0/24", "type": "trunk", "trunk_vlans": [1, 10, 20]}
            if vendor == "huawei" else
            {"interface": "GigabitEthernet1/0/24", "type": "trunk", "trunk_vlans": [1, 10, 20]}
        ]
        up = call("PUT", f"/api/topologies/{tid}/nodes/{node['id']}", {"config": cfg, "name": name})
        check(up.get("success"), f"{name} 属性保存成功 (管理IP {ip})")

    print("[3] 连线（端口应自动分配）")
    core = nodes.get("SW-Core", {}).get("node_key")
    acc = nodes.get("SW-Acc", {}).get("node_key")
    ap = nodes.get("AP-01", {}).get("node_key")
    l1 = call("POST", f"/api/topologies/{tid}/links",
              {"src_node_key": core, "dst_node_key": acc, "link_type": "trunk"})
    check(l1.get("success") and l1["link"]["src_port"], f"核心→接入链路, 端口 {l1.get('link', {}).get('src_port')} ←→ {l1.get('link', {}).get('dst_port')}")
    l2 = call("POST", f"/api/topologies/{tid}/links",
              {"src_node_key": acc, "dst_node_key": ap, "link_type": "access"})
    check(l2.get("success"), f"接入→AP 链路, 端口 {l2.get('link', {}).get('src_port')} ←→ {l2.get('link', {}).get('dst_port')}")

    print("[4] 读取拓扑")
    r = call("GET", f"/api/topologies/{tid}")
    check(len(r.get("nodes", [])) == 3, f"节点数 3 (实际 {len(r.get('nodes', []))})")
    check(len(r.get("links", [])) == 2, f"链路数 2 (实际 {len(r.get('links', []))})")
    check(r.get("nodes", [{}])[0].get("mgmt_ip") is not None, "节点摘要含管理 IP")

    print("[5] 拓扑体检")
    r = call("POST", f"/api/topologies/{tid}/check", {})
    s = r.get("summary", {})
    check(r.get("success"), "体检接口可用")
    print(f"      摘要: 错误 {s.get('error')} / 警告 {s.get('warn')} / 提示 {s.get('info')}")
    for i in (r.get("issues") or [])[:5]:
        print(f"      - [{i['level']}] {i['message']}")

    print("[6] 整图生成")
    r = call("POST", f"/api/topologies/{tid}/generate", {})
    check(r.get("total") == 3 and r.get("ok") == 3, f"3 台全部生成成功 (ok={r.get('ok')}/{r.get('total')})")
    for x in r.get("results", []):
        check(len(x.get("config_text", "")) > 30, f"{x['name']} 配置 {len(x.get('config_text',''))} 字符")
    core_cfg = next((x["config_text"] for x in r.get("results", []) if x["name"] == "SW-Core"), "")
    check("sysname SW-Core" in core_cfg, "配置内含 sysname SW-Core")
    check("GigabitEthernet0/0/24" in core_cfg, "配置内含接口配置")

    print("[7] 单节点生成")
    r = call("POST", f"/api/topologies/{tid}/generate", {"node_keys": [core]})
    check(r.get("total") == 1, "只生成选中节点")

    print("[8] 导出 ZIP")
    r = call("GET", f"/api/topologies/{tid}/export")
    check(r.get("_binary", 0) > 200, f"ZIP 字节数 {r.get('_binary')}")
    check("zip" in (r.get("_ctype") or ""), f"Content-Type {r.get('_ctype')}")

    print("[9] 风险校验: 端口冲突 / IP 冲突 / VLAN 未定义")
    snap = call("GET", f"/api/topologies/{tid}")
    core_node = next(n for n in snap["nodes"] if n["name"] == "SW-Core")
    acc_node = next(n for n in snap["nodes"] if n["name"] == "SW-Acc")
    link = snap["links"][0]
    # 制造端口占用: 新增一条与已有链路同端口的链路
    call("POST", f"/api/topologies/{tid}/links", {
        "src_node_key": link["src_node_key"], "src_port": link["src_port"],
        "dst_node_key": link["dst_node_key"], "dst_port": link["dst_port"],
        "link_type": "trunk",
    })
    # 制造 IP 冲突 + VLAN 未定义
    cfg = core_node["config"]
    cfg["vlan"]["interfaces"].append({"interface": "GigabitEthernet0/0/23", "type": "access", "vlan_id": 99})
    call("PUT", f"/api/topologies/{tid}/nodes/{core_node['id']}", {"config": cfg})
    acc_cfg = acc_node["config"]
    acc_cfg["basic"]["mgmt_interface"]["ip_address"] = "192.168.10.1"
    call("PUT", f"/api/topologies/{tid}/nodes/{acc_node['id']}", {"config": acc_cfg})

    r = call("POST", f"/api/topologies/{tid}/check", {})
    msgs = [i["message"] for i in (r.get("issues") or [])]
    check(any("占用" in m for m in msgs), "检出端口被多条链路占用")
    check(any("192.168.10.1" in m and "多处使用" in m for m in msgs), "检出 IP 冲突")
    check(any("99" in m and "未定义" in m for m in msgs), "检出 VLAN 99 未定义")

    print("[10] 清理测试数据")
    r = call("DELETE", f"/api/topologies/{tid}")
    check(r.get("success"), "删除拓扑成功")
    r = call("GET", f"/api/topologies/{tid}")
    check(r.get("_status") == 404 or not r.get("success"), "删除后不可访问")

    print()
    if FAILS:
        print(f"结果: {len(FAILS)} 项失败")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("结果: 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
