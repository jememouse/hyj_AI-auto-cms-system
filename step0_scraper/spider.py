import sys
import os
import json
import time
import random
import datetime
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# 添加项目根目录到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from shared.d1_client import D1Client

# ==========================================
# 1. 全品类大种子词库与规则字典
# ==========================================
SEEDS = [
    "包装定制", "包装订制", "包装设计", "礼盒定制", "纸盒定做", "包装盒设计", 
    "彩盒印刷", "食品包装设计", "手提袋定制", "纸箱定制", "化妆品包装设计", "茶叶包装定制",
    "纸质包装", "塑料包装袋", "吸塑包装定制", "金属包装罐", "马口铁盒定制", "铝罐包装设计",
    "玻璃瓶定制", "玻璃酒瓶设计", "陶瓷酒瓶定制", "木盒定做", "茶叶木盒定制", "竹质包装盒",
    "帆布袋定制", "无纺布袋定做", "绒布束口袋", "复合包装膜", "铝箔自立袋",
    "包装材料", "包装机械", "包装工艺", "物流包装", "真空包装", "环保包装", 
    "可降解包装", "智能包装", "冷链包装", "药品包装", "缓冲包装", "软包装",
    "FSC认证纸张", "食品级包装标准", "UN危险品包装", "SGS包装检测",
    "包装刀模线设计", "纸箱抗压强度", "包装跌落测试", "包装结构设计",
    "苹果包装", "iPhone包装", "华为包装", "小米包装", "香奈儿包装", "爱马仕包装", 
    "古驰包装", "LV包装", "迪奥包装", "茅台包装", "五粮液包装", "星巴克包装", 
    "喜茶包装", "瑞幸包装", "可口可乐包装", "百事可乐包装", "农夫山泉包装", 
    "麦当劳包装", "肯德基包装", "三只松鼠包装", "霸王茶姬包装", "霸王茶姬手提袋", 
    "茶颜悦色包装", "奈雪的茶包装", "蒂芙尼包装", "卡地亚包装", "劳力士包装", 
    "花西子包装", "完美日记包装", "大疆包装", "乐高包装", "耐克鞋盒", 
    "阿迪达斯鞋盒", "雅诗兰黛包装", "兰蔻包装", "大白兔包装", "泡泡玛特包装", 
    "盲盒包装设计", "瑞幸咖啡手提袋", "喜茶保温袋",
    "亚克力展示架", "塑料促销台定制", "金属展架定制", "马口铁牌广告", "纸展示架定制", 
    "纸质手提袋制作", "牛皮纸信封定制", "KT板喷绘", "广告灯箱定制", "易拉宝双面", 
    "刀旗制作", "快展展架", "高档名片定制", "定制笔记本礼品", "广告伞定制", "钥匙扣定制",
    "AI包装设计", "人工智能包装", "包装大数据", "精准营销包装", "一物一码包装", 
    "AR互动包装", "RFID智能包装", "智能防伪包装", "数字化包装设计",
    "包装色彩管理", "潘通色卡对照表", "包装加工制造", "包装模切折叠", "逆向UV工艺", 
    "包装刀模设计", "包装打样标准", "包装专色控制", "包装表面工艺"
]

def filter_noise(word: str) -> bool:
    w = word.lower()
    if "小米" in w and any(x in w for x in ["吃", "煮", "大米", "粮食", "农产品", "饭", "粥", "过期", "保质期", "大米发霉", "煮饭"]):
        return False
    if any(x in w for x in ["招聘", "找工作", "工资", "人才网", "累不累", "包吃住", "包装工", "招工", "月薪", "待遇"]):
        return False
    if any(x in w for x in ["会计分录", "怎么记账", "做账", "报销", "税率"]):
        return False
    return True

