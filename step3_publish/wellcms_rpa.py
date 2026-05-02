# step3_publish/wellcms_rpa.py
"""
WellCMS RPA 发布器
使用 Playwright (Sync) 自动登录并发布文章
"""
import sys
import os
import time
import logging

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from typing import Dict, Tuple, Optional
from playwright.sync_api import sync_playwright, Page, Browser
from shared import config

# 配置 logger
logger = logging.getLogger(__name__)


class WellCMSPublisher:
    """WellCMS RPA 发布器 (同步版)"""
    
    def __init__(self, username: str = None, password: str = None):
        """
        初始化发布器
        
        Args:
            username: CMS 用户名 (不传则使用 config 默认值)
            password: CMS 密码 (不传则使用 config 默认值)
        """
        self.username = username or config.WELLCMS_USERNAME
        self.password = password or config.WELLCMS_PASSWORD
        self.login_url = config.WELLCMS_LOGIN_URL
        self.admin_url = config.WELLCMS_ADMIN_URL
        self.post_url = config.WELLCMS_POST_URL
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    def _init_browser(self):
        """初始化浏览器"""
        self.playwright = sync_playwright().start()
        # 支持通过环境变量控制 Headless (方便本地调试)
        is_headless = os.getenv("HEADLESS", "true").lower() == "true"
        
        # 增加防检测参数
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-size=1920,1080",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        self.browser = self.playwright.chromium.launch(
            headless=is_headless,
            args=args
        )
        
        # 使用特定 UserAgent 和 Viewport 创建 Context
        context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai"
        )
        # 注入 stealth js
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = context.new_page()
    
    def _close_browser(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def _safe_goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000, retries: int = 3) -> bool:
        """
        安全的页面导航，统一处理 ERR_ABORTED 等网络问题
        
        Args:
            url: 目标 URL
            wait_until: 等待策略 (domcontentloaded 比 networkidle 更稳定)
            timeout: 超时时间 (毫秒)
            retries: 重试次数
        
        Returns:
            是否成功导航
        """
        for attempt in range(retries + 1):
            try:
                self.page.goto(url, wait_until=wait_until, timeout=timeout)
                time.sleep(1)  # 等待页面稳定 (优化)
                return True
            except Exception as e:
                error_msg = str(e)
                print(f"      ⚠️ 导航失败 ({attempt + 1}/{retries + 1}): {error_msg[:100]}")
                
                # 检查是否已在目标页面 (精确匹配完整 URL)
                current_url = self.page.url
                # 移除末尾斜杠进行比较
                if current_url.rstrip('/') == url.rstrip('/'):
                    print(f"      ℹ️ 已在目标页面，继续执行")
                    return True
                
                # 最后一次重试也失败了
                if attempt >= retries:
                    print(f"      ❌ 导航最终失败，当前页面: {current_url}")
                    return False
                
                # 在重试前等待更长时间 (网络可能有波动)
                wait_time = 3 + attempt * 2  # 3s, 5s, 7s...
                print(f"      ⏳ 等待 {wait_time}s 后重试...")
                time.sleep(wait_time)
        
        return False
    
    def _login(self) -> bool:
        """
        登录 WellCMS (基于用户提供的精确 Selector)
        Step 1: https://heyijiapack.com/news/user-login.html
        Step 2: https://heyijiapack.com/news/admin/index.php
        """
        logger.info("[RPA] 启动精确匹配登录流程...")
        try:
            # ==================================================================
            # Step 1: 前台登录
            # ==================================================================
            logger.info(f"[Step 1] 访问前台: {self.login_url}")
            if not self._safe_goto(self.login_url):
                return False
            
            try:
                # 检查 #email 是否存在
                if self.page.wait_for_selector('#email', state="visible", timeout=5000):
                    print("      👀 [Step 1] 填写账号密码...")
                    # 用户提供的 Selector: #email, #password
                    self.page.fill('#email', self.username)
                    self.page.fill('#password', self.password)
                    
                    print("      🖱️ [Step 1] 点击登录并等待路由导航完成...")
                    try:
                        # 采用原子级的上下文绑定：预期会发生一次导航跳转
                        # wait_until="domcontentloaded" 速度最快，只要 DOM 树出来就算成功，不管外链图片和统计代码死活
                        with self.page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                            self.page.click('button.btn-primary#submit')
                    except Exception as e:
                        # 兼容处理：有可能刚点下去还没跳，就已经算是成功了 (SPA框架特性)
                        print(f"      ℹ️ [Step 1] 导航监听结束或超时，继续向下校验状态: {e}")
                else:
                    print("      ℹ️ [Step 1] 未检测到输入框，可能已登录")
            except Exception as e:
                print(f"      ⚠️ [Step 1] 异常: {e}")

            # ==================================================================
            # Step 2: 后台二次验证
            # ==================================================================
            time.sleep(2)  # 等待登录跳转完成
            
            print(f"      📍 [Step 2] 强制访问后台: {self.admin_url}")
            self._safe_goto(self.admin_url)
            
            # 检查是否被踢回
            if "user-login" in self.page.url:
                 print(f"      ❌ [Step 2] 失败: 被重定向回前台登录页 ({self.page.url})")
                 return False

            try:
                # 页面包含: <input id="password"> 和 <button id="submit">
                # 注意: 这里 input id 也是 password，所以要确保是在 admin 页面下
                if self.page.wait_for_selector('input#password', state="visible", timeout=3000):
                    print("      🔐 [Step 2] 填写后台密码...")
                    self.page.fill('input#password', self.password)
                    
                    print("      🖱️ [Step 2] 点击后台登录按钮 (button.btn-danger)...")
                    # 后台登录按钮是 btn-danger 类，不是 btn-primary
                    # <button class="btn btn-block btn-danger shadow" id="submit">
                    self.page.click('button.btn-danger#submit')
                    
                    print("      🔄 [Step 2] 等待跳转...")
                    self.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as e:
                 print(f"      ℹ️ [Step 2] 无需二次验证或异常: {e}")

            # ==================================================================
            # 结果检查
            # ==================================================================
            current_url = self.page.url
            if "operate-search" in current_url:
                 print(f"      ❌ [Result] 误触搜索页 ({current_url})")
                 return False
                 
            if "admin" in current_url and "login" not in current_url:
                print("      ✅ [Result] 登录成功")
                time.sleep(2)  # 等待 session 完全建立 (优化)
                return True
            else:
                print(f"      ❌ [Result] 登录失败 ({current_url})")
                return False
                
        except Exception as e:
            print(f"      ❌ 登录流程异常终止: {e}")
            return False
    
    def _publish_article(self, article: Dict) -> Tuple[bool, str]:
        """发布文章"""
        try:
            # 导航到发布页面 (增加等待确保后台登录 session 稳定)
            time.sleep(1)  # (优化)
            if not self._safe_goto(self.post_url):
                return False, ""
            time.sleep(1)  # 等待页面完全加载 (优化)
            
            # 填写标题
            # 填写标题
            try:
                self.page.fill('#subject', article.get('title', ''), timeout=30000)
            except Exception as e:
                print(f"      ❌ 填写标题失败: {e}")
                print(f"      📄 当前页面: {self.page.title()}")
                print(f"      🔗 当前URL: {self.page.url}")
                # 尝试保存截图 (CI/CD Artifacts 无法直接看，但本地调试有用)
                try: 
                    self.page.screenshot(path="error_publish_fail.png") 
                except: pass
                raise e
            
            # 选择分类
            # 根据用户配置: 专业知识=1, 行业资讯=2, 产品介绍=3
            # 默认发布页现在是: fid=0 (用户更新)
            category_mapping = {
                "专业知识": "1",
                "行业资讯": "2",
                "产品介绍": "3"
            }
            category_id = category_mapping.get(article.get('category_id'), "0") # 默认为 0
            
            # 如果 category_id 在 map 里没找到，尝试用 article 从上游传来的原始值
            if category_id == "0" and article.get('category_id') in ["1", "2", "3"]:
                category_id = article.get('category_id')

            try:
                self.page.select_option('select[name="fid"]', category_id)
                print(f"      📂 已选择分类 ID: {category_id}")
            except Exception:
                print(f"      ⚠️ 选择分类失败 (ID: {category_id})")
            
            time.sleep(0.5)  # (优化)
            
            # -------------------------------------------------------------------
            # 🖼️ 封面图处理 (多源 Fallback 机制)
            # -------------------------------------------------------------------
            html_content = article.get('html_content', '')
            import re
            import random as rand_module
            # 改进正则：只匹配 <img ... src="..."> 避免匹配到 script 或 iframe
            img_match = re.search(r'<img[^>]+src="([^">]+)"', html_content)
            
            def _get_random_pollinations_key() -> str:
                """随机选择一个 Pollinations API Key (负载均衡)"""
                keys = getattr(config, 'POLLINATIONS_API_KEYS', [])
                if keys:
                    selected = rand_module.choice(keys)
                    logger.debug(f"🔄 选择 Pollinations Key: {selected[:8]}...")
                    return selected
                return config.POLLINATIONS_API_KEY  # 兼容旧配置
            
            # Fallback 图片源列表
            def _get_unsplash_cover(keywords: str) -> str:
                """生成 Unsplash Source 备选图片 URL"""
                search_terms = ["packaging", "gift", "box", "design"]
                if keywords:
                    for kw in ["packaging", "box", "paper", "gift", "luxury", "minimal"]:
                        if kw in keywords.lower():
                            search_terms.insert(0, kw)
                            break
                query = ",".join(search_terms[:2])
                return f"https://source.unsplash.com/1024x768/?{query}"
            
            def _get_pexels_cover(keywords: str) -> tuple:
                """从 Pexels 获取图片 (需要 API Key，免费 200次/小时)"""
                import requests
                # Pexels API Key (免费申请)
                PEXELS_API_KEY = config.PEXELS_API_KEY
                if not PEXELS_API_KEY:
                    return None, False
                
                search_query = "packaging box" if not keywords else keywords.split(",")[0].strip()
                headers = {"Authorization": PEXELS_API_KEY}
                
                try:
                    resp = requests.get(
                        f"https://api.pexels.com/v1/search?query={search_query}&per_page=1&size=large",
                        headers=headers,
                        timeout=15
                    )
                    if resp.status_code == 200:
                        photos = resp.json().get("photos", [])
                        if photos:
                            img_url = photos[0].get("src", {}).get("large", "")
                            if img_url:
                                # 下载图片
                                img_resp = requests.get(img_url, timeout=20)
                                if img_resp.status_code == 200 and len(img_resp.content) >= 10 * 1024:
                                    return img_resp.content, True
                except Exception as e:
                    logger.debug(f"Pexels 获取失败: {e}")
                return None, False
            
            def _get_pixabay_cover(keywords: str) -> tuple:
                """从 Pixabay 获取图片 (需要 API Key，免费 5000次/小时)"""
                import requests
                # Pixabay API Key (免费申请)
                PIXABAY_API_KEY = config.PIXABAY_API_KEY
                if not PIXABAY_API_KEY:
                    return None, False
                
                search_query = "packaging box" if not keywords else keywords.split(",")[0].strip()
                
                try:
                    resp = requests.get(
                        f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={search_query}&image_type=photo&per_page=3",
                        timeout=15
                    )
                    if resp.status_code == 200:
                        hits = resp.json().get("hits", [])
                        if hits:
                            img_url = hits[0].get("largeImageURL", "")
                            if img_url:
                                img_resp = requests.get(img_url, timeout=20)
                                if img_resp.status_code == 200 and len(img_resp.content) >= 10 * 1024:
                                    return img_resp.content, True
                except Exception as e:
                    logger.debug(f"Pixabay 获取失败: {e}")
                return None, False
            
            def _generate_ai_horde_image(prompt: str, timeout: int = 60) -> tuple:
                """
                使用 AI Horde (开源众包) 生成 AI 图片
                https://stablehorde.net/ - 免费、无需注册
                """
                import requests
                import json as json_lib
                
                # AI Horde API (匿名访问使用 0000000000 作为 API Key)
                API_KEY = "0000000000"
                GENERATE_URL = "https://stablehorde.net/api/v2/generate/async"
                CHECK_URL = "https://stablehorde.net/api/v2/generate/check/"
                STATUS_URL = "https://stablehorde.net/api/v2/generate/status/"
                
                headers = {
                    "Content-Type": "application/json",
                    "apikey": API_KEY
                }
                
                # 简化 prompt 用于快速生成
                payload = {
                    "prompt": f"{prompt}, product photography, studio lighting, minimalist style",
                    "params": {
                        "width": 1024,
                        "height": 768,
                        "steps": 20,
                        "n": 1
                    },
                    "nsfw": False,
                    "models": ["stable_diffusion"]
                }
                
                try:
                    # 1. 提交生成请求
                    resp = requests.post(GENERATE_URL, headers=headers, json=payload, timeout=15)
                    if resp.status_code != 202:
                        logger.debug(f"AI Horde 提交失败: {resp.status_code}")
                        return None, False
                    
                    job_id = resp.json().get("id")
                    if not job_id:
                        return None, False
                    
                    # 2. 轮询等待完成 (最多等待 timeout 秒)
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        check_resp = requests.get(f"{CHECK_URL}{job_id}", timeout=10)
                        if check_resp.status_code == 200:
                            data = check_resp.json()
                            if data.get("done"):
                                break
                            if data.get("faulted"):
                                logger.debug("AI Horde 生成失败")
                                return None, False
                        time.sleep(3)
                    else:
                        logger.debug("AI Horde 生成超时")
                        return None, False
                    
                    # 3. 获取结果
                    status_resp = requests.get(f"{STATUS_URL}{job_id}", timeout=10)
                    if status_resp.status_code == 200:
                        generations = status_resp.json().get("generations", [])
                        if generations and generations[0].get("img"):
                            # AI Horde 返回 base64 编码的图片
                            import base64
                            img_data = base64.b64decode(generations[0]["img"])
                            if len(img_data) >= 10 * 1024:
                                return img_data, True
                    
                except Exception as e:
                    logger.debug(f"AI Horde 异常: {e}")
                
                return None, False
            
            def _load_blacklist() -> set:
                """从文件加载黑名单，支持热更新"""
                import json
                blacklist_file = os.path.join(PROJECT_ROOT, "config", "rate_limit_image_blacklist.json")
                try:
                    with open(blacklist_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return set(data.get("blacklist", [])) | set(data.get("auto_learned", []))
                except FileNotFoundError:
                    logger.warning("黑名单文件不存在，使用默认值")
                    return {"12aff62f69f5c0a5798c6f2d15dfa3c1", "694684906bafe9aec36a70ca08e8c1a7"}
                except Exception as e:
                    logger.error(f"加载黑名单失败: {e}，使用默认值")
                    return {"12aff62f69f5c0a5798c6f2d15dfa3c1", "694684906bafe9aec36a70ca08e8c1a7"}

            def _auto_learn_hash(hash_value: str):
                """将新发现的限流图 MD5 自动加入黑名单"""
                import json
                from datetime import datetime
                blacklist_file = os.path.join(PROJECT_ROOT, "config", "rate_limit_image_blacklist.json")
                try:
                    with open(blacklist_file, 'r+', encoding='utf-8') as f:
                        data = json.load(f)
                        if hash_value not in data.get("auto_learned", []):
                            data.setdefault("auto_learned", []).append(hash_value)
                            data["updated_at"] = datetime.now().isoformat()
                            f.seek(0)
                            json.dump(data, f, indent=2, ensure_ascii=False)
                            f.truncate()
                            logger.info(f"✅ 自动学习: 已添加 MD5 {hash_value} 到黑名单")
                except Exception as e:
                    logger.error(f"自动学习失败: {e}")

            def _download_image(url: str, timeout: int = 30) -> tuple:
                """下载图片，返回 (content, is_valid)"""
                import requests
                import hashlib
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
                MIN_VALID_SIZE = 10 * 1024  # 10KB
                # 基于已知限流图的精确尺寸范围
                SUSPICIOUS_SIZE_MIN = 45000  # 45KB
                SUSPICIOUS_SIZE_MAX = 55000  # 55KB
                
                # 🚀 Pollinations AI 生成图片需要更长超时
                is_ai_gen = "pollinations" in url.lower()
                effective_timeout = 45 if is_ai_gen else timeout
                if is_ai_gen:
                    logger.info(f"📥 [AI图片] 开始下载: {url[:80]}... (超时: {effective_timeout}s)")
                else:
                    logger.info(f"📥 开始下载图片: {url[:80]}...")
                
                for retry in range(3):
                    try:
                        resp = requests.get(url, headers=headers, timeout=effective_timeout, allow_redirects=True)
                        if resp.status_code == 200 and len(resp.content) >= MIN_VALID_SIZE:
                            # 🔍 多策略检测限流图
                            content_hash = hashlib.md5(resp.content).hexdigest()
                            content_size = len(resp.content)

                            if "pollinations" in url:
                                # 策略 1: MD5 黑名单检测（最可靠）
                                blacklist = _load_blacklist()
                                if content_hash in blacklist:
                                    mode = "认证模式" if "key=" in url else "匿名模式"
                                    logger.warning(f"🛡️ 黑名单拦截 [{mode}]: MD5 {content_hash}")
                                    return None, False

                                # 策略 2: 启发式规则 - 尺寸模式检测（辅助，仅记录可疑）
                                if SUSPICIOUS_SIZE_MIN <= content_size <= SUSPICIOUS_SIZE_MAX:
                                    mode = "认证模式" if "key=" in url else "匿名模式"
                                    logger.info(f"⚠️  可疑尺寸 [{mode}]: Size={content_size}B, MD5={content_hash}")
                                    logger.info(f"   如确认为限流图，请手动添加 MD5 到黑名单")
                                    # 不自动拦截，避免误杀正常图片

                                # 调试日志（用于未来分析）
                                mode = "认证" if "key=" in url else "匿名"
                                logger.debug(f"[Image Check] Mode: {mode} | MD5: {content_hash} | Size: {content_size}B")

                            logger.info(f"✅ 图片下载成功: {content_size//1024}KB, MD5={content_hash[:8]}...")
                            return resp.content, True
                        elif resp.status_code == 200:
                            logger.warning(f"❌ 图片太小 ({len(resp.content)} bytes)，可能是限流图")
                            return None, False
                    except requests.exceptions.Timeout:
                        if retry < 2:
                            logger.warning(f"⏳ 下载超时，重试 {retry + 1}/3... (timeout={effective_timeout}s)")
                            time.sleep(3)  # 增加重试间隔
                        else:
                            logger.error(f"❌ 下载超时 (已重试3次, timeout={effective_timeout}s)")
                    except Exception as e:
                        logger.warning(f"❌ 下载异常: {e}")
                        break
                return None, False

            
            
            # 初始化变量
            image_content = None
            source_name = ""
            
            # 1. 优先尝试从文章正文中提取图片（跳过 Pollinations，因为生成太慢）
            if img_match:
                img_url = img_match.group(1)
                img_url = img_url.replace('&amp;', '&')
                
                # 🚀 短期优化：跳过 Pollinations 图片，因为 AI 生成太慢容易超时
                if "pollinations" in img_url.lower():
                    logger.info(f"⏭️ 跳过 Pollinations 图片 (生成太慢)，使用快速图库")
                else:
                    logger.info(f"🖼️ 发现正文图片，尝试作为封面: {img_url[:80]}...")
                    try:
                        # 尝试下载正文图片
                        image_content, is_valid = _download_image(img_url)
                        
                        if is_valid:
                            source_name = "Article Content Image"
                        else:
                            logger.warning(f"⚠️ 正文图片下载失败或无效")
                            
                    except Exception as e:
                        logger.warning(f"❌ 下载正文图片异常: {e}")

            try:
                import tempfile
                
                if not image_content:
                    logger.info("未获取到正文图片，开始尝试 Fallback 图库...")

                # ================================================================
                # 🔄 Fallback 策略 (优化顺序：快速图库优先，Pollinations 最后)
                # 优先级: Pexels → Pixabay → Unsplash → Pollinations
                # ================================================================
                
                keywords = article.get('keywords', 'packaging box')
                
                # 方案 1: Pexels (速度快，1-3秒)
                if not image_content:
                    logger.info("[Fallback 1] 尝试 Pexels (快速图库)...")
                    image_content, is_valid = _get_pexels_cover(keywords)
                    if is_valid:
                        source_name = "Pexels"
                
                # 方案 2: Pixabay (速度快，1-3秒)
                if not image_content:
                    logger.info("[Fallback 2] 尝试 Pixabay (快速图库)...")
                    image_content, is_valid = _get_pixabay_cover(keywords)
                    if is_valid:
                        source_name = "Pixabay"
                
                # 方案 3: Unsplash (CDN，较快)
                if not image_content:
                    logger.info("[Fallback 3] 尝试 Unsplash...")
                    fallback_url = _get_unsplash_cover(article.get('keywords', ''))
                    image_content, is_valid = _download_image(fallback_url, timeout=15)
                    if is_valid:
                        source_name = "Unsplash"
                
                # 方案 4: Pollinations AI 生成 (最慢，作为最后备选)
                if not image_content:
                    import urllib.parse
                    prompt = keywords
                    logger.info(f"[Fallback 4] 最后尝试 Pollinations AI 生成 (Prompt: {prompt})...")
                    
                    encoded_prompt = urllib.parse.quote(prompt)
                    poll_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=384"  # 降低分辨率加速
                    
                    # 只尝试认证模式（更稳定）
                    auth_url = f"{poll_url}&key={_get_random_pollinations_key()}"
                    image_content, is_valid = _download_image(auth_url)
                    if is_valid:
                        source_name = "Pollinations (Last Resort)"
                    else:
                        logger.warning("[Pollinations] 生成失败，文章将无封面发布")
                
                # 上传图片
                if image_content:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        tmp.write(image_content)
                        tmp.flush()
                        tmp_path = tmp.name
                        
                        file_input = self.page.query_selector('input[data-assoc="img_1"]')
                        if file_input:
                            file_input.set_input_files(tmp_path)
                            logger.info(f"封面图上传成功 [{source_name}] ({len(image_content) // 1024}KB)")
                            time.sleep(2)  # (优化)
                        else:
                            logger.warning("未找到封面图上传框")
                        
                        # 清理临时文件
                        try:
                            os.unlink(tmp_path)
                        except Exception as e:
                            logger.debug(f"清理临时文件失败: {e}")
                else:
                    logger.warning("所有图片源均失败，文章将无封面发布")
                    
            except Exception as e:
                logger.error(f"封面图逻辑错误: {e}")
            # -------------------------------------------------------------------
            
            # ===================================================================
            # ⚡ 极速 JS 注入模式 (B计划)
            # ===================================================================
            html_content = article.get('html_content', '')
            
            # 🚨 过滤掉所有 4字节字符 (Emoji) 防止 MySQL 截断
            html_content = "".join(c for c in html_content if ord(c) <= 65535)
            
            form_data = {
                "brief": article.get('summary', ''),
                "keyword": article.get('keywords', ''),
                "description": article.get('description', ''),
                "tags": article.get('tags', article.get('keywords', '')),
                "message": html_content
            }
            
            print("      ⚡ 启动底层 JS 极速数据注入...")
            
            self.page.evaluate('''((data) => {
                const setVal = (sel, val) => {
                    const el = document.querySelector(sel);
                    if (el && val) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                };
                
                setVal('textarea[name="brief"]', data.brief);
                setVal('input[name="keyword"]', data.keyword);
                setVal('textarea[name="description"]', data.description);
                
                ['#tags', '#tag', 'input[name="tags"]', 'input[name="tag"]'].forEach(sel => {
                    setVal(sel, data.tags);
                });
                
                const closedBox = document.querySelector('#closed-box');
                if (closedBox && !closedBox.checked) {
                    closedBox.click();
                }
                
                const messageHtml = data.message;
                const msgArea = document.querySelector('textarea[name="message"]');
                if (msgArea) msgArea.value = messageHtml;
                
                if (typeof UM !== 'undefined' && UM.getEditor('message')) {
                    UM.getEditor('message').setContent(messageHtml);
                } else if (typeof UE !== 'undefined' && UE.getEditor('message')) {
                    UE.getEditor('message').setContent(messageHtml);
                } else {
                    for (let key in window) {
                        if (window[key] && window[key].key === 'message' && window[key].setContent) {
                            window[key].setContent(messageHtml);
                            break;
                        }
                    }
                }
            })''', form_data)
            
            time.sleep(0.5)
            
            print("      🖱️ 极速触发提交事件...")
            try:
                with self.page.expect_navigation(timeout=30000):
                    self.page.evaluate("document.getElementById('submit').click();")
            except Exception as e:
                print(f"      ⚠️ 等待跳转超时或失败，尝试根据当前 URL 继续: {e}")
            
            # -------------------------------------------------------------------
            # 🔗 URL 修正逻辑 (修复 "Same Link" Bug)
            # -------------------------------------------------------------------
            # 原问题：发布后直接取 page.url，得到的是后台列表页地址
            # 解决方案：
            # 1. 提交后，自动跳转到列表页 (或手动跳转)
            # 2. 在列表页根据标题找到对应的行
            # 3. 提取 data-tid 或 href 中的 tid
            # 4. 拼接前台 URL
            
            print("      🔍 正在解析文章真实 URL...")
            time.sleep(1) # 等待列表页加载 (优化)
            
            # 确保在列表页 (content-list)
            # 无论之前是在哪，强制去一次内容管理页，确保能找到刚发的文章
            list_url = f"{self.admin_url}?0=content&1=list"
            # 重试机制提取 URL
            max_retries = 3
            tid = None
            
            for attempt in range(max_retries):
                if attempt > 0:
                     print(f"      🔄 尝试 {attempt + 1}/{max_retries}: 正在重试提取 TID...")

                try:
                    # 1. 强制刷新/跳转列表页
                    self._safe_goto(list_url)
                    
                    # 2. 显式等待表格加载 (尝试等待3秒)
                    try:
                         # 轮询检查是否有包含 data-tid 的行
                         for _ in range(3):
                             found = False
                             for frame in self.page.frames:
                                 if frame.locator("tr[data-tid]").count() > 0:
                                     found = True
                                     break
                             if found: break
                             time.sleep(1)
                    except:
                        pass

                    # 3. 遍历提取
                    frames = self.page.frames
                    print(f"      👀 页面共有 {len(frames)} 个 Frame, 正在查找内容表格...")
                    
                    for frame in frames:
                        rows = frame.locator("tr[data-tid]")
                        count = rows.count()
                        
                        if count > 0:
                            first_row = rows.first
                            tid_attr = first_row.get_attribute("data-tid")
                            if tid_attr:
                                tid = tid_attr
                                print(f"      ✅ [Strategy:Frame+FirstRow] 找到 TID: {tid}")
                                break
                            
                        # Fallback Link (兼容旧版/另一种渲染)
                        links = frame.locator("a[href*='tid=']").all()
                        for link in links[:5]:
                            href = link.get_attribute("href")
                            if href:
                                import re
                                match = re.search(r'tid=(\d+)', href)
                                if match:
                                    tid = match.group(1)
                                    print(f"      ✅ [Strategy:Link] 找到 TID: {tid}")
                                    break
                        if tid: break
                    
                    if tid:
                        break
                    else:
                         print("      ⚠️ 当前页面未找到 TID，等待后重试...")
                         time.sleep(2)

                except Exception as e:
                    print(f"      ⚠️ 提取过程异常: {e}")
                    time.sleep(2)
                
            # 构造最终 URL
            if tid:
                # 格式: https://heyijiapack.com/news/read-{tid}.html
                current_url = f"https://heyijiapack.com/news/read-{tid}.html"
            else:
                # 兜底
                print("      ⚠️ 未能提取 TID (遍历所有 Frame 后)，使用当前页面 URL")
                current_url = self.page.url
            
            logger.info(f"文章发布成功: {article.get('title', '')}")
            logger.info(f"链接: {current_url}")
            
            return True, current_url
            
        except Exception as e:
            logger.error(f"发布失败: {e}")
            return False, ""
    
    def publish(self, article: Dict) -> Tuple[bool, str]:
        """
        发布文章到 WellCMS (同步)
        Returns: (success, url)
        """
        try:
            self._init_browser()
            
            if not self._login():
                return False, ""
            
            return self._publish_article(article)
            
        finally:
            self._close_browser()
            
    def publish_sync(self, article: Dict) -> Tuple[bool, str]:
        """兼容旧接口"""
        return self.publish(article)

    # ================================================================
    # 会话复用接口: 同一账号多篇文章共享浏览器，减少登录开销
    # ================================================================
    def open_session(self) -> bool:
        """
        打开浏览器并登录，建立可复用的会话。
        成功返回 True，失败返回 False。
        调用方需在结束后调用 close_session()。
        """
        try:
            self._init_browser()
            if not self._login():
                self._close_browser()
                return False
            return True
        except Exception as e:
            logger.error(f"[Session] 打开会话失败: {e}")
            self._close_browser()
            return False

    def publish_in_session(self, article: Dict) -> Tuple[bool, str]:
        """
        在已打开的会话中发布单篇文章（不重新登录）。
        必须先调用 open_session() 且返回 True。
        """
        try:
            return self._publish_article(article)
        except Exception as e:
            logger.error(f"[Session] 会话内发布失败: {e}")
            return False, ""

    def close_session(self):
        """关闭浏览器会话"""
        self._close_browser()
