import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

HARDCORE_TEST_CASES = [
    {
        "name": "🦀 Rust 底层并发 (Lock-Free MPMC Queue)",
        "prompt": "请使用 Rust 实现一个无锁的 (Lock-Free) 多生产者多消费者 (MPMC) 环形缓冲区。要求：\n1. 不能使用 Mutex 或 RwLock，必须纯靠 `std::sync::atomic`。\n2. 必须精准、正确地使用内存屏障（Memory Ordering：Acquire, Release, Relaxed 等），并加注释说明为什么该处要用这个 Ordering。\n3. 请在回答中解释你是如何避免并发中的 ABA 问题的。"
    },
    {
        "name": "🌐 分布式共识协议 (Raft 脑裂与日志一致性)",
        "prompt": "在 Raft 协议中，如果发生网络分区，旧的 Leader A 被隔离在少数派网络中。此时有客户端向 A 发送了写入请求。当网络恢复，A 重新加入集群（此时集群已有新 Leader B），请深入推演整个集群是如何解决这次数据冲突并恢复强一致性的？\n另外，请用 Python 编写一段核心代码，模拟新 Leader 向 Follower 发送 `AppendEntries` RPC 时，Follower 端关于 Log Matching Property（日志匹配原则）的强校验与覆盖逻辑。"
    },
    {
        "name": "🧠 进阶算法 (Bitmask DP 状态压缩)",
        "prompt": "请解决以下高难度算法问题：给定 N 个任务（N ≤ 20），每个任务 i 有一个消耗时间 `time[i]` 和一个依赖掩码 `prerequisite[i]`（即在开始任务 i 之前，必须先完成 `prerequisite[i]` 中所有的任务，并发执行的任务数量不限）。\n请使用 Python 写出时间复杂度约为 O(2^N * N) 的状态压缩动态规划（Bitmask DP）解法，求出完成所有任务的最短总时间。\n要求：\n1. 给出严谨的状态定义和状态转移方程说明。\n2. 代码必须做到高效率（考虑位运算优化）。"
    }
]

def run_hardcore_tests():
    print("🔥 开启 MiMo 模型 极限硬核 (Hardcore) 能力压测...\n")
    
    output_dir = "tests/mimo_hardcore_outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    for idx, test in enumerate(HARDCORE_TEST_CASES, 1):
        print(f"==================================================")
        print(f"▶ [极限压测] 关卡 {idx}/3: {test['name']}")
        
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
                model="mimo-v2.5-pro",
                messages=[
                    {"role": "system", "content": "你是一位计算机科学领域的泰斗（Fellow），也是资深底层开发专家，专精于操作系统、分布式共识算法、底层并发（Rust/C++）和高级数据结构。你的回答必须极其深奥、准确、无懈可击。"},
                    {"role": "user", "content": test["prompt"]}
                ],
                max_completion_tokens=65536,
                temperature=0.2, # 极低温度以求最严谨的推演
                extra_body={"thinking": {"type": "enabled"}}
            )
            elapsed = time.time() - start_time
            
            message = completion.choices[0].message
            content = message.content
            reasoning = getattr(message, 'reasoning_content', None)
            
            filename = os.path.join(output_dir, f"hardcore_test_{idx}.md")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# {test['name']}\n\n")
                f.write(f"**Prompt:**\n> {test['prompt']}\n\n")
                if reasoning:
                    f.write(f"## 🤖 深度思考过程 ({getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)} tokens)\n```text\n{reasoning}\n```\n\n")
                f.write(f"## 💻 模型输出\n\n{content}")
                
            print(f"✅ 关卡突破！硬核解析已存入 -> {filename}")
            print(f"⏱ 耗时: {elapsed:.2f}秒 | ⚡ Tokens: {completion.usage.total_tokens}")
            print(f"==================================================\n")
            
        except Exception as e:
            print(f"❌ 压测失败: {e}\n")

if __name__ == "__main__":
    run_hardcore_tests()
