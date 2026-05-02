import sys
import os
import time
import re
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import config
from step3_publish.wellcms_rpa import WellCMSPublisher

def run_delete_duplicates():
    print("=" * 50)
    print("🗑️ 开始检测并删除 CMS 后台重复文章")
    print("=" * 50)
    
    # 使用 config 中默认的账号密码（通常为管理账号）
    username = config.WELLCMS_USERNAME
    password = config.WELLCMS_PASSWORD
    
    if not username or not password:
        print("❌ 未在环境变量中找到 WELLCMS_USERNAME / WELLCMS_PASSWORD，请先配置！")
        return
        
    publisher = WellCMSPublisher(username=username, password=password)
    
    try:
        print("🌐 正在启动浏览器...")
        publisher._init_browser()
        
        # 自动同意所有的弹窗确认（如点击删除后的确认）
        publisher.page.on("dialog", lambda dialog: dialog.accept())
        
        print("🔑 正在登录 CMS 后台...")
        if not publisher._login():
            print("❌ 登录失败，请检查账号密码")
            return
            
        print("✅ 登录成功，进入文章列表页...")
        list_url = f"{config.WELLCMS_ADMIN_URL}?0=content&1=list"
        
        deleted_count = 0
        seen_titles = {} # dict of title -> kept_tid
        
        current_page = 1
        max_page = 50
        
        # 使用 while 循环，解决删除数据后分页数据上移导致的漏扫问题
        while current_page <= max_page:
            print(f"\n📄 正在扫描第 {current_page} 页...")
            
            # 由于 WellCMS 分页可能是基于参数的，如果通过第一页的"下一页"按钮会更好
            # 我们先刷新当前列表页面
            list_url = f"{config.WELLCMS_ADMIN_URL}?0=content&1=list&page={current_page}"
            publisher._safe_goto(list_url)
            time.sleep(2)
            
            # 在某些情况下，数据在 iframe 中
            target_frame = None
            for frame in publisher.page.frames:
                try:
                    frame.wait_for_selector("li.thread[tid]", timeout=3000)
                    target_frame = frame
                    break
                except:
                    pass
                    
            if not target_frame:
                target_frame = publisher.page
                
            # 查找所有的数据行
            # 真实结构为: li.media.thread[tid]
            try:
                target_frame.wait_for_selector("li.thread[tid]", timeout=5000)
            except:
                pass
                
            rows = target_frame.locator("li.thread[tid]")
            count = rows.count()
            
            if count == 0:
                print("⚠️ 未找到任何文章行，扫描结束")
                break
            
            # 因为删除后页面可能会刷新或 DOM 变化，所以我们先收集当前页的所有重复项，再逐个处理
            to_delete_indexes = []
            
            for i in range(count):
                row = rows.nth(i)
                tid = row.get_attribute("tid")
                
                # 尝试提取标题
                try:
                    # 标题在 div.subject h2 a 里面
                    title_elem = row.locator("div.subject h2 a").first
                    if title_elem.count() > 0:
                        # 替换掉可能包含的锁头图标等不可见字符
                        title = title_elem.inner_text().strip()
                        # 去除开头的锁头图标
                        if title.startswith("🔒"):
                            title = title.replace("🔒", "").strip()
                    else:
                        title = row.inner_text().strip().split('\n')[0][:30]
                        if title.startswith("🔒"):
                            title = title.replace("🔒", "").strip()
                        
                    if title and tid:
                        if title in seen_titles:
                            if seen_titles[title] == tid:
                                # 这是我们保留的那一份，跳过
                                pass
                            else:
                                print(f"   🗑️ 发现重复文章 (tid={tid}): {title[:20]}...")
                                to_delete_indexes.append(i)
                        else:
                            seen_titles[title] = tid
                except Exception as e:
                    pass
            
            if not to_delete_indexes:
                print("✅ 本页未发现重复文章。")
            else:
                # 勾选重复文章的 checkbox
                for i in to_delete_indexes:
                    try:
                        row = rows.nth(i)
                        checkbox = row.locator("input[type='checkbox']").first
                        if checkbox.count() > 0:
                            checkbox.check(force=True)  # custom-control 的 input 可能是隐藏的，需要 force=True
                        else:
                            print(f"   ⚠️ 未能定位到第 {i+1} 行的复选框")
                    except Exception as e:
                        print(f"   ❌ 勾选失败: {e}")
                
                # 点击批量删除按钮
                try:
                    delete_btn = target_frame.locator("button.delete, button:has-text('删除')").first
                    if delete_btn.count() > 0:
                        delete_btn.click()
                        time.sleep(1)
                        
                        # WellCMS 会弹出一个 Bootstrap Modal 确认对话框
                        # 等待 Modal 出现并点击确认按钮
                        modal_submit = target_frame.locator(".modal-dialog button#submit, .modal-dialog button.btn-danger").first
                        if modal_submit.count() > 0:
                            modal_submit.click()
                            print(f"   ✅ 已确认删除 {len(to_delete_indexes)} 篇文章")
                        else:
                            # 尝试其他可能的确认按钮
                            modal_submit = target_frame.locator("button:has-text('确定'), button:has-text('确认')").last
                            if modal_submit.count() > 0:
                                modal_submit.click()
                                print(f"   ✅ 已确认删除 {len(to_delete_indexes)} 篇文章")
                            else:
                                print(f"   ⚠️ 找不到 Modal 确认按钮")
                                
                        time.sleep(3) # 等待删除请求完成和页面刷新
                        deleted_count += len(to_delete_indexes)
                    else:
                        print(f"   ⚠️ 未能定位到批量删除按钮")
                except Exception as e:
                    print(f"   ❌ 批量删除操作失败: {e}")
            
            # 翻页逻辑
            try:
                if to_delete_indexes:
                    print(f"   🔄 数据已刷新，继续扫描第 {current_page} 页...")
                else:
                    current_page += 1
                    print(f"   ➡️ 准备进入第 {current_page} 页...")
            except Exception as e:
                print(f"   ❌ 翻页失败: {e}")
                break
                
        print(f"\n🎉 扫描完成！共删除了 {deleted_count} 篇重复文章。")
        
    except Exception as e:
        print(f"❌ 运行过程中发生错误: {e}")
    finally:
        publisher._close_browser()


if __name__ == "__main__":
    run_delete_duplicates()
