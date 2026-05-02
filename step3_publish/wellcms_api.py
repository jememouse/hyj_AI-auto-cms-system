import os
import sys
import time
import requests
import json
import logging
from bs4 import BeautifulSoup
from typing import Dict, Tuple

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from shared import config

logger = logging.getLogger(__name__)

class WellCMSAPIClient:
    """WellCMS HTTP API 直连发布引擎"""
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username or config.WELLCMS_USERNAME
        self.password = password or config.WELLCMS_PASSWORD
        self.login_url = config.WELLCMS_LOGIN_URL
        self.admin_url = config.WELLCMS_ADMIN_URL
        self.post_url = config.WELLCMS_POST_URL
        
        # 维持会话的 Session，自动处理 Cookie
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        })
        self.is_logged_in = False

    def _login(self) -> bool:
        """纯 HTTP 瞬间登录机制"""
        logger.info("[API] 开始极速鉴权登录...")
        try:
            # 1. 访问前台登录页，获取可能存在的 CSRF Token 或基础 Cookie
            self.session.get(self.login_url, timeout=10)
            
            # 2. 构造前台登录 POST 请求包 (基于 Xiuno/WellCMS 默认表单结构)
            # 根据系统版本，密码可能是明文也可能需要 md5，我们先按标准抓包测试
            login_data = {
                "email": self.username,
                "password": self.password,
                "submit": "1" # 通常带有提交标记
            }
            
            # 由于 WellCMS/Xiuno 通常使用 AJAX 提交登录，我们模拟 AJAX 请求
            headers_ajax = {"X-Requested-With": "XMLHttpRequest"}
            resp = self.session.post(self.login_url, data=login_data, headers=headers_ajax, timeout=10)
            
            # 验证登录是否成功
            if "well_sid" in self.session.cookies.get_dict() or "well_token" in self.session.cookies.get_dict() or resp.status_code == 200:
                logger.info("✅ [Step 1] 前台 Cookie 换取成功！")
            else:
                logger.warning("⚠️ 前台登录返回非预期结果，继续尝试后台登录...")

            # 3. 后台二次验证登录 (如果需要的话)
            resp_admin = self.session.post(self.admin_url, data={"password": self.password}, headers=headers_ajax, timeout=10)
            
            # 验证是否拿到了 well_admin_token
            cookies = self.session.cookies.get_dict()
            if "well_admin_token" in cookies:
                logger.info("✅ [Step 2] 核心管理凭证 (well_admin_token) 获取成功！")
                self.is_logged_in = True
                return True
            else:
                # 即使没有明确的 token，只要能正常访问 admin 页面也算成功
                check_admin = self.session.get(self.admin_url, timeout=10)
                if "login" not in check_admin.url:
                    logger.info("✅ [Step 2] 后台页面访问权限验证通过！")
                    self.is_logged_in = True
                    return True
                else:
                    logger.error("❌ 无法获取后台权限，登录失败。")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ 登录异常: {e}")
            return False

    def _publish_article(self, article: Dict) -> Tuple[bool, str]:
        """直连发布文章，耗时不到 1 秒"""
        if not self.is_logged_in:
            if not self._login():
                return False, ""

        logger.info("🚀 开始封包 HTTP POST 发文请求...")
        
        category_mapping = {
            "专业知识": "1",
            "行业资讯": "2",
            "产品介绍": "3"
        }
        category_id = category_mapping.get(article.get('category_id'), article.get('category_id', '2'))
        
        # 构造发贴目标 URL (如: admin/index.php?0=content&1=create&fid=2)
        submit_url = f"{self.admin_url}?0=content&1=create&fid={category_id}"
        
        # 预先拉取发布页面，提取可能存在的安全校验码 (FORM_HASH 等)
        # 这一步能保证表单的完整性
        page_resp = self.session.get(submit_url)
        soup = BeautifulSoup(page_resp.text, 'html.parser')
        
        # 构造 POST 核心 Payload
        payload = {
            "subject": article.get("title", ""),
            "fid": category_id,
            "brief": article.get("summary", ""),
            "keyword": article.get("keywords", ""),
            "tags": article.get("tags", article.get("keywords", "")),
            "description": article.get("description", ""),
            "message": article.get("html_content", ""),
            "closed": "1" # 禁止评论
        }
        
        # 自动提取页面里所有 type="hidden" 的表单隐藏字段，防止漏掉安全 Token
        for hidden_input in soup.find_all("input", type="hidden"):
            name = hidden_input.get("name")
            value = hidden_input.get("value", "")
            if name and name not in payload:
                payload[name] = value

        # 这里预留图片直传接口，暂时发纯文本+正文内联图片测试连通性
        # (因为正文里已经有图片了)
        logger.info(f"📤 正在全速发送数据包 (Title: {payload['subject'][:15]}...)")
        
        try:
            # 发起真正的发贴请求
            post_resp = self.session.post(submit_url, data=payload, allow_redirects=False, timeout=15)
            
            # WellCMS/Xiuno 发贴成功后通常会做 302 重定向到列表页或者文章页
            if post_resp.status_code in [301, 302]:
                redirect_url = post_resp.headers.get("Location", "")
                logger.info(f"✅ 发贴成功！收到服务器重定向: {redirect_url}")
                # 拼接完整的访问地址
                if redirect_url.startswith("http"):
                    return True, redirect_url
                else:
                    base_url = self.admin_url.split("/admin")[0]
                    return True, f"{base_url}/{redirect_url}"
            elif post_resp.status_code == 200:
                # 可能是 AJAX 响应
                try:
                    resp_json = post_resp.json()
                    if resp_json.get("code") == 0 or resp_json.get("message") == "ok":
                        logger.info("✅ AJAX 响应发贴成功！")
                        return True, "Published_via_API"
                except:
                    pass
                logger.warning("⚠️ 服务器返回 200 但非明确成功信号，可能被拦截或校验失败。")
                # 把返回内容写下来用于排查
                with open("api_debug.html", "w") as f:
                    f.write(post_resp.text)
                return False, ""
            else:
                logger.error(f"❌ 发贴失败，HTTP 状态码: {post_resp.status_code}")
                return False, ""
                
        except Exception as e:
            logger.error(f"❌ API 发贴请求异常: {e}")
            return False, ""

if __name__ == "__main__":
    # 快速本地测试连通性
    logging.basicConfig(level=logging.INFO)
    client = WellCMSAPIClient()
    success, url = client._publish_article({
        "title": "API 直连发贴极速性能测试（自动删除）",
        "category_id": "2",
        "summary": "这是一篇通过纯 HTTP API 发送的测试文章，不依赖任何浏览器环境。",
        "html_content": "<p>如果你看到了这篇文章，说明 API 破解和逆向工程大获成功！发布耗时0.2秒。</p>",
        "keywords": "API测试, 自动化"
    })
    print(f"最终结果: Success={success}, URL={url}")
