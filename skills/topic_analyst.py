import sys
import os
import random
import logging
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.skill import BaseSkill
from shared import config, llm_utils

# 配置 logger
logger = logging.getLogger(__name__)

class TopicAnalysisSkill(BaseSkill):
    """
    技能: 话题分析师 (使用 LLM 分析热点并生成选题)
    """
    def __init__(self):
        super().__init__(
            name="topic_analysis",
            description="分析热点列表，挑选最有价值的 25 个，并为每个生成 4 个 SEO 标题"
        )

    def execute(self, input_data: Dict) -> List[Dict]:
        """
        Input: {"trends": [], "config": {}}
        Output: [{"Topic": "...", "大项分类": "...", ...}]
        """
        trends = input_data.get("trends", [])
        if not trends: return []

        # 1. 第一步：筛选热点
        analyzed_trends = self._analyze_trends(trends, input_data)
        
        results = []
        generated_texts = [] # 用于去重检查

        # 2. 第二步：批量为所有热点生成标题 (Batching，引入分块机制防止大模型 Output Token 溢出)
        print(f"   🧠 [Analyst] 启动大模型分块批处理，为 {len(analyzed_trends)} 个热点生成标题...")
        titles_batch = []
        batch_size = 20
        for i in range(0, len(analyzed_trends), batch_size):
            chunk = analyzed_trends[i:i + batch_size]
            print(f"      - 正在处理批次: 第 {i+1} ~ {i+len(chunk)} 个热点...")
            chunk_results = self._generate_titles_batch(chunk, input_data.get("config", {}))
            if chunk_results:
                titles_batch.extend(chunk_results)
        
        if not titles_batch:
             print("   ❌ [Analyst] 批量生成标题失败，所有批次 LLM 均未返回有效数据")
             return []

        for t in titles_batch:
            raw_title = t.get('title', '').strip()
            if not raw_title: 
                continue
                
            # [Deduplication] 查重
            if self._is_text_similar(raw_title, generated_texts):
                print(f"   🗑️ [Dedupe] 丢弃高相似度标题: {raw_title}")
                continue
            
            generated_texts.append(raw_title)
            
            # 使用 LLM 返回的 source 匹配，若没有则用 unknown
            results.append({
                "Topic": raw_title,
                "大项分类": self._clean_category(t.get('category', '')),
                "Status": "Pending",
                "Source_Trend": t.get('source_topic', 'Unknown Trend'),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
        print(f"   ✅ [Analyst] 批量处理完毕，最终入库有效不重复标题 {len(results)} 个")
        return results

    def _is_text_similar(self, new_text: str, existing_texts: List[str], threshold: float = 0.6) -> bool:
        """
        简单的文本相似度去重 (Jaccard Similarity on chars)
        """
        if not existing_texts: return False
        
        s1 = set(new_text)
        for t in existing_texts:
            s2 = set(t)
            intersection = len(s1.intersection(s2))
            union = len(s1.union(s2))
            if union == 0: continue
            
            sim = intersection / union
            # 放宽前缀匹配：原来的 5 个字太短（例如“化妆品包装”就会全部被杀），改为 12 个字以上前缀一致才算重复
            if len(new_text) > 12 and len(t) > 12 and new_text[:12] == t[:12]:
                return True
                
            # 放宽整体相似度阈值，让更多 SEO 词条可以通过
            if sim > 0.75:
                return True
        return False

    def _analyze_trends(self, trends, input_data: Dict):
        import re
        trends_str = "\n".join([f"- {t}" for t in trends])

        # 动态选择城市 (GEO Local SEO 策略同步扩展至内陆核心节点与轻工业重镇)
        GEO_CITIES = [
            "东莞", "深圳", "广州", "佛山", "中山", "珠海",
            "上海", "杭州", "苏州", "宁波", "义乌", "无锡", "常州",
            "青岛", "济南", "北京", "天津",
            "成都", "重庆", "武汉", "郑州", "西安", "长沙", "合肥", "晋江"
        ]
        selected_city = random.choice(GEO_CITIES)
        
        trend_settings = input_data.get("config", {}).get("trend_settings", {})
        target_count = trend_settings.get("max_trends_to_analyze", 5)

        prompt = f"""
        你是一位拥有10年经验的独立包装产业观察员与高级供应链咨询专家。
        你的任务是站在中立、客观的第三方视角，为企业和电商客户深度剖析包装产业链与定制趋势。你擅长同时洞察 **B2B企业采购** 追求稳定合规 与 **B2C/C2M个人定制** 追求敏捷测试的需求痛点。即使是讨论 **{selected_city}** 当地的通用话题，也要保持严肃客观的产业调查风格，绝对避免任何王婆卖瓜式的品牌推销语。

        请从以下全网热点中，**务必挑选出 {target_count} 个** 最适合写文章的话题。

        筛选优先级（兼顾 B2B 与 B2C）：
        0. **VIP级（无条件通过 - 平台外部词汇绿通道）**：
           - **只要话题中带有 `[外部指定]` 标签**，代表它是人工高优导入的 5118 等词条库，这类词汇享有绝对优先权（免审），**请你务必将其全部抽出，并强制标注为 "S" 级优先级！绝对不要漏掉任何一个带此标签的话题。**
        1. **S级（必选 - 借势营销/高意图）**：
           - **社会热点强关联 (Newsjacking)**：能通过"隐喻/场景/配色"强行关联的破圈热点。
             - *思维模型*：哈尔滨火了 -> 思考"抗寒/冷链包装"；繁花热播 -> 思考"复古/港风礼盒"；多巴胺穿搭 -> 思考"鲜艳配色包装"。
           - **高意图转化**：包含 [搜索需求]、[1688采购]、多少钱、怎么选。
        2. **A级（重点 - 商业场景）**：
           - 包含 小批量、礼品定制、伴手礼、Etsy包装、私域包装。
           - 季节性话题：春节礼盒、电商大促、展会、环保新规。
        3. **B级（特定关联）**：
           - 有明确商业价值的行业长尾词。

        热搜列表：
        {trends_str}

        请严格返回 JSON 格式列表：
        [
            {{"topic": "话题名", "angle": "结合角度(如: 借势哈尔滨热度，切入冷链包装场景)", "priority": "S"}}
        ]
        不要返回 Markdown。
        """
        res = llm_utils.call_llm_json_array(prompt, model=config.TITLE_MODEL, temperature=0.7, max_retries=2)
        analyzed_trends = res if res else []
        
        # === Fallback: 确保数量达标 ===
        trend_settings = input_data.get("config", {}).get("trend_settings", {})
        target_count = trend_settings.get("max_trends_to_analyze", 5)
        
        if len(analyzed_trends) < target_count:
            print(f"⚠️ [Topics] LLM仅返回 {len(analyzed_trends)} 个 (目标{target_count})，启动自动补全...")
            
            # 1. 提取已有的 topics 以避免重复
            existing_topics = {t.get("topic", "") for t in analyzed_trends}
            
            # 2. 从原始列表中寻找候选，[外部指定] 具有强插队特权
            candidates = []
            external_candidates = []
            for raw_t in trends:
                clean_t = re.sub(r'\[.*?\]\s*', '', raw_t)
                # 保留 [外部指定] 特权标识，但对于去重比对，需要使用它清洗后的核心词
                if clean_t and clean_t not in existing_topics:
                    if "[外部指定]" in raw_t:
                        external_candidates.append(clean_t)
                    else:
                        candidates.append(clean_t)
            
            # 把外部特供词放到最优先补充位置
            candidates = external_candidates + candidates
            
            # 3. 随机抽取补全
            needed = target_count - len(analyzed_trends)
            if candidates:
                # 重点：不再随机取样，严格从排序好的最顶端按顺序取，以保证 external_candidates 被百分百提取
                fillers = candidates[:needed]
                for f in fillers:
                    analyzed_trends.append({
                        "topic": f,
                        "angle": "全网热点流量承接",
                        "priority": "A"
                    })
            print(f"✅ [Topics] 已补全至 {len(analyzed_trends)} 个")
            
        # === 终极保险：强行还原 [外部指定] 标识符 ===
        is_external = set()
        for raw_t in trends:
            if "[外部指定]" in raw_t:
                ct = re.sub(r'\[.*?\]\s*', '', raw_t).strip()
                is_external.add(ct)
                
        for t in analyzed_trends:
            topic_str = t.get("topic", "")
            ct = re.sub(r'\[.*?\]\s*', '', topic_str).strip()
            # 前缀或部分匹配，找回外部词组
            for ext in is_external:
                if ext in topic_str or ct in ext:
                    if "[外部指定]" not in topic_str:
                        t["topic"] = f"[外部指定] {topic_str}"
                    break
        
        return analyzed_trends[:target_count]

    def _generate_titles_batch(self, trends, brand_config):
        if not trends: 
            return []
            
        brand_name = brand_config.get('brand', {}).get('name', '盒艺家')
        trend_settings = brand_config.get('trend_settings', {})
        count = trend_settings.get('titles_per_trend', 3)
        current_year = datetime.now().year

        # 构造热点长文本清单
        trends_str = ""
        for i, trend in enumerate(trends):
            t_topic = trend.get('topic', '')
            t_angle = trend.get('angle', '无')
            trends_str += f"{i+1}. 【{t_topic}】 (切入角度: {t_angle})\n"

        expected_total = len(trends) * count

        prompt = f"""
        背景：{brand_name} (既接B2B大单，也接B2C小单，**1个起订**)
        当前年份：{current_year}年

        核心任务：我将提供 {len(trends)} 个热点话题。请你为【列表中的每一项热点】分别生成 {count} 个 SEO 标题。
        这就意味着，你总共必须精确输出 {expected_total} 条数据记录！

        === 热点话题列表 ===
        {trends_str}
        ====================

        0. **全品类生态与前沿基因融合 (生态破壁)**：在生成标题时，**绝对不能局限于低端的“纸箱/纸盒/打样”思维！必须战略性地**将热点话题向以下三大高维场景进行借势与升维组合：
           - **全材质与泛印刷周边生态**：融合包装的跨界材质（金属马口铁、环保塑料），以及Z世代与电商狂热的周边营销物料（如：典藏抽赏卡牌、吧唧/徽章、异形贴纸、不干胶系列）。
           - **前述 AI 端到端能力**：融合【包装AI协同结构算力排测】与【智能色彩打样预测算法】。
           - **全球化履约护航**：融合【DTC跨国出海防损退赔】与【FBA合规海运体积重降本规范】。
        1. **客群靶向与原声提问搜一搜截流 (Persona & PAA)**：
           - **三大核心客群锁定**：你必须让每个生成的标题天然锚定以下核心受众之一：
             【受众1-微创客/出海DTC】：痛点缺钱怕压货。标题切入“小批量起订、防坑测品、出海防潮”。
             【受众2-B2B大厂采购】：痛点怕背锅卡进度。标题切入“线上秒报价、供应链避险、老板算账”。
             【受众3-品牌设计主理人】：痛点缺乏视觉质感。标题切入“AI结构打样、开箱视觉、包装溢价”。
           - **流量毒药(绝对违禁词)**：严禁出现 "高级感的秘密"、"还在为...发愁"、"一文看懂"、"正确打开方式"、"...小白必看"、"建议收藏" 等一眼假的营销号句法。
           - **采用“真人痛点提问/反常识爆论”**：迎合用户真实搜索流（例：“一个报价卡3天？揭开传统包装厂效率毒瘤” 或 “同样是牛皮纸，凭什么跨境出海频频受潮被退款”）。
        2. **针对不同分类的降维打击风格**：
           - **【专业知识】分类（极客剖析与大厂解密风）**：要有工业壁垒感或结构拆解的极致严密感（如: "打破黑盒：基于AI算力的包装边压强度最优解模型"）。
           - **【行业资讯/产品介绍】分类（痛点清账与商业反转）**：杜绝说明书式的列举，必须用强情绪和“算账逻辑”表达（如: "一个复古款被退货两次？拆解DTC礼盒出海必须避开的三道送命题！"）。
        3. **分类覆盖均衡**：对于上述每一个热点，其所属的 {count} 个标题必须均衡交叉覆盖这三个分类类别。绝对不允许全是同一类。
        4. **【核心禁令 - 去硬广化】**：为了保证 SEO 点击率，建立中立专家人设，**强制要求生成的标题中绝对不允许直接出现品牌名 "{brand_name}"**。
        5. **字段溯源约束**：为了关联热点跟踪，你必须在每条返回的 JSON 里附带 "source_topic" 字段，写入当时你参照的原热点完整名称。

        请严格仅返回 JSON 数组对象格式：
        [
            {{"source_topic": "热点A的名字", "title": "热点A的标题1", "category": "专业知识"}},
            {{"source_topic": "热点A的名字", "title": "热点A的标题2", "category": "产品介绍"}},
            {{"source_topic": "热点B的名字", "title": "热点B的标题1", "category": "行业资讯"}},
            ... (总共精准返回 {expected_total} 条)
        ]
        """
        
        # 为了一次吞吐大量文本，可能需要更高的容错时间 (使用 shared 工具底层的 requests 已经配了 timeout=90)
        res = llm_utils.call_llm_json_array(prompt, model=config.TITLE_MODEL, temperature=0.7, max_retries=2)
        return res if res else []

    def _clean_category(self, cat):
        valid_cats = ["专业知识", "行业资讯", "产品介绍"]
        for v in valid_cats:
            if v in cat: return v
        return "行业资讯"