def classify_word(word: str) -> str:
    w = word.lower()
    if any(x in w for x in ["解决方案", "标准", "测试", "认证", "色差", "爆线", "爆角", "抗压", "跌落", "防潮", "fda", "fsc", "sgs", "un", "防静电", "合规", "说明书管理", "名词解释", "原理", "验证", "rfid", "ar", "智能", "一物一码", "人工智能", "ai", "大数据", "精准营销", "数字化", "潘通", "色卡", "打样", "模切", "uv工艺", "制造工艺", "专色", "加工"]):
        return "工艺与合规方案"
    if any(x in w for x in ["厂家", "定做", "定制", "订制", "批发", "公司推荐", "公司名称", "公司简介", "排名", "名单", "一般多少钱", "价格表", "起订", "一个起", "生产厂家", "包装袋制作", "机械", "设备", "手提袋制作", "杯套多少钱", "回收价", "价格"]):
        return "商业采购与找厂"
    if any(x in w for x in ["设计", "图片", "刀模", "展开图", "手绘", "卡通", "素材", "画册", "折页", "海报设计", "视觉设计", "配色", "图鉴", "演变", "样式"]):
        return "设计与灵感"
    if any(x in w for x in ["苹果", "iphone", "华为", "小米", "香奈儿", "爱马仕", "古驰", "lv", "迪奥", "蒂芙尼", "卡地亚", "劳力士", "星巴克", "喜茶", "瑞幸", "可口可乐", "百事", "农夫山泉", "麦当劳", "肯德基", "三只松鼠", "大白兔", "泡泡玛特", "茶颜悦色", "奈雪", "真伪", "真假", "防伪", "退货", "序列号", "防篡改", "怎么打", "结怎么打"]):
        return "品牌与消费者行为"
    return "其他长尾检索"

def generate_knowledge_and_solutions():
    titles = []
    problems = [
        ["白卡纸包装盒", "印刷爆线与爆角", "解决方案与成因分析"], ["礼盒定制", "面纸起泡与脱胶", "整体预防解决方案"],
        ["高档包装定制", "大面积专色印刷色差控制", "整体解决方案"], ["瓦楞纸箱", "高湿环境抗压防潮软化", "优化解决方案"],
        ["高档纸质手提袋", "手挽穿绳处承重破裂", "结构加固优化设计方案"], ["化妆品PET/玻璃瓶包装", "料体与瓶身相容性测试", "整体解决方案"],
        ["特种纸礼盒", "烫金工艺跑位与漏烫", "工艺解决方案"], ["生鲜食品包装", "真空破袋率高", "材料升级与热封解决方案"]
    ]
    for p in problems:
        titles.extend([f"如何解决{p[0]}{p[1]}的{p[2]}", f"{p[0]}{p[1]}的常见成因与{p[2]}"])

    knowledge = [
        ["食品级包装材料", "合规性认证与检测技术标准指南"], ["环保可降解餐盒", "PLA/麦秸秆材料工艺及环保参数对比"],
        ["快递物流包装", "绿色减量化设计与成本控制标准指南"], ["智能溯源标签", "在高端品牌防伪包装中的应用技术方案"],
        ["包装防静电设计", "电子元器件缓冲包装规范与标准"], ["防油防潮淋膜纸袋", "技术原理与制作工艺百科说明"],
        ["特种艺术纸张分类", "在高档礼盒设计中的应用与配色原则"], ["AI驱动智能包装", "在快消品精准营销中的应用与数据闭环方案"],
        ["数字化包装印刷", "如何利用大数据实现个性化定制与按需生产"], ["AR/RFID智能包装", "在前沿包装交互与防伪溯源中的最新技术应用"],
        ["AI人工智能包装设计", "从灵感生成到刀模线自动排版的技术前沿"], ["大数据精准营销", "基于一物一码包装方案的消费者画像构建指南"],
        ["包装色彩设计与管理", "潘通色卡(Pantone)印刷色差控制与配色标准说明"], ["高档彩盒包装", "数码打样与大货专色印刷色彩校准方案"],
        ["全自动包装加工制造", "智能联动线在纸盒高速模切折叠中的工艺规范"], ["包装制造工艺流程", "从原材料进厂到成品打包出货的全链路品质监控"],
        ["高档礼盒包装设计", "3D折纸结构与异形刀模线绘制技巧与规范"], ["特种表面工艺处理", "UV逆向光油、烫金浮雕与击凸工艺的应用与成因"]
    ]
    for k in knowledge:
        titles.extend([f"{k[0]}{k[1]}", f"一文读懂：{k[0]}的{k[1]}"])

    return titles

