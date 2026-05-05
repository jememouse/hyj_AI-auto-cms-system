import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.chief_editor import ChiefEditorAgent

def run_full_document_test():
    print("🔥 开启 MiMo 模型 [完整流水线长文生成] 联合测试...\n")
    
    topic = "2026年环保材料在奢侈品纸盒包装中的创新应用"
    category = "专业知识"
    source_trend = "奢侈品牌加速淘汰不可降解包装，竹浆与甘蔗渣特种纸搜索热度飙升"
    
    print(f"📌 测试主题: {topic}")
    print(f"📌 测试分类: {category}")
    print(f"📌 关联热点: {source_trend}")
    print("-" * 50)
    
    editor = ChiefEditorAgent()
    
    start_time = time.time()
    article = editor.write_article(topic, category, source_trend)
    elapsed = time.time() - start_time
    
    if article:
        output_dir = "tests/mimo_html_outputs"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, "full_pipeline_test.html")
        
        # 写入完整的 HTML，并且把其他字段写在文件顶部作为注释
        with open(filename, "w", encoding="utf-8") as f:
            f.write("<!--\n")
            f.write(f"【标题】: {article.get('title')}\n")
            f.write(f"【描述】: {article.get('description')}\n")
            f.write(f"【关键词】: {article.get('keywords')}\n")
            f.write(f"【一句话摘要】: {article.get('one_line_summary', '')}\n")
            f.write(f"【Tags】: {article.get('tags')}\n")
            f.write("-->\n\n")
            f.write(article.get('html_content', ''))
            
        print(f"\n✅ 完整流水线生成成功！")
        print(f"🎯 最终提取标题: {article.get('title')}")
        print(f"⏱ 耗时: {elapsed:.2f} 秒")
        print(f"📂 完整文档与元数据已保存至: {filename}")
    else:
        print("\n❌ 生成失败！")

if __name__ == "__main__":
    run_full_document_test()
