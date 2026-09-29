# NetOps Fusion — 融合版网络设备配置工具

> 多厂商配置生成 · 设备推送(命令级回滚) · 11+网络工具 · 命令手册知识库

## 项目简介

NetOps Fusion 是一个基于 FastAPI 的网络设备配置自动化平台，融合了三个开源项目（NetOps-toolkit、network-configurator、network-config-tool）的优点，并修复了它们的命令错误和架构缺陷。

### 核心特性

| 特性 | 说明 |
|------|------|
| **多厂商配置生成** | 华为 / H3C / 锐捷 / 迈普，命令格式以 NetOps-toolkit 为正确基准 |
| **命令级回滚** | 每条命令生成对应 undo 反向命令，失败时按逆序回滚已执行命令（非整配置备份恢复） |
| **11+ 网络工具** | 子网计算、Ping、端口扫描、路由跟踪、DNS、配置比较、命令转换等 |
| **命令手册** | 华为 59 条 + H3C 47 条命令，8 大分类，全文检索 |
| **配置模板** | YAML 外部模板，即插即用 |
| **异步架构** | FastAPI + asyncssh + aiosqlite，全链路异步 |
| **WebSocket** | 配置推送实时日志流 |

## 技术栈

- **后端框架**: FastAPI 0.115.6 + Uvicorn
- **数据模型**: Pydantic v2 2.10.6
- **ORM**: SQLAlchemy 2.0.36 (async) + aiosqlite
- **SSH**: asyncssh 2.18.0
- **串口**: pyserial 3.5
- **数据库**: SQLite (异步)
- **前端**: 原生 HTML + CSS + JavaScript（FastAPI 内嵌托管，零构建）
- **Python**: 3.12+

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动服务

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

启动后访问：
- **Web 界面**: http://localhost:5000  ← 浏览器打开即可视化操作界面
- Swagger 文档: http://localhost:5000/docs
- 系统信息 JSON: http://localhost:5000/api/info
- 健康检查: http://localhost:5000/health

> 根路径 `/` 现在直接返回可视化 Web 界面（无需单独部署前端）。
> 界面包含 6 大模块：仪表盘、配置生成器、设备管理、网络工具箱、命令手册、配置模板。

### 3. Docker 部署

```bash
docker-compose up -d
```

## API 总览 (41 条路由)

### 配置生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/config/generate` | 生成设备配置（指定厂商） |
| POST | `/api/config/validate` | 校验配置参数 |
| POST | `/api/config/export` | 导出配置文件 (.cfg) |

### 厂商管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vendors` | 获取已注册厂商列表 |

### 配置模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/templates` | 模板列表（可按厂商过滤） |
| GET | `/api/templates/{id}` | 模板详情 |
| GET | `/api/templates/{id}/config` | 模板配置数据 |

### 命令手册

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/manual/vendors` | 有手册的厂商 |
| GET | `/api/manual/stats` | 手册统计 |
| GET | `/api/manual/search?keyword=xxx` | 全文检索命令 |
| GET | `/api/manual/{vendor}/categories` | 厂商命令分类 |
| GET | `/api/manual/{vendor}/commands` | 厂商全部命令 |
| GET | `/api/manual/{vendor}/category/{cat}` | 按分类获取命令 |

### 网络工具箱 (11+ 工具)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/subnet/calculate` | 子网计算 |
| POST | `/api/tools/subnet/divide` | 子网划分 |
| POST | `/api/tools/subnet/ip-range-to-cidr` | IP 范围转 CIDR |
| POST | `/api/tools/subnet/ip-convert` | IP 格式转换 (二进制/十进制/十六进制) |
| POST | `/api/tools/ping` | 单主机 Ping |
| POST | `/api/tools/ping/batch` | 批量 Ping |
| POST | `/api/tools/ping/scan` | Ping 扫描网段 |
| POST | `/api/tools/port-scan` | 端口扫描 |
| POST | `/api/tools/port-scan/range` | 端口范围扫描 |
| POST | `/api/tools/port-test` | 快速端口测试 |
| POST | `/api/tools/traceroute` | 路由跟踪 |
| GET | `/api/tools/dns/{domain}` | DNS 查询 |
| GET | `/api/tools/reverse-dns/{ip}` | 反向 DNS |
| GET | `/api/tools/whois/{domain}` | Whois 查询 |
| GET | `/api/tools/network-info/local` | 本机 IP |
| GET | `/api/tools/network-info/public-ip` | 公网 IP |
| POST | `/api/tools/config-compare` | 配置差异对比 |
| POST | `/api/tools/config-convert` | 华为↔H3C 命令转换 |
| POST | `/api/tools/config-parse` | 解析配置文本 |
| POST | `/api/tools/config-import/json` | JSON 导入配置 |