# ==========================================
# 2. 多引擎高并发聚合爬取器
# ==========================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
}

def fetch_baidu(kw: str):
    try:
        url = f"https://suggestion.baidu.com/su?wd={urllib.parse.quote(kw)}&p=3"
        res = requests.get(url, headers=HEADERS, timeout=5)
        text = res.content.decode('gbk', errors='ignore')
        import re
        match = re.search(r's:(\[.*?\])', text)
        if match:
            return json.loads(match.group(1))
    except Exception:
        pass
    return []

def fetch_bing(kw: str):
    try:
        url = f"https://api.bing.com/qsonhs.aspx?q={urllib.parse.quote(kw)}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        data = res.json()
        results = data.get("AS", {}).get("Results", [])
        return [sug.get("Txt") for item in results for sug in item.get("Suggests", [])]
    except Exception:
        pass
    return []

def fetch_360(kw: str):
    try:
        url = f"https://sug.so.360.cn/suggest?word={urllib.parse.quote(kw)}&encodein=utf-8&encodeout=utf-8"
        res = requests.get(url, headers=HEADERS, timeout=5)
        data = res.json()
        return [x.get("word") for x in data.get("result", [])]
    except Exception:
        pass
    return []

def fetch_taobao(kw: str):
    try:
        url = f"https://suggest.taobao.com/sug?code=utf-8&q={urllib.parse.quote(kw)}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        data = res.json()
        return [x[0] for x in data.get("result", []) if x]
    except Exception:
        pass
    return []

def get_aggregated_suggestions(keyword: str):
    words_set = set()
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_baidu, keyword): 'baidu',
            executor.submit(fetch_bing, keyword): 'bing',
            executor.submit(fetch_360, keyword): '360',
            executor.submit(fetch_taobao, keyword): 'taobao'
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    for w in res:
                        words_set.add(w)
            except Exception:
                pass
    if keyword in words_set:
        words_set.remove(keyword)
    return list(words_set)

# ==========================================
# 3. 核心流与探针分流器
# ==========================================
def run_hybrid_scraper_workflow():
    newly_fetched = set()
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # 获取 UTC 当前小时 (GitHub Actions 默认 UTC)
    current_hour = datetime.datetime.now(datetime.timezone.utc).hour
    period = current_hour // 4  # 0 到 5 的时段编号
    
    # 取基底词
    current_seeds = [s for i, s in enumerate(SEEDS) if i % 6 == period]
    
    # 随机打乱数组，防饿死
    random.shuffle(current_seeds)
    
    print(f"[Sharding] 当前处于每天第 {period} 时段 (UTC {current_hour}时)，分配 {len(current_seeds)} 个基底词下钻...")
    
    # 无需 8.5 秒时间限制，我们可以肆意抓取全部 16 个词及其子词
    # 限制 15 分钟即可，避免意外卡死
    start_time = time.time()
    MAX_DURATION = 15 * 60  
    
    for seed in current_seeds:
        if time.time() - start_time > MAX_DURATION:
            print("[Warning] 达到 15 分钟最大执行时间，提前结束当前时段抓取。")
            break
            
        print(f"正在深度挖掘: {seed}")
        suggestions = get_aggregated_suggestions(seed)
        for w in suggestions:
            if filter_noise(w):
                newly_fetched.add(w)
                
        # 取前两名进行下钻
        sub_seeds = suggestions[:2]
        for sub in sub_seeds:
            if filter_noise(sub):
                print(f"  --> 正在下钻子词: {sub}")
                sub_sug = get_aggregated_suggestions(sub)
                for w in sub_sug:
                    if filter_noise(w):
                        newly_fetched.add(w)
            time.sleep(0.5)  # 礼貌性延时
            
    # 生成专业标题，并提取独立的 Set 以备探针交叉比对
    b2b_titles = [t for t in generate_knowledge_and_solutions() if filter_noise(t)]
    b2b_titles_set = set(b2b_titles)
    for t in b2b_titles:
        newly_fetched.add(t)
        
    results = []
    for word in newly_fetched:
        results.append({
            "关键词": word,
            "搜索意图分类": classify_word(word),
            "抓取日期": today_str,
            "更新状态": "本周新增",
            "是否为内容标题": word in b2b_titles_set
        })
    return results

