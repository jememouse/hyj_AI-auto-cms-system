import requests
import os
import json
from typing import List, Dict, Any, Union
from dotenv import load_dotenv

load_dotenv()

class D1Client:
    def __init__(self):
        self.account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
        self.db_id = os.getenv("CF_D1_DATABASE_ID", "").strip()
        self.token = os.getenv("CF_API_TOKEN", "").strip()
        
        if not all([self.account_id, self.db_id, self.token]):
            print("⚠️ 警告: D1 环境变量缺失，请在 .env 中配置 CF_ACCOUNT_ID, CF_D1_DATABASE_ID, CF_API_TOKEN")

        self.url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.db_id}/query"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def execute(self, sql: str, params: list = None) -> Union[List[Dict[str, Any]], None]:
        """
        执行单条 SQL 操作并返回结果 (SELECT/INSERT/UPDATE/DELETE)
        """
        payload = {
            "sql": sql,
            "params": params if params else []
        }
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("success"):
                return data["result"][0].get("results", [])
            else:
                print(f"❌ D1 API 执行报错: {json.dumps(data.get('errors'))}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求异常: {e}")
            return None

    def execute_batch(self, queries: List[Dict[str, Any]]) -> bool:
        """
        🚀 高效率批处理接口：一次 HTTP 请求执行多条 SQL 语句
        参数示例:
        queries = [
            {"sql": "INSERT INTO seo_articles (topic) VALUES (?)", "params": ["标题1"]},
            {"sql": "INSERT INTO seo_articles (topic) VALUES (?)", "params": ["标题2"]}
        ]
        """
        if not queries:
            return True
            
        try:
            # D1 REST API 支持传入数组以进行批处理
            response = requests.post(self.url, headers=self.headers, json={"batch": queries})
            response.raise_for_status()
            data = response.json()
            
            if data.get("success"):
                return True
            else:
                print(f"❌ D1 API 批处理报错: {json.dumps(data.get('errors'))}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求异常: {e}")
            return False

if __name__ == "__main__":
    # 测试代码
    db = D1Client()
    print("D1 Client 初始化成功，等待执行...")
