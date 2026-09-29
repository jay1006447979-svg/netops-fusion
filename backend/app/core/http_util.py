"""HTTP 响应头工具 — 生成文件下载头

背景: 直接在 Content-Disposition 里放中文文件名会触发 latin-1 编码错误
      (HTTP 头只允许 ASCII), 导致下载接口 500。
      标准做法: 给一个 ASCII 回退名 + RFC 5987 的 filename* 携带 UTF-8 名。
"""

from __future__ import annotations

import re
from urllib.parse import quote

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_filename(filename: str, fallback: str = "download") -> str:
    """去掉路径分隔符与非法字符"""
    clean = _INVALID_CHARS.sub("_", (filename or "").strip())
    return clean or fallback


def attachment_header(filename: str, fallback: str = "download") -> str:
    """构造可安全下发中文文件名的 Content-Disposition 头"""
    clean = safe_filename(filename, fallback)
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", clean).strip("._") or fallback
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(clean)}'
