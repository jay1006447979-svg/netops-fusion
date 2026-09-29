"""设备连接服务 — 异步SSH/串口连接 + 命令级回滚

回滚策略（用户要求）:
  每条命令执行前生成对应 undo 反向命令, 记录执行状态。
  任一命令失败时, 按逆序执行已成功命令的 undo 实现回滚。
  而非备份整个配置再恢复。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class ConnectionType(str, Enum):
    ssh = "ssh"
    telnet = "telnet"
    serial = "serial"


class ConnectionStatus(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    connected = "connected"
    error = "error"
    rolling_back = "rolling_back"


@dataclass
class ConnectionParams:
    connection_type: ConnectionType = ConnectionType.ssh
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    enable_password: Optional[str] = None
    serial_port: Optional[str] = None
    baudrate: int = 9600
    data_bits: int = 8
    parity: str = "N"
    stop_bits: int = 1
    timeout: int = 30
    vendor: str = "huawei"


@dataclass
class CommandResult:
    command: str
    success: bool
    output: str = ""
    undo_command: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ConnectionResult:
    success: bool
    status: ConnectionStatus
    message: str
    output: str = ""
    progress: float = 0.0
    results: List[CommandResult] = field(default_factory=list)
    rollback_performed: bool = False
    rollback_results: List[CommandResult] = field(default_factory=list)


class CommandRollbackEngine:
    """命令级回滚引擎

    核心逻辑:
    1. 每条命令执行前, 根据 vendor 生成 undo 反向命令
    2. 记录每条命令的执行结果
    3. 任一命令失败时, 按逆序执行已成功命令的 undo
    """

    # 各厂商的 undo 前缀
    UNDO_PREFIX = {
        "huawei": "undo ",
        "h3c": "undo ",
        "ruijie": "no ",
        "maipu": "no ",
        "cisco": "no ",
    }

    # 需要特殊处理回滚的命令模式 (无法简单 undo 的)
    NO_ROLLBACK_PATTERNS = [
        r"^display\s",
        r"^show\s",
        r"^save$",
        r"^quit$",
        r"^return$",
        r"^system-view$",
        r"^reset\s",
        r"^reboot$",
        r"^interface\s",  # 进入视图, undo 时需要重新进入
    ]

    # 进入视图类命令 (回滚时需配合退出)
    VIEW_ENTER_PATTERNS = {
        r"^interface\s(\S+)": "interface {0}",
        r"^vlan\s(\d+)": "vlan {0}",
        r"^acl\s(number\s)?(\d+)": "acl number {1}",
        r"^aaa$": "aaa",
        r"^ospf\s(\d+)": "ospf {0}",
        r"^bgp\s(\d+)": "bgp {0}",
        r"^radius-server\stemplate\s(\S+)": "radius-server template {0}",
        r"^user-interface\s(\S+\s\d+\s\d+)": "user-interface {0}",
    }

    def __init__(self, vendor: str = "huawei"):
        self.vendor = vendor
        self.prefix = self.UNDO_PREFIX.get(vendor, "undo ")

    def generate_undo(self, command: str) -> Optional[str]:
        """为一条命令生成对应的 undo 反向命令

        Returns:
            undo 命令字符串, 或 None 表示该命令不需要/无法回滚
        """
        cmd = command.strip()
        if not cmd:
            return None

        # 查询类命令不需要回滚
        for pattern in self.NO_ROLLBACK_PATTERNS:
            if re.match(pattern, cmd):
                return None

        # 进入视图类命令 — 回滚时需要进入视图再 undo 子命令
        # 但视图本身不需要 undo, 返回 None
        for pattern in self.VIEW_ENTER_PATTERNS:
            if re.match(pattern, cmd):
                return None

        # 已是 undo/no 命令 — 回滚时恢复原值, 但无法知道原值, 标记为不可回滚
        if cmd.startswith("undo ") or cmd.startswith("no "):
            # 去掉 undo/no 前缀即为原命令, 但原值未知
            return None

        # 通用: 加 undo/no 前缀
        return self.prefix + cmd

    def generate_undo_batch(self, commands: List[str]) -> List[tuple[str, Optional[str]]]:
        """为命令批次生成 (命令, undo命令) 对"""
        return [(cmd, self.generate_undo(cmd)) for cmd in commands]

    def get_rollback_commands(self, executed: List[CommandResult]) -> List[str]:
        """从已执行命令中提取需要回滚的 undo 命令 (逆序)"""
        rollback = []
        for cr in reversed(executed):
            if cr.success and cr.undo_command:
                rollback.append(cr.undo_command)
        return rollback


class DeviceConnector:
    """异步设备连接器"""

    def __init__(self):
        self.status: ConnectionStatus = ConnectionStatus.disconnected
        self.progress: float = 0.0
        self.log: List[str] = []
        self._connection = None
        self._shell = None
        self._lock = asyncio.Lock()

    def _log(self, msg: str):
        self.log.append(msg)
        logger.info(msg)
        if len(self.log) > 1000:
            self.log = self.log[-500:]

    async def connect(self, params: ConnectionParams) -> ConnectionResult:
        """连接设备"""
        self.status = ConnectionStatus.connecting
        self._log(f"正在连接 {params.host}:{params.port} ({params.connection_type.value})")

        try:
            if params.connection_type == ConnectionType.ssh:
                return await self._connect_ssh(params)
            elif params.connection_type == ConnectionType.telnet:
                return await self._connect_telnet(params)
            elif params.connection_type == ConnectionType.serial:
                return await self._connect_serial(params)
            else:
                return ConnectionResult(
                    success=False,
                    status=ConnectionStatus.error,
                    message=f"暂不支持 {params.connection_type.value} 连接",
                )
        except Exception as e:
            self.status = ConnectionStatus.error
            self._log(f"连接失败: {e}")
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message=str(e),
            )

    async def _connect_ssh(self, params: ConnectionParams) -> ConnectionResult:
        """SSH 连接"""
        try:
            import asyncssh
        except ImportError:
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message="asyncssh 未安装, 请执行 pip install asyncssh",
            )

        try:
            self._connection = await asyncio.wait_for(
                asyncssh.connect(
                    host=params.host,
                    port=params.port,
                    username=params.username,
                    password=params.password,
                    known_hosts=None,
                ),
                timeout=params.timeout,
            )
            self._connection_type = "ssh"
            self.status = ConnectionStatus.connected
            self.progress = 100.0
            self._log(f"SSH 连接成功: {params.host}")
            return ConnectionResult(
                success=True,
                status=ConnectionStatus.connected,
                message=f"SSH 连接成功: {params.host}",
                progress=100.0,
            )
        except asyncio.TimeoutError:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message="连接超时",
            )
        except Exception as e:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message=f"SSH 连接失败: {e}",
            )

    @staticmethod
    async def _read_until_prompt(
        reader, idle: float = 1.0, total: float = 6.0
    ) -> bytes:
        """读取 Telnet 输出直到出现提示符或静默, 替代固定时长的阻塞读

        出现以下任一情况立即返回:
        - 读到 Username:/Password:/login: 等登录提示 (以 ':' 结尾)
        - 读到 '>' / '#' 执行提示符
        - idle 秒内无新数据 (设备静默)
        """
        buf = b""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + total
        while loop.time() < deadline:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=idle)
            except asyncio.TimeoutError:
                break  # 静默 — 设备暂时没有更多输出
            if not chunk:
                break
            buf += chunk
            text = buf.decode(errors="ignore").rstrip()
            # 登录提示以 ':' 结尾; 华为/H3C 用户提示符 '>', 特权 '#'
            if text.endswith((":", ">", "#")):
                break
        return buf

    async def _connect_telnet(self, params: ConnectionParams) -> ConnectionResult:
        """Telnet 连接 — 使用 asyncio.open_connection() 替代已废弃的 telnetlib"""
        try:
            t0 = asyncio.get_event_loop().time()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(params.host, params.port),
                timeout=params.timeout,
            )

            # 等待登录提示 (读到提示符/静默即返回, 不再固定等待 5s)
            banner = await self._read_until_prompt(reader, idle=1.0, total=6.0)
            banner_str = banner.decode(errors="ignore")

            # 检测登录提示
            if "Username:" in banner_str or "login:" in banner_str.lower() or "username:" in banner_str.lower():
                writer.write((params.username + "\n").encode())
                await writer.drain()
                resp = await self._read_until_prompt(reader, idle=1.0, total=4.0)
                banner_str += resp.decode(errors="ignore")

            # 密码提示 (可能在同一段输出里, 也可能在用户名之后)
            if "Password:" in banner_str or "password:" in banner_str.lower():
                writer.write(((params.password or "") + "\n").encode())
                await writer.drain()
                resp = await self._read_until_prompt(reader, idle=1.2, total=4.0)
                banner_str += resp.decode(errors="ignore")

            # 验证登录结果
            post_str = banner_str
            login_failed = any(
                kw in post_str.lower()
                for kw in ["login incorrect", "authentication failed", "bad password", "login failed", "access denied", "try again"]
            )

            if login_failed:
                writer.close()
                self.status = ConnectionStatus.error
                self._log(f"Telnet 登录失败: 用户名或密码错误")
                return ConnectionResult(
                    success=False,
                    status=ConnectionStatus.error,
                    message="Telnet 登录失败: 用户名或密码错误",
                )

            # 存储 reader/writer 供后续读写
            self._reader = reader
            self._writer = writer
            self._connection = writer  # 保持兼容性
            self._connection_type = "telnet"
            self.status = ConnectionStatus.connected
            self.progress = 100.0
            self._log(f"Telnet 连接成功: {params.host} (耗时 {asyncio.get_event_loop().time() - t0:.1f}s)")
            return ConnectionResult(
                success=True,
                status=ConnectionStatus.connected,
                message=f"Telnet 连接成功: {params.host}",
                progress=100.0,
            )
        except asyncio.TimeoutError:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message="Telnet 连接超时",
            )
        except ConnectionRefusedError:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message=f"Telnet 连接被拒绝: {params.host}:{params.port}",
            )
        except Exception as e:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message=f"Telnet 连接失败: {e}",
            )

    async def _connect_serial(self, params: ConnectionParams) -> ConnectionResult:
        """串口连接"""
        try:
            import serial
        except ImportError:
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message="pyserial 未安装, 请执行 pip install pyserial",
            )

        try:
            self._connection = serial.Serial(
                port=params.serial_port,
                baudrate=params.baudrate,
                bytesize=params.data_bits,
                parity=params.parity,
                stopbits=params.stop_bits,
                timeout=params.timeout,
            )
            self.status = ConnectionStatus.connected
            self.progress = 100.0
            self._log(f"串口连接成功: {params.serial_port}")
            return ConnectionResult(
                success=True,
                status=ConnectionStatus.connected,
                message=f"串口连接成功: {params.serial_port}",
                progress=100.0,
            )
        except Exception as e:
            self.status = ConnectionStatus.error
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.error,
                message=f"串口连接失败: {e}",
            )

    async def send_command(self, command: str, timeout: int = 10) -> str:
        """发送单条命令并获取输出"""
        if self._connection_type == "telnet" and self._reader and self._writer:
            # Telnet: 通过 reader/writer 读写
            try:
                self._writer.write((command + "\n").encode())
                await self._writer.drain()
                # 等待设备响应 — 多次短读拼起来
                out = b""
                for _ in range(10):
                    try:
                        chunk = await asyncio.wait_for(self._reader.read(4096), timeout=0.8)
                        if chunk:
                            out += chunk
                        else:
                            break
                    except asyncio.TimeoutError:
                        break
                text = out.decode(errors="ignore")
                # 清理回显 (去掉第一行回显的命令本身)
                lines = text.splitlines()
                if lines and command.strip() in lines[0]:
                    text = "\n".join(lines[1:])
                return text.strip() or text
            except Exception as e:
                return f"error: {e}"

        if not self._connection:
            return ""

        if self._connection_type == "ssh" and hasattr(self._connection, "run"):
            # asyncssh
            try:
                result = await asyncio.wait_for(
                    self._connection.run(command), timeout=timeout
                )
                return result.stdout or ""
            except Exception as e:
                return f"error: {e}"
        elif hasattr(self._connection, "write"):
            # serial
            self._connection.write((command + "\n").encode())
            await asyncio.sleep(0.5)
            output = self._connection.read_all().decode(errors="ignore")
            return output
        return ""

    async def send_config(
        self,
        config_text: str,
        vendor: str = "huawei",
        log_callback: Optional[Callable] = None,
    ) -> ConnectionResult:
        """下发配置 — 带命令级回滚

        1. 解析配置为命令列表
        2. 每条命令执行前生成 undo 反向命令
        3. 逐条执行, 记录结果
        4. 任一命令失败, 按逆序执行已成功命令的 undo
        """
        async with self._lock:
            if self.status != ConnectionStatus.connected:
                return ConnectionResult(
                    success=False,
                    status=self.status,
                    message=f"设备未连接 (当前状态: {self.status.value})",
                )

            # 解析配置为命令列表
            commands = self._parse_config_to_commands(config_text)
            rollback_engine = CommandRollbackEngine(vendor)

            total = len(commands)
            results: List[CommandResult] = []
            self._log(f"开始下发配置, 共 {total} 条命令")

            for i, cmd in enumerate(commands):
                undo = rollback_engine.generate_undo(cmd)
                progress = (i / total * 100) if total else 100
                self.progress = progress

                output = await self.send_command(cmd)
                # 简单判断成功: 无 error/Error/Invalid 关键字
                is_error = any(
                    kw in output for kw in ["Error", "error", "Invalid", "invalid", "Wrong", "% "]
                )
                success = not is_error

                cr = CommandResult(
                    command=cmd,
                    success=success,
                    output=output,
                    undo_command=undo,
                    error=output if is_error else None,
                )
                results.append(cr)

                if log_callback:
                    log_callback({
                        "type": "command",
                        "index": i + 1,
                        "total": total,
                        "command": cmd,
                        "success": success,
                        "output": output,
                    })

                self._log(f"[{i+1}/{total}] {'OK' if success else 'FAIL'}: {cmd}")

                if not success:
                    # 命令失败 — 触发命令级回滚
                    self._log(f"命令执行失败, 开始命令级回滚: {cmd}")
                    self.status = ConnectionStatus.rolling_back

                    rollback_cmds = rollback_engine.get_rollback_commands(results)
                    rollback_results = []

                    for rb_cmd in rollback_cmds:
                        rb_output = await self.send_command(rb_cmd)
                        rb_success = not any(
                            kw in rb_output
                            for kw in ["Error", "error", "Invalid", "invalid"]
                        )
                        rb_cr = CommandResult(
                            command=rb_cmd,
                            success=rb_success,
                            output=rb_output,
                        )
                        rollback_results.append(rb_cr)
                        if log_callback:
                            log_callback({
                                "type": "rollback",
                                "command": rb_cmd,
                                "success": rb_success,
                                "output": rb_output,
                            })
                        self._log(f"[回滚] {'OK' if rb_success else 'FAIL'}: {rb_cmd}")

                    self.status = ConnectionStatus.connected
                    self.progress = 100.0
                    return ConnectionResult(
                        success=False,
                        status=ConnectionStatus.connected,
                        message=f"配置下发失败, 已回滚 {len(rollback_cmds)} 条命令",
                        output=f"失败命令: {cmd}\n回滚执行: {len(rollback_results)} 条",
                        progress=100.0,
                        results=results,
                        rollback_performed=True,
                        rollback_results=rollback_results,
                    )

            self.progress = 100.0
            self._log("配置下发完成")
            return ConnectionResult(
                success=True,
                status=ConnectionStatus.connected,
                message=f"配置下发成功, 共执行 {total} 条命令",
                progress=100.0,
                results=results,
            )

    async def send_show_command(self, command: str) -> ConnectionResult:
        """发送查询命令"""
        if self.status != ConnectionStatus.connected:
            return ConnectionResult(
                success=False,
                status=self.status,
                message="设备未连接",
            )
        output = await self.send_command(command)
        return ConnectionResult(
            success=True,
            status=ConnectionStatus.connected,
            message="命令执行成功",
            output=output,
        )

    # 各厂商获取运行配置的命令
    RUNNING_CONFIG_COMMANDS = {
        "huawei": "display current-configuration",
        "h3c": "display current-configuration",
        "ruijie": "show running-config",
        "maipu": "show running-config",
        "cisco": "show running-config",
    }

    # 各厂商关闭分页的命令 (抓长输出前必须先执行, 否则设备按屏暂停等空格)
    PAGING_DISABLE_COMMANDS = {
        "huawei": "screen-length 0 temporary",
        "h3c": "screen-length disable",
        "ruijie": "terminal length 0",
        "maipu": "terminal length 0",
        "cisco": "terminal length 0",
    }

    @staticmethod
    def _clean_stream_output(text: str) -> str:
        """清洗 Telnet 流式输出 — 去除 More 提示、翻页覆盖残留与 ANSI 转义序列

        设备分页翻页时会回显终端控制序列, 例如:
          #\\x1b[42D<42个空格>\\x1b[42Dinterface GigabitEthernet0/0/24
        其中 \\x1b[42D 是"光标左移42列", 用于擦除屏底的 ---- More ---- 提示符,
        不清理会把上一行和续接行粘在一起, 污染配置文件。
        """
        # 1) 分页提示符 (华为/H3C 新版本可能带百分比, 如 ---- More ---- (42%))
        text = re.sub(r"----\s*More\s*----\s*(?:\(\d+%\))?\s*", "", text)
        # 2) 翻页覆盖残留: 光标左移 + 擦除空格 (+再次光标左移) → 还原为换行,
        #    让续接内容 (如 interface xxx) 独立成行
        text = re.sub(r"\x1b\[\d+D {2,}\x1b\[\d+D[ ]*", "\n", text)
        text = re.sub(r"\x1b\[\d+D {2,}", "\n", text)
        # 3) 其余 ANSI 转义序列 (光标移动/清屏/字符集切换等)
        text = re.sub(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[()][0-9A-B]|[@-Z\\-_])", "", text)
        # 4) 残留控制字符 (保留 \r \n \t)
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
        # 5) 压缩翻页还原产生的连续空行 (配置文件中无意义)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    async def _read_telnet_stream(self, budget: float = 90, idle: float = 3.0) -> str:
        """Telnet 长输出流式读取 — 读到空闲为止, 自动处理 More 分页

        Args:
            budget: 总时长上限 (秒)
            idle: 连续无新数据的空闲判定 (秒)
        """
        out = b""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        while loop.time() < deadline:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=idle)
            except asyncio.TimeoutError:
                break  # 空闲 — 输出结束
            if not chunk:
                break  # EOF
            out += chunk
            tail = out[-120:].decode(errors="ignore")
            # 兜底: 若设备仍在分页, 发空格翻页
            if "---- More" in tail or "----more" in tail.lower():
                try:
                    self._writer.write(b" ")
                    await self._writer.drain()
                except Exception:
                    break
        text = out.decode(errors="ignore")
        # 清理分页提示符/ANSI 转义序列/翻页覆盖残留
        return self._clean_stream_output(text)

    async def _reset_telnet_session(self):
        """复位 Telnet 会话 — Ctrl+C 中断可能挂起的分页/上一条命令, 清空残留输出"""
        try:
            self._writer.write(b"\x03")  # Ctrl+C 中断当前输出/命令
            await self._writer.drain()
            await asyncio.sleep(0.5)
            self._writer.write(b"\r\n")
            await self._writer.drain()
            await asyncio.sleep(0.5)
            # 排空残留输出
            loop = asyncio.get_running_loop()
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)
                    if not chunk:
                        break
                except asyncio.TimeoutError:
                    break
        except Exception:
            pass

    async def get_running_config(self, vendor: str = "huawei") -> ConnectionResult:
        """获取设备当前运行配置 (用于配置备份)

        Args:
            vendor: 设备厂商, 决定执行的查看命令
                - 华为/H3C: display current-configuration
                - 锐捷/迈普: show running-config
        """
        if self.status != ConnectionStatus.connected:
            return ConnectionResult(
                success=False,
                status=self.status,
                message="设备未连接",
            )

        # 0. 复位会话 — 上次连接遗留的 "---- More ----" 等待状态会吞掉后续命令
        if self._connection_type == "telnet" and self._reader and self._writer:
            await self._reset_telnet_session()

        # 1. 先关闭分页, 否则长配置输出会在第一屏暂停等待按键
        disable_cmd = self.PAGING_DISABLE_COMMANDS.get(vendor)
        if disable_cmd and self._connection_type == "telnet":
            self._log(f"关闭分页: {disable_cmd}")
            await self.send_command(disable_cmd, timeout=10)

        command = self.RUNNING_CONFIG_COMMANDS.get(vendor, "display current-configuration")
        self._log(f"获取运行配置: {command} ({vendor})")

        # 2. 获取配置 — Telnet 用流式读取 (大配置可能需要较长时间)
        if self._connection_type == "telnet" and self._reader and self._writer:
            try:
                self._writer.write((command + "\n").encode())
                await self._writer.drain()
                output = await self._read_telnet_stream(budget=90, idle=3.0)
            except Exception as e:
                return ConnectionResult(
                    success=False,
                    status=ConnectionStatus.connected,
                    message=f"获取配置失败: {e}",
                )
        else:
            output = await self.send_command(command, timeout=60)
            output = self._clean_stream_output(output)

        # 3. 清理: 去掉命令回显行、末尾提示符行和空行 (厂商配置输出中无空行)
        lines = output.splitlines()
        if lines and command.split()[0] in lines[0] and command in lines[0]:
            lines = lines[1:]
        if lines and re.match(r"^[<\[]?[\w.-]+[>\]]\s*$", lines[-1].strip()):
            lines = lines[:-1]
        lines = [line for line in lines if line.strip()]
        output = "\n".join(lines).strip()

        # 简单校验: 输出不能为空/纯错误
        if not output or not output.strip():
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.connected,
                message="获取配置失败: 设备无输出 (请检查用户级别是否足够)",
            )
        if any(kw in output for kw in ["Error:", "error:", "Invalid command", "% Unknown"]):
            return ConnectionResult(
                success=False,
                status=ConnectionStatus.connected,
                message=f"获取配置失败: 设备返回错误: {output[:200]}",
            )

        self._log(f"获取配置成功: {len(output)} 字符")
        return ConnectionResult(
            success=True,
            status=ConnectionStatus.connected,
            message="获取运行配置成功",
            output=output,
        )

    async def test_connection(self, params: ConnectionParams) -> ConnectionResult:
        """测试连通性"""
        result = await self.connect(params)
        if result.success:
            await self.disconnect()
        return result

    async def disconnect(self):
        """断开连接"""
        if self._connection:
            try:
                if self._connection_type == "telnet" and self._writer:
                    self._writer.close()
                    try:
                        await self._writer.wait_closed()
                    except Exception:
                        pass
                elif hasattr(self._connection, "close"):
                    self._connection.close()
                    if hasattr(self._connection, "wait_closed"):
                        await self._connection.wait_closed()
            except Exception:
                pass
            self._connection = None
        self._reader = None
        self._writer = None
        self._connection_type = None
        self.status = ConnectionStatus.disconnected
        self.progress = 0.0
        self._log("连接已断开")

    @staticmethod
    def _parse_config_to_commands(config_text: str) -> List[str]:
        """将配置文本解析为命令列表"""
        commands = []
        for line in config_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith("!"):
                continue
            commands.append(line)
        return commands


# 全局单例
_connector: Optional[DeviceConnector] = None


async def tcp_probe(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """快速 TCP 探测 — 判断网络层是否可达, 不做任何协议交互

    网络不通的场景 3 秒内即可返回, 不必等完整登录流程超时。
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, f"TCP {host}:{port} 可达"
    except asyncio.TimeoutError:
        return False, f"网络不可达: {host}:{port} {timeout:.0f} 秒内无响应"
    except ConnectionRefusedError:
        return False, f"端口拒绝连接: {host}:{port} (服务未开启或端口错误)"
    except OSError as e:
        return False, f"网络错误: {e}"


def get_connector() -> DeviceConnector:
    global _connector
    if _connector is None:
        _connector = DeviceConnector()
    return _connector


def reset_connector():
    global _connector
    _connector = None
