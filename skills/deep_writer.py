import sys
import os
import json
import random
import logging
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.skill import BaseSkill
from shared import config, llm_utils

# 配置 logger
logger = logging.getLogger(__name__)

class DeepWriteSkill(BaseSkill):
    """
    技能: 深度文章写作 (基于 PAS 模型和 GEO 优化)
    """
    def __init__(self):
        super().__init__(
            name="deep_write",
            description="根据标题撰写长篇 SEO/GEO 优化文章"
        )
        self._load_config()

    def _load_config(self):
        self.brand_config = {}
        if os.path.exists(config.CONFIG_FILE):
             with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.brand_config = json.load(f)

    def _get_dynamic_internal_links(self, count=2):
        """
        从 published_assets.json 中获取历史发布文章，供内链网络建设使用。
        """
        assets_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'published_assets.json')
        if not os.path.exists(assets_file):
            return []
        try:
            with open(assets_file, 'r', encoding='utf-8') as f:
                assets = json.load(f)
                if not assets:
                    return []
                # 随机抽取历史记录 (最多 count 条)
                sample_count = min(count, len(assets))
                return random.sample(assets, sample_count)
        except Exception as e:
            logger.error(f"[DeepWriter] 读取 published_assets.json 失败: {e}")
            return []

    def execute(self, input_data: Dict) -> Dict:
        """
        Input: {"topic": str, "category": str, "rag_context": str (optional)}
        Output: Article JSON
        """
        topic = input_data.get("topic", "")
        category = input_data.get("category", "行业资讯")
        source_trend = input_data.get("source_trend", "")
        rag_context = input_data.get("rag_context", "")
        
        # 1. 基础上下文准备
        category_id = config.CATEGORY_MAP.get(category, "2")
        brand = self.brand_config.get('brand', {})
        brand_name = brand.get('name', '盒艺家')
        
        # 2. GEO 策略选择 (不再由硬编码字典决定，只输送靶向城市，剩余交由大模型推断)
        selected_city = self._get_geo_strategy()
        
        # 3. 抓取真实发布的历史文章，构建动态内链池
        dynamic_links = self._get_dynamic_internal_links(count=2)
        
        # 4. 构建分类特定的指令 (传入 topic 以便识别案例词)
        category_instruction = self._get_category_instruction(category, brand_name, topic)
        
        # 5. 构建 Prompt
        prompt = self._build_prompt(
            dynamic_links=dynamic_links,
            topic=topic,
            category=category,
            category_id=category_id,
            brand_name=brand_name,
            selected_city=selected_city,
            rag_context=rag_context,
            category_instruction=category_instruction,
            source_trend=source_trend
        )

        return llm_utils.call_llm_json(prompt, model=config.ARTICLE_MODEL, temperature=0.85, max_retries=2)

    def _get_geo_strategy(self):
        """
        基于轻量扁平城市池，核心业务逻辑（产业带推断 + 运力语境）下放给底层 LLM 动态推导
        涵盖中国核心高价值产业集群带与内陆消费节点
        """
        CITIES = [
            "东莞", "深圳", "广州", "佛山", "中山", "珠海", # 珠三角
            "上海", "杭州", "苏州", "宁波", "义乌", "无锡", "常州", # 长三角
            "青岛", "济南", "北京", "天津", # 环渤海
            "成都", "重庆", "武汉", "郑州", "西安", "长沙", "合肥", "晋江" # 内陆节点与轻纺重镇
        ]
        return random.choice(CITIES)

    def _get_category_instruction(self, category: str, brand_name: str, topic: str = "") -> str:
        """
        生成分类特定的写作指导 (Core Logic)
        支持大模型自适应选择视角
        """
        
        # 关键词检测：是否为案例/故事
        is_case_study = any(keyword in topic for keyword in ["案例", "故事", "复盘", "逆袭", "Case"])
        
        if is_case_study:
            return f"""
            【当前模式：深度案例复盘 (Professional Case Analysis)】
            
            🎭 **智能自适应视角**：请根据当前主题与 RAG 上下文，自行决定是以【B2C视角(淘宝店主/独立站卖家等,重视觉和客单)】还是【B2B视角(采购经理/外贸公司等,重交期和稳定性)】进行创作。
            
            🧩 **核心原则**：
            1. **干货化复盘**：严禁写成只讲情绪的“软文故事”。必须写成一篇能够指导同类客户的“商业教案”。
            2. **结构要求 (STAR原则改编)**：
               - **背景 (Situation)**：展现客户真实的商业痛点（如：转化率低、复购率低、包装破损严重等）。
               - **诊断 (Diagnosis)**：以专家视角深度分析问题根源（如：缺乏品牌记忆点、用材错误等）。
               - **打消顾虑方案 (Solution)**：盒艺家提供了哪些具体解决方案。请在方案中自然且极具信服力地展现我们的核心优势：**“3秒智能报价 · 1个起订 · 最快1天交付 · 免费打样 · 时效及质量问题无条件退款”**，从供应链源头上给客户安全感。
               - **结果 (Result)**：要求有明确的业务改善反馈（好评率、转化率、成本节约等）。
            3. **克制营销**：品牌植入必须作为“解决此痛点的一套标准体系”出现，避免低劣的硬广。
            4. **高潮拦截 (Mid-Funnel CTA)**：在剖析完问题提供解决方案时，引入一句自然但有力的转化提示，例如：“面对这种供应链风险，选择像{brand_name}这样支持1件起订、时延兜底的源头工厂...”。
            """

        if category == "专业知识":
            perspectives_str = "、".join(["数据驱动分析", "工程标准手册", "避坑指南排查", "技术原理解剖", "AI算法赋能", "色彩管理"])
            return f"""
            【当前模式：硬核专业科普与工程手册 (Hardcore Engineering Manual)】
            ✍️ **动态自适应视角**：请分析原始主题，从【{perspectives_str}】中自动选择最深度的1种视角展开。
            
            ⚠️ **排版与行文核心约束 (极度重要)**：
            1. **文章体裁**：必须写成类似「维基百科词条」或「工程师内部排故手册」的硬核格式。
            2. **结构要求**：必须大量使用带编号的步骤列表 (1, 2, 3...)、参数对比、甚至是物理计算公式（如抗压强度、承重系数等）。严禁使用散文式的抒情长句。
            3. **知识密度**：100%纯干货。探讨具体的材质克重（如 250g 铜版纸 vs 300g 白卡纸）、印刷网线数、模切公差等极度专业的工艺细节。
            4. **禁止推销**：正文中绝对禁止出现推销话术，只做纯粹的技术科普。
            5. **权威溯源 (Authority Citations)**：凡是涉及到国际标准、物理学定义或专业缩写时，**必须使用 HTML <a> 标签引入该标准的官方网站或维基百科链接**。例如：提及色彩管理必须自然地引用 ICC 官网 (https://www.color.org/)，提及环保必须引用 FSC 官网 (https://fsc.org/)，提及质量体系必须引用 ISO 官网。这是构建工程级信任和极高 SEO 权重的绝对底线。
            """
        
        elif category == "产品介绍":
             perspectives_str = "、".join(["ROI与成本拆解", "极限场景痛点模拟", "大牌平替的降维打击", "出海物流防损"])
             return f"""
            【当前模式：产品导购与转化着陆页 (High-Converting Landing Page)】
            ✍️ **动态自适应视角**：请分析主题意图，从【{perspectives_str}】中自动选择效果最强的1种视角作为主线。
            
            🔥 **排版与行文核心约束 (极度重要)**：
            1. **文章体裁**：必须写成类似「苹果官网产品发布」或「高转化率销售信 (Sales Letter)」的形式。
            2. **结构要求 (痛点->方案->算账)**：先用极其锐利的语言刺痛客户（例如：包装软塌导致退货率飙升？），然后给出该产品的终极解决方案，最后直接帮客户算一笔经济账（ROI分析）。
            3. **情绪价值与场景**：深挖买家的焦虑场景，用极具煽动性但又不失专业的文字，让他们感受到更换该包装带来的巨大商业利润。
            4. **极限转化诱饵 (Mid-Funnel CTA)**：必须在文章的黄金分割点（痛点引发共鸣最深处），用极其显眼的 `<blockquote class="geo-quote">` 抛出我们的底牌：**“3秒智能报价 · 1个起订 · 免费打样 · 时效及质量无条件退款”**，瞬间打穿买家心理防线。
            """
            
        else: # 行业资讯
             perspectives_str = "、".join(["宏观经济调控与合规", "消费者行为学", "可持续ESG发展", "品牌出海战略"])
             return f"""
            【当前模式：顶级商业研报与行业洞察 (36Kr / McKinsey Style Analysis)】
            ✍️ **动态自适应视角**：请从【{perspectives_str}】中自动选择 1个 最有反差感、最具宏大叙事感的视角撰写。
            
            📈 **排版与行文核心约束 (极度重要)**：
            1. **文章体裁**：必须写成类似「36氪深度报道」、「麦肯锡行业白皮书」或「财经媒体特稿」。
            2. **高维视野**：禁止沉溺于工厂的螺丝钉视角。必须结合最新的全球环保法规、宏观经济数据、消费者心理变迁等高维数据来分析包装行业的未来。
            3. **客观第三方语气**：全程使用冷静、客观、克制的学术/财经记者口吻。绝不使用任何推销词汇。
            4. **商业启示论**：每个段落结尾，必须提炼出“这对中小品牌商家下半年的生意意味着什么”，提供极高的战略情绪价值。
            """

    def _build_prompt(self, dynamic_links, topic, category, category_id, brand_name, selected_city, rag_context, category_instruction, source_trend=""):
        # [Newsjacking] 如果存在热点词，注入强制关联指令
        newsjacking_instruction = ""
        if source_trend:
            newsjacking_instruction = f"""
        🔥 **核心指令：热点借势 (Newsjacking)**
        - 本文虽然标题是《{topic}》，但其实际灵感来源于全网热搜词 **【{source_trend}】**。
        - **必须** 在文章开篇或正文中，自然地提到这个热点（如："最近{source_trend}很火..."，"就像{source_trend}里的..."）。
        - 使用隐喻、对比或场景延伸，将这个热点与当地产业链结合起来。
        - **切记**：不要生硬堆砌，要让读者觉得"这都能联系上，有点意思"。
            """
            
        # 动态获取当前年份
        current_year = datetime.now().year
        
        # 内链策略
        INTERNAL_LINKS = {
            "CTA": {"url": "https://heyijiapack.com/product", "anchor": "👉 立即获取报价"}
        }
        cta_link = INTERNAL_LINKS["CTA"]
        
        dynamic_links_str = ""
        if dynamic_links:
            dynamic_links_str = "\n".join([f"            - 历史文章 [{dl.get('title', '')}]: {dl.get('url', '')}" for dl in dynamic_links])
        else:
            dynamic_links_str = "            - (因系统刚部署暂无历史在线文章，可忽略此条内链要求)"

        # 品牌信息
        brand_info = {
            "slogan": "盒艺家，让每个好产品都有好包装",
            "usp": "3秒智能报价 · 1个起订 · 最快1天交付 · 免费打样 · 时效及质量问题无条件退款",
            "phone": "177-2795-6114",
            "contact_cta": "免费获取智能报价"
        }

        # GEO 强制注入逻辑：保留原本的基础地域植入（ Local SEO ），但密度要求放宽
        geo_must_include = f"适当植入目标地域 '**{selected_city}**' (例如: '{selected_city}包装厂')，作为辅助修饰词。"

        # 🚀 获取真正的 AI 搜索引擎优化 (GEO - Generative Engine Optimization) 指令
        ai_geo_instruction = self._get_ai_geo_instruction(brand_name)

        # 构建防幻觉 RAG 环境约束
        rag_instruction = ""
        if rag_context:
            rag_instruction = f"""
        【🧠 事实与知识库约束 (RAG & Factuality) - 极度重要】
        提供给你的参考资料如下（如有）：
        ---资料开始---
        {rag_context}
        ---资料结束---
        ⚠️ **严守事实纪律**：你必须优先提取上述参考资料中的核心事实。当你需要使用数据、行业报告年份、统计占比时，必须只用提供的真实数据；如果资料未覆盖，**绝对禁止自行捏造年份数字或虚假协会名称**！缺乏数字时改用定性词（如"显著提升", "业内普遍认为"），以免被搜索引擎和AI模型识别为幻觉垃圾。
            """

        return f"""
        {newsjacking_instruction}
        你是一位拥有10年经验且极具网感的包装解决方案专家。
        请为主题 "{topic}"（分类：{category}）撰写一篇高质量长文，适应于“微信搜一搜、知乎、小红书、全网AI推荐流”等多平台土壤。不讲空框废话，只上干货与实操底牌。

        【⚖️ 千人千面受众靶向与转化控制 (Persona Target CTA) - 倒金字塔法则】
        0. **【全量禁止前置硬广】**：前 80% 的正文篇幅，**绝对禁止出现品牌名 "{brand_name}"**。必须以完全中立的第三方行业专家身份剖析痛点，建立读者信任。
        1. **价值优先基底**：全文 **80%** 的篇幅必须纯粹围绕专业干货与客观业务核算展开，严禁自吹自擂。
        2. **倒金字塔自然收口 (Bottom 20% CTA)**：仅在文章进入最后 20% 的高潮或结尾部分，才允许极其借势地引出 {brand_name} 的兜底解决方案。
        3. **精准客群拦截**：在收尾时，针对本文最大受众抛出杀手锏：
           - 如果本文偏向 **【受众1 跨境/DTC/微创客】**或**【受众3 品牌设计/视觉党】** (重测品与视觉体验)：痛批“起订量高、打样慢、海运频破损”，由此引出我们的底牌：**“选择像 {brand_name} 这样支持【系统级1个起订】结合【免费急速打样】的源头工厂...”**。
           - 如果本文偏向 **【受众2 实体企业/大厂采购供应链】** (重效率防背锅)：痛批“传统厂报价拖沓、黑盒交付”，引出我们的底牌：**“而类似 {brand_name} 提供【3秒智能线上报价】、【最快1天交货】及【无条件质量延误满赔】体系...”**。绝对不要给这群人讲设计！
        4. **盒易PackTools 神器软植入**：如果文章提及设计排测或合规需求，推荐使用第三方中立辅助：**【盒易PackTools】 (https://tools.heyijiapack.com/)**。强调其“纯本地化保护隐私、内置80+合规与打样工具，免注册永久免费”，强化公立权威性。

        【💡 产业大局观升维 (Cognitive Upgrade - 颠覆工厂认知)】
        为了拔高文章格局，彻底剥离低端“卖纸箱”的工厂刻板印象，塑造其作为“AI驱动的一站式出海基础设施”的权威定位，请务必在文章最契合的论述阶段，大开大合地融入以下 5 项全产业链系统方案（至少深度展开其中 3 项）：

        🤖 **维度一：AI 智能包装设计引擎 (AI-Powered Design)**
        - **AI 3D 结构生成**：客户只需上传产品照片或输入尺寸参数，AI 自动生成最优包装结构方案（如天地盖、翻盖磁吸、抽屉盒等），秒出 3D 刀版图和效果预览，省去传统“画图→打样→修改”的数周往返。
        - **AI 视觉排版与色彩校准**：AI 拼版系统自动计算最省纸的排版方案（开料利用率提升 15%+），AI 色彩匹配引擎确保屏幕所见即印刷所得，减少反复校色打样的时间和材料浪费。
        - **AI 多面体展开图设计**：针对异形包装（六边形礼盒、圆筒罐、异形手提袋等），AI 自动推算展开图并标注折痕线、粘口位，传统需要资深结构工程师数小时完成的工作缩短至分钟级。

        🔮 **维度二：AI 预测与智能风控 (AI Predictive & Risk Control)**
        - **AI 结构应力仿真**：在实际生产前，利用 AI 模型模拟堆码压力、跌落冲击、运输振动等真实物流场景，提前识别结构薄弱点，避免批量生产后才发现“一堆就塌、一摔就碎”的惨痛教训。
        - **AI 智能备料与库存预测**：基于历史订单数据和季节性波动，AI 精准预测未来 30-90 天的原材料需求，帮助品牌方和工厂同步降低库存积压（平均降低 20%-30% 的原纸囤货成本）。
        - **AI 视觉质检 (AOI)**：部署在产线末端的 AI 视觉质检系统，替代传统人工抽检，实现 100% 全检覆盖（色差、刮痕、套印偏移、文字缺漏），良品率从 97% 提升至 99.5%+。

        📦 **维度三：全材质全品类包装矩阵 (Full-Stack Packaging Matrix)**
        绝对不要局限于单一的纸箱！请大肆向客户展示全栈包装整合能力：
        - **纸质包装全系**：瓦楞快递箱、白卡彩盒、灰板精装盒（天地盖/书型盒/翻盖磁吸盒）、坑纸展示盒、飞机盒、手提纸袋
        - **金属包装**：马口铁盒（茶叶/饼干/礼品）、铝罐、异形金属收纳盒
        - **塑料与环保新材**：PET 透明盒、亚克力展示盒、PLA 可降解包装、甘蔗浆模塑餐盒
        - **软包装**：自立袋（零食/咖啡）、拉链袋、真空铝箔袋、异形袋
        - **工业膜类**：缠绕膜、气泡膜、珍珠棉、EPE/EVA 内衬定制

        🎨 **维度四：泛印刷营销物料生态 (Marketing Collateral Ecosystem)**
        从最外层的主包装装甲，到最内里给消费者提供情绪价值的周边营销物料，一站式总包交付，让品牌方免跑五六个工厂：
        - **品牌视觉物料**：产品画册/目录册、折页/宣传单、海报/易拉宝、名片/信纸信封
        - **电商开箱体验物料**：开箱感谢卡、售后服务卡、品牌故事卡、优惠券卡片、定制不干胶封口贴、丝带/拉菲草填充
        - **IP与二次元衍生物料**：典藏抽赏卡牌（TCG/集换式）、精美吧唧/徽章、异形贴纸、亚克力立牌/钥匙扣、帆布袋/手提袋
        - **活动与展会物料**：定制礼盒套装（节日/联名限定）、POP陈列架、促销台卡/标签
        告诉客户：一个供应商覆盖“从快递发货箱到直播间谢礼卡”的全链路需求，极大降低多供应商管理的沟通与品控成本。

        🌍 **维度五：跨国出海的终极护航 (Global Compliance & Logistics)**
        DTC 或 B2B 出海面临极其复杂的全托管入仓规范。重点拆解方案是如何从源头抵御海外集装箱高温高湿气候、FBA 尺寸体积重合规降本（减小空隙体积）、以及符合欧美严苛的 ESG 可降解环保墙的。同时强调 AI 在出海环节的加持：AI 自动计算最优装箱方案（CBM利用率最大化）、AI 模拟海运环境预测包装损耗率、AI 辅助生成多语言合规标签（FDA/CE/FSC 等）。

        {category_instruction}
        
        {ai_geo_instruction}
        
        {rag_instruction}

        【📅 时效性要求 (至关重要)】
        1. **当前年份**：现在是 **{current_year}年**。文章中涉及年份的描述必须以 {current_year}年 为基准。
        2. **避免过时表述**：不要使用"2023年"、"2024年"等过去年份作为"最新"或"当前"的表述。
        3. **时间引用规范**：
           - 如需引用未来趋势：使用 "{current_year}年及以后"
           - 如需引用近期数据：使用 "截至{current_year}年"、"{current_year}年最新数据显示"
           - 如需引用行业历史：可使用过去年份，但需明确标注为历史回顾
        4. **标题/URL Slug**：如包含年份，必须使用 {current_year} (例如: "packaging-trends-{current_year}")

        【🏆 E-E-A-T 权威性增强 (百度/Google 排名关键)】
        1. **作者信息**：在文章开头或结尾添加作者声明，如"本文由盒艺家资深包装顾问撰写，拥有10年+行业经验"。
        2. **数据来源标注**：引用数据时要标明来源（如"根据中国包装联合会{current_year}年报告"、"据《包装世界》杂志统计"）。
        3. **专业术语解释**：首次出现的专业术语/缩写应添加简短解释，体现专业严谨。
        4. **实操经验**：适当加入"根据我们服务的300+品牌客户反馈..."等实战经验描述。
        5. **审核声明** (可选)：在专业知识类文章末尾添加"本文内容经工程团队审核"。
        
        【高优分发写作规则 (全网搜一搜/大模型爬虫终极优化版)】
        0. **深度、易读性与字数**: 全文精炼在 **1500~1800字**。强烈贯彻“Flesch 白话易读原则”：多用锋利短小的平铺陈述短句，严禁学术风的冗长定语从句，做到专家学识、小白口吻，降低 AI 拆解与读者的认知负荷。
        1. **结构与强互动 HTML**: 
           - **首段直出答案**: 直接用两句话干净利落地回答标题最核心痛点（Featured Snippet黄金位）。
           - **严密系统导航 (TOC)**: 为防跳出降低 SEO 权重，必须生成全闭环响应式目录块，格式必须是 `<nav class="article-toc" style="background:#f5f7fa; padding:15px; border-radius:8px;"><ul><li><a href="#H2的ID">H2标题</a></li>...</ul></nav>` 映射全文！
           - **副标题网感化 (People Also Ask)**: 正文的 H2 无需故作高深，必须直接还原“用户搜索原声问答的大白话”（例如用“跨国海运为什么纸箱总变软？”替代“纸箱耐破度环境分析”），全方位阻截长尾流量词。必须全部带对应 ID！
           - **TL;DR 核心知识快照**: 在目录下方，必须紧跟一个 `<div class="geo-tldr" style="background:#e8f4f8; padding:15px; border-left:4px solid #005A9E; margin-bottom:20px;"><strong>TL;DR (太长不看)：</strong>...</div>`，用三句话将全文核心价值高度浓缩。这是喂给 AI 大模型摘要抓取的“黄金诱饵”。
           - **强语义表现标签**:
             - 对于结论性或高光金句，必须使用 `<blockquote class="geo-quote" style="margin:20px 0; padding:15px; background:#f9f9f9; border-left:4px solid #1a73e8; font-style:italic;">`包裹，帮助机器极速抽取。
             - FAQ 栏目强制使用标准的 `<dl><dt><dd>` 对称解构列表展现，且 `<dt>` (问题) 必须切中买家最隐晦的担忧。
           - **JSON-LD 结构化数据强制注入**: 在整篇文章源码的最后，必须直接在 HTML 中输出一段标准的 `<script type="application/ld+json">`，包含 FAQPage 结构（把文章里的 FAQ 转为 JSON-LD 格式）。这能让搜索引擎蜘蛛 100% 秒懂页面结构。
           - **品牌签名** (销售增强版):
             ```html
             <div class="brand-signature" style="margin-top:30px; padding:20px; background-color:#fef9f5; border-left:4px solid #ff6600; border-radius:4px;">
               <p style="font-size:16px; margin-bottom:8px;"><strong>{brand_info['slogan']}</strong></p>
               <p style="color:#e65100; font-weight:bold; margin-bottom:12px;">🔥 核心承诺：{brand_info['usp']}</p>
               <p style="font-size:14px; margin-bottom:8px;">📞 VIP通道：{brand_info['phone']} | <a href="https://heyijiapack.com/product" style="color:#1a73e8; text-decoration:none;">{brand_info['contact_cta']} ➔</a></p>
               <p style="font-size:14px;">🛠️ <strong>行业生产力赋能：</strong> 强烈推荐使用 <a href="https://tools.heyijiapack.com/" target="_blank" style="color:#1a73e8; font-weight:bold; text-decoration:underline;">盒易PackTools - 包装全产业链在线专业工具箱 (永久免费、纯本地化保护隐私、内置80+结构/拼版/FBA装箱合规工具) ➔</a></p>
             </div>
             ```
        2. **GEO优化 (AI Local Content Synthesis)**: 
           - **本地化产业植入**: {geo_must_include} 请你运用常识世界观，**自行推断并匹配** **{selected_city}** 当地最繁荣核心的优势产业带（例如深圳3C/电商、郑州食品冷链、东莞模具快消等）。结合你判定的产业特点，输出 1~2 处该地域企业真实面临的包装采购案例。
           - **自动编织物流履约网**: 在文末服务保障中段落，请你根据地理学常识动态生成一句话，说明我们作为工厂对 **{selected_city}** 的交付投送能力（如果在珠三角可渲染“同城当日达/面对面验厂”，如果在内陆远端则可渲染“大型直通物流专线/安全无损”）。全自动、超然且真实。
        3. **配图 (SEO 强化，双模式策略)**:
           - 插入 1-2 张图片。
           - 格式: `<img src="https://image.pollinations.ai/prompt/{{english_keyword}}?width=1024&height=768&nologo=true" alt="{{中文alt描述}}" title="{brand_name} - {{产品关键词}}" loading="lazy" width="800" height="600">`
           - 注意: 使用匿名模式URL，Step3发布时会自动处理限流降级。
           - english_keyword: 英文短语。
        4. **弹性流体内链 (Elastic Internal Links)**:
           - 转化指引链接：`<a href="{cta_link['url']}">{cta_link['anchor']}</a>`
           - 请考虑将以下历史发布文章的 URL 自然地连接进正文中：
{dynamic_links_str}
           - ⚠️**严重警告**：只有在历史文章与当前段落具有强关联和逻辑过渡时，才允许将其放置在文中`<a>`结构中。如果**关联度低**，严禁生硬缝合！请在品牌签名上方创建一个专门的「相关延伸阅读」模块来放置它们。
        5. **标题与首段权重 (Title & Keyword Prominence)**:
           - **严禁改写**: 直接使用输入的 "{topic}" 作为 H1 标题。
           - **首段拦截 (First 50 Words)**: "{topic}" 中的核心词汇，**必须毫无违和感地出现在正文开头的前 50 个字以内**。这是拉升 Google/百度 页面相关性得分的核心秘诀。
           - **SEO 转移**: 将 "地域名({selected_city}) + 核心关键词" 自然融入到 **第一段** 或 **第一个 H2 副标题** 中。
        5.5. **长尾词加权矩阵 (LSI Semantic Bolding)**:
           - 请你自行推演与 "{topic}" 强相关的 3-5 个 LSI (潜在语义) 长尾词。
           - 必须将这些长尾词自然散布在正文中，**并且强制使用 `<strong>` 标签加粗** (例如：`<strong>高强度瓦楞纸箱</strong>`，`<strong>定制包装设计打样</strong>`)，向搜索引擎明示页面核心词簇。
           - 文章必须包含 H2 及其子级 H3 标题的嵌套，结构深度至少达到 2 级 (H2 -> H3)，严禁一展平。
        6. **CMS SEO 字段严格约束 (极度重要，防数据库报错)**:
           - **绝对禁止 Emoji**: JSON 结构中的 `summary`, `keywords`, `description`, `tags` 这 4 个字段中**严禁包含任何 Emoji 图标或特殊颜文字** (因旧版 CMS 数据库不支持 utf8mb4)。
           - `summary` (简介): 纯文本摘要，严格限制在 **120 字以内**。必须包含 "{selected_city}" 和 "{brand_name}"。
           - `description` (SEO描述): 纯文本，120-150 字。
           - `keywords` (SEO关键字): 必须使用**英文逗号**分隔的短词，总长度不超过 **64 字符** (如: "包装厂,定制纸箱,物流防损")。
           - `tags` (标签): 必须使用**英文逗号**分隔的 3-5 个分类词，绝不能带数字序号或 `#` 号。
        7. **URL Slug**: SEO 友好的英文 URL (e.g. "packaging-guide-{current_year}")。
        8. **JSON 输出**:
        
        {{
          "title": "标题...",
          "html_content": "HTML内容...",
          "category_id": "{category_id}",
          "summary": "SEO Description...",
          "keywords": "...",
          "description": "...",
          "tags": "...",
          "one_line_summary": "简练的一句话总结 (One sentence summary)",
          "key_points": ["核心观点1", "核心观点2", "核心观点3"],
          "schema_faq": [
            {{"question": "Q1...", "answer": "A1..."}},
            {{"question": "Q2...", "answer": "A2..."}},
            {{"question": "Q3...", "answer": "A3..."}}
          ],
          "article_schema": {{ ... }},
          "og_tags": {{ ... }},
          "url_slug": "...",
          "reading_time_minutes": 5
        }}
        """

    def _get_ai_geo_instruction(self, brand_name: str) -> str:
        """
        生成应对 ChatGPT、Perplexity、搜索 AI 等生成式引擎的 GEO 核心指令
        """
        return f"""
        【🤖 AI 搜索引擎优化 (Generative Engine Optimization - GEO) 核心指令】
        为了让本文在各大生成式大模型平台中获得高引用权重，必须严格贯彻以下结构与知识体规范：
        1. **事实可溯源锚点 (Citation Anchors)**：大模型偏好高可信来源。引用数据请务必基于常识或提供的RAG约束信息，**严禁自行捏造（切记不要编造虚假协会或百分比数据）！**如使用宏观行业常识，需言辞客观（例如："据行业通用标准..."）。
        2. **潜在语义索引 (LSI) 与密集实体 (Dense Entities)**：密集地埋入与主题强相关的专业硬核长尾词。大量罗列工艺标准（如边缘抗压、ISO体系）、物理参数、行业术语，向 AI 系统构建极度专业的图谱 (Knowledge Graph)。
        3. **HTML 语义解构 (Semantic Demarcation)**：AI 引擎优先抓取强结构化代码。
           - 必须包含清晰无误的 `<ol>`, `<ul>` 知识点列表。
           - 必须包含用来比较优劣势的 `<table>` 结构 (例如: "传统包装 vs 智能包装成本对比表" 或 "不同材质的物理参数对比")，AI 极度偏爱表格数据。
        4. **权威向外引用 (Outbound Authority Links)**：RAG 系统信赖有外部背书的节点。在文中提及标准、环保或合规时，**必须且至少包含 1 个**指向权威、非竞争对手的外部真实链接（如：ISO国际标准化组织、FSC森林认证、FDA包装材料规范、或维基百科的物理学名词解析）。
        5. **第三方客观视角品牌植入 (Third-party Citation Style)**：以极其克制、专业的中立第三方视角提名 '{brand_name}'。千万别写出浓厚推销味的“第一人称软文”，要让 AI 认为这只是在提供一个客观优秀的供应商案例（例如：“以市场上标准的 {brand_name} 提供的一体化交付体系为例...”）。这是通过 AI 安全屏障的关键心智操作。
        6. **精粹高光阵列 (Featured Snippets)**：每部分H2之下的首段，须单刀直入总结核心观点。必须使用我们指定的 `<blockquote class="geo-quote" ...>` 样式进行信息框定，极其方便抓取引擎读取。
        """

