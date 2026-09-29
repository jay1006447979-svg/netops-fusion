"""迈普配置生成器 — 命令与思科风格接近

迈普关键特点:
  hostname (非 sysname)
  crypto key generate rsa
  line vty (非 user-interface)
  switchport 风格接口配置
  ip route (非 ip route-static)
"""

from __future__ import annotations

from app.core.registry import vendor_registry
from app.vendors.base import BaseConfigGenerator


@vendor_registry.register("maipu", device_types=["switch", "router"])
class MaipuGenerator(BaseConfigGenerator):
    vendor = "maipu"

    def generate_basic(self, config: dict) -> str:
        lines = ["#\n", "# 基础配置\n", "#\n"]

        if "hostname" in config:
            lines.append(f"hostname {config['hostname']}\n")

        pwd = config.get("password")
        if pwd:
            enc = "5" if pwd.get("encrypted") else "0"
            lines.append(f"enable password {enc} {pwd['value']}\n")

        ssh = config.get("ssh")
        if ssh and ssh.get("enable", False):
            lines.append("\n#\n# SSH配置\n#\n")
            lines.append("ip ssh server\n")
            lines.append(f"ip ssh port {ssh.get('port', 22)}\n")
            lines.append(f"ip ssh timeout {ssh.get('timeout', 60)}\n")
            lines.append("crypto key generate rsa\n")

        telnet = config.get("telnet")
        if telnet and telnet.get("enable", False):
            lines.append("\n#\n# Telnet配置\n#\n")
            lines.append("ip telnet server\n")
            lines.append("line vty 0 4\n")
            lines.append(" login local\n")

        console = config.get("console")
        if console and console.get("enable", False):
            lines.append("\n#\n# Console配置\n#\n")
            lines.append("line console 0\n")
            lines.append(f" exec-timeout {console.get('idle_timeout', 10)}\n")
            if console.get("password"):
                lines.append(f" password {console['password']}\n")

        user = config.get("user")
        if user and user.get("enable", False):
            lines.append("\n#\n# 用户配置\n#\n")
            username = user.get("username", "admin")
            enc = "5" if user.get("encrypted") else "0"
            lines.append(f"username {username} privilege {user.get('level', 15)}\n")
            lines.append(f"username {username} password {enc} {user.get('password', 'admin@123')}\n")

        ntp = config.get("ntp")
        if ntp and ntp.get("enable", False):
            lines.append("\n#\n# NTP配置\n#\n")
            lines.append(f"clock timezone {ntp.get('timezone', 'UTC+8')}\n")
            for srv in ntp.get("servers") or []:
                cmd = f"ntp server {srv['ip']}"
                if srv.get("prefer"):
                    cmd += " prefer"
                lines.append(cmd + "\n")

        snmp = config.get("snmp")
        if snmp and snmp.get("enable", False):
            lines.append("\n#\n# SNMP配置\n#\n")
            if snmp.get("community_read"):
                lines.append(f"snmp-server community {snmp['community_read']} ro\n")
            if snmp.get("community_write"):
                lines.append(f"snmp-server community {snmp['community_write']} rw\n")
            if snmp.get("trap_enable") and snmp.get("trap_host"):
                lines.append(f"snmp-server host {snmp['trap_host']} traps\n")

        log = config.get("log")
        if log:
            lines.append("\n#\n# 日志配置\n#\n")
            if log.get("host"):
                lines.append(f"logging {log['host']}\n")

        mgmt = config.get("mgmt_interface")
        if mgmt and mgmt.get("enable", False):
            lines.append("\n#\n# 管理接口配置\n#\n")
            iface = mgmt.get("interface", "vlan 1")
            lines.append(f"interface {iface}\n")
            if mgmt.get("ip_address"):
                lines.append(f" ip address {mgmt['ip_address']} {mgmt.get('mask', '255.255.255.0')}\n")
            lines.append(" exit\n")
            if mgmt.get("gateway"):
                lines.append(f"ip route 0.0.0.0 0.0.0.0 {mgmt['gateway']}\n")

        dns = config.get("dns")
        if dns and dns.get("enable", False):
            lines.append("\n#\n# DNS配置\n#\n")
            if dns.get("resolve_enable", False):
                lines.append("ip domain lookup\n")
            for srv in dns.get("servers") or []:
                lines.append(f"ip name-server {srv}\n")
            if dns.get("domain"):
                lines.append(f"ip domain name {dns['domain']}\n")

        return "".join(lines)

    def generate_vlan(self, config: dict) -> str:
        lines = ["\n#\n# VLAN配置\n", "#\n"]

        for vlan in config.get("vlans") or []:
            if isinstance(vlan, dict):
                lines.append(f"vlan {vlan['id']}\n")
                if vlan.get("name"):
                    lines.append(f" name {vlan['name']}\n")
                lines.append(" exit\n")

        for iface in config.get("interfaces") or []:
            lines.append(f"interface {iface['interface']}\n")
            t = iface.get("type", "access")
            lines.append(f" switchport mode {t}\n")
            if t == "access" and iface.get("vlan_id"):
                lines.append(f" switchport access vlan {iface['vlan_id']}\n")
            elif t == "trunk":
                if iface.get("trunk_vlans"):
                    lines.append(f" switchport trunk allowed vlan {','.join(map(str, iface['trunk_vlans']))}\n")
                if iface.get("pvid"):
                    lines.append(f" switchport trunk native vlan {iface['pvid']}\n")
            lines.append(" exit\n")

        for vf in config.get("vlanifs") or []:
            lines.append(f"interface vlan {vf['vlan_id']}\n")
            if vf.get("description"):
                lines.append(f" description {vf['description']}\n")
            lines.append(f" ip address {vf['ip_address']} {vf.get('mask', '255.255.255.0')}\n")
            lines.append(" exit\n")

        stp = config.get("stp")
        if stp and stp.get("enable", False):
            lines.append("\n#\n# STP配置\n#\n")
            lines.append(f"spanning-tree mode {stp.get('mode', 'stp')}\n")
            lines.append("spanning-tree\n")

        return "".join(lines)

    def generate_routing(self, config: dict) -> str:
        lines = ["\n#\n# 路由配置\n", "#\n"]

        for route in config.get("static_routes") or []:
            cmd = f"ip route {route['dest_network']} {route['mask']}"
            if route.get("next_hop"):
                cmd += f" {route['next_hop']}"
            if route.get("preference"):
                cmd += f" {route['preference']}"
            lines.append(cmd + "\n")

        dr = config.get("default_route")
        if dr and dr.get("next_hop"):
            lines.append(f"ip route 0.0.0.0 0.0.0.0 {dr['next_hop']}\n")

        ospf = config.get("ospf")
        if ospf:
            lines.append("\n#\n# OSPF配置\n#\n")
            cmd = f"router ospf {ospf.get('process_id', 1)}"
            if ospf.get("router_id"):
                cmd += f" router-id {ospf['router_id']}"
            lines.append(cmd + "\n")
            for net in ospf.get("networks") or []:
                lines.append(f" network {net['address']} {net.get('mask', '0.0.0.255')} area {net.get('area', '0')}\n")

        bgp = config.get("bgp")
        if bgp:
            lines.append("\n#\n# BGP配置\n#\n")
            lines.append(f"router bgp {bgp['as_number']}\n")
            for peer in bgp.get("peers") or []:
                lines.append(f" neighbor {peer['ip']} remote-as {peer['as_number']}\n")

        return "".join(lines)

    def generate_security(self, config: dict) -> str:
        lines = ["\n#\n# 安全配置\n", "#\n"]

        for acl in config.get("acls") or []:
            lines.append(f"ip access-list {'extended' if acl['number'] >= 3000 else 'standard'} {acl['number']}\n")
            for rule in acl.get("rules") or []:
                action = rule.get("action", "permit")
                proto = rule.get("protocol", "ip")
                src = rule.get("source", "any")
                dst = rule.get("destination", "any")
                if acl["number"] < 3000:
                    lines.append(f" {action} {src}\n")
                else:
                    line = f" {action} {proto} {src}"
                    if dst != "any":
                        line += f" {dst}"
                    if rule.get("dest_port") and proto in ("tcp", "udp"):
                        line += f" eq {rule['dest_port']}"
                    lines.append(line + "\n")
            lines.append(" exit\n")

        for ps in config.get("port_security") or []:
            lines.append(f"interface {ps['interface']}\n")
            lines.append(" switchport port-security\n")
            lines.append(f" switchport port-security maximum {ps.get('max_mac', 1)}\n")
            lines.append(f" switchport port-security violation {ps.get('protect_action', 'protect')}\n")
            lines.append(" exit\n")

        ds = config.get("dhcp_snooping")
        if ds and ds.get("enable", False):
            lines.append("ip dhcp snooping\n")
            if ds.get("vlans"):
                lines.append(f"ip dhcp snooping vlan {' '.join(map(str, ds['vlans']))}\n")

        return "".join(lines)

    def generate_interface(self, config: dict) -> str:
        lines = ["\n#\n# 接口配置\n", "#\n"]

        for trunk in config.get("eth_trunks") or []:
            lines.append(f"interface aggregateport {trunk['trunk_id']}\n")
            if trunk.get("description"):
                lines.append(f" description {trunk['description']}\n")
            plt = trunk.get("port_link_type", "trunk")
            lines.append(f" switchport mode {plt}\n")
            if plt == "trunk" and trunk.get("trunk_vlans"):
                lines.append(f" switchport trunk allowed vlan {','.join(map(str, trunk['trunk_vlans']))}\n")
            lines.append(" exit\n")
            for port in trunk.get("member_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(f" port-group {trunk['trunk_id']}\n")
                lines.append(" exit\n")

        lldp = config.get("lldp")
        if lldp and lldp.get("enable", False):
            lines.append("\n#\n# LLDP配置\n#\n")
            lines.append("lldp enable\n")
            lines.append(f"lldp timer {lldp.get('interval', 30)}\n")
            lines.append(f"lldp holdtime {lldp.get('holdtime', 120)}\n")

        lbd = config.get("loopback_detection")
        if lbd and lbd.get("enable", False):
            lines.append("\n#\n# 环路检测配置\n#\n")
            lines.append("loopback-detection enable\n")
            lines.append(f"loopback-detection interval {lbd.get('interval', 5)}\n")
            if lbd.get("vlan_ids"):
                lines.append(f"loopback-detect vlan {' '.join(map(str, lbd['vlan_ids']))}\n")
            lines.append(f"loopback-detection action {lbd.get('action', 'block')}\n")

        for rl in config.get("rate_limits") or []:
            lines.append(f"interface {rl['interface']}\n")
            if rl.get("cir_in"):
                lines.append(f" rate-limit input {rl['cir_in']}\n")
            if rl.get("cir_out"):
                lines.append(f" rate-limit output {rl['cir_out']}\n")
            lines.append(" exit\n")

        return "".join(lines)
