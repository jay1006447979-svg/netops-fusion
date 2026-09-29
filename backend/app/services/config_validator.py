"""配置校验服务 — IP/掩码/VLAN ID/主机名/密码强度校验"""

from __future__ import annotations

import ipaddress
import re


class ConfigValidator:
    """配置参数校验器"""

    @staticmethod
    def validate_ip(ip: str) -> bool:
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_mask(mask: str) -> bool:
        if not mask:
            return False
        try:
            if mask.isdigit():
                prefix = int(mask)
                return 0 <= prefix <= 32
            net = ipaddress.ip_network(f"0.0.0.0/{mask}", strict=False)
            return str(net.netmask) == mask
        except ValueError:
            return False

    @staticmethod
    def validate_cidr(cidr: str) -> bool:
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_vlan_id(vlan_id: int) -> bool:
        return isinstance(vlan_id, int) and 1 <= vlan_id <= 4094

    @staticmethod
    def validate_hostname(hostname: str) -> bool:
        if not hostname or len(hostname) > 32:
            return False
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9\-_]*$", hostname))

    @staticmethod
    def validate_mac(mac: str) -> bool:
        return bool(re.match(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$", mac))

    @staticmethod
    def validate_password_strength(password: str) -> dict:
        result = {"valid": True, "score": 0, "issues": []}
        if len(password) < 8:
            result["issues"].append("密码长度不足8位")
            result["score"] += 1
        else:
            result["score"] += 2
        if re.search(r"[A-Z]", password):
            result["score"] += 1
        if re.search(r"[a-z]", password):
            result["score"] += 1
        if re.search(r"\d", password):
            result["score"] += 1
        if re.search(r"[!@#$%^&*()\-_=+]", password):
            result["score"] += 1
        if result["score"] < 3:
            result["valid"] = False
            result["issues"].append("密码强度不足, 建议包含大小写字母/数字/特殊字符")
        return result

    def validate(self, config: dict) -> dict:
        """校验完整配置, 返回 {valid, errors, warnings}"""
        errors = []
        warnings = []

        basic = config.get("basic", {})
        if isinstance(basic, dict):
            hostname = config.get("hostname") or basic.get("hostname")
            if hostname and not self.validate_hostname(hostname):
                errors.append(f"无效的主机名: {hostname}")

            pwd = basic.get("password")
            if pwd and isinstance(pwd, dict):
                pw = self.validate_password_strength(pwd.get("value", ""))
                if not pw["valid"]:
                    warnings.append(f"密码强度: {', '.join(pw['issues'])}")

            mgmt = basic.get("mgmt_interface")
            if mgmt and isinstance(mgmt, dict):
                if mgmt.get("ip_address") and not self.validate_ip(mgmt["ip_address"]):
                    errors.append(f"无效的管理IP: {mgmt['ip_address']}")
                if mgmt.get("mask") and not self.validate_mask(mgmt["mask"]):
                    errors.append(f"无效的子网掩码: {mgmt['mask']}")
                if mgmt.get("gateway") and not self.validate_ip(mgmt["gateway"]):
                    errors.append(f"无效的网关: {mgmt['gateway']}")

        vlan = config.get("vlan", {})
        if isinstance(vlan, dict):
            for vf in vlan.get("vlanifs") or []:
                if vf.get("ip_address") and not self.validate_ip(vf["ip_address"]):
                    errors.append(f"VLANIF无效IP: {vf['ip_address']}")
                if vf.get("mask") and not self.validate_mask(vf["mask"]):
                    errors.append(f"VLANIF无效掩码: {vf['mask']}")

        routing = config.get("routing", {})
        if isinstance(routing, dict):
            for route in routing.get("static_routes") or []:
                if route.get("dest_network") and not self.validate_ip(route["dest_network"]):
                    errors.append(f"静态路由无效目的网络: {route['dest_network']}")
                if route.get("next_hop") and not self.validate_ip(route["next_hop"]):
                    errors.append(f"静态路由无效下一跳: {route['next_hop']}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


validator = ConfigValidator()
