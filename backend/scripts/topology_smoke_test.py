"""拓扑服务离线冒烟测试 — 不依赖 HTTP 服务, 直接验证生成/体检逻辑

用法:
    python scripts/topology_smoke_test.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import topology_service as ts  # noqa: E402


class FakeNode:
    def __init__(self, key, name, config, device_id=None):
        self.node_key = key
        self.name = name
        self.config = config
        self.device_id = device_id


class FakeLink:
    def __init__(self, lid, s, sp, d, dp, lt="trunk"):
        self.id = lid
        self.src_node_key = s
        self.src_port = sp
        self.dst_node_key = d
        self.dst_port = dp
        self.link_type = lt


def main() -> int:
    failures: list[str] = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            failures.append(msg)

    print("[1] 默认属性骨架 → 生成配置")
    core_cfg = ts.default_node_config("huawei", "switch", "SW-Core")
    core_cfg["basic"]["mgmt_interface"]["ip_address"] = "192.168.1.1"
    core_cfg["vlan"]["vlans"] = [{"id": 1, "name": "Default"}, {"id": 10, "name": "Mgmt"}]
    core_cfg["vlan"]["vlanifs"] = [{"vlan_id": 10, "ip_address": "192.168.10.1", "mask": "255.255.255.0"}]
    core = FakeNode("node-1", "SW-Core", core_cfg)
    r = ts.generate_for_node(core)
    check(r["success"], "生成成功")
    check("sysname" in r["config_text"], "配置含 sysname(hostname)")
    check(len(r["config_text"]) > 50, f"配置长度 {len(r['config_text'])}")

    print("[2] 四厂商均可生成")
    for vendor in ("huawei", "h3c", "ruijie", "maipu"):
        cfg = ts.default_node_config(vendor, "switch", f"SW-{vendor}")
        cfg["vlan"]["vlans"] = [{"id": 1, "name": "Default"}, {"id": 20, "name": "Data"}]
        cfg["vlan"]["interfaces"] = [{"interface": ts.port_name(vendor, 1), "type": "access", "vlan_id": 20}]
        rr = ts.generate_for_node(FakeNode("n", f"SW-{vendor}", cfg))
        check(rr["success"], f"{vendor} 生成成功")

    print("[3] 端口命名规则")
    check(ts.port_name("huawei", 1) == "GigabitEthernet0/0/1", "华为 GE0/0/1")
    check(ts.port_name("h3c", 1) == "GigabitEthernet1/0/1", "H3C GE1/0/1")
    check(ts.port_name("ruijie", 1) == "GigabitEthernet0/1", "锐捷 GE0/1")

    print("[4] 体检: 端口占用 / IP 冲突 / VLAN 未定义 / 链路不一致")
    core_cfg["vlan"]["interfaces"] = [
        {"interface": "GigabitEthernet0/0/1", "type": "trunk", "trunk_vlans": [1, 10]}
    ]
    acc = FakeNode(
        "node-2",
        "SW-Acc",
        {
            "vendor": "huawei",
            "device_type": "switch",
            "vlan": {
                "vlans": [{"id": 1, "name": "Default"}, {"id": 10, "name": "Mgmt"}],
                "interfaces": [
                    {"interface": "GigabitEthernet0/0/1", "type": "trunk", "trunk_vlans": [1, 10, 30]},
                    {"interface": "GigabitEthernet0/0/2", "type": "access", "vlan_id": 99},
                ],
            },
            "basic": {"mgmt_interface": {"enable": True, "ip_address": "192.168.1.1"}},
        },
    )
    links = [
        FakeLink("l1", "node-1", "GigabitEthernet0/0/1", "node-2", "GigabitEthernet0/0/1"),
        FakeLink("l2", "node-1", "GigabitEthernet0/0/1", "node-2", "GigabitEthernet0/0/1"),
        FakeLink("l4", "node-1", "GigabitEthernet0/0/9", "node-2", "GigabitEthernet0/0/8", "access"),
    ]
    res = ts.check_topology([core, acc], links, managed_hosts={"192.168.1.9"})
    msgs = [i["message"] for i in res["issues"]]
    joined = " | ".join(msgs)
    check(any("占用" in m for m in msgs), "检出端口重复占用")
    check(any("192.168.1.1" in m and "多处使用" in m for m in msgs), "检出 IP 冲突")
    check(any("未定义的 VLAN 30" in m for m in msgs), "检出 VLAN 30 未定义")
    check(any("VLAN 99" in m for m in msgs), "检出 VLAN 99 未定义")
    check(any("不一致" in m for m in msgs), "检出链路两端 trunk VLAN 不一致")
    check(any("未在节点" in m and "接口配置中定义" in m for m in msgs), "检出链路端口未在接口配置中定义")
    check(res["summary"]["error"] >= 2, f"error 计数 {res['summary']['error']}")
    print("      体检摘要:", res["summary"])
    if failures:
        print("      (问题清单)", joined[:500])

    print("[5] 自动补全端口")
    l3 = FakeLink("l3", "node-1", None, "node-2", None)
    upd = ts.autofill_link_ports([core, acc], [l3], apply_config=True)
    check(upd["changed"] == 1, "补全 1 条链路")
    check(l3.src_port == "GigabitEthernet0/0/2", f"源端口自动续号 → {l3.src_port}")
    check(l3.dst_port == "GigabitEthernet0/0/3", f"对端端口自动续号 → {l3.dst_port}")
    check(any(
        (i.get("interface") or "") == l3.src_port
        for i in (core.config["vlan"].get("interfaces") or [])
    ), "端口已写入节点接口配置")
    check(any(
        (i.get("interface") or "") == l3.dst_port
        for i in (acc.config["vlan"].get("interfaces") or [])
    ), "对端端口已写入接口配置")

    print("[6] 未指定端口的链路体检提示")
    l5 = FakeLink("l5", "node-1", None, "node-2", None)
    res2 = ts.check_topology([core, acc], [l5], set())
    check(any("未指定端口" in i["message"] for i in res2["issues"]), "提示用了“按链路生成端口配置”")

    print()
    if failures:
        print(f"结果: {len(failures)} 项失败")
        return 1
    print("结果: 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
