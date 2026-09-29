"""模板服务 — 从 YAML 文件加载预设配置模板"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml

from app.core.config import settings


class TemplateService:
    """配置模板管理"""

    def __init__(self):
        self.template_dir: Path = settings.TEMPLATE_DIR

    def list_templates(self, vendor: Optional[str] = None) -> list[dict]:
        templates = []
        if not self.template_dir.exists():
            return templates
        for f in sorted(self.template_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if vendor and data.get("vendor") != vendor:
                    continue
                templates.append(
                    {
                        "id": f.stem,
                        "name": data.get("name", f.stem),
                        "description": data.get("description", ""),
                        "vendor": data.get("vendor", "huawei"),
                        "device_type": data.get("device_type", "switch"),
                    }
                )
            except Exception:
                continue
        return templates

    def get_template(self, template_id: str) -> Optional[dict]:
        f = self.template_dir / f"{template_id}.yaml"
        if not f.exists():
            return None
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        return data

    def get_template_config(self, template_id: str) -> Optional[dict]:
        data = self.get_template(template_id)
        if data is None:
            return None
        return data.get("config", {})


template_service = TemplateService()
