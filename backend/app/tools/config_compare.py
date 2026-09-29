"""配置比较工具 — 配置差异对比、华为/H3C命令转换"""

from __future__ import annotations

import difflib
from typing import Optional


class ConfigCompare:
    """配置比较与转换"""

    @staticmethod
    def compare(config1: str, config2: str, context: int = 3) -> dict:
        """配置差异对比"""
        lines1 = config1.splitlines()
        lines2 = config2.splitlines()

        differ = difflib.HtmlDiff()
        html_diff = differ.make_table(lines1, lines2, context=context)

        diff_lines = list(difflib.unified_diff(lines1, lines2, lineterm=""))
        text_diff = "\n".join(diff_lines)

        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

        return {
            "text_diff": text_diff,
            "html_diff": html_diff,
            "added": added,
            "removed": removed,
            "identical": len(diff_lines) == 0,
        }

    # 华为 -> H3C 命令转换映射
    HUAWEI_TO_H3C = {
        "interface Vlanif": "interface Vlan-interface",
        "interface Eth-Trunk": "interface Bridge-Aggregation ",
        "stelnet server enable": "ssh server enable",
        "port trunk allow-pass vlan": "port trunk permit vlan",
        "port default vlan": "port access vlan",
        "port hybrid untagged vlan": "port hybrid vlan",
        "port hybrid tagged vlan": "port hybrid vlan",
        " eth-trunk ": " port link-aggregation group ",
        "mode lacp-static": "link-aggregation mode dynamic",
        "mode lacp-dynamic": "link-aggregation mode dynamic",
        "mode manual": "link-aggregation mode static",
        "super password cipher": "super password cipher",
        "super password simple": "super password simple",
        "local-user": "local-user",
        "privilege level": "authorization-attribute level",
        "port-security protect-action": "port-security violation",
        "port-security max-mac-num": "port-security max-mac-count",
        "port-security mac-address sticky": "port-security mac-address sticky",
        "lldp enable": "lldp global enable",
        "lldp mode": "lldp work",
        "lldp transmit interval": "lldp timer tx-interval",
        "lldp transmit holdtime": "lldp timer tx-ttl",
        "ntp-service unicast-server": "ntp-service unicast-server",
        "port link-type": "port link-type",
        "vlan batch": "vlan",
        "user-interface vty": "user-interface vty",
        "user-interface console": "user-interface console",
        " authentication-mode aaa": " authentication-mode scheme",
    }

    @staticmethod
    def convert_huawei_to_h3c(config: str) -> str:
        """华为配置转H3C"""
        result = config
        for hw_cmd, h3c_cmd in ConfigCompare.HUAWEI_TO_H3C.items():
            result = result.replace(hw_cmd, h3c_cmd)

        # 处理 hybrid untagged/tagged 的参数顺序
        # 华为: port hybrid untagged vlan 10 20
        # H3C: port hybrid vlan 10,20 untagged
        import re

        def _hybrid_untagged(m):
            vlans = m.group(1).split()
            return f"port hybrid vlan {','.join(vlans)} untagged"

        result = re.sub(
            r"port hybrid vlan (.+) untagged", _hybrid_untagged, result
        )

        def _hybrid_tagged(m):
            vlans = m.group(1).split()
            return f"port hybrid vlan {','.join(vlans)} tagged"

        result = re.sub(
            r"port hybrid vlan (.+) tagged", _hybrid_tagged, result
        )

        # 权限级别转换 0-15 -> 0-3
        def _level(m):
            level = int(m.group(1))
            h3c_level = min(3, (level // 4) + 1) if level else 0
            return f"authorization-attribute level {h3c_level}"

        result = re.sub(r"privilege level (\d+)", _level, result)

        return result


config_compare = ConfigCompare()
