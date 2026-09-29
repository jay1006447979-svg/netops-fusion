"""子网计算器 — IP子网计算/子网划分/CIDR转换"""

from __future__ import annotations

import ipaddress
from typing import Optional


class SubnetCalculator:
    @staticmethod
    def calculate(ip: str, mask: str = "24") -> dict:
        """计算子网信息"""
        if mask.isdigit():
            cidr = f"{ip}/{int(mask)}"
        else:
            cidr = f"{ip}/{mask}"
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError as e:
            return {"error": str(e)}

        return {
            "network": str(net.network_address),
            "mask": str(net.netmask),
            "wildcard": str(net.hostmask),
            "broadcast": str(net.broadcast_address),
            "prefix_length": net.prefixlen,
            "num_addresses": net.num_addresses,
            "num_hosts": net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses,
            "first_host": str(net.network_address + 1) if net.prefixlen < 31 else str(net.network_address),
            "last_host": str(net.broadcast_address - 1) if net.prefixlen < 31 else str(net.broadcast_address),
            "is_private": net.is_private,
        }

    @staticmethod
    def subnet_divide(ip: str, prefix: int, new_prefix: int) -> list[dict]:
        """子网划分"""
        try:
            net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
            subnets = list(net.subnets(new_prefix=new_prefix))
        except ValueError as e:
            return [{"error": str(e)}]

        return [
            {
                "network": str(s.network_address),
                "mask": str(s.netmask),
                "broadcast": str(s.broadcast_address),
                "range": f"{s.network_address + 1} - {s.broadcast_address - 1}",
                "num_hosts": s.num_addresses - 2,
            }
            for s in subnets
        ]

    @staticmethod
    def ip_range_to_cidr(start: str, end: str) -> list[str]:
        """IP范围转CIDR"""
        try:
            start_ip = ipaddress.ip_address(start)
            end_ip = ipaddress.ip_address(end)
            nets = list(ipaddress.summarize_address_range(start_ip, end_ip))
            return [str(n) for n in nets]
        except ValueError as e:
            return [f"error: {e}"]

    @staticmethod
    def convert_ip_format(ip: str, target: str = "binary") -> str:
        """IP格式转换: binary/hex/decimal"""
        try:
            addr = ipaddress.ip_address(ip)
            addr_int = int(addr)
        except ValueError as e:
            return f"error: {e}"

        if target == "binary":
            return bin(addr_int)
        elif target == "hex":
            return hex(addr_int)
        elif target == "decimal":
            return str(addr_int)
        return str(addr)


subnet_calculator = SubnetCalculator()