### 设备管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 设备列表 |
| POST | `/api/devices` | 添加设备 |
| PUT | `/api/devices/{id}` | 更新设备 |
| DELETE | `/api/devices/{id}` | 删除设备 |
| POST | `/api/devices/{id}/test` | 测试连通性 |
| POST | `/api/devices/{id}/push` | 推送配置（带命令级回滚） |
| GET | `/api/devices/{id}/configs` | 配置历史 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `ws://host/ws/logs` | 实时日志流（配置推送过程） |

## 命令级回滚机制

这是本项目的核心设计，区别于传统的"整配置备份恢复"方式。

### 工作原理

```
命令1 (成功) → undo_1 记录
命令2 (成功) → undo_2 记录
命令3 (成功) → undo_3 记录
命令4 (失败) → 触发回滚
  ↓
逆序执行 undo: undo_3 → undo_2 → undo_1
```

### 厂商 undo 前缀

| 厂商 | undo 前缀 | 示例 |
|------|-----------|------|
| 华为 / H3C | `undo ` | `undo port default vlan 10` |
| 锐捷 / 迈普 / Cisco | `no ` | `no hostname SW1` |

### 不回滚的命令

以下命令不生成 undo（无法或不需要回滚）：

- **查询类**: `display`、`show`
- **操作类**: `save`、`quit`、`return`、`reset`、`reboot`
- **视图进入**: `system-view`、`interface`、`vlan`、`aaa`、`ospf`、`bgp` 等
- **已是 undo 的命令**: `undo xxx` / `no xxx`（原值未知）

### 回滚规则

1. **只回滚已成功的命令** — 失败的命令本身不回滚
2. **逆序执行** — 最后执行的先回滚
3. **跳过无 undo 的命令** — 视图进入/查询类自动跳过

## 厂商命令差异对照

| 功能 | 华为 | H3C |
|------|------|-----|
| VLAN 接口 | `interface Vlanif10` | `interface Vlan-interface10` |
| Access VLAN | `port default vlan 10` | `port access vlan 10` |
| Trunk 放行 | `port trunk allow-pass vlan 10 20` | `port trunk permit vlan 10,20` |
| SSH 启用 | `stelnet server enable` | `ssh server enable` |
| 链路聚合 | `interface Eth-Trunk1` | `interface Bridge-Aggregation1` |
| 静态路由 | `ip route-static` | `ip route-static` |
| OSPF | `ospf 1` | `ospf 1` |

## 配置生成示例

### 请求

```bash
POST /api/config/generate
Content-Type: application/json

{
  "vendor": "huawei",
  "device_type": "switch",
  "hostname": "Core-SW-01",
  "basic": {
    "ssh": {"enable": true, "port": 22},
    "user": {"username": "admin", "password": "Admin@123", "level": 15},
    "ntp": {"servers": [{"ip": "10.1.1.1"}], "timezone": "UTC+8"}
  },
  "vlan": {
    "vlans": [{"id": 10, "name": "Mgmt"}],
    "interfaces": [
      {"interface": "GigabitEthernet0/0/1", "type": "access", "vlan_id": 10}
    ]
  }
}
```