# ==========================================
# 4. 持久化总控室 (D1 + 谷歌物理网关)
# ==========================================
GOOGLE_GAS_URL = "https://script.google.com/macros/s/AKfycbwxKA1sQfs1Cc10d4Pi-YlzJJ8XUFN2--GzkV0-iOC77Z3c8t9asjSO1Hw-GzuerzSz/exec"

def main():
    print("🚀 开始纯 Python 多引擎并发爬取流程...")
    fetched_data = run_hybrid_scraper_workflow()
    
    if not fetched_data:
        print("未抓取到任何数据。")
        return
        
    print(f"✅ 抓取完成，共提取 {len(fetched_data)} 个有效词条。准备入库去重...")
    
    db = D1Client(db_id=os.getenv("CF_D1_PACKAGING_DB_ID", "2ef1ee52-ad2e-48c8-9c6e-63e76873b855"))
    if not db.account_id or not db.token:
        print("❌ [Fatal Error] 缺少 D1 数据库环境变量 (CF_ACCOUNT_ID, CF_API_TOKEN)。")
        return
        
    new_keywords = [item["关键词"] for item in fetched_data]
    
    # 步骤一：D1 数据湖全量过滤历史冗余
    CHUNK_SIZE = 100
    existing_set = set()
    
    for i in range(0, len(new_keywords), CHUNK_SIZE):
        chunk = new_keywords[i:i+CHUNK_SIZE]
        placeholders = ",".join(["?"] * len(chunk))
        query_stmt = f"SELECT keyword FROM keywords_repo WHERE keyword IN ({placeholders})"
        
        records = db.execute(query_stmt, params=chunk)
        if records:
            for r in records:
                existing_set.add(r.get("keyword"))
                
    incremental_data = [item for item in fetched_data if item["关键词"] not in existing_set]
    
    if incremental_data:
        print(f"♻️ 去重完毕，准备将 {len(incremental_data)} 个新鲜长尾词入库 D1...")
        
        # 步骤二：向热数据湖 (D1) 全量下沉
        insert_queries = []
        for item in incremental_data:
            insert_queries.append({
                "sql": "INSERT INTO keywords_repo (keyword, intent, fetch_date, status) VALUES (?, ?, ?, ?)",
                "params": [item["关键词"], item["搜索意图分类"], item["抓取日期"], item["更新状态"]]
            })
            
        BATCH_SIZE = 100
        for i in range(0, len(insert_queries), BATCH_SIZE):
            batch = insert_queries[i:i+BATCH_SIZE]
            success = db.execute_batch(batch)
            if success:
                print(f"[Batch Insert] 成功吸纳第 {i+1} 到 {i+len(batch)} 条新词汇入库。")
            else:
                print(f"[Batch Insert Error] 第 {i+1} 批次写入失败。")
                
        # 步骤三：数据泵分流，将探针命中的 "纯标题" 发向谷歌云做高价值归档
        titles_only_data = [item for item in incremental_data if item["是否为内容标题"]]
        if titles_only_data:
            try:
                res = requests.post(GOOGLE_GAS_URL, json={"data": titles_only_data}, headers={"Content-Type": "application/json"}, timeout=10)
                res.raise_for_status()
                print(f"[Archive Success] {len(titles_only_data)} 个高价值 B2B 标题已跨云推送至 Google Drive。")
            except Exception as e:
                print(f"[Archive Failed] 跨云推送失败: {e}")
    else:
        print("[Notice] 抓取到的词汇已全在 D1 数据库中存在，本次无新增。")

if __name__ == "__main__":
    main()
