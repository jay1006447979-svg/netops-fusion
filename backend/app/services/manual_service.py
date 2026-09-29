"""命令手册知识库服务 — 全文检索/按厂商模块筛选/命令转换"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml

from app.core.config import settings
from app.tools.config_compare import ConfigCompare


class ManualService:
    """命令手册知识库"""

    def __init__(self):
        self.manual_dir: Path = settings.MANUAL_DIR
        self._cache: dict[str, dict] = {}

    def _load_manual(self, vendor: str) -> Optional[dict]:
        """加载指定厂商的命令手册"""
        if vendor in self._cache:
            return self._cache[vendor]

        f = self.manual_dir / f"{vendor}_manual.yaml"
        if not f.exists():
            return None

        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            self._cache[vendor] = data
            return data
        except Exception:
            return None

    def list_vendors(self) -> List[str]:
        """列出有手册的厂商"""
        if not self.manual_dir.exists():
            return []
        return sorted(f.stem.replace("_manual", "") for f in self.manual_dir.glob("*_manual.yaml"))

    def get_categories(self, vendor: str) -> List[dict]:
        """获取厂商的命令分类"""
        manual = self._load_manual(vendor)
        if not manual:
            return []
        return [
            {"name": cat.get("name", ""), "count": len(cat.get("commands", []))}
            for cat in manual.get("categories", [])
        ]

    def search(self, keyword: str, vendor: Optional[str] = None) -> List[dict]:
        """全文检索命令"""
        results = []
        vendors = [vendor] if vendor else self.list_vendors()

        for v in vendors:
            manual = self._load_manual(v)
            if not manual:
                continue
            for cat in manual.get("categories", []):
                for cmd in cat.get("commands", []):
                    searchable = " ".join(
                        str(cmd.get(k, ""))
                        for k in ["command", "syntax", "description", "example"]
                    )
                    if keyword.lower() in searchable.lower():
                        results.append(
                            {
                                "vendor": v,
                                "category": cat.get("name", ""),
                                **cmd,
                            }
                        )
        return results

    def get_by_category(self, vendor: str, category: str) -> List[dict]:
        """按分类获取命令"""
        manual = self._load_manual(vendor)
        if not manual:
            return []
        for cat in manual.get("categories", []):
            if cat.get("name") == category:
                return cat.get("commands", [])
        return []

    def get_cases(self, vendor: str) -> List[dict]:
        """获取厂商的配置案例"""
        manual = self._load_manual(vendor)
        if not manual:
            return []
        return manual.get("cases", [])

    def get_all_commands(self, vendor: str) -> List[dict]:
        """获取厂商全部命令"""
        manual = self._load_manual(vendor)
        if not manual:
            return []
        commands = []
        for cat in manual.get("categories", []):
            for cmd in cat.get("commands", []):
                commands.append({"category": cat.get("name", ""), **cmd})
        return commands

    def convert_config(self, config_text: str, from_vendor: str, to_vendor: str) -> str:
        """命令转换"""
        if from_vendor == "huawei" and to_vendor == "h3c":
            return ConfigCompare.convert_huawei_to_h3c(config_text)
        elif from_vendor == "h3c" and to_vendor == "huawei":
            # 简单逆向转换
            result = config_text
            for h3c_cmd, hw_cmd in reversed(list(ConfigCompare.HUAWEI_TO_H3C.items())):
                result = result.replace(h3c_cmd, hw_cmd)
            return result
        return config_text

    def get_stats(self) -> dict:
        """获取手册统计信息 — 返回 { vendor: command_count } 简单格式"""
        stats = {}
        for vendor in self.list_vendors():
            manual = self._load_manual(vendor)
            if manual:
                total = sum(
                    len(cat.get("commands", []))
                    for cat in manual.get("categories", [])
                )
                stats[vendor] = total
        return stats


manual_service = ManualService()
