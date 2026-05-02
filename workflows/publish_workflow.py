import os
import sys
import json
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import BaseWorkflow
from agents.publisher import PublisherAgent
from shared import config, stats


class PublishWorkflow(BaseWorkflow):
    """
    Step 3：RPA 发布工作流

    fetch_jobs  → StateBus.pull_pending_publish_jobs()，Priority 优先
    process_job → PublisherAgent RPA 发布，支持多账号 Round-Robin 轮换
    on_success  → StateBus.mark_as_published()，写入 URL + SEO 资产库
    on_failure  → StateBus.mark_as_ready_to_retry()，重置为 Ready 等待重生成

    特殊处理：
    - 幂等检查：URL 已存在时比对生成时间，防止重复发布
    - 数据完整性校验：无效内容直接 mark_as_ready_to_retry
    - 运行后发送飞书通知
    """

    def __init__(self):
        super().__init__("PublishWorkflow")
        self.active_accounts = self._load_accounts()

    def _load_accounts(self) -> list:
        config_json = os.getenv("PUBLISH_CONFIG_JSON")
        if config_json:
            try:
                print("🔐 读取环境变量配置: PUBLISH_CONFIG_JSON")
                publish_config = json.loads(config_json)
            except json.JSONDecodeError as e:
                print(f"⚠️ 解析环境变量配置失败: {e}")
                publish_config = None
        elif os.path.exists(config.PUBLISH_CONFIG_FILE):
            try:
                with open(config.PUBLISH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    publish_config = json.load(f)
                print(f"📖 读取本地配置文件: {config.PUBLISH_CONFIG_FILE}")
            except Exception as e:
                print(f"⚠️ 读取配置文件失败: {e}")
                publish_config = None
        else:
            publish_config = None

        accounts = (publish_config or {}).get("accounts", [])
        if accounts:
            print(f"👥 加载了 {len(accounts)} 个发布账号 (启用轮换模式)")
            return accounts

        default_user = config.WELLCMS_USERNAME
        if default_user:
            print(f"👤 加载默认账号: {default_user}")
            return [{"username": default_user, "password": config.WELLCMS_PASSWORD}]

        print("⚠️ 未找到任何账号配置")
        return []

    def run(self):
        """覆写 run()：发布工作流有幂等检查、数据校验、统计和通知，逻辑更复杂"""
        start_ts = time.time()
        print(f"\n{'=' * 50}")
        print(f"🤖 启动 Workflow: {self.name}")
        print(f"{'=' * 50}\n")

        limit = 20
        num_accounts = len(self.active_accounts) if self.active_accounts else 1
        print(f"⚙️  账号数: {num_accounts} | 本次锁定发布: {limit} 篇")

        pending_records = self.bus.pull_pending_publish_jobs(limit)

        total_success = 0
        total_fail = 0

        # [Account Allocation] 账号分堆聚合 (Session 复用机制)
        account_groups = {}
        for idx, record in enumerate(pending_records):
            account = self.active_accounts[idx % len(self.active_accounts)] if self.active_accounts else {}
            cur_user = account.get("username", config.WELLCMS_USERNAME)
            cur_pass = account.get("password", config.WELLCMS_PASSWORD)
            
            if cur_user not in account_groups:
                account_groups[cur_user] = {"password": cur_pass, "records": []}
            account_groups[cur_user]["records"].append((idx, record))

        for username, group_data in account_groups.items():
            password = group_data["password"]
            records = group_data["records"]
            
            print(f"\n🚀 [Session] 正在启动账号 {username}，本批次分配了 {len(records)} 篇文章")
            
            agent = PublisherAgent(username=username, password=password)
            session_opened = agent.open_session()
            
            if not session_opened:
                print(f"❌ [Session] 账号 {username} 登录失败，跳过该账号的 {len(records)} 篇文章")
                total_fail += len(records)
                for _ in range(len(records)):
                    stats.record_failed() # 保证统计数字准确
                continue
                
            try:
                for j, item in enumerate(records):
                    idx, record = item
                    print(f"\n--- [{idx + 1}/{len(pending_records)}] 发布: {record.get('Title', '')[:30]}... ---")

                    # [Idempotency Check] 防止重复发布
                    existing_url = record.get('URL', '').strip()
                    if existing_url and existing_url.startswith('http'):
                        gen_time_str = record.get('生成时间', '2000-01-01 00:00:00')
                        pub_time_str = record.get('发布时间', '')
                        try:
                            gen_time = datetime.strptime(gen_time_str, "%Y-%m-%d %H:%M:%S")
                            pub_time = datetime.min if not pub_time_str else datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            gen_time = datetime.max
                            pub_time = datetime.min

                        if gen_time > pub_time:
                            print(f"   🔄 [Stale Check] 检测到内容已重生成 (Gen: {gen_time_str} > Pub: {pub_time_str})")
                            print(f"   🗑️ 忽略旧 URL，执行重新发布...")
                        else:
                            print(f"   ⚠️ 已有有效 URL ({existing_url})，修复状态为 Published...")
                            article_data_fix = {
                                "title": record.get('Title'),
                                "keywords": record.get('关键词'),
                                "category_id": config.CATEGORY_MAP.get(str(record.get('大项分类', '')).strip(), "1"),
                                "summary": record.get('摘要')
                            }
                            self.bus.mark_as_published(record['record_id'], article_data_fix, existing_url)
                            print(f"   ✅ 状态修复完成，跳过重复发布。")
                            continue

                    # [Data Integrity Check] 内容校验
                    title_chk = record.get('Title', '').strip()
                    content_chk = record.get('HTML_Content', '').strip()
                    if not title_chk or len(content_chk) < 50:
                        print(f"   🛑 无效内容 (Title: {bool(title_chk)}, Content: {len(content_chk)})，重置为 Ready...")
                        self.bus.mark_as_ready_to_retry(record['record_id'])
                        continue

                    # --- 解析 tags 和 summary 的逻辑 ---
                    raw_tags = str(record.get('Tags', ''))
                    parsed_tags = raw_tags
                    if raw_tags.startswith('[') and raw_tags.endswith(']'):
                        import json
                        try:
                            tag_list = json.loads(raw_tags)
                            if isinstance(tag_list, list):
                                parsed_tags = ", ".join(str(t) for t in tag_list)
                        except Exception:
                            pass
                    
                    summary_val = str(record.get('摘要', ''))
                    if summary_val == 'None':
                        summary_val = ''
                    one_line = str(record.get('One_Line_Summary', ''))
                    if one_line == 'None':
                        one_line = ''
                        
                    # 优先使用 One_Line_Summary 作为 brief，以防摘要被大模型充当成 "SEO Description..." 等无意义占位符
                    if one_line and len(one_line) > 5 and "SEO Description" not in one_line:
                        summary_val = one_line
                    elif not summary_val or "SEO Description" in summary_val:
                        summary_val = one_line

                    # [Publish]
                    article_data = {
                        "title": record.get('Title'),
                        "html_content": record.get('HTML_Content'),
                        "category_id": config.CATEGORY_MAP.get(str(record.get('大项分类', '')).strip(), "1"),
                        "summary": summary_val,
                        "keywords": record.get('关键词'),
                        "description": record.get('描述'),
                        "tags": parsed_tags
                    }

                    try:
                        published_url = agent.publish_in_session(article_data)

                        if published_url:
                            self.bus.mark_as_published(record['record_id'], article_data, published_url)
                            total_success += 1
                            stats.record_published()
                        else:
                            total_fail += 1
                            stats.record_failed()
                            print(f"   ❌ [Failed] 发布失败，未返回 URL")
                    except Exception as e:
                        total_fail += 1
                        stats.record_failed()
                        print(f"   ❌ [Error] 发布异常: {e}")
                        import traceback
                        traceback.print_exc()

                    if j < len(records) - 1:
                        wait_time = random.uniform(1.0, 2.5)
                        print(f"   ⏳ 同一账号连续发布，等待 {wait_time:.1f} 秒缓冲...")
                        time.sleep(wait_time)
            
            finally:
                agent.close_session()

        # [Notification] 发送飞书通知
        if total_success > 0 or total_fail > 0:
            elapsed = int(time.time() - start_ts)
            elapsed_str = f"{elapsed // 60}分{elapsed % 60}秒"
            self.bus.send_notification(
                title="📤 CMS 发布任务完成",
                content=(
                    f"**发布结果**\n"
                    f"- ✅ 成功: {total_success} 篇\n"
                    f"- ❌ 失败: {total_fail} 篇\n"
                    f"- ⏱️ 耗时: {elapsed_str}\n"
                    f"- ⏰ 时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"{stats.get_summary()}"
                )
            )
            print(f"📢 已发送飞书通知 (成功: {total_success}, 失败: {total_fail})")
        else:
            print("⚠️ 本次未找到待发布文章 (Status=Pending 或 Top priority)")
            self.bus.send_notification(
                title="⚠️ CMS 发布轮空",
                content=(
                    f"本次运行未找到 'Pending' 或 'Top priority' 状态的文章。\n"
                    f"⏰ 时间: {time.strftime('%Y-%m-%d %H:%M')}\n"
                    f"请检查 Step 1/2 是否生成了足够内容。"
                )
            )
