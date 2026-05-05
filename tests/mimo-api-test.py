import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 加载项目中根目录的 .env 文件
load_dotenv()

API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
def test_mimo_api():
    """
    测试 Xiaomi MiMo API 通讯
    """
    print("🚀 正在初始化 MiMo API 客户端...")
    # 初始化 OpenAI 客户端，通过自定义 base_url 和 api_key 实现与 MiMo API 的兼容
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL
    )

    try:
        print("⏳ 正在发送请求，请稍候...\n")
        # 发起 Chat Completion 请求
        completion = client.chat.completions.create(
            model="mimo-v2.5-pro", # 使用文档中推荐的默认 pro 模型
            messages=[
                {
                    "role": "system",
                    "content": "你是由小米开发的 AI 助手 MiMo。请使用简体中文回答问题，并保持专业和友善。"
                },
                {
                    "role": "user",
                    "content": "你好，请简单介绍一下你自己，并说明你支持哪些主要的功能特性？"
                }
            ],
            max_completion_tokens=2048, # 限制生成的最大 token 数
            temperature=1.0,            # 采样温度，1.0 是文档中 mimo-v2.5-pro 的默认值
            top_p=0.95,                 # 核采样的概率阈值
            stream=False,               # 关闭流式输出，方便一次性打印结果
            # MiMo 专有的深度思考控制字段
            extra_body={
                "thinking": {"type": "enabled"} 
            }
        )

        # 提取回复内容和可能存在的思维链内容
        message = completion.choices[0].message
        content = message.content
        reasoning_content = getattr(message, 'reasoning_content', None)

        if reasoning_content:
            print("🧠 [深度思考过程]:")
            print("-" * 40)
            print(reasoning_content)
            print("-" * 40 + "\n")

        print("🤖 [MiMo 回复]:")
        print("-" * 40)
        print(content)
        print("-" * 40 + "\n")
        
        print("📊 [Token 消耗统计]:")
        print(f"Prompt Tokens: {completion.usage.prompt_tokens}")
        print(f"Completion Tokens: {completion.usage.completion_tokens} (其中推理使用了 {getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)} tokens)")
        print(f"Total Tokens: {completion.usage.total_tokens}")

    except Exception as e:
         print(f"❌ API 调用失败: {e}")

if __name__ == "__main__":
    test_mimo_api()
