"""
测试脚本: 验证 DeepSeek V4 Flash + Thinking 模式文章生成
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import config, llm_utils

def main():
    print("=" * 60)
    print("🧪 测试: DeepSeek V4 Flash + Thinking 模式文章生成")
    print("=" * 60)
    
    # 打印当前配置
    print(f"\n📋 当前配置:")
    print(f"   模型: {config.LLM_MODEL}")
    print(f"   Thinking: {getattr(config, 'DEEPSEEK_THINKING_ENABLED', False)}")
    print(f"   Effort: {getattr(config, 'DEEPSEEK_REASONING_EFFORT', 'N/A')}")
    print(f"   API URL: {config.LLM_API_URL}")
    print(f"   API Key: {config.LLM_API_KEY[:8]}...{config.LLM_API_KEY[-4:]}" if config.LLM_API_KEY else "   API Key: ⚠️ 未配置")
    
    # 测试主题
    topic = "2026年跨境电商包装避坑指南：FBA合规箱尺寸怎么选才不被亚马逊退货？"
    category = "专业知识"
    
    print(f"\n📝 测试主题: {topic}")
    print(f"📂 分类: {category}")
    print(f"\n⏳ 正在调用 LLM (Thinking 模式可能需要 30-60 秒)...\n")
    
    start_time = time.time()
    
    # 使用简化版 prompt 测试
    prompt = f"""
    你是一位拥有10年经验的包装行业专家。
    请为主题 "{topic}"（分类：{category}）撰写一篇 800 字左右的专业文章。
    
    要求：
    1. 使用 Markdown 格式
    2. 包含 H1 标题、H2 副标题、要点列表
    3. 内容专业、有深度
    4. 适合 SEO 优化
    5. 文末附带 3 个 FAQ
    
    直接输出 Markdown 内容，不要包裹在 JSON 或代码块中。
    """
    
    result = llm_utils.call_llm_with_retry(
        prompt=prompt,
        model=config.ARTICLE_MODEL,
        temperature=0.85,
        max_retries=1
    )
    
    elapsed = time.time() - start_time
    
    if result:
        # 保存为 MD 文件
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_article_output.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        
        print(f"\n{'=' * 60}")
        print(f"✅ 生成成功！")
        print(f"   耗时: {elapsed:.1f} 秒")
        print(f"   字数: {len(result)} 字符")
        print(f"   输出: {output_path}")
        print(f"{'=' * 60}")
        
        # 打印前 500 字预览
        print(f"\n📄 内容预览 (前 500 字):\n")
        print(result[:500])
        if len(result) > 500:
            print(f"\n... (共 {len(result)} 字符，完整内容已保存到文件)")
    else:
        print(f"\n❌ 生成失败！耗时 {elapsed:.1f} 秒")
        print("请检查 API Key 和网络连接")

if __name__ == "__main__":
    main()
