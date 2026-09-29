"""端到端 API 测试 — 启动服务器并验证所有路由"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import httpx

BASE = "http://127.0.0.1:8765"
VENV_PY = r"C:\Users\User\.workbuddy\binaries\python\envs\netops\Scripts\python.exe"
BACKEND_DIR = r"D:\WorkBuddy\NetWorkFig\netops-fusion\backend"


def start_server() -> subprocess.Popen:
    """启动 uvicorn 服务器"""
    env = {
        "PYTHONPATH": BACKEND_DIR,
        "PORT": "8765",
        "DEBUG": "false",
    }
    full_env = {**os.environ, **env}
    proc = subprocess.Popen(
        [VENV_PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=BACKEND_DIR,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = httpx.get(f"{BASE}/health", timeout=1.0)
            if r.status_code == 200:
                return proc
        except Exception:
            continue
    proc.terminate()
    out, _ = proc.communicate(timeout=5)
    print("服务器启动失败, 输出:")
    print(out[-2000:])
    sys.exit(1)


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(name: str, resp: httpx.Response, expect_status: int = 200) -> bool:
    ok = resp.status_code == expect_status
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}  (HTTP {resp.status_code})")
    if not ok:
        print(f"         body: {resp.text[:300]}")
    return ok


# 正确的华为配置 (字段名与 Pydantic 模型一致)
HUAWEI_CONFIG = {
    "vendor": "huawei",
    "device_type": "switch",
    "hostname": "Core-SW-01",
    "basic": {
        "ssh": {"enable": True, "port": 22, "max_auth_tries": 5},
        "user": {"enable": True, "username": "admin", "password": "Admin@123", "level": 15},
        "ntp": {"enable": True, "servers": [{"ip": "10.1.1.1", "prefer": True}], "timezone": "UTC+8"},
        "snmp": {"enable": True, "community_read": "public", "community_write": "private", "sys_location": "DC1"},
    },
    "vlan": {
        "vlans": [{"id": 10, "name": "Mgmt"}, {"id": 20, "name": "Data"}],
        "interfaces": [
            {"interface": "GigabitEthernet0/0/1", "type": "access", "vlan_id": 10},
            {"interface": "GigabitEthernet0/0/2", "type": "trunk", "trunk_vlans": [10, 20]},
        ],
        "vlanifs": [
            {"vlan_id": 10, "ip_address": "10.10.10.1", "mask": "255.255.255.0", "description": "Mgmt-GW"},
        ],
    },
}


async def run_tests():
    results = {"pass": 0, "fail": 0, "details": []}

    def record(name, ok, detail=""):
        results["pass" if ok else "fail"] += 1
        results["details"].append({"name": name, "ok": ok, "detail": detail})

    async with httpx.AsyncClient(base_url=BASE, timeout=15.0) as c:
        # ---- 1. 基础路由 ----
        section("1. 基础路由")
        r = await c.get("/")
        ok = check("GET /", r)
        record("GET /", ok)
        if ok:
            # 根路径现在是 HTML 界面, API 信息在 /api/info
            r2 = await c.get("/api/info")
            ok2 = check("GET /api/info", r2)
            record("GET /api/info", ok2)
            if ok2:
                info = r2.json()
            print(f"         app={info.get('app')}, vendors={info.get('vendors')}")

        r = await c.get("/health")
        ok = check("GET /health", r)
        record("GET /health", ok)

        r = await c.get("/openapi.json")
        ok = check("GET /openapi.json", r)
        record("GET /openapi.json", ok)
        if ok:
            paths = r.json().get("paths", {})
            print(f"         路由总数: {len(paths)}")

        # ---- 2. 厂商 ----
        section("2. 厂商管理")
        r = await c.get("/api/vendors")
        ok = check("GET /api/vendors", r)
        record("GET /api/vendors", ok)
        if ok:
            print(f"         厂商: {r.json()}")

        # ---- 3. 配置生成 (华为) ----
        section("3. 配置生成 — 华为")
        r = await c.post("/api/config/generate", json=HUAWEI_CONFIG)
        ok = check("POST /api/config/generate (huawei)", r)
        record("配置生成-华为", ok)
        if ok:
            data = r.json()
            cfg_text = data.get("config_text", "")
            print(f"         hostname={data.get('hostname')}, vendor={data.get('vendor')}")
            print(f"         生成 {len(cfg_text.splitlines())} 行配置")
            for k in ["sysname Core-SW-01", "stelnet server enable",
                       "port default vlan 10", "port trunk allow-pass vlan 10 20"]:
                found = k in cfg_text
                print(f"         {'OK' if found else 'MISSING'}: {k}")
                if not found:
                    record(f"华为命令: {k}", False)

        # ---- 4. 配置生成 (H3C) ----
        section("4. 配置生成 — H3C")
        h3c_config = dict(HUAWEI_CONFIG)
        h3c_config["vendor"] = "h3c"
        h3c_config["hostname"] = "H3C-Core-01"
        r = await c.post("/api/config/generate", json=h3c_config)
        ok = check("POST /api/config/generate (h3c)", r)
        record("配置生成-H3C", ok)
        if ok:
            cfg_text = r.json().get("config_text", "")
            for k in ["sysname H3C-Core-01", "ssh server enable",
                       "port access vlan 10", "port trunk permit vlan 10,20",
                       "Vlan-interface"]:
                found = k in cfg_text
                print(f"         {'OK' if found else 'MISSING'}: {k}")
                if not found:
                    record(f"H3C命令: {k}", False)

        # ---- 5. 配置生成 (锐捷/迈普) ----
        section("5. 配置生成 — 锐捷 & 迈普")
        rj_config = dict(HUAWEI_CONFIG)
        rj_config["vendor"] = "ruijie"
        r = await c.post("/api/config/generate", json=rj_config)
        ok = check("POST /api/config/generate (ruijie)", r)
        record("配置生成-锐捷", ok)

        mp_config = dict(HUAWEI_CONFIG)
        mp_config["vendor"] = "maipu"
        r = await c.post("/api/config/generate", json=mp_config)
        ok = check("POST /api/config/generate (maipu)", r)
        record("配置生成-迈普", ok)

        # ---- 6. 配置校验 ----
        section("6. 配置校验 & 导出")
        r = await c.post("/api/config/validate", json=HUAWEI_CONFIG)
        ok = check("POST /api/config/validate", r)
        record("配置校验", ok)
        if ok:
            data = r.json()
            print(f"         valid={data.get('valid')}, errors={data.get('errors')}")

        r = await c.post("/api/config/export", json=HUAWEI_CONFIG)
        ok = check("POST /api/config/export", r)
        record("配置导出", ok)

        # ---- 7. 模板 ----
        section("7. 配置模板")
        r = await c.get("/api/templates")
        ok = check("GET /api/templates", r)
        record("GET /api/templates", ok)
        if ok:
            data = r.json()
            templates = data.get("templates", [])
            print(f"         模板数: {len(templates)}")
            for t in templates:
                print(f"           - {t.get('id')}: {t.get('name')} ({t.get('vendor')})")
            if templates:
                tid = templates[0]["id"]
                r2 = await c.get(f"/api/templates/{tid}")
                ok2 = check(f"GET /api/templates/{tid}", r2)
                record(f"获取模板详情: {tid}", ok2)

        # ---- 8. 命令手册 ----
        section("8. 命令手册")
        r = await c.get("/api/manual/vendors")
        ok = check("GET /api/manual/vendors", r)
        record("手册厂商列表", ok)
        if ok:
            print(f"         {r.json()}")

        r = await c.get("/api/manual/stats")
        ok = check("GET /api/manual/stats", r)
        record("手册统计", ok)
        if ok:
            print(f"         {r.json()}")

        r = await c.get("/api/manual/search?keyword=vlan")
        ok = check("GET /api/manual/search?keyword=vlan", r)
        record("手册搜索(vlan)", ok)
        if ok:
            results_list = r.json().get("results", [])
            print(f"         搜索结果: {len(results_list)} 条")

        r = await c.get("/api/manual/huawei/categories")
        ok = check("GET /api/manual/huawei/categories", r)
        record("华为命令分类", ok)
        if ok:
            cats = r.json().get("categories", [])
            print(f"         分类数: {len(cats)}")

        r = await c.get("/api/manual/huawei/commands")
        ok = check("GET /api/manual/huawei/commands", r)
        record("华为全部命令", ok)
        if ok:
            cmds = r.json().get("commands", [])
            print(f"         命令数: {len(cmds)}")

        # ---- 9. 网络工具箱 ----
        section("9. 网络工具箱 (11+工具)")
        # 子网计算
        r = await c.post("/api/tools/subnet/calculate", json={"ip": "192.168.1.1", "mask": "24"})
        ok = check("POST /api/tools/subnet/calculate", r)
        record("子网计算", ok)
        if ok:
            print(f"         {r.json().get('result', {})}")

        # 子网划分
        r = await c.post("/api/tools/subnet/divide", json={"ip": "192.168.1.0", "prefix": 24, "new_prefix": 26})
        ok = check("POST /api/tools/subnet/divide", r)
        record("子网划分", ok)

        # IP范围转CIDR
        r = await c.post("/api/tools/subnet/ip-range-to-cidr", json={"start": "192.168.1.1", "end": "192.168.1.10"})
        ok = check("POST /api/tools/subnet/ip-range-to-cidr", r)
        record("IP范围转CIDR", ok)

        # IP格式转换
        r = await c.post("/api/tools/subnet/ip-convert", json={"ip": "192.168.1.1", "target": "binary"})
        ok = check("POST /api/tools/subnet/ip-convert", r)
        record("IP格式转换", ok)

        # Ping
        r = await c.post("/api/tools/ping", json={"host": "127.0.0.1", "count": 3, "timeout": 2})
        ok = check("POST /api/tools/ping", r)
        record("Ping工具", ok)

        # 批量Ping
        r = await c.post("/api/tools/ping/batch", json={"hosts": ["127.0.0.1", "127.0.0.2"], "count": 2})
        ok = check("POST /api/tools/ping/batch", r)
        record("批量Ping", ok)

        # Ping扫描
        r = await c.post("/api/tools/ping/scan", json={"network": "127.0.0.0/24", "timeout": 1})
        ok = check("POST /api/tools/ping/scan", r)
        record("Ping扫描", ok)

        # 端口扫描
        r = await c.post("/api/tools/port-scan", json={"host": "127.0.0.1", "ports": [22, 80, 443, 8765]})
        ok = check("POST /api/tools/port-scan", r)
        record("端口扫描", ok)
        if ok:
            print(f"         开放端口: {r.json().get('open_ports', [])}")

        # 端口范围扫描
        r = await c.post("/api/tools/port-scan/range", json={"host": "127.0.0.1", "start": 8760, "end": 8770})
        ok = check("POST /api/tools/port-scan/range", r)
        record("端口范围扫描", ok)

        # 快速端口测试
        r = await c.post("/api/tools/port-test", json={"host": "127.0.0.1", "port": 8765})
        ok = check("POST /api/tools/port-test", r)
        record("端口测试", ok)

        # 路由跟踪
        r = await c.post("/api/tools/traceroute", json={"host": "127.0.0.1", "max_hops": 5, "timeout": 2})
        ok = check("POST /api/tools/traceroute", r)
        record("路由跟踪", ok)

        # DNS查询
        r = await c.get("/api/tools/dns/localhost")
        ok = check("GET /api/tools/dns/localhost", r)
        record("DNS查询", ok)

        # 反向DNS
        r = await c.get("/api/tools/reverse-dns/127.0.0.1")
        ok = check("GET /api/tools/reverse-dns/127.0.0.1", r)
        record("反向DNS", ok)

        # 本机信息
        r = await c.get("/api/tools/network-info/local")
        ok = check("GET /api/tools/network-info/local", r)
        record("本机IP", ok)

        # 配置比较
        r = await c.post("/api/tools/config-compare", json={
            "config1": "sysname R1\ninterface Vlanif10\n ip address 10.1.1.1 24",
            "config2": "sysname R2\ninterface Vlanif10\n ip address 10.2.2.1 24",
        })
        ok = check("POST /api/tools/config-compare", r)
        record("配置比较", ok)

        # 命令转换
        r = await c.post("/api/tools/config-convert", json={
            "config": "port trunk allow-pass vlan 10 20",
            "from_vendor": "huawei",
            "to_vendor": "h3c",
        })
        ok = check("POST /api/tools/config-convert", r)
        record("命令转换", ok)
        if ok:
            print(f"         {r.json().get('result', '')}")

        # 配置解析
        r = await c.post("/api/tools/config-parse", json={
            "config_text": "sysname Test\ninterface GigabitEthernet0/0/1\n port link-type access"
        })
        ok = check("POST /api/tools/config-parse", r)
        record("配置解析", ok)

        # JSON导入
        r = await c.post("/api/tools/config-import/json", json={
            "json_str": '{"vendor": "huawei", "hostname": "Test"}'
        })
        ok = check("POST /api/tools/config-import/json", r)
        record("JSON导入", ok)

        # ---- 10. 设备管理 ----
        section("10. 设备管理 (CRUD)")
        r = await c.get("/api/devices")
        ok = check("GET /api/devices", r)
        record("设备列表", ok)

        r = await c.post("/api/devices", json={
            "name": "Test-SW-01",
            "vendor": "huawei",
            "device_type": "switch",
            "host": "192.168.255.1",
            "port": 22,
            "username": "admin",
            "password": "test",
        })
        ok = check("POST /api/devices", r)
        record("创建设备", ok)
        device_id = r.json().get("device_id") if ok else None
        if device_id:
            print(f"         设备ID: {device_id}")

            r = await c.get(f"/api/devices/{device_id}/configs")
            ok = check("GET /api/devices/{id}/configs", r)
            record("设备配置历史", ok)

            r = await c.put(f"/api/devices/{device_id}", json={"location": "DC1-Rack1"})
            ok = check("PUT /api/devices/{id}", r)
            record("更新设备", ok)

            r = await c.delete(f"/api/devices/{device_id}")
            ok = check("DELETE /api/devices/{id}", r)
            record("删除设备", ok)

    # ---- 11. 命令级回滚引擎 ----
    section("11. 命令级回滚引擎 (单元测试)")
    sys.path.insert(0, BACKEND_DIR)
    from app.services.device_connector import CommandRollbackEngine, CommandResult

    engine_hw = CommandRollbackEngine("huawei")
    test_cases = [
        ("sysname Core-SW-01", "undo sysname Core-SW-01"),
        ("vlan 10", None),
        ("description Mgmt", "undo description Mgmt"),
        ("port default vlan 10", "undo port default vlan 10"),
        ("display current-configuration", None),
        ("save", None),
        ("quit", None),
        ("system-view", None),
        ("interface GigabitEthernet0/0/1", None),
        ("ip address 10.1.1.1 24", "undo ip address 10.1.1.1 24"),
    ]
    all_ok = True
    for cmd, expected in test_cases:
        actual = engine_hw.generate_undo(cmd)
        ok = actual == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] undo('{cmd}') = '{actual}'  (期望: '{expected}')")
        if not ok:
            all_ok = False
    record("华为undo生成", all_ok)

    # H3C
    engine_h3c = CommandRollbackEngine("h3c")
    h3c_undo = engine_h3c.generate_undo("port access vlan 10")
    ok = h3c_undo == "undo port access vlan 10"
    print(f"  [{'PASS' if ok else 'FAIL'}] h3c undo('port access vlan 10') = '{h3c_undo}'")
    record("H3C undo生成", ok)

    # 锐捷 (no 前缀)
    engine_rj = CommandRollbackEngine("ruijie")
    rj_undo = engine_rj.generate_undo("hostname SW1")
    ok = rj_undo == "no hostname SW1"
    print(f"  [{'PASS' if ok else 'FAIL'}] ruijie undo('hostname SW1') = '{rj_undo}'")
    record("锐捷no前缀", ok)

    # 逆序回滚
    executed = [
        CommandResult(command="sysname R1", success=True, undo_command="undo sysname R1"),
        CommandResult(command="interface Vlanif10", success=True, undo_command=None),
        CommandResult(command="ip address 10.1.1.1 24", success=True, undo_command="undo ip address 10.1.1.1 24"),
        CommandResult(command="description Mgmt", success=True, undo_command="undo description Mgmt"),
        CommandResult(command="bad-cmd", success=False, undo_command=None),
    ]
    rollback = engine_hw.get_rollback_commands(executed)
    expected_rb = ["undo description Mgmt", "undo ip address 10.1.1.1 24", "undo sysname R1"]
    ok = rollback == expected_rb
    print(f"  [{'PASS' if ok else 'FAIL'}] 逆序回滚: {rollback}")
    if not ok:
        print(f"         期望: {expected_rb}")
    record("逆序回滚逻辑", ok)

    # 只回滚成功的命令
    executed2 = [
        CommandResult(command="cmd1", success=True, undo_command="undo cmd1"),
        CommandResult(command="cmd2", success=False, undo_command="undo cmd2"),
        CommandResult(command="cmd3", success=True, undo_command="undo cmd3"),
    ]
    rollback2 = engine_hw.get_rollback_commands(executed2)
    ok = rollback2 == ["undo cmd3", "undo cmd1"]
    print(f"  [{'PASS' if ok else 'FAIL'}] 只回滚成功命令: {rollback2}  (期望: ['undo cmd3', 'undo cmd1'])")
    record("只回滚成功命令", ok)

    # ---- 汇总 ----
    section("测试汇总")
    total = results["pass"] + results["fail"]
    print(f"  总计: {total}  通过: {results['pass']}  失败: {results['fail']}")
    if results["fail"]:
        print("\n  失败项:")
        for d in results["details"]:
            if not d["ok"]:
                print(f"    - {d['name']}: {d['detail']}")
    print(f"\n  通过率: {results['pass']}/{total} = {results['pass']/total*100:.1f}%")
    return results["fail"] == 0


if __name__ == "__main__":
    import httpx as _hx
    try:
        _hx.get(f"{BASE}/health", timeout=2)
        print(f"服务器已在运行 ({BASE})")
        proc = None
    except:
        print("启动服务器...")
        proc = start_server()
        print(f"服务器已启动 (PID={proc.pid})")
    try:
        ok = asyncio.run(run_tests())
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)
        print("\n服务器已停止")
    sys.exit(0 if ok else 1)
