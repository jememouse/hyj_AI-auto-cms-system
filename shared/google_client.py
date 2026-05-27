# shared/google_client.py
"""
Google Sheets 客户端
完全兼容 FeishuClient 接口，支持平滑迁移
支持多工作表 (cms, xhs) 动态切换
"""
import os
import json
import time
import uuid
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import List, Dict, Optional, Any
from . import config

class GoogleSheetClient:
    """Google Sheets 客户端 (单例模式)"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GoogleSheetClient, cls).__new__(cls, *args, **kwargs)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        self.creds_file = config.GOOGLE_CREDENTIALS_FILE
        self.sheet_id = config.GOOGLE_SHEET_ID
        
        self.client = None
        self.spreadsheet = None
        
        # 总是尝试连接
        self._connect()
        self.__class__._initialized = True

    def _connect(self):
        """连接到 Google Spreadsheet"""
        try:
            creds = None
            
            # 1. 尝试从环境变量读取
            json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if json_str:
                # print(f"🔍 检测到环境变量 GOOGLE_CREDENTIALS_JSON (长度: {len(json_str)})") # Debug
                try:
                    keyfile_dict = json.loads(json_str)
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, self.scope)
                    # print("✅ 成功解析 Service Account JSON")
                except json.JSONDecodeError as e:
                    print(f"❌ 环境变量 JSON 解析失败: {e}")
            else:
                pass 
                # print("ℹ️ 未检测到环境变量 GOOGLE_CREDENTIALS_JSON")

            # 2. 如果环境变量没搞定，再尝试从文件加载
            if not creds:
                if os.path.exists(self.creds_file):
                    # print(f"🔍 尝试从文件加载: {self.creds_file}")
                    creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_file, self.scope)
                else:
                    # 只有当两个都失败时，才打印这个警告
                    print(f"⚠️ Google Credentials 文件未找到: {self.creds_file}")

            if not creds:
                print("❌ [Fatal] 未找到有效的 Google Credentials (既无 ENV 也无 File)")
                self.client = None
                return

            # print("🔐 正在进行 gspread 认证...")
            self.client = gspread.authorize(creds)
            
            if self.sheet_id:
                self.spreadsheet = self.client.open_by_key(self.sheet_id)
                print(f"✅ Google Spreadsheet 连接成功: {self.spreadsheet.title}")
            
        except Exception as e:
            print(f"❌ Google Sheet 连接异常: {e}")
            # 打印更详细的错误堆栈，如果是认证错误
            import traceback
            traceback.print_exc()
            self.client = None

    def _get_sheet(self, table_id: str = None):
        """
        根据 table_id (即 worksheet name) 获取 Worksheet 对象
        如果 table_id 为空，使用默认 'cms'
        """
        if not self.spreadsheet: return None
        
        target_name = table_id if table_id else "cms"
        
        try:
            return self.spreadsheet.worksheet(target_name)
        except gspread.WorksheetNotFound:
            print(f"⚠️ 工作表 '{target_name}' 不存在，尝试创建...")
            try:
                # 创建新表
                new_sheet = self.spreadsheet.add_worksheet(title=target_name, rows=100, cols=20)
                # 初始化表头 (根据不同表结构)
                if target_name == "xhs":
                    # Aligned with step4_social/agent_runner.py
                    headers = ["Title", "Content", "Keywords", "Source", "Status", "Cover", "生成时间", "XHS_Link", "Post_Date"]
                else:
                    # Aligned with all steps
                    headers = [
                        "Topic", "Status", "大项分类", "Source_Trend", "Title", "HTML_Content", 
                        "摘要", "关键词", "描述", "Tags", "Schema_FAQ", "One_Line_Summary",
                        "Key_Points", "URL", "发布时间", "XHS_Status", "选题生成时间", "生成时间"
                    ]
                new_sheet.append_row(headers)
                print(f"✅ 已创建并初始化工作表: {target_name}")
                return new_sheet
            except Exception as e:
                print(f"❌ 创建工作表失败: {e}")
                return None

    def _retry_on_api_error(func):
        """
        装饰器：API 调用失败自动重试
        针对 Google API 500/502/503/429 错误
        """
        from functools import wraps
        
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            max_retries = 8
            base_delay = 5
            max_delay = 60
            
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    # 检查是否为可重试错误
                    # gspread.exceptions.APIError: APIError: [503]: The service is currently unavailable.
                    # APIError: [429]: Too Many Requests
                    is_retryable = False
                    if "500" in error_str or "502" in error_str or "503" in error_str:
                        is_retryable = True
                    elif "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "Quota exceeded" in error_str:
                        is_retryable = True
                    elif "104" in error_str or "Connection reset" in error_str: # Connection errors
                        is_retryable = True
                        
                    if is_retryable:
                        if attempt < max_retries - 1:
                            sleep_time = min(base_delay * (2 ** attempt), max_delay) # 指数退避，带上限
                            print(f"   ⚠️ Google API 临时错误，将在 {sleep_time}秒 后重试 ({attempt + 1}/{max_retries})...")
                            time.sleep(sleep_time)
                            
                            # 如果是 Auth 错误，尝试重新连接一次
                            if "401" in error_str or "invalid_grant" in error_str:
                                print("      🔄 尝试刷新认证...")
                                self._connect()
                            continue
                    
                    # 不可重试或重试耗尽，抛出异常或返回默认值避免崩溃
                    print(f"❌ Google API 调用失败 (已重试 {attempt} 次): {e}")
                    if "fetch" in func.__name__:
                        return []
                    elif "update" in func.__name__ or "create" in func.__name__:
                        return False
                    return None
            return None
        return wrapper

    @_retry_on_api_error
    def fetch_records_by_status(self, status: str, category: str = None, limit: int = 50, sort_by_time_col: str = None, reverse_batch: bool = False, table_id: str = "cms", fetch_from_bottom: bool = False) -> List[Dict]:
        """
        获取指定状态的记录
        兼容 FeishuClient 接口
        :param sort_by_time_col: 按指定的列名进行降序排列（提取最新时间的内容）。如："选题生成时间"或"生成时间"
        :param reverse_batch: 若为 True，则把分出的批次反转（例如让最新内容的放在批次末尾发布，以确保处于 CMS 最顶部）
        :param table_id: 目标工作表名称，默认为 'cms'
        :param fetch_from_bottom: 若为 True，则优先从表格的最末尾向上抽取数据（实现真正的先进后出 LIFO）
        """
        sheet = self._get_sheet(table_id)
        if not sheet: return []
        
        # 不要在这里 try-except 掩盖错误，交给装饰器处理
        all_records = sheet.get_all_records()
        filtered_records = []
        
        # 原逻辑：顺序遍历附加 Row ID 与过滤，保证能够回写数据到准确的横行
        for i, row in enumerate(all_records):
            row_num = i + 2
            rec_id = f"row:{row_num}"
            row["record_id"] = rec_id
            
            if str(row.get("Status")) == status:
                if category:
                    if str(row.get("大项分类")) == category:
                        filtered_records.append(row)
                else:
                    filtered_records.append(row)
                    
        # 若指定了排序列，按该列时间字符串降序（最新的在列表前面）
        if sort_by_time_col:
            # 兼容空字符串处理
            def parse_time(r):
                val = str(r.get(sort_by_time_col, "")).strip()
                return val if val else ""
            filtered_records.sort(key=parse_time, reverse=True)
            
        # 若需要从底部拉取（真正的先进后出 LIFO），反转整个列表，让最底部的数据跑到前面
        if fetch_from_bottom:
            filtered_records.reverse()
            
        # 截取所需长度的批次
        results = filtered_records[:limit]
        
        # 若需要批次倒置，反转数组使得最新的在最后执行
        if reverse_batch:
            results.reverse()
            
        print(f"   📋 [GoogleSheet:{sheet.title}] 获取 {len(results)} 条 '{status}' 记录 (sort_col={sort_by_time_col}, reverse={reverse_batch})")
        return results

    @_retry_on_api_error
    def update_record(self, record_id: str, fields: Dict, retry: bool = True, table_id: str = "cms") -> bool:
        """
        更新记录
        """
        sheet = self._get_sheet(table_id)
        if not sheet: return False
        
        row_num = -1
        
        # 策略 1: 解析 Row ID
        if record_id.startswith("row:"):
            try:
                row_num = int(record_id.split(":")[1])
            except:
                pass
        
        # 策略 2: 如果不是 Row ID，或者是 UUID，需要扫描查找
        if row_num == -1:
            cell = sheet.find(record_id)
            if cell:
                row_num = cell.row
        
        if row_num == -1:
            print(f"❌ 未找到记录 ID: {record_id}")
            return False
            
        # 执行更新
        headers = sheet.row_values(1)
        cells_to_update = []
        
        for key, value in fields.items():
            if key in headers:
                col_index = headers.index(key) + 1
                # 格式处理
                if isinstance(value, (list, dict)):
                    val_str = json.dumps(value, ensure_ascii=False)
                else:
                    val_str = str(value)
                    
                # 创建 Cell 对象并加入列表
                cells_to_update.append(gspread.Cell(row_num, col_index, val_str))
            else:
                pass
                # print(f"⚠️ 警告: 字段 '{key}' 不在 Sheet 表头中，已忽略")
        
        if cells_to_update:
            sheet.update_cells(cells_to_update)
        
        return True

    @_retry_on_api_error
    def create_record(self, fields: Dict, table_id: str = None) -> Optional[str]:
        """创建记录 (支持指定 table_id/worksheet)"""
        sheet = self._get_sheet(table_id)
        if not sheet: return None
        
        # 不使用 try-except 掩盖异常，交给装饰器处理重试
        # 移除 record_id 生成逻辑 (用户不需要)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        fields["created_at"] = now_str
        
        # 自动填充 "生成时间" (System Created Time)
        if "生成时间" not in fields:
            fields["生成时间"] = now_str
        
        # 对齐表头
        headers = sheet.row_values(1)
        row_data = []
        
        for h in headers:
            val = fields.get(h, "")
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            row_data.append(val)
            
        sheet.append_row(row_data)
        return "row:new" # 无法立即知道 row number，除非再查一次

    @_retry_on_api_error
    def batch_create_records(self, records: List[Dict], table_id: str = None) -> bool:
        """批量创建"""
        sheet = self._get_sheet(table_id)
        if not sheet or not records: return False
        
        headers = sheet.row_values(1)
        rows_to_append = []
        
        for r in records:
            # 生成 ID
            if "record_id" not in r:
                r["record_id"] = str(uuid.uuid4())
            
            row_data = []
            for h in headers:
                val = r.get(h, "")
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False)
                row_data.append(val)
            rows_to_append.append(row_data)
            
        sheet.append_rows(rows_to_append)
        print(f"   ✅ Google Sheet [{sheet.title}]: 批量插入 {len(rows_to_append)} 条")
        return True

    def send_notification(self, title: str, content: str) -> bool:
        """
        发送飞书消息通知（使用 Webhook）
        """
        import requests
        
        webhook_url = getattr(config, 'FEISHU_WEBHOOK_URL', None)
        if not webhook_url:
            print("   ⚠️ 未配置 FEISHU_WEBHOOK_URL，跳过通知")
            return False
        
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": "blue"
                    },
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": content}}
                    ]
                }
            }
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                print(f"   📨 飞书通知已发送: {title}")
                return True
            else:
                print(f"   ⚠️ 飞书通知失败: {resp.text}")
                return False
        except Exception as e:
            print(f"   ⚠️ 飞书通知异常: {e}")
            return False
