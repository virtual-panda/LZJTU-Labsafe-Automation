#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新版 genlink：只处理 coursePlayer 形式的链接。

链接形如：
    https://***/lab-study-front/coursePlayer?periodId=xxx&requireStudyLength=180&studyLength=0&examId=78

匹配规则：使用 URL 中的 periodId 与 JSON 数组中每条记录的 periodId 匹配。
输出格式：
{
  "links": [
    {"courseName": "...", "url": "...", "requiredStudyTime": "180"},
    ...
  ]
}
"""

import argparse
import json
import sys
from urllib.parse import urlparse, parse_qs


def parse_link(url):
    """从 coursePlayer URL 中提取 periodId 与 requireStudyLength。

    返回 (period_id, require_study_length)，解析不到的项为 None。
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    period_id = qs.get("periodId", [None])[0]
    req_len = qs.get("requireStudyLength", [None])[0]
    return period_id, req_len


def read_lines(path):
    """读取链接文件，每行一条；path 为 '-' 时从标准输入读取。"""
    if path is None or path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    return [line.strip() for line in text.splitlines() if line.strip()]


def build_links(urls, json_data):
    """把 coursePlayer 链接与 JSON 记录按 periodId 关联。

    返回 (links, skipped)。
    """
    content = (json_data.get("data") or {}).get("content") or []

    # 建立索引：periodId(str) -> item
    index = {}
    for item in content:
        pid = item.get("id")
        if pid is None:
            continue
        index[str(pid)] = item

    links = []
    skipped = []

    for url in urls:
        period_id, url_req_len = parse_link(url)
        if period_id is None:
            skipped.append((url, "URL 中缺少 periodId 参数"))
            continue

        item = index.get(str(period_id))
        if item is None:
            skipped.append((url, f"JSON 中未找到 periodId={period_id} 的记录"))
            continue

        # requiredStudyTime 优先取 URL 中的 requireStudyLength，
        # 若 URL 中缺失则回退到 JSON 的 requireStudyLength
        if url_req_len is None:
            raw = item.get("requireStudyLength")
            url_req_len = "" if raw is None else str(raw)

        links.append({
            "courseName": item.get("title", ""),
            "url": url,
            "requiredStudyTime": url_req_len,
        })

    return links, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="根据 coursePlayer 链接与 JSON 生成 links 数据（按 periodId 匹配）"
    )
    parser.add_argument("--json", "-j", required=True,
                        help="合并后的 JSON 文件（merge 脚本的输出）")
    parser.add_argument("--links", "-l", default="-",
                        help="链接文件，每行一条；默认从标准输入读取")
    parser.add_argument("--output", "-o", default="-",
                        help="输出文件，默认打印到标准输出")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="打印被跳过的链接及原因")
    args = parser.parse_args(argv)

    with open(args.json, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    content = (json_data.get("data") or {}).get("content")
    if content is None:
        print("警告：输入 JSON 缺少 data.content，请确认来源", file=sys.stderr)

    urls = read_lines(args.links)
    links, skipped = build_links(urls, json_data)

    result = {"links": links}
    text = json.dumps(result, ensure_ascii=False, indent=4)

    if args.output == "-":
        print(text)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入 {args.output}，共 {len(links)} 条", file=sys.stderr)

    if args.verbose:
        for url, reason in skipped:
            print(f"[跳过] {url} -> {reason}", file=sys.stderr)


if __name__ == "__main__":
    main()