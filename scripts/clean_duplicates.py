import sys
import os
import time
from functools import wraps
from collections import defaultdict
from shared.google_client import GoogleSheetClient

def execute_with_retry(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise e
                    print(f"⚠️ 操作失败: {e}，将在 5 秒后重试...")
                    time.sleep(5)
        return wrapper
    return decorator

def clean_duplicates():
    print("🚀 开始清理 Google Sheet 中的重复行...")
    client = GoogleSheetClient()
    sheet = client._get_sheet("cms")
    if not sheet:
        print("❌ 无法连接到 Google Sheet")
        return
        
    all_records = sheet.get_all_records()
    if not all_records:
        print("ℹ️ 表格为空")
        return
        
    print(f"📊 当前总行数: {len(all_records)}")
    
    # 获取标题行
    headers = sheet.row_values(1)
    
    # 根据 Title (或 Topic) + Category 进行去重，保留最新（或者任意一个）
    # 为了保留状态，我们优先保留 Status = "Published" 的，其次 "Pending"
    seen = {}
    unique_records = []
    duplicate_count = 0
    
    for row in all_records:
        title = row.get("Title") or row.get("Topic") or ""
        category = row.get("大项分类") or ""
        status = row.get("Status") or ""
        
        if not title:
            unique_records.append(row)
            continue
            
        key = f"{title}::{(category)}"
        
        if key in seen:
            duplicate_count += 1
            # 比较状态，优先保留 Published
            existing_row = seen[key]
            existing_status = existing_row.get("Status") or ""
            
            if status == "Published" and existing_status != "Published":
                # 替换为新的（Published优先）
                unique_records.remove(existing_row)
                unique_records.append(row)
                seen[key] = row
        else:
            seen[key] = row
            unique_records.append(row)
            
    print(f"🧹 发现并准备清理 {duplicate_count} 条重复数据。清理后行数: {len(unique_records)}")
    
    if duplicate_count == 0:
        print("✅ 没有重复数据需要清理")
        return
        
    # 转换为数组格式以便批量写入
    new_values = [headers]
    for row in unique_records:
        # 将字典转换为按 header 顺序的列表
        row_values = [row.get(h, "") for h in headers]
        new_values.append(row_values)
        
    @execute_with_retry(max_retries=3)
    def update_sheet():
        sheet.clear()
        # 分批写入避免超时
        batch_size = 1000
        for i in range(0, len(new_values), batch_size):
            batch = new_values[i:i + batch_size]
            start_row = i + 1
            end_row = i + len(batch)
            end_col = chr(ord('A') + len(headers) - 1) if len(headers) <= 26 else 'Z' # 简化处理列名
            # 为了支持超过Z列，可以用数字
            range_str = f"R{start_row}C1:R{end_row}C{len(headers)}"
            sheet.update(values=batch, range_name=range_str)
            print(f"   🔄 已写入 {start_row} 到 {end_row} 行...")
            
    try:
        update_sheet()
        print("🎉 重复数据清理完成！")
    except Exception as e:
        print(f"❌ 清理过程中发生错误: {e}")

if __name__ == "__main__":
    clean_duplicates()
