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

# 深度编程能力测试用例
CODING_TEST_CASES = [
    {
        "name": "前端架构能力 (Vue3 + TS + 虚拟滚动)",
        "prompt": "请使用 Vue 3 (Composition API) 编写一个带虚拟滚动（Virtual Scroll）的长列表组件。要求包含完整的 TypeScript 类型定义，精准的 JS 滚动计算逻辑（如何计算 offset 和渲染区间），只渲染可视区域的 DOM 节点，并附带关联的 CSS。"
    },
    {
        "name": "后端与并发控制 (FastAPI + Redis 秒杀系统)",
        "prompt": "请用 Python (FastAPI) 写一个高并发安全的商品抢购（秒杀）接口。必须使用 Redis Lua 脚本原子扣减库存防止超卖。代码要求体现高并发下的防御逻辑，并具有清晰的目录结构/模块划分思想。"
    },
    {
        "name": "数据与复杂SQL引擎 (连续动作分析)",
        "prompt": "表名 orders，字段：id, user_id, amount, status, created_at。请写一个 MySQL 的 SQL 语句，查询出过去 30 天内，至少存在连续 3 天下单，且这 30 天内总消费成功（status='success'）金额超过 1000 元的 user_id。并且请你给出这个业务查询所需的联合索引设计。"
    },
    {
        "name": "系统架构设计 (千万日活短视频后端)",
        "prompt": "我们需要设计一个日活 1000 万级别的短视频后端系统。请输出系统架构设计，必须涵盖核心链路：视频断点续传/极速秒传、异步高可靠转码（如何保证转码任务不丢失）、CDN智能分发。架构描述需专业、条理清晰。"
    },
    {
        "name": "系统性与组织性 (重构复杂 if-else)",
        "prompt": "假设一个电商计价模块，支付通道有：微信、支付宝、海外信用卡；用户等级有：普通、VIP、黑卡。交叉组合后折扣逻辑极度复杂，满是 if-else 嵌套。请用 TypeScript 和策略模式/工厂模式设计一套符合 SOLID 原则的定价计算引擎架构，彻底消除冗余分支结构。"
    }
]

def run_coding_tests():
    print("🚀 开启 MiMo 模型 深度编程与系统架构能力测试...\n")
    
    # 创建保存目录
    output_dir = "tests/mimo_coding_outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    for idx, test in enumerate(CODING_TEST_CASES, 1):
        print(f"==================================================")
        print(f"▶ [正在测试] 维度 {idx}/5: {test['name']}")
        
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
                model="mimo-v2.5-pro",
                messages=[
                    {"role": "system", "content": "你是一个硅谷顶尖的全栈架构师（Staff Engineer），精通前端框架、高并发后端、系统架构和代码整洁之道（Clean Code）。请直接给出高质量的技术方案与代码，无需过多寒暄。"},
                    {"role": "user", "content": test["prompt"]}
                ],
                max_completion_tokens=65536,
                temperature=0.3, # 代码和架构任务，降低温度保证逻辑严密性
                extra_body={"thinking": {"type": "enabled"}}
            )
            elapsed = time.time() - start_time
            
            message = completion.choices[0].message
            content = message.content
            reasoning = getattr(message, 'reasoning_content', None)
            
            # 保存完整结果至 Markdown 文件
            filename = os.path.join(output_dir, f"test_result_{idx}.md")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# {test['name']}\n\n")
                f.write(f"**Prompt:**\n> {test['prompt']}\n\n")
                if reasoning:
                    f.write(f"## 🤖 深度思考过程 ({getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)} tokens)\n```text\n{reasoning}\n```\n\n")
                f.write(f"## 💻 模型输出\n\n{content}")
                
            print(f"✅ 测试完成！结果已存入 -> {filename}")
            print(f"⏱ 耗时: {elapsed:.2f}秒 | ⚡ Tokens: {completion.usage.total_tokens}")
            print(f"==================================================\n")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}\n")

if __name__ == "__main__":
    run_coding_tests()
