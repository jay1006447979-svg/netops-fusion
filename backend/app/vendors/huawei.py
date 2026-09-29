"""华为配置生成器 — 命令格式参照 NetOps-toolkit, 修复原项目 f-string bug"""

from __future__ import annotations

from app.core.registry import vendor_registry
from app.vendors.base import BaseConfigGenerator


@vendor_registry.register("huawei", device_types=["switch", "router", "ap"])
class HuaweiGenerator(BaseConfigGenerator):
    vendor = "huawei"

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
            # SSH 用户名取自配置 (用户配置里的 username), 避免硬编码
            ssh_user = (config.get("user") or {}).get("username") or ssh.get("username") or "admin"
            lines.append("\n#\n# SSH配置\n#\n")
            # rsa local-key-pair create 在多数 VRP 版本会交互询问密钥长度,
            # 紧跟一行密钥位数作为应答, 避免脚本推送时挂起等待输入
            lines.append("rsa local-key-pair create\n")
            lines.append(f"{ssh.get('key_modulus', 2048)}\n")
            lines.append("stelnet server enable\n")
            lines.append(f"ssh server port {ssh.get('port', 22)}\n")
            lines.append(f"ssh server timeout {ssh.get('timeout', 60)}\n")
            lines.append(f"ssh server max-auth-times {ssh.get('max_auth_tries', 5)}\n")
            lines.append(f"ssh server rekey-interval {ssh.get('rekey_interval', 60)}\n")
            lines.append("ssh server compatible-huawei-version enable\n")
            lines.append(f"ssh version {ssh.get('version', 2)}\n")
            lines.append(f"ssh user {ssh_user}\n")
            lines.append(f"ssh user {ssh_user} authentication-type password\n")
            lines.append(f"ssh user {ssh_user} service-type stelnet\n")
            lines.append("user-interface vty 0 4\n")
            lines.append(" authentication-mode aaa\n")
            lines.append(" protocol inbound ssh\n")

        telnet = config.get("telnet")
        if telnet and telnet.get("enable", False):
            lines.append("\n#\n# Telnet配置\n#\n")
            lines.append("telnet server enable\n")
            lines.append("user-interface vty 0 4\n")
            lines.append(" authentication-mode aaa\n")
            lines.append(" protocol inbound telnet\n")

        console = config.get("console")
        if console and console.get("enable", False):
            lines.append("\n#\n# Console配置\n#\n")
            lines.append("user-interface console 0\n")
            auth = console.get("authentication", "password")
            if auth == "password" and console.get("password"):
                lines.append(" authentication-mode password\n")
                lines.append(f" set authentication password simple {console['password']}\n")
            elif auth == "aaa":
                lines.append(" authentication-mode aaa\n")
            lines.append(f" idle-timeout {console.get('idle_timeout', 10)} 0\n")

        banner = config.get("banner")
        if banner:
            lines.append("\n#\n# Banner配置\n#\n")
            if banner.get("motd"):
                lines.append(f'header shell information "#{"#" * 49}\n{banner["motd"]}\n{"#" * 50}"\n')
            if banner.get("login"):
                lines.append(f'header login information "#{"#" * 49}\n{banner["login"]}\n{"#" * 50}"\n')

        user = config.get("user")
        if user and user.get("enable", False):
            lines.append("\n#\n# 用户配置\n#\n")
            lines.append("aaa\n")
            enc = "cipher" if user.get("encrypted") else "simple"
            lines.append(f" local-user {user.get('username', 'admin')} password {enc} {user.get('password', 'admin@123')}\n")
            lines.append(f" local-user {user.get('username', 'admin')} privilege level {user.get('level', 15)}\n")
            st = user.get("service_types", ["terminal", "ssh", "telnet"])
            lines.append(f" local-user {user.get('username', 'admin')} service-type {' '.join(st)}\n")
            lines.append("#\n")

        ntp = config.get("ntp")
        if ntp and ntp.get("enable", False):
            lines.append("\n#\n# NTP配置\n#\n")
            lines.append(f"clock timezone {ntp.get('timezone', 'UTC+8')} add 08:00:00\n")
            for srv in ntp.get("servers") or []:
                cmd = f"ntp-service unicast-server {srv['ip']}"
                if srv.get("prefer"):
                    cmd += " preference"
                lines.append(cmd + "\n")
            if ntp.get("broadcast_enable"):
                lines.append("ntp-service broadcast enable\n")

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
                lines.append(f"snmp-agent target-host trap address udp-domain {snmp['trap_host']} params securityname public\n")
            lines.append("#\n")

        log = config.get("log")
        if log:
            lines.append("\n#\n# 日志配置\n#\n")
            if log.get("info_center_enable", True):
                lines.append("info-center enable\n")
            lines.append(f"info-center timestamp log {log.get('time_stamp', 'date')}\n")
            if log.get("host"):
                lines.append(f"info-center loghost {log['host']}\n")
                lines.append("info-center loghost source Vlanif1\n")
            lines.append("info-center console channel 0\n")
            lines.append("#\n")

        mgmt = config.get("mgmt_interface")
        if mgmt and mgmt.get("enable", False):
            lines.append("\n#\n# 管理接口配置\n#\n")
            lines.append(f"interface {mgmt.get('interface', 'Vlanif1')}\n")
            lines.append(f" description {mgmt.get('description', 'Management Interface')}\n")
            if mgmt.get("ip_address"):
                lines.append(f" ip address {mgmt['ip_address']} {mgmt.get('mask', '255.255.255.0')}\n")
            lines.append("#\n")
            if mgmt.get("gateway"):
                lines.append(f"ip route-static 0.0.0.0 0.0.0.0 {mgmt['gateway']}\n")

        dhcp = config.get("dhcp_global")
        if dhcp:
            lines.append("\n#\n# DHCP全局配置\n#\n")
            if dhcp.get("enable", True):
                lines.append("dhcp enable\n")
            for ip_range in dhcp.get("excluded_ips") or []:
                start = ip_range.get("start")
                end = ip_range.get("end")
                if end:
                    lines.append(f"dhcp server excluded-ip-address {start} {end}\n")
                else:
                    lines.append(f"dhcp server excluded-ip-address {start}\n")
            if dhcp.get("dns_servers"):
                lines.append(f"dhcp server dns-list {' '.join(dhcp['dns_servers'])}\n")

        dns = config.get("dns")
        if dns and dns.get("enable", False):
            lines.append("\n#\n# DNS配置\n#\n")
            if dns.get("resolve_enable", False):
                lines.append("ip dns resolve\n")
            for srv in dns.get("servers") or []:
                lines.append(f"ip dns server {srv}\n")
            if dns.get("domain"):
                lines.append(f"ip dns domain {dns['domain']}\n")

        return "".join(lines)

    # ======================== VLAN 配置 ========================
    def generate_vlan(self, config: dict) -> str:
        lines = ["\n#\n# VLAN配置\n", "#\n"]

        vlans = config.get("vlans")
        if vlans:
            vlan_ids = [v["id"] if isinstance(v, dict) else v for v in vlans]
            if len(vlan_ids) > 3:
                lines.append(f"vlan batch {self._vlan_range_str(vlan_ids)}\n")
            for vlan in vlans:
                if isinstance(vlan, dict):
                    lines.append(f"vlan {vlan['id']}\n")
                    vlan_desc = vlan.get("description") or vlan.get("name")
                    if vlan_desc:
                        lines.append(f" description {vlan_desc}\n")
                    lines.append("#\n")

        for iface in config.get("interfaces") or []:
            lines.append(f"interface {iface['interface']}\n")
            lines.append(f" port link-type {iface.get('type', 'access')}\n")
            t = iface.get("type", "access")
            if t == "access" and iface.get("vlan_id"):
                lines.append(f" port default vlan {iface['vlan_id']}\n")
            elif t == "trunk":
                if iface.get("trunk_vlans"):
                    lines.append(f" port trunk allow-pass vlan {' '.join(map(str, iface['trunk_vlans']))}\n")
                if iface.get("pvid"):
                    lines.append(f" port trunk pvid vlan {iface['pvid']}\n")
            elif t == "hybrid":
                if iface.get("vlan_id"):
                    lines.append(f" port hybrid pvid vlan {iface['vlan_id']}\n")
                if iface.get("trunk_vlans"):
                    lines.append(f" port hybrid untagged vlan {' '.join(map(str, iface['trunk_vlans']))}\n")
            lines.append("#\n")

        for vf in config.get("vlanifs") or []:
            lines.append(f"interface Vlanif{vf['vlan_id']}\n")
            if vf.get("description"):
                lines.append(f" description {vf['description']}\n")
            lines.append(f" ip address {vf['ip_address']} {vf.get('mask', '255.255.255.0')}\n")
            lines.append("#\n")

        stp = config.get("stp")
        if stp and stp.get("enable", False):
            lines.append("\n#\n# STP配置\n#\n")
            lines.append(f"stp mode {stp.get('mode', 'stp')}\n")
            lines.append("stp enable\n")
            if stp.get("priority", 32768) != 32768:
                lines.append(f"stp priority {stp['priority']}\n")

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
            if ospf.get("cost"):
                lines.append(f" default-cost {ospf['cost']}\n")
            lines.append(f" area {ospf.get('area_id', '0')}\n")
            for net in ospf.get("networks") or []:
                lines.append(f"  network {net['address']} {net.get('mask', '0.0.0.255')}\n")
            for iface in ospf.get("interfaces") or []:
                lines.append(f"  interface {iface}\n")
            lines.append("#\n")

        for oi in config.get("ospf_interfaces") or []:
            lines.append(f"interface {oi['interface']}\n")
            lines.append(" ospf enable 1 area 0\n")
            if oi.get("cost"):
                lines.append(f" ospf cost {oi['cost']}\n")
            if oi.get("priority"):
                lines.append(f" ospf dr-priority {oi['priority']}\n")
            lines.append(f" ospf timer hello {oi.get('hello_time', 10)}\n")
            lines.append(f" ospf timer dead {oi.get('dead_time', 40)}\n")
            lines.append("#\n")

        bgp = config.get("bgp")
        if bgp:
            lines.append("\n#\n# BGP配置\n#\n")
            lines.append(f"bgp {bgp['as_number']}\n")
            if bgp.get("router_id"):
                lines.append(f" router-id {bgp['router_id']}\n")
            for peer in bgp.get("peers") or []:
                lines.append(f" peer {peer['ip']} as-number {peer['as_number']}\n")
            lines.append(" ipv4-family unicast\n")
            for net in bgp.get("networks") or []:
                lines.append(f"  network {net}\n")
            for route in bgp.get("import_routes") or []:
                lines.append(f"  import-route {route.get('protocol', 'ospf')} process {route.get('process', 1)}\n")
            for peer in bgp.get("peers") or []:
                lines.append(f"  peer {peer['ip']} enable\n")
            lines.append("#\n")

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
                if src == "any":
                    lines.append(f" rule {rule_id} {action} source any\n")
                else:
                    lines.append(f" rule {rule_id} {action} source {src} {rule.get('source_wildcard', '0.0.0.0')}\n")
                    if proto != "ip":
                        dst = rule.get("destination", "any")
                        if dst == "any":
                            line = f" rule {rule_id} {action} {proto} source any destination any"
                        else:
                            line = f" rule {rule_id} {action} {proto} source {src} {rule.get('source_wildcard', '0.0.0.0')} destination {dst} {rule.get('dest_wildcard', '0.0.0.0')}"
                        if rule.get("dest_port") and proto in ("tcp", "udp"):
                            line += f" destination-port eq {rule['dest_port']}"
                        lines.append(line + "\n")
            lines.append("#\n")

        for ps in config.get("port_security") or []:
            lines.append(f"interface {ps['interface']}\n")
            lines.append(" port-security enable\n")
            lines.append(f" port-security max-mac-num {ps.get('max_mac', 1)}\n")
            lines.append(f" port-security protect-action {ps.get('protect_action', 'protect')}\n")
            if ps.get("sticky", True):
                lines.append(" port-security mac-address sticky\n")
                if ps.get("mac_address") and ps.get("vlan_id"):
                    lines.append(f" port-security mac-address sticky {ps['mac_address']} vlan {ps['vlan_id']}\n")
            lines.append("#\n")

        for mb in config.get("mac_bindings") or []:
            lines.append(f"interface {mb['interface']}\n")
            lines.append(f" port-security mac-address sticky {mb['mac_address']} vlan {mb['vlan_id']}\n")
            lines.append("#\n")

        for sm in config.get("static_macs") or []:
            lines.append(f"mac-address static {sm['mac_address']} {sm['interface']} vlan {sm['vlan_id']}\n")

        for bm in config.get("blackhole_macs") or []:
            lines.append(f"mac-address blackhole {bm['mac_address']}\n")

        for ml in config.get("mac_limits") or []:
            if ml.get("vlan"):
                lines.append(f"mac-address limit maximum {ml.get('limit', 100)} vlan {ml['vlan']} action {ml.get('action', 'discard')} alarm {'enable' if ml.get('alarm', True) else 'disable'}\n")
            if ml.get("interface"):
                lines.append(f"interface {ml['interface']}\n")
                lines.append(f" mac-address limit maximum {ml.get('limit', 100)} action {ml.get('action', 'discard')} alarm {'enable' if ml.get('alarm', True) else 'disable'}\n")
                lines.append("#\n")

        d1g = config.get("dot1x_global")
        if d1g and d1g.get("enable", False):
            lines.append("\n#\n# 802.1X全局配置\n#\n")
            lines.append("dot1x enable\n")
            lines.append(f"dot1x authentication-method {d1g.get('method', 'chap')}\n")
            lines.append(f"dot1x reauthenticate period {d1g.get('reauth_period', 3600)}\n")
            lines.append(f"dot1x timer tx-period {d1g.get('tx_period', 30)}\n")

        for di in config.get("dot1x_interfaces") or []:
            lines.append(f"interface {di['interface']}\n")
            lines.append(" dot1x enable\n")
            lines.append(f" dot1x port-method {di.get('port_method', 'mac')}\n")
            lines.append(f" dot1x max-user {di.get('max_users', 256)}\n")
            lines.append(f" dot1x timer quiet-period {di.get('quiet_period', 60)}\n")
            lines.append("#\n")

        arp_p = config.get("arp_protection")
        if arp_p:
            if arp_p.get("vlans"):
                lines.append(f"arp inspection vlan {' '.join(map(str, arp_p['vlans']))}\n")
            for port in arp_p.get("trust_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(" arp inspection trust\n")
                lines.append("#\n")

        for sa in config.get("static_arps") or []:
            cmd = f"arp static {sa['ip_address']} {sa['mac_address']}"
            if sa.get("vlan_id"):
                cmd += f" vid {sa['vlan_id']}"
            if sa.get("interface"):
                cmd += f" interface {sa['interface']}"
            lines.append(cmd + "\n")

        for al in config.get("arp_limits") or []:
            if al.get("interface"):
                lines.append(f"interface {al['interface']}\n")
                lines.append(f" arp-limit maximum {al.get('limit', 100)}\n")
                lines.append("#\n")
            if al.get("vlan"):
                lines.append(f"vlan {al['vlan']}\n")
                lines.append(f" arp-limit maximum {al.get('limit', 100)}\n")
                lines.append("#\n")

        for rs in config.get("radius_servers") or []:
            lines.append(f"radius-server template {rs['server_name']}\n")
            lines.append(f" radius-server shared-key cipher {rs['shared_key']}\n")
            lines.append(f" radius-server authentication {rs['ip_address']} {rs.get('auth_port', 1812)}\n")
            lines.append(f" radius-server accounting {rs['ip_address']} {rs.get('acct_port', 1813)}\n")
            lines.append(f" radius-server retransmit {rs.get('retransmit', 3)}\n")
            lines.append(f" radius-server timeout {rs.get('timeout', 5)}\n")

        ds = config.get("dhcp_snooping")
        if ds and ds.get("enable", False):
            lines.append("dhcp snooping enable\n")
            if ds.get("vlans"):
                lines.append(f"dhcp snooping vlan {' '.join(map(str, ds['vlans']))}\n")
            for port in ds.get("trust_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(" dhcp snooping trusted\n")
                lines.append("#\n")

        for sc in config.get("storm_controls") or []:
            lines.append(f"interface {sc['interface']}\n")
            if sc.get("broadcast") is not None:
                lines.append(f" storm-control broadcast min-rate {sc['broadcast']}\n")
            if sc.get("multicast") is not None:
                lines.append(f" storm-control multicast min-rate {sc['multicast']}\n")
            if sc.get("unicast") is not None:
                lines.append(f" storm-control unicast min-rate {sc['unicast']}\n")
            lines.append(f" storm-control action {sc.get('action', 'block')}\n")
            lines.append("#\n")

        for tf in config.get("traffic_filters") or []:
            lines.append(f"interface {tf['interface']}\n")
            lines.append(f" traffic-filter {tf.get('direction', 'inbound')} acl {tf['acl_number']}\n")
            lines.append("#\n")

        for ub in config.get("user_binds") or []:
            lines.append(f"interface {ub['interface']}\n")
            cmd = " user-bind static"
            if ub.get("ip_address"):
                cmd += f" ip {ub['ip_address']}"
            if ub.get("mac_address"):
                cmd += f" mac {ub['mac_address']}"
            if ub.get("vlan_id"):
                cmd += f" vlan {ub['vlan_id']}"
            lines.append(cmd + "\n")
            lines.append("#\n")

        return "".join(lines)

    # ======================== 接口配置 ========================
    def generate_interface(self, config: dict) -> str:
        lines = ["\n#\n# 接口配置\n", "#\n"]

        for trunk in config.get("eth_trunks") or []:
            lines.append(f"interface Eth-Trunk{trunk['trunk_id']}\n")
            if trunk.get("description"):
                lines.append(f" description {trunk['description']}\n")
            plt = trunk.get("port_link_type", "trunk")
            lines.append(f" port link-type {plt}\n")
            if plt == "trunk" and trunk.get("trunk_vlans"):
                lines.append(f" port trunk allow-pass vlan {' '.join(map(str, trunk['trunk_vlans']))}\n")
            if plt == "access" and trunk.get("native_vlan"):
                lines.append(f" port default vlan {trunk['native_vlan']}\n")
            lines.append(f" mode {trunk.get('mode', 'lacp-static')}\n")
            lines.append("#\n")
            for port in trunk.get("member_ports") or []:
                lines.append(f"interface {port}\n")
                lines.append(f" eth-trunk {trunk['trunk_id']}\n")
                lines.append("#\n")

        lacp = config.get("lacp")
        if lacp:
            lines.append("\n#\n# LACP全局配置\n#\n")
            lines.append(f"lacp priority {lacp.get('priority', 32768)}\n")
            if lacp.get("system_id"):
                lines.append(f"lacp system-id {lacp['system_id']}\n")
            if lacp.get("fast_switchover", True):
                lines.append("lacp fast-switchover enable\n")

        lldp = config.get("lldp")
        if lldp and lldp.get("enable", False):
            lines.append("\n#\n# LLDP配置\n#\n")
            lines.append("lldp enable\n")
            lines.append(f"lldp mode {lldp.get('mode', 'both')}\n")
            lines.append(f"lldp message-fasts count {lldp.get('fast_count', 4)}\n")
            lines.append(f"lldp transmit interval {lldp.get('interval', 30)}\n")
            lines.append(f"lldp transmit holdtime {lldp.get('holdtime', 120)}\n")
            for iface in lldp.get("interfaces") or []:
                lines.append(f"interface {iface['interface']}\n")
                if iface.get("enable", True):
                    lines.append(" lldp enable\n")
                    lines.append(f" lldp admin-status {iface.get('admin_status', 'txrx')}\n")
                else:
                    lines.append(" lldp disable\n")
                lines.append("#\n")

        poe = config.get("poe")
        if poe and poe.get("enable", False):
            lines.append("\n#\n# PoE全局配置\n#\n")
            lines.append("poe enable\n")
            lines.append(f"poe max-power {poe.get('max_power', 74000)}\n")
            if poe.get("legacy_enable"):
                lines.append("poe legacy enable\n")
            for iface in poe.get("interfaces") or []:
                lines.append(f"interface {iface['interface']}\n")
                if iface.get("enable", True):
                    lines.append(" poe enable\n")
                    lines.append(f" poe mode {iface.get('mode', 'auto')}\n")
                    lines.append(f" poe priority {iface.get('priority', 'low')}\n")
                    lines.append(f" poe max-power {iface.get('max_power', 15400)}\n")
                else:
                    lines.append(" poe disable\n")
                lines.append("#\n")

        pi = config.get("port_isolation")
        if pi and pi.get("enable", False) and pi.get("interfaces"):
            lines.append("\n#\n# 端口隔离配置\n#\n")
            lines.append("port-isolate mode all\n")
            for interface in pi["interfaces"]:
                lines.append(f"interface {interface}\n")
                lines.append(f" port-isolate enable group {pi.get('group_id', 1)}\n")
                lines.append("#\n")

        lbd = config.get("loopback_detection")
        if lbd and lbd.get("enable", False):
            lines.append("\n#\n# 环路检测配置\n#\n")
            lines.append("loopback-detect enable\n")
            lines.append(f"loopback-detect interval {lbd.get('interval', 5)}\n")
            if lbd.get("vlan_ids"):
                lines.append(f"loopback-detect vlan {' '.join(map(str, lbd['vlan_ids']))}\n")
            lines.append(f"loopback-detect action {lbd.get('action', 'block')}\n")

        for rl in config.get("rate_limits") or []:
            lines.append(f"interface {rl['interface']}\n")
            if rl.get("cir_in"):
                lines.append(f" qos lr inbound cir {rl['cir_in']}\n")
            if rl.get("cir_out"):
                lines.append(f" qos lr outbound cir {rl['cir_out']}\n")
            lines.append("#\n")

        for qos in config.get("interface_qos") or []:
            lines.append(f"interface {qos['interface']}\n")
            if qos.get("car_inbound"):
                lines.append(f" qos car inbound cir {qos['car_inbound']} cbs {qos['car_inbound'] * 125}\n")
            if qos.get("car_outbound"):
                lines.append(f" qos car outbound cir {qos['car_outbound']} cbs {qos['car_outbound'] * 125}\n")
            if qos.get("priority") is not None:
                lines.append(f" qos priority {qos['priority']}\n")
            lines.append("#\n")

        return "".join(lines)
