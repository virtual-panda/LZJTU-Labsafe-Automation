#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并多份分片 JSON 文件（结构相同），只保留 mustStudy == 1 的记录。"""

import argparse
import glob
import json
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge(files):
    """按顺序合并 files 中的 data.content，只保留 mustStudy==1，
    并按 (tableCode, id) 去重。"""
    merged = None
    all_content = []
    seen = set()

    for path in files:
        data = load_json(path)
        if merged is None:
            # 以第一个文件的结构为模板
            merged = data

        content = (data.get("data") or {}).get("content") or []
        for item in content:
            # 只保留 mustStudy == 1 的记录
            if item.get("mustStudy") != 1:
                continue

            key = (item.get("tableCode"), item.get("id"))
            if key in seen:
                continue
            seen.add(key)
            all_content.append(item)

    if merged is None:
        raise SystemExit("没有可合并的 JSON 文件")

    data = merged.setdefault("data", {})
    data["content"] = all_content

    # 更新分页相关的统计字段
    data["totalElements"] = len(all_content)
    data["numberOfElements"] = len(all_content)
    data["totalPages"] = 1
    data["last"] = True
    data["first"] = True

    return merged


def main(argv=None):
    parser = argparse.ArgumentParser(description="合并多份分片 JSON 文件（仅保留 mustStudy==1）")
    parser.add_argument("inputs", nargs="+", help="JSON 文件路径或 glob 通配符")
    parser.add_argument("-o", "--output", default="merged.json", help="输出文件，默认 merged.json")
    args = parser.parse_args(argv)

    # 支持 shell 通配符，并保持顺序去重
    files = []
    for pattern in args.inputs:
        matched = glob.glob(pattern)
        files.extend(matched if matched else [pattern])

    seen = set()
    files = [f for f in files if not (f in seen or seen.add(f))]

    merged = merge(files)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)

    print(
        f"已合并 {len(files)} 个文件 -> {args.output}"
        f"（保留 mustStudy==1 共 {len(merged['data']['content'])} 条记录）",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()