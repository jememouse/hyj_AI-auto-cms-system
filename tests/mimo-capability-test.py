import os
import time
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)

# 定义多维度测试用例
TEST_CASES = [
    {
        "name": "🧮 逻辑与陷阱题测试",
        "system": "你是一个严谨的逻辑学家，善于识破题目中的语言陷阱。",
        "prompt": "桌子上有3个苹果，我拿走了2个，我手里现在有几个苹果？桌子上还有几个苹果？"
    },
    {
        "name": "💻 代码编写与解析能力",
        "system": "你是一个资深的 Python 架构师。",
        "prompt": "请用Python写一个带有重试机制的装饰器（retry_decorator），支持配置最大重试次数和延迟时间，并给出一个简单的应用示例代码。"
    },
    {
        "name": "📝 创意文案与营销感",
        "system": "你是一个顶尖的 4A 广告公司文案策划。",
        "prompt": "请为一款名为“小米手环9 Pro 星空探索版”的智能穿戴设备写一段发布会预热文案。卖点是：钛金属机身、卫星通讯、超长续航。字数控制在150字以内，情绪要燃！"
    },
    {
        "name": "🎭 角色扮演与上下文沉浸",
        "system": "你现在是三国时期的诸葛亮，说话风格需符合《三国演义》中的古风设定。",
        "prompt": "丞相，司马懿十五万大军兵临西城，而我军城内仅有两千老弱病残，该当如何应对？请速速定夺！"
    }
]

def run_capability_tests():
    print("🚀 开启 MiMo 模型 (mimo-v2.5-pro) 多维度能力测试...\n")
    
    for idx, test in enumerate(TEST_CASES, 1):
        print(f"==================================================")
        print(f"▶ 测试维度 [{idx}/{len(TEST_CASES)}]: {test['name']}")
        print(f"❓ User Prompt: {test['prompt']}")
        print(f"--------------------------------------------------")
        
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
                model="mimo-v2.5-pro",
                messages=[
                    {"role": "system", "content": test["system"]},
                    {"role": "user", "content": test["prompt"]}
                ],
                max_completion_tokens=2048,
                temperature=0.7, # 平衡创造力与严谨性
                extra_body={"thinking": {"type": "enabled"}}
            )
            elapsed = time.time() - start_time
            
            message = completion.choices[0].message
            content = message.content
            reasoning = getattr(message, 'reasoning_content', None)
            
            if reasoning:
                print(f"🧠 [深度思考] (使用了 {getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)} tokens):")
                print(reasoning.strip())
                print("- " * 25)
                
            print(f"🤖 [模型输出]:\n{content.strip()}\n")
            print(f"⏱ 耗时: {elapsed:.2f}秒 | ⚡ Tokens: {completion.usage.total_tokens} (Prompt: {completion.usage.prompt_tokens}, Completion: {completion.usage.completion_tokens})")
            print(f"==================================================\n")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}\n")

if __name__ == "__main__":
    run_capability_tests()