### 响应 (华为)

```
sysname Core-SW-01
stelnet server enable
ssh server port 22
...
vlan 10
 name Mgmt
#
interface GigabitEthernet0/0/1
 port link-type access
 port default vlan 10
#
```

### 响应 (H3C — 同参数切换 vendor)

```
sysname H3C-Core-01
ssh server enable
...
vlan 10
 name Mgmt
#
interface GigabitEthernet0/0/1
 port link-type access
 port access vlan 10
#
```

## 项目结构

```
netops-fusion/
├── backend/
│   ├── app/
│   │   ├── api/              # API 路由层
│   │   │   ├── config_routes.py      # 配置生成/校验/导出
│   │   │   ├── device_routes.py      # 设备 CRUD + 推送
│   │   │   ├── manual_routes.py      # 命令手册
│   │   │   ├── template_routes.py    # 配置模板
│   │   │   ├── tool_routes.py        # 网络工具
│   │   │   └── ws_routes.py          # WebSocket
│   │   ├── core/             # 核心配置
│   │   │   ├── config.py             # 全局设置
│   │   │   └── registry.py           # 厂商注册表
│   │   ├── data/             # 数据文件
│   │   │   ├── manuals/              # YAML 命令手册
│   │   │   └── templates/            # YAML 配置模板
│   │   ├── db/               # 数据库层
│   │   ├── models/           # Pydantic 数据模型
│   │   ├── services/         # 业务服务层
│   │   │   ├── config_generator.py   # 配置生成工厂
│   │   │   ├── config_validator.py   # 配置校验
│   │   │   ├── device_connector.py   # 设备连接 + 回滚引擎
│   │   │   ├── manual_service.py     # 手册服务
│   │   │   └── template_service.py   # 模板服务
│   │   ├── tools/            # 网络工具箱
│   │   ├── vendors/          # 厂商配置生成器
│   │   │   ├── base.py               # 抽象基类
│   │   │   ├── huawei.py             # 华为 (正确命令基准)
│   │   │   ├── h3c.py                # H3C
│   │   │   ├── ruijie.py             # 锐捷
│   │   │   └── maipu.py              # 迈普
│   │   └── main.py           # FastAPI 入口
│   ├── tests/
│   │   └── test_e2e.py       # 端到端测试 (45 项全通过)
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## 扩展厂商

通过装饰器注册新厂商，零核心代码修改：

```python
from app.core.registry import vendor_registry
from app.vendors.base import BaseConfigGenerator

@vendor_registry.register("cisco", device_types=["switch", "router"])
class CiscoGenerator(BaseConfigGenerator):
    vendor = "cisco"

    def generate_basic(self, config: dict) -> str:
        ...

    def generate_vlan(self, config: dict) -> str:
        ...
    # ... 实现 5 个抽象方法即可
```

## 测试

```bash
cd backend
python tests/test_e2e.py
```

测试覆盖 45 项：
- 基础路由 (3)
- 厂商管理 (1)
- 四厂商配置生成 + 命令正确性验证 (9)
- 配置校验与导出 (2)
- 配置模板 (2)
- 命令手册 (5)
- 网络工具箱 11+ 工具 (18)
- 设备管理 CRUD (5)
- 命令级回滚引擎单元测试 (14)

## 已修复的原项目问题

| 问题 | 来源 | 修复 |
|------|------|------|
| f-string 缺少 f 前缀 | NetOps-toolkit huawei.py | `stp mode`、`lacp priority`、`lldp transmit interval`、`storm-control action` |
| 大量错误配置命令 | network-configurator / network-config-tool | 以 NetOps-toolkit 命令为正确基准重写 |
| 整配置备份回滚 | network-configurator | 改为命令级 undo 回滚 |
| telnetlib 不兼容 Python 3.13+ | NetOps-toolkit | 改用 asyncssh |
| 同步阻塞 IO | 三个项目均有 | 全链路异步化 |

## License

MIT
