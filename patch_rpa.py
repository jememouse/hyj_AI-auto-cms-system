import os

file_path = "/Users/wang/code-project/hyj-cms-system/step3_publish/wellcms_rpa.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

start_marker = "            # 填写 SEO 字段 (使用 fill 触发事件，若元素不可见则用 evaluate 强制赋值)"
end_marker = '                print(f"      ⚠️ 等待跳转超时或失败，尝试根据当前 URL 判断: {e}")'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker) + len(end_marker)

if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
    print("Could not find markers!")
    print("Start:", start_idx, "End:", end_idx)
    exit(1)

new_code = """            # ===================================================================
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
            
            import time
            time.sleep(0.5)
            
            print("      🖱️ 极速触发提交事件...")
            try:
                with self.page.expect_navigation(timeout=30000):
                    self.page.evaluate("document.getElementById('submit').click();")
            except Exception as e:
                print(f"      ⚠️ 等待跳转超时或失败，尝试根据当前 URL 继续: {e}")"""

new_content = content[:start_idx] + new_code + content[end_idx:]

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Patch applied successfully!")
