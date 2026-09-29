# -*- coding: utf-8 -*-
"""合并桌面命令数据文件 (netops_toolkit) 到项目 YAML 手册。

数据源: C:/Users/User/Desktop/{huawei,h3c,ruijie,maipu}_manual.py
两种结构:
  - 华为/H3C: {大类: {子类: {命令名: {command, description, example}}}}
  - 锐捷/迈普: {大类: {子类: [{name, command, description, example}]}}
输出: backend/app/data/manuals/{vendor}_manual.yaml
规则:
  - 桌面命令以子类作为 YAML category，source 标记为 netops_toolkit
  - 现有 YAML 命令按归一化 syntax 去重后并入(同名列存在则跳过)
  - 现有命令保留其原 category 和 source 标签
  - 桌面文件中的 CASES 配置案例写入顶层 cases 字段
"""
import importlib.util
import re
import sys
from pathlib import Path

import yaml

DESKTOP = Path("C:/Users/User/Desktop")
MANUAL_DIR = Path("D:/WorkBuddy/NetWorkFig/netops-fusion/backend/app/data/manuals")

VENDORS = {
    "huawei": ("huawei_manual.py", "HUAWEI_COMMANDS", "HUAWEI_CASES"),
    "h3c": ("h3c_manual.py", "H3C_COMMANDS", "H3C_CASES"),
    "ruijie": ("ruijie_manual.py", "RUIJIE_COMMANDS", "RUIJIE_CASES"),
    "maipu": ("maipu_manual.py", "MAIPU_COMMANDS", "MAIPU_CASES"),
}

# 旧YAML分类 -> 新子类分类 映射(仅当目标分类存在时生效)
CATEGORY_MAP = {
    "基础配置": "系统管理",
    "系统管理与维护": "系统管理",
    "用户与AAA": "用户与权限管理",
    "VLAN配置": "VLAN接口",
    "接口基础配置": "以太网接口",
    "STP生成树": "STP基础",
    "VRRP与高可用": "VRRP配置",
    "QoS与限速": "流量整形",
}


def load_desktop_module(filename: str):
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), DESKTOP / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def norm(text: str) -> str:
    """归一化命令字符串用于去重比较(空白折叠 + 占位符内容忽略)"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"<[^<>]*>", "<>", t)  # <hostname> / <name> 视为相同占位符
    t = re.sub(r"\{[^{}]*\}", "{}", t)
    return t


def first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("或"):
            return line
    return ""


def normalize_commands(raw: dict) -> list[dict]:
    """统一两种桌面数据结构为 [{name, command, description, example}]"""
    out = []
    if isinstance(raw, dict):
        for name, info in raw.items():
            if not isinstance(info, dict):
                continue
            out.append(
                {
                    "name": name,
                    "command": info.get("command", ""),
                    "description": info.get("description", ""),
                    "example": info.get("example", ""),
                }
            )
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append(
                    {
                        "name": item.get("name", ""),
                        "command": item.get("command", ""),
                        "description": item.get("description", ""),
                        "example": item.get("example", ""),
                    }
                )
    return out


def extract_categories(commands_data: dict) -> list[dict]:
    """提取 {大类: {子类: ...}} -> [(子类, [命令...]), ...] 保持顺序"""
    cats = []
    for major, subs in commands_data.items():
        if not isinstance(subs, dict):
            continue
        for sub, raw in subs.items():
            cmds = normalize_commands(raw)
            if cmds:
                cats.append((sub, cmds))
    return cats


def main():
    report = {}
    for vendor, (fname, cmds_var, cases_var) in VENDORS.items():
        mod = load_desktop_module(fname)
        commands_data = getattr(mod, cmds_var)
        cases = getattr(mod, cases_var, [])

        yaml_path = MANUAL_DIR / f"{vendor}_manual.yaml"
        existing = {}
        refs = []
        reliability = ""
        if yaml_path.exists():
            old = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            refs = old.get("references", []) or []
            reliability = old.get("reliability", "")
            for cat in old.get("categories", []) or []:
                cname = cat.get("name", "")
                for cmd in cat.get("commands", []) or []:
                    key = norm(cmd.get("syntax", "") or cmd.get("command", ""))
                    if key:
                        existing.setdefault(cname, []).append(cmd)

        # 新结构: 桌面子类作为分类
        new_categories = []
        seen_keys = set()
        added_from_toolkit = 0
        for sub, cmds in extract_categories(commands_data):
            cat_cmds = []
            for c in cmds:
                key = norm(c["command"])
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                entry = {
                    "command": first_line(c["command"]),
                    "syntax": c["command"].replace("\n或: ", " / "),
                    "description": c["description"],
                    "source": "netops_toolkit",
                }
                if c["example"]:
                    entry["example"] = c["example"]
                cat_cmds.append(entry)
                added_from_toolkit += 1
            if cat_cmds:
                new_categories.append({"name": sub, "commands": cat_cmds})

        # 并入现有 YAML 未重复命令
        cat_names = {c["name"] for c in new_categories}
        cat_by_name = {c["name"]: c for c in new_categories}
        kept_old = 0
        for cname, cmds in existing.items():
            target = CATEGORY_MAP.get(cname, cname)
            if target in cat_names:
                bucket = cat_by_name[target]
            else:
                bucket = {"name": cname, "commands": []}
                new_categories.append(bucket)
                cat_names.add(cname)
                cat_by_name[cname] = bucket
            for cmd in cmds:
                key = norm(cmd.get("syntax", "") or cmd.get("command", ""))
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                kept_old += 1
                bucket["commands"].append(cmd)

        total = sum(len(c["commands"]) for c in new_categories)
        if "netops_toolkit 数据源: Desktop 命令手册 Python 数据文件" not in refs:
            refs.append("netops_toolkit 数据源: Desktop 命令手册 Python 数据文件")

        data = {
            "vendor": vendor,
            "total": total,
            "references": refs,
            "reliability": reliability,
            "categories": new_categories,
            "cases": cases,
        }
        yaml_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
            encoding="utf-8",
        )
        report[vendor] = {
            "toolkit_added": added_from_toolkit,
            "old_kept": kept_old,
            "total": total,
            "categories": len(new_categories),
            "cases": len(cases),
        }
        print(f"{vendor}: +{added_from_toolkit} toolkit, +{kept_old} old-kept, "
              f"total={total}, cats={len(new_categories)}, cases={len(cases)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
