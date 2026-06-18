import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import BaseWorkflow
from agents.trend_hunter import TrendHunterAgent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TrendWorkflow(BaseWorkflow):
    """
    Step 1：热点发现工作流

    fetch_jobs  → 读取 box_artist_config.json 作为种子词配置（单任务）
    process_job → TrendHunterAgent 搜索+分析，返回话题列表
    on_success  → StateBus.push_new_topics() 去重入库并同步 Google Sheet
    """

    def __init__(self):
        super().__init__("TrendWorkflow")
        self.agent = TrendHunterAgent()

    def fetch_jobs(self) -> list:
        config_file = os.path.join(BASE_DIR, 'box_artist_config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return [json.load(f)]
        return [{"mining_seeds": ["包装", "礼盒"]}]

    def process_job(self, job: dict):
        return self.agent.hunt_and_analyze(job)

    def on_success(self, job: dict, topics: list):
        # 1. 正常推送生成的话题
        self.bus.push_new_topics(topics)
        
        # 2. 对账与清算逻辑
        tracker_file = os.path.join(BASE_DIR, "data", "pending_seeds.json")
        processing_file = tracker_file + ".processing"
        
        if os.path.exists(tracker_file):
            try:
                # 原子操作防并发
                os.rename(tracker_file, processing_file)
            except OSError:
                print("⚠️ [Reconcile] 无法获取种子词追踪文件锁，可能已被其他进程处理。")
                return
                
            try:
                with open(processing_file, 'r', encoding='utf-8') as f:
                    pending_data = json.load(f)
                
                orphans = pending_data.get("pending_records", [])
                if orphans:
                    # 获取本次成功消费的所有词条核心词
                    consumed_kws = set()
                    if topics:
                        import re
                        for t in topics:
                            st = t.get("Source_Trend", "")
                            clean_st = re.sub(r'\[.*?\]\s*', '', st).strip()
                            if clean_st:
                                consumed_kws.add(clean_st)

                    from shared.d1_client import D1Client
                    db = D1Client(db_id=os.getenv("CF_D1_PACKAGING_DB_ID", "2ef1ee52-ad2a-48c8-9c60-a20c3260cc70"))
                    
                    if db:
                        rollback_count = 0
                        rollback_kws_d1 = []
                        rollback_gs = []
                        
                        for orphan in orphans:
                            kw = orphan.get("keyword", "")
                            # 模糊匹配容错：允许大模型输出带有修饰词
                            if kw and not any((kw in c or c in kw) for c in consumed_kws):
                                if orphan.get("source") == "GS":
                                    rollback_gs.append(orphan)
                                else:
                                    rollback_kws_d1.append(kw)
                                rollback_count += 1
                        
                        # D1 回滚
                        if rollback_kws_d1:
                            placeholders = ",".join(["?"] * len(rollback_kws_d1))
                            db.execute(f"UPDATE keywords_repo SET status = '本周新增' WHERE keyword IN ({placeholders})", rollback_kws_d1)
                            
                        # GS 回滚
                        if rollback_gs:
                            from shared.google_client import GoogleSheetClient
                            gs_client = GoogleSheetClient()
                            if gs_client.client:
                                for o in rollback_gs:
                                    rec_id = o.get("record_id")
                                    if rec_id:
                                        gs_client.update_record(rec_id, {"Status": "Unused"}, table_id="keywords_lib")
                                        
                        if rollback_count > 0:
                            print(f"🔄 [Reconcile] 本地对账完毕，发现 {rollback_count} 个脱落种子词(D1: {len(rollback_kws_d1)}, GS: {len(rollback_gs)})，已安全回拨。")
                        else:
                            print("✅ [Reconcile] 本地对账完毕，所有种子词均成功消费，无脱落。")
            except Exception as e:
                print(f"❌ [Reconcile] 对账异常: {e}")
            finally:
                if os.path.exists(processing_file):
                    os.remove(processing_file)

    def on_failure(self, job: dict, error):
        # 覆写失败机制，遇到全盘崩溃时全量回拨
        tracker_file = os.path.join(BASE_DIR, "data", "pending_seeds.json")
        processing_file = tracker_file + ".processing"
        
        if os.path.exists(tracker_file):
            try:
                os.rename(tracker_file, processing_file)
            except OSError:
                return
                
            try:
                with open(processing_file, 'r', encoding='utf-8') as f:
                    pending_data = json.load(f)
                
                orphans = pending_data.get("pending_records", [])
                if orphans:
                    print(f"⚠️ [Reconcile] 发现进程彻底失败，正在全量回滚 {len(orphans)} 个锁定的种子词...")
                    
                    # D1 回滚
                    from shared.d1_client import D1Client
                    db = D1Client(db_id=os.getenv("CF_D1_PACKAGING_DB_ID", "2ef1ee52-ad2a-48c8-9c60-a20c3260cc70"))
                    if db:
                        rollback_kws_d1 = [orphan.get("keyword") for orphan in orphans if orphan.get("keyword") and orphan.get("source") != "GS"]
                        if rollback_kws_d1:
                            placeholders = ",".join(["?"] * len(rollback_kws_d1))
                            db.execute(f"UPDATE keywords_repo SET status = '本周新增' WHERE keyword IN ({placeholders})", rollback_kws_d1)
                    
                    # GS 回滚
                    rollback_gs = [o for o in orphans if o.get("source") == "GS"]
                    if rollback_gs:
                        from shared.google_client import GoogleSheetClient
                        gs_client = GoogleSheetClient()
                        if gs_client.client:
                            for o in rollback_gs:
                                rec_id = o.get("record_id")
                                if rec_id:
                                    gs_client.update_record(rec_id, {"Status": "Unused"}, table_id="keywords_lib")

                    print("✅ [Reconcile] 全量回滚完毕，种子词已安全释放。")
            except Exception as e:
                print(f"❌ [Reconcile] 回滚异常: {e}")
            finally:
                if os.path.exists(processing_file):
                    os.remove(processing_file)

        super().on_failure(job, error)
