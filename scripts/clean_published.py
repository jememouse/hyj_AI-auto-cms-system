#!/usr/bin/env python3
"""
清理脚本：删除 Google Sheet 中所有 'Published' 状态的行
用于定期清理已发布的文章记录，释放表格空间

用法:
    uv run python scripts/clean_published.py          # 默认清理 cms 表
    uv run python scripts/clean_published.py --dry-run # 仅预览，不实际删除
    uv run python scripts/clean_published.py --all     # 清理所有工作表 (cms + 社交平台)
"""
import sys
import os
import argparse
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.google_client import GoogleSheetClient
from shared import config


def clean_published_rows(sheet_name: str = "cms", dry_run: bool = False):
    """
    删除指定工作表中所有 Status=Published 的行

    策略: 读取全部数据 → 过滤掉 Published → 清空表格 → 一次性写回剩余行
    比逐行删除快几十倍，18000 行可在几秒内完成
    """
    client = GoogleSheetClient()
    sheet = client._get_sheet(sheet_name)
    if not sheet:
        print(f"❌ 工作表 '{sheet_name}' 不存在或连接失败")
        return 0

    print(f"\n{'='*50}")
    print(f"🧹 正在扫描工作表: {sheet_name}")
    print(f"{'='*50}")

    # 读取全部原始数据 (含表头)
    all_values = sheet.get_all_values()
    if len(all_values) <= 1:
        print(f"✅ 工作表 '{sheet_name}' 为空，无需清理。")
        return 0

    headers = all_values[0]
    data_rows = all_values[1:]
    total_rows = len(data_rows)

    # 找到 Status 列的索引
    try:
        status_col = headers.index("Status")
    except ValueError:
        print(f"❌ 工作表 '{sheet_name}' 中未找到 'Status' 列")
        return 0

    # 分离: 保留行 vs 待删除行
    keep_rows = []
    published_count = 0
    sample_titles = []

    # 找到 Title/Topic 列用于预览
    title_col = None
    for col_name in ["Title", "Topic", "title"]:
        if col_name in headers:
            title_col = headers.index(col_name)
            break

    for row in data_rows:
        status = str(row[status_col]).strip() if status_col < len(row) else ""
        if status == config.STATUS_PUBLISHED:
            published_count += 1
            if len(sample_titles) < 5 and title_col is not None:
                sample_titles.append(str(row[title_col])[:40])
        else:
            keep_rows.append(row)

    if published_count == 0:
        print(f"✅ 工作表 '{sheet_name}' 中没有已发布的记录，无需清理。")
        return 0

    print(f"📋 共 {total_rows} 行数据")
    print(f"   🗑️  待删除 (Published): {published_count} 行")
    print(f"   ✅ 保留 (其他状态):     {len(keep_rows)} 行")
    if sample_titles:
        print(f"   预览待删除:")
        for title in sample_titles:
            print(f"   - {title}")
        if published_count > 5:
            print(f"   ... 还有 {published_count - 5} 条")

    if dry_run:
        print(f"\n🔍 [DRY RUN] 预览模式，不执行实际删除。")
        return published_count

    # 安全确认
    print(f"\n⚠️  即将删除 {published_count} 行，保留 {len(keep_rows)} 行，操作不可撤销！")
    print(f"   5 秒后开始执行...")
    time.sleep(5)

    # 安全重写: 先覆盖写入，再删除多余行 (避免 clear 后写入失败导致数据丢失)
    print(f"   📝 正在分批重写工作表...")
    new_data = [headers] + keep_rows
    batch_size = 1000

    # 带有重试机制的执行函数
    def execute_with_retry(func, *args, **kwargs):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"      ⚠️ 网络异常或 API 错误: {e}")
                if attempt < max_retries - 1:
                    sleep_time = 5 * (attempt + 1)
                    print(f"      ⏳ 等待 {sleep_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(sleep_time)
                else:
                    print("      ❌ 达到最大重试次数，放弃操作")
                    raise e

    # 第 1 步: 分批覆盖写入新数据
    for i in range(0, len(new_data), batch_size):
        batch = new_data[i:i + batch_size]
        start_row = i + 1
        execute_with_retry(sheet.update, range_name=f"A{start_row}", values=batch)
        print(f"   📝 已写入 {min(i + batch_size, len(new_data))}/{len(new_data)} 行...")
        time.sleep(2)  # 防止 API 限流

    # 第 2 步: 删除尾部多余的旧行 (新数据行数 < 旧数据行数时才需要)
    new_total = len(new_data)        # 含表头
    old_total = total_rows + 1       # 含表头
    if old_total > new_total:
        # 删除从 new_total+1 到 old_total 的所有行
        print(f"   🗑️  清除尾部多余行: {new_total + 1} ~ {old_total}")
        execute_with_retry(sheet.delete_rows, new_total + 1, old_total)

    print(f"\n✅ 工作表 '{sheet_name}' 清理完成！")
    print(f"   🗑️  已删除: {published_count} 行")
    print(f"   ✅ 保留:   {len(keep_rows)} 行")
    return published_count


def main():
    parser = argparse.ArgumentParser(description="清理 Google Sheet 中已发布的记录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际删除")
    parser.add_argument("--all", action="store_true", help="清理所有工作表 (cms + 社交平台)")
    parser.add_argument("--sheet", type=str, default="cms", help="指定工作表名称 (默认: cms)")
    args = parser.parse_args()

    print("🧹 Google Sheet 已发布记录清理工具")
    if args.dry_run:
        print("📌 模式: DRY RUN (仅预览)")

    total_deleted = 0

    if args.all:
        # 清理所有工作表
        sheets = ["cms"]
        for platform in config.SOCIAL_PLATFORMS:
            sheet_name = config.SOCIAL_PLATFORMS[platform].get("sheet_name", platform)
            if sheet_name not in sheets:
                sheets.append(sheet_name)

        for sheet_name in sheets:
            total_deleted += clean_published_rows(sheet_name, dry_run=args.dry_run)
    else:
        total_deleted = clean_published_rows(args.sheet, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print(f"📊 总计{'预览' if args.dry_run else '删除'}: {total_deleted} 行")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
