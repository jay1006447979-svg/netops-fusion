"""H3C 配置生成器 — 命令差异参照 NetOps-toolkit

与华为的关键差异:
  Vlanif{N}        -> Vlan-interface{N}
  Eth-Trunk{N}     -> Bridge-Aggregation {N}
  stelnet server enable -> ssh server enable
  port trunk allow-pass -> port trunk permit
  port default vlan     -> port access vlan
  port hybrid untagged vlan X -> port hybrid vlan X untagged
  eth-trunk N     -> port link-aggregation group N
  mode lacp-static -> link-aggregation mode dynamic
  level 15 (0-15) -> level 3 (0-3)
"""

from __future__ import annotations

from app.core.registry import vendor_registry
from app.vendors.base import BaseConfigGenerator


@vendor_registry.register("h3c", device_types=["switch", "router", "ap"])
class H3CGenerator(BaseConfigGenerator):
    vendor = "h3c"

    # ======================== 基础配置 ========================
    def generate_basic(self, config: dict) -> str:
        lines = ["#\n", "# 基础配置\n", "#\n"]

        if "hostname" in config:
            lines.append(f"sysname {config['hostname']}\n")

        pwd = config.get("password")
        if pwd:
            enc = "cipher" if pwd.get("encrypted") else "simple"
            lines.append(f"super password {enc} {pwd['value']}\n")

        ssh = config.get("ssh")
        if ssh and ssh.get("enable", False):
            lines.append("\n#\n# SSH配置\n#\n")
            lines.append("ssh server enable\n")
            lines.append(f"ssh server port {ssh.get('port', 22)}\n")
            lines.append(f"ssh server timeout {ssh.get('timeout', 60)}\n")
            lines.append(f"ssh server authentication-timeout {ssh.get('timeout', 60)}\n")
            lines.append(f"ssh server max-auth-times {ssh.get('max_auth_tries', 5)}\n")
            version = ssh.get("version", 2)
            lines.append(f"ssh server compatible-ssh1x disable\n")

        telnet = config.get("telnet")
        if telnet and telnet.get("enable", False):
            lines.append("\n#\n# Telnet配置\n#\n")
            lines.append("telnet server enable\n")
            lines.append("user-interface vty 0 4\n")
            lines.append(" authentication-mode scheme\n")
            lines.append(" protocol inbound all\n")
            lines.append(" quit\n")

        console = config.get("console")
        if console and console.get("enable", False):
            lines.append("\n#\n# Console配置\n#\n")
            lines.append("user-interface console 0\n")
            auth = console.get("authentication", "password")
            if auth == "password" and console.get("password"):
                lines.append(" authentication-mode password\n")
                lines.append(f" set authentication password simple {console['password']}\n")
            elif auth == "aaa":
                lines.append(" authentication-mode scheme\n")
            lines.append(f" idle-timeout {console.get('idle_timeout', 10)} 0\n")
            lines.append(" quit\n")

        user = config.get("user")
        if user and user.get("enable", False):
            lines.append("\n#\n# 用户配置\n#\n")
            username = user.get("username", "admin")
            enc = "cipher" if user.get("encrypted") else "simple"
            lines.append(f"local-user {username}\n")
            lines.append(f" password {enc} {user.get('password', 'admin@123')}\n")
            # H3C 权限 0-3, 华为 0-15, 需转换
            hw_level = user.get("level", 15)
            h3c_level = min(3, (hw_level // 4) + 1) if hw_level else 0
            lines.append(f" authorization-attribute level {h3c_level}\n")
            st = user.get("service_types", ["terminal", "ssh", "telnet"])
            lines.append(f" service-type {' '.join(st)}\n")
            lines.append(" quit\n")

        ntp = config.get("ntp")
        if ntp and ntp.get("enable", False):
            lines.append("\n#\n# NTP配置\n#\n")
            lines.append(f"clock timezone {ntp.get('timezone', 'UTC+8')} add 08:00:00\n")
            lines.append("ntp-service enable\n")
            for srv in ntp.get("servers") or []:
                cmd = f"ntp-service unicast-server {srv['ip']}"
                if srv.get("prefer"):
                    cmd += " preference"
                lines.append(cmd + "\n")

        snmp = config.get("snmp")
        if snmp and snmp.get("enable", False):
            lines.append("\n#\n# SNMP配置\n#\n")
            lines.append("snmp-agent\n")
            lines.append(f"snmp-agent sys-info version {snmp.get('version', 'v2c')}\n")
            if snmp.get("sys_location"):
                lines.append(f"snmp-agent sys-info location {snmp['sys_location']}\n")
            if snmp.get("sys_contact"):
                lines.append(f"snmp-agent sys-info contact {snmp['sys_contact']}\n")
            if snmp.get("version", "v2c") in ("v2c", "all"):
                if snmp.get("community_read"):
                    lines.append(f"snmp-agent community read {snmp['community_read']}\n")
                if snmp.get("community_write"):
                    lines.append(f"snmp-agent community write {snmp['community_write']}\n")
            if snmp.get("trap_enable") and snmp.get("trap_host"):
                lines.append("snmp-agent trap enable\n")
                lines.append(f"snmp-agent target-host trap address udp-domain {snmp['trap_host']} params securityname public v2c\n")

        log = config.get("log")
        if log:
            lines.append("\n#\n# 日志配置\n#\n")
            if log.get("info_center_enable", True):
                lines.append("info-center enable\n")
            if log.get("host"):
                lines.append(f"info-center loghost {log['host']}\n")
            lines.append(f"info-center source default channel loghost log level {log.get('log_level', 'informational')}\n")

        mgmt = config.get("mgmt_interface")
        if mgmt and mgmt.get("enable", False):
            lines.append("\n#\n# 管理接口配置\n#\n")
            # H3C: Vlanif -> Vlan-interface
            iface_name = mgmt.get("interface", "Vlan-interface1")
            if iface_name.startswith("Vlanif"):
                iface_name = iface_name.replace("Vlanif", "Vlan-interface")
            lines.append(f"interface {iface_name}\n")
            lines.append(f" description {mgmt.get('description', 'Management Interface')}\n")
            if mgmt.get("ip_address"):
                lines.append(f" ip address {mgmt['ip_address']} {mgmt.get('mask', '255.255.255.0')}\n")
            lines.append(" quit\n")
            if mgmt.get("gateway"):
                lines.append(f"ip route-static 0.0.0.0 0 {mgmt['gateway']}\n")

        return "".join(lines)

    # ======================== VLAN 配置 ========================
    def generate_vlan(self, config: dict) -> str:
        lines = ["\n#\n# VLAN配置\n", "#\n"]

        vlans = config.get("vlans")
        if vlans:
            vlan_ids = [v["id"] if isinstance(v, dict) else v for v in vlans]
            for vlan in vlans:
                if isinstance(vlan, dict):
                    lines.append(f"vlan {vlan['id']}\n")
                    vlan_desc = vlan.get("description") or vlan.get("name")
                    if vlan_desc:
                        lines.append(f" description {vlan_desc}\n")
                    lines.append(" quit\n")

        for iface in config.get("interfaces") or []:
            lines.append(f"interface {iface['interface']}\n")
            t = iface.get("type", "access")
            lines.append(f" port link-type {t}\n")
            if t == "access" and iface.get("vlan_id"):
                # H3C: port default vlan -> port access vlan
                lines.append(f" port access vlan {iface['vlan_id']}\n")
            elif t == "trunk":
                if iface.get("pvid"):
                    lines.append(f" port trunk pvid vlan {iface['pvid']}\n")
                if iface.get("trunk_vlans"):
                    # H3C: allow-pass -> permit, 用逗号分隔
                    vlan_str = ",".join(map(str, iface["trunk_vlans"]))
                    lines.append(f" port trunk permit vlan {vlan_str}\n")
            elif t == "hybrid":
                if iface.get("vlan_id"):
                    lines.append(f" port hybrid pvid vlan {iface['vlan_id']}\n")
                if iface.get("untagged_vlans"):
                    # H3C: port hybrid vlan X untagged (顺序与华为相反)
                    lines.append(f" port hybrid vlan {','.join(map(str, iface['untagged_vlans']))} untagged\n")
                if iface.get("tagged_vlans"):
                    lines.append(f" port hybrid vlan {','.join(map(str, iface['tagged_vlans']))} tagged\n")
            lines.append(" quit\n")

        for vf in config.get("vlanifs") or []:
            # H3C: Vlanif -> Vlan-interface
            lines.append(f"interface Vlan-interface{vf['vlan_id']}\n")
            if vf.get("description"):
                lines.append(f" description {vf['description']}\n")
            lines.append(f" ip address {vf['ip_address']} {vf.get('mask', '255.255.255.0')}\n")
            lines.append(" quit\n")

        stp = config.get("stp")
        if stp and stp.get("enable", False):
            lines.append("\n#\n# STP配置\n#\n")
            lines.append(f"stp mode {stp.get('mode', 'stp')}\n")
            if stp.get("priority", 32768) != 32768:
                lines.append(f"stp priority {stp['priority']}\n")
            lines.append("stp enable\n")

        return "".join(lines)

    # ======================== 路由配置 ========================
    def generate_routing(self, config: dict) -> str:
        lines = ["\n#\n# 路由配置\n", "#\n"]

        for route in config.get("static_routes") or []:
            cmd = f"ip route-static {route['dest_network']} {route['mask']}"
            if route.get("next_hop"):
                cmd += f" {route['next_hop']}"
            elif route.get("interface"):
                cmd += f" {route['interface']}"
            if route.get("preference"):
                cmd += f" preference {route['preference']}"
            lines.append(cmd + "\n")

        dr = config.get("default_route")
        if dr:
            if dr.get("next_hop"):
                lines.append(f"ip route-static 0.0.0.0 0.0.0.0 {dr['next_hop']}\n")
            elif dr.get("interface"):
                lines.append(f"ip route-static 0.0.0.0 0.0.0.0 {dr['interface']}\n")

        ospf = config.get("ospf")
        if ospf:
            lines.append("\n#\n# OSPF配置\n#\n")
            cmd = f"ospf {ospf.get('process_id', 1)}"
            if ospf.get("router_id"):
                cmd += f" router-id {ospf['router_id']}"
            lines.append(cmd + "\n")
            lines.append(f" area {ospf.get('area_id', '0')}\n")
            for net in ospf.get("networks") or []:
                lines.append(f"  network {net['address']} {net.get('mask', '0.0.0.255')}\n")
            lines.append(" quit\n")

        bgp = config.get("bgp")
        if bgp:
            lines.append("\n#\n# BGP配置\n#\n")
            lines.append(f"bgp {bgp['as_number']}\n")
            if bgp.get("router_id"):
                lines.append(f" router-id {bgp['router_id']}\n")
            for peer in bgp.get("peers") or []:
                lines.append(f" peer {peer['ip']} as-number {peer['as_number']}\n")
            for net in bgp.get("networks") or []:
                lines.append(f" network {net}\n")
            for route in bgp.get("import_routes") or []:
                lines.append(f" import-route {route.get('protocol', 'ospf')} process {route.get('process', 1)}\n")

        return "".join(lines)

    # ======================== 安全配置 ========================
    def generate_security(self, config: dict) -> str:
        lines = ["\n#\n# 安全配置\n", "#\n"]

        for acl in config.get("acls") or []:
            lines.append(f"acl number {acl['number']}\n")
            if acl.get("description"):
                lines.append(f" description {acl['description']}\n")
            for rule in acl.get("rules") or []:
                action = rule.get("action", "permit")
                proto = rule.get("protocol", "ip")
                rule_id = rule["rule_id"]
                src = rule.get("source", "any")
                if proto == "ip" or src == "any":
                    lines.append(f" rule {rule_id} {action} source {src}\n")
                else:
                    dst = rule.get("destination", "any")
                    line = f" rule {rule_id} {action} {proto} source {src}"
                    if dst != "any":
                        line += f" destination {dst}"
                    if rule.get("dest_port") and proto in ("tcp", "udp"):
                        line += f" destination-port eq {rule['dest_port']}"
                    lines.append(line + "\n")
            lines.append(" quit\n")

        for ps in config.get("port_security") or []:
            lines.append(f"interface {ps['interface']}\n")
            lines.append(" port-security enable\n")
            lines.append(f" port-security max-mac-count {ps.get('max_mac', 1)}\n")
            # H3C: protect-action -> violation
            lines.append(f" port-security violation {ps.get('protect_action', 'protect')}\n")
            if ps.get("sticky", True):
                lines.append(" port-security mac-address sticky\n")
            lines.append(" quit\n")

        for sm in config.get("static_macs") or []:
            lines.append(f"mac-address static {sm['mac_address']} interface {sm['interface']} vlan {sm['vlan_id']}\n")

        for bm in config.get("blackhole_macs") or []:
            lines.append(f"mac-address blackhole {bm['mac_address']}\n")

        d1g = config.get("dot1x_global")
        if d1g and d1g.get("enable", False):
            lines.append("\n#\n# 802.1X全局配置\n#\n")
            lines.append("dot1x enable\n")
            lines.append(f"dot1x authentication-method {d1g.get('method', 'chap')}\n")

        for di in config.get("dot1x_interfaces") or []:
            lines.append(f"interface {di['interface']}\n")
            lines.append(" dot1x enable\n")
            lines.append(f" dot1x port-method {di.get('port_method', 'mac')}\n")
            lines.append(f" dot1x max-user {di.get('max_users', 256)}\n")
            lines.append(" quit\n")

        arp_p = config.get("arp_protection")
        if arp_p:
            lines.append("arp-check enable\n")
            for port in arp_p.get("trust_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(" arp detection trust\n")
                lines.append(" quit\n")

        for sa in config.get("static_arps") or []:
            cmd = f"arp static {sa['ip_address']} {sa['mac_address']}"
            if sa.get("interface"):
                cmd += f" {sa['interface']}"
            lines.append(cmd + "\n")

        ds = config.get("dhcp_snooping")
        if ds and ds.get("enable", False):
            lines.append("dhcp snooping enable\n")
            if ds.get("vlans"):
                lines.append(f"dhcp snooping vlan {' '.join(map(str, ds['vlans']))}\n")
            for port in ds.get("trust_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(" dhcp snooping trust\n")
                lines.append(" quit\n")

        for sc in config.get("storm_controls") or []:
            lines.append(f"interface {sc['interface']}\n")
            if sc.get("broadcast") is not None:
                lines.append(f" storm-constrain broadcast level {sc['broadcast']}\n")
            if sc.get("multicast") is not None:
                lines.append(f" storm-constrain multicast level {sc['multicast']}\n")
            if sc.get("unicast") is not None:
                lines.append(f" storm-constrain unicast level {sc['unicast']}\n")
            lines.append(f" storm-constrain control {sc.get('action', 'block')}\n")
            lines.append(" quit\n")

        return "".join(lines)

    # ======================== 接口配置 ========================
    def generate_interface(self, config: dict) -> str:
        lines = ["\n#\n# 接口配置\n", "#\n"]

        for trunk in config.get("eth_trunks") or []:
            # H3C: Eth-Trunk -> Bridge-Aggregation
            lines.append(f"interface Bridge-Aggregation {trunk['trunk_id']}\n")
            if trunk.get("description"):
                lines.append(f" description {trunk['description']}\n")
            plt = trunk.get("port_link_type", "trunk")
            lines.append(f" port link-type {plt}\n")
            if plt == "trunk" and trunk.get("trunk_vlans"):
                vlan_str = ",".join(map(str, trunk["trunk_vlans"]))
                lines.append(f" port trunk permit vlan {vlan_str}\n")
            if plt == "access" and trunk.get("native_vlan"):
                lines.append(f" port access vlan {trunk['native_vlan']}\n")
            # H3C: mode -> link-aggregation mode
            mode = trunk.get("mode", "lacp-static")
            h3c_mode = "dynamic" if "lacp" in mode else "static"
            lines.append(f" link-aggregation mode {h3c_mode}\n")
            lines.append(" quit\n")
            for port in trunk.get("member_ports") or []:
                lines.append(f"interface {port}\n")
                # H3C: eth-trunk N -> port link-aggregation group N
                lines.append(f" port link-aggregation group {trunk['trunk_id']}\n")
                lines.append(" quit\n")

        lacp = config.get("lacp")
        if lacp:
            lines.append("\n#\n# LACP全局配置\n#\n")
            lines.append(f"lacp system-priority {lacp.get('priority', 32768)}\n")
            if lacp.get("fast_switchover", True):
                lines.append("link-aggregation selected-port minimum 1\n")

        lldp = config.get("lldp")
        if lldp and lldp.get("enable", False):
            lines.append("\n#\n# LLDP配置\n#\n")
            lines.append("lldp global enable\n")
            lines.append(f"lldp work {lldp.get('mode', 'both')}\n")
            # H3C 用不同命令名
            lines.append(f"lldp timer tx-interval {lldp.get('interval', 30)}\n")
            lines.append(f"lldp timer tx-ttl {lldp.get('holdtime', 120)}\n")

        poe = config.get("poe")
        if poe and poe.get("enable", False):
            lines.append("\n#\n# PoE全局配置\n#\n")
            lines.append("poe enable\n")
            lines.append(f"poe max-power {poe.get('max_power', 74000)}\n")
            for iface in poe.get("interfaces") or []:
                lines.append(f"interface {iface['interface']}\n")
                if iface.get("enable", True):
                    lines.append(" poe enable\n")
                    lines.append(f" poe mode {iface.get('mode', 'auto')}\n")
                    lines.append(f" poe priority {iface.get('priority', 'low')}\n")
                lines.append(" quit\n")

        pi = config.get("port_isolation")
        if pi and pi.get("enable", False) and pi.get("interfaces"):
            lines.append("\n#\n# 端口隔离配置\n#\n")
            for interface in pi["interfaces"]:
                lines.append(f"interface {interface}\n")
                lines.append(f" port-isolate enable group {pi.get('group_id', 1)}\n")
                lines.append(" quit\n")

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
            if rl.get("cir_out"):
                lines.append(f" qos lr outbound cir {rl['cir_out']} cbs {rl['cir_out'] * 125}\n")
            if rl.get("cir_in"):
                lines.append(f" qos lr inbound cir {rl['cir_in']} cbs {rl['cir_in'] * 125}\n")
            lines.append(" quit\n")

        return "".join(lines)
