# step3_publish/wellcms_rpa.py
"""
WellCMS API 发布器 (Pure HTTP 极速重构版)
完全脱离 Playwright，使用 requests 进行毫秒级原生接口发布
"""
import sys
import os
import time
import logging
import requests
import hashlib
import json
import re

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from typing import Dict, Tuple, Optional
from shared import config

# 配置 logger
logger = logging.getLogger(__name__)

def get_md5(text: str) -> str:
    """获取字符串的 MD5，用于适配前台密码加密策略"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

class WellCMSPublisher:
    """WellCMS 极速 HTTP 发布引擎"""
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username or config.WELLCMS_USERNAME
        self.password = password or config.WELLCMS_PASSWORD
        self.login_url = config.WELLCMS_LOGIN_URL
        self.admin_url = config.WELLCMS_ADMIN_URL
        self.post_url = config.WELLCMS_POST_URL
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://heyijiapack.com",
            "Referer": "https://heyijiapack.com/news/"
        })
        self.is_logged_in = False
    
    def open_session(self) -> bool:
        """纯 HTTP 原生接口登录"""
        if self.is_logged_in:
            return True
            
        logger.info(f"🔐 [HTTP Engine] 开始网络直连登录: {self.username}")
        try:
            # 1. 前台登录获取会话
            login_data = {"email": self.username, "password": get_md5(self.password)}
            r1 = self.session.post("https://heyijiapack.com/news/user-login.html", data=login_data, timeout=10)
            
            if r1.status_code != 200 or '"code":"password"' in r1.text:
                logger.error(f"❌ 前台登录失败: {r1.text}")
                return False
                
            # 2. 后台验证获取权限
            self.session.headers["Referer"] = self.admin_url
            r2 = self.session.post(self.admin_url, data={"password": get_md5(self.password)}, timeout=10)
            
            if r2.status_code == 200 and '"code":0' in r2.text:
                self.is_logged_in = True
                logger.info("✅ [HTTP Engine] 登录大捷！拿到服务器 Cookie，耗时 < 1秒。")
                return True
                
            logger.error(f"❌ 后台验证失败: {r2.text}")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"💥 [HTTP Engine] 网络请求异常: {e}")
            return False
    
    def close_session(self):
        """关闭 HTTP 会话池"""
        self.session.close()
        self.is_logged_in = False
        logger.info("🔌 [HTTP Engine] 会话已关闭")
        
    def _publish_article(self, article: Dict) -> Tuple[bool, str]:
        """纯 HTTP 原生极速发文流程"""
        if not self.is_logged_in:
            if not self.open_session():
                return False, ""
                
        logger.info(f"🚀 [HTTP Engine] 开始推送: {article.get('title', '')}")
        
        # 1. 解析基础数据
        category_mapping = {"专业知识": "1", "行业资讯": "2", "产品介绍": "3"}
        category_id = category_mapping.get(article.get('category_id'), "1")
        if article.get('category_id') in ["1", "2", "3"]:
            category_id = article.get('category_id')
            
        post_url = f"https://heyijiapack.com/news/admin/index.php?0=content&1=create&fid={category_id}"
        
        # 过滤 Emoji 防止 MySQL 截断
        html_content = article.get('html_content', '')
        html_content = "".join(c for c in html_content if ord(c) <= 65535)
        
        # 2. 尝试提取图片 (沿用之前的辅助方法，这里为了代码整洁直接使用正则表达式提取正文图片，或者通过 fallback 获取)
        image_content = None
        img_match = re.search(r'<img[^>]+src="([^">]+)"', html_content)
        if img_match:
            img_url = img_match.group(1).replace('&amp;', '&')
            if "pollinations" not in img_url.lower():
                try:
                    logger.info(f"📥 正在下载正文图片作为封面: {img_url[:60]}...")
                    resp = requests.get(img_url, headers={"User-Agent": self.session.headers["User-Agent"]}, timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 10240:
                        image_content = resp.content
                except Exception as e:
                    logger.warning(f"下载正文图片失败: {e}")
                    
        # 3. 构建多部分表单 (Multipart Form-Data)
        data_payload = {
            "fid": category_id,
            "subject": article.get('title', ''),
            "brief": article.get('summary', ''),
            "keyword": article.get('keywords', ''),
            "description": article.get('description', ''),
            "tags": article.get('tags', article.get('keywords', '')),
            "message": html_content,
            "submit": "1"
        }
        
        files_payload = None
        if image_content:
            logger.info("🖼️ 附带封面图数据上传...")
            files_payload = {'img_1': ('cover.jpg', image_content, 'image/jpeg')}
            
        # 4. 执行 POST 极速注入
        try:
            logger.info(f"⚡ 发起 POST 请求至: {post_url}")
            # 注意：使用 files 会自动将 Content-Type 转为 multipart/form-data
            if files_payload:
                response = self.session.post(post_url, data=data_payload, files=files_payload, timeout=15)
            else:
                response = self.session.post(post_url, data=data_payload, timeout=15)
                
            if response.status_code == 200:
                logger.info("✅ 响应成功，正在解析真实 URL...")
                # 5. URL 修正逻辑 (修复 "Same Link" Bug)
                list_url = f"{self.admin_url}?0=content&1=list"
                r_list = self.session.get(list_url, timeout=10)
                
                tid = None
                # 正则解析后台列表页，寻找最新发表的 tid
                # 例如：data-tid="123" 或 href="...tid=123"
                match = re.search(r'data-tid="(\d+)"', r_list.text)
                if match:
                    tid = match.group(1)
                else:
                    match = re.search(r'tid=(\d+)', r_list.text)
                    if match:
                        tid = match.group(1)
                        
                if tid:
                    current_url = f"https://heyijiapack.com/news/read-{tid}.html"
                    logger.info(f"🔗 提取文章链接成功: {current_url}")
                else:
                    current_url = "https://heyijiapack.com/news/published_success_please_check"
                    logger.warning("⚠️ 未能提取 TID，返回通用成功链接。")
                    
                return True, current_url
            else:
                logger.error(f"❌ 发布失败，HTTP 状态码: {response.status_code}")
                return False, ""
                
        except Exception as e:
            logger.error(f"❌ 极速发布流程异常: {e}")
            return False, ""

    def publish(self, article: Dict) -> Tuple[bool, str]:
        """独立发布文章 (建立连接 -> 发送 -> 关闭连接)"""
        try:
            if not self.open_session():
                return False, ""
            return self._publish_article(article)
        finally:
            self.close_session()

    def publish_in_session(self, article: Dict) -> Tuple[bool, str]:
        """在已打开的 Session 中连续发布文章"""
        return self._publish_article(article)
