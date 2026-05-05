import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

HTML_ARTICLE_PROMPT = """
请你作为资深的高端包装结构设计师与 SEO 内容专家，为我们的包装印刷内容管理系统（CMS）生成一篇关于【2026年高端精品纸盒包装（Rigid Box）设计趋势与特种纸应用】的专业深究文章。

要求：
1. 输出格式：**必须是纯净的 HTML 代码片段**（不需要 <html>、<head>、<body> 等外围标签，只需输出内部节点，从 <h1> 开始，适合直接无缝注入到 CMS 的富文本字段中）。
2. SEO 与排版结构：
   - 包含一个具有极强转化吸引力的 <h1> 标题。
   - 至少包含 3 个 <h2> 核心论点章节。
   - 丰富合理的 HTML 语义化标签：<h3>、<strong>（高亮关键术语）、<blockquote>（用于引用行业金句或前卫设计理念）。
   - 必须包含至少一个 <ul> 列表（总结工艺特点等）和一个 <table> 结构（如：普通硬纸板与高级灰板/特种纸的核心参数或体验对比）。
3. 内容质量：
   - 深度探讨最新材料与工艺特性（如：触感膜结合局部UV、高克重灰板包纸、磁吸隐形结构、烫金/击凸工艺等）。
   - 语言极其专业，具备商业营销与品牌溢价感，等量字数需丰满（视觉上超过1000字的内容密度）。
4. SEO 预埋：在输出的 HTML 尾部，添加一段单行 HTML 注释 <!-- SEO Meta: Title=xxx, Keywords=xxx, Description=xxx --> 给出最强抓取建议。
"""

def run_html_article_test():
    print("📰 开启 MiMo 模型 [富文本 HTML 文章自动化生产] 能力压测...\n")
    print("⏳ 正在请求生成复杂的行业级 HTML 长文，请稍候...")
    
    try:
        start_time = time.time()
        completion = client.chat.completions.create(
            model="mimo-v2.5-pro", # 此类长文强逻辑场景，使用 Pro 版本最合适
            messages=[
                {"role": "system", "content": "你是一个拥有10年经验的高端包装结构专家与前端HTML排版大师。你总是输出优雅、结构化、符合W3C标准的CMS可直接解析的内容。"},
                {"role": "user", "content": HTML_ARTICLE_PROMPT}
            ],
            max_completion_tokens=8192,
            temperature=0.6,
            extra_body={"thinking": {"type": "enabled"}}
        )
        elapsed = time.time() - start_time
        
        message = completion.choices[0].message
        content = message.content
        reasoning = getattr(message, 'reasoning_content', None)
        
        # 保存到独立文件
        output_dir = "tests/mimo_html_outputs"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, "article_rigid_box_trends.html")
        
        # 清除可能返回的 markdown 代码块包裹 (如 ```html ... ```)
        clean_content = content
        if clean_content.startswith("```html"):
            clean_content = clean_content[7:]
        elif clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()
            
        with open(filename, "w", encoding="utf-8") as f:
            f.write(clean_content)
            
        print(f"\n✅ HTML 商业文章生成完成！结果已存入 -> {filename}")
        print(f"⏱ 耗时: {elapsed:.2f}秒 | ⚡ 总 Tokens: {completion.usage.total_tokens}")
        if reasoning:
            print(f"🧠 深度思考消耗 Tokens: {getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)}")
        print(f"🚀 生成速度: {(completion.usage.completion_tokens / elapsed):.2f} Tokens/秒\n")
        
        preview = clean_content[:600] + "\n\n... [后略，完整代码请查看生成的文件] ..."
        print("🔍 HTML 代码截取预览：\n")
        print(preview)
        print("\n==================================================")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}\n")

if __name__ == "__main__":
    run_html_article_test()
