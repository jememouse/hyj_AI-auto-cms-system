# shared/config.py
"""
共享配置模块
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# LLM API 配置 (Xiaomi MiMo 最高优先级 → DeepSeek 备用 → Google GenAI 备用 → OpenRouter 兜底)
# MIMO_API_KEY = os.getenv("MIMO_API_KEY", "").strip()
MIMO_API_KEY = ""
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# 级联通道配置
# 1. 优先主通道: Xiaomi MiMo
MIMO_API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MIMO_MODEL = "mimo-v2.5"

# 2. 二级备用通道: DeepSeek 官方直连
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# 兼容模型 Thinking 模式配置 (支持 MiMo / DeepSeek)
LLM_THINKING_ENABLED = False   # 开启思考模式 (思维链推理)
LLM_REASONING_EFFORT = "high" # 思考强度: "high" (默认) 或 "max" (复杂任务)

# 3. 三级备用通道: Google GenAI (当上述通道失败后切换)
GOOGLE_GENAI_API_KEY = os.getenv("GOOGLE_GENAI_API_KEY", "").strip()
GOOGLE_GENAI_MODEL = "gemini-3.1-flash-lite"

# 业务解耦模型设置 (可被环境变量覆写)
TITLE_MODEL = os.getenv("TITLE_MODEL", DEEPSEEK_MODEL)             
ARTICLE_MODEL = os.getenv("ARTICLE_MODEL", DEEPSEEK_MODEL)           

# 4. 四级兜底通道: OpenRouter (所有通道失败后最终兜底)
FALLBACK_API_KEY = OPENROUTER_API_KEY
FALLBACK_API_URL = "https://openrouter.ai/api/v1/chat/completions"
FALLBACK_MODEL = "deepseek/deepseek-v4-flash"

# 兼容旧代码变量调用
LLM_API_KEY = MIMO_API_KEY
LLM_API_URL = MIMO_API_URL
LLM_MODEL = MIMO_MODEL

# 飞书配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
FEISHU_BASE_ID = os.getenv("FEISHU_BASE_ID", "").strip()
FEISHU_TABLE_ID = "cms" # Mapped to Google Worksheet Name
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "").strip()

# Google Sheets Configuration
GOOGLE_CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "service_account.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_BACKUP_ID = os.getenv("GOOGLE_SHEET_BACKUP_ID", "").strip()
GOOGLE_WORKSHEET_NAME = "cms" # Default

# 社交媒体平台配置 (矩阵系统)
SOCIAL_PLATFORMS = {
    "douyin": {
        "name": "抖音",
        "type": "article", # User requested Article
        "sheet_name": "douyin",
        "title_limit": 18,
        "content_limit": 900,
        "keywords_limit": 4,
        "daily_target": int(os.getenv("DOUYIN_DAILY_TARGET") or 15)
    },
    "wechat_video": {
        "name": "微信视频",
        "type": "article", # User requested Article
        "sheet_name": "wechat_video",
        "title_limit": 18,
        "content_limit": 900,
        "keywords_limit": 4,
        "daily_target": int(os.getenv("WECHAT_VIDEO_DAILY_TARGET") or 12)
    },
    "xhs": {
        "name": "小红书",
        "type": "note",
        "sheet_name": "xhs",
        "title_limit": 18,
        "content_limit": 900,
        "keywords_limit": 4,
        "daily_target": int(os.getenv("XHS_DAILY_TARGET") or 15)
    },
    "kuaishou": {
        "name": "快手",
        "type": "article", # User requested Article
        "sheet_name": "kuaishou",
        "title_limit": 18,
        "content_limit": 400, # 短快
        "keywords_limit": 4,
        "daily_target": int(os.getenv("KUAISHOU_DAILY_TARGET") or 15)
    },
    "baijiahao": {
        "name": "百家号",
        "type": "article",
        "sheet_name": "baijiahao",
        "title_limit": 18,
        "content_limit": 900,
        "keywords_limit": 1, # 只要一个精准词
        "daily_target": int(os.getenv("BAIJIAHAO_DAILY_TARGET") or 15)
    },
    "weibo": {
        "name": "微博",
        "type": "microblog",
        "sheet_name": "weibo",
        "title_limit": 18, # 微博其实没标题，这里指第一句
        "content_limit": 900,
        "keywords_limit": 4,
        "daily_target": int(os.getenv("WEIBO_DAILY_TARGET") or 15)
    },
    "bilibili": {
        "name": "BILIBILI",
        "type": "article", # User requested Article
        "sheet_name": "bilibili",
        "title_limit": 18,
        "content_limit": 900,
        "keywords_limit": 10, # B站tag多
        "daily_target": int(os.getenv("BILIBILI_DAILY_TARGET") or 6)
    }
}
# 旧配置兼容
FEISHU_XHS_TABLE_ID = "xhs"
MAX_DAILY_XHS = 12 # Default fallback

# WellCMS 配置
WELLCMS_USERNAME = os.getenv("WELLCMS_USERNAME", "")
WELLCMS_PASSWORD = os.getenv("WELLCMS_PASSWORD", "")
WELLCMS_LOGIN_URL = os.getenv("WELLCMS_LOGIN_URL", "")
WELLCMS_ADMIN_URL = os.getenv("WELLCMS_ADMIN_URL", "")
WELLCMS_POST_URL = os.getenv("WELLCMS_POST_URL", "")

# 配置文件
CONFIG_FILE = os.path.join(PROJECT_ROOT, "box_artist_config.json")

# 分类映射
CATEGORY_MAP = {
    "专业知识": "1",
    "行业资讯": "2",
    "产品介绍": "3"
}

# 状态常量 (按节点流转)
STATUS_PRIORITY = "Priority"   # 特权插队: 用于人工指定的外部词条
STATUS_READY = "Ready"         # 节点1完成: 标题已生成，等待文章生成
STATUS_PENDING = "Pending"     # 节点2完成: 文章已生成，等待发布
STATUS_TOP_PRIORITY_PENDING = "Top priority" # 节点2完成: Priority文章已生成，最高优先级等待发布
STATUS_PUBLISHED = "Published" # 节点3完成: 已发布
# STATUS_GENERATED 已废弃，合并入 STATUS_PENDING

# 核心业务策略配置
STEP2_STRATEGY = {
    "max_generate_total": 120,   # 单次最大处理数量回调至安全区间(原9999)
    "wait_time_min": 1.5,      # 生成后最少等待时间(秒)，极限压缩
    "wait_time_max": 2.5       # 生成后最大等待时间(秒)，极限压缩
}

# 每分类最大处理数量
MAX_PUBLISH_PER_CATEGORY = int(os.getenv("MAX_PUBLISH_PER_CATEGORY", "50"))      # 节点3: RPA 发布

# 发布配置文件路径
PUBLISH_CONFIG_FILE = os.path.join(PROJECT_ROOT, "publish_config.json")

# Pollinations AI Configuration (多 Key 负载均衡)
# 从环境变量读取，逗号分隔多个 Key
_pollinations_keys_str = os.getenv("POLLINATIONS_API_KEYS", "")
POLLINATIONS_API_KEYS = [k.strip() for k in _pollinations_keys_str.split(",") if k.strip()]
# 兼容旧代码：取第一个 Key
POLLINATIONS_API_KEY = POLLINATIONS_API_KEYS[0] if POLLINATIONS_API_KEYS else ""
POLLINATIONS_USE_ANONYMOUS_FIRST = True  # 优先使用匿名模式（省额度）
POLLINATIONS_ANONYMOUS_INTERVAL = 6      # 匿名模式请求间隔（秒）

# 图库 API Configuration (Fallback 服务)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
