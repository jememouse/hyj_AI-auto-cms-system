import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

TEST_CASES = [
    {
        "name": "常识推理与陷阱",
        "system": "你是一个细心、聪明的物理学助手。",
        "prompt": "如果我把一块冰块放在室温为 25 度的桌子上，然后过了一小时，我用一条吸水性很好的干毛巾把它盖住。请问毛巾下面现在有什么？"
    },
    {
        "name": "基础业务代码 (HTML/CSS/JS)",
        "system": "你是一个资深的前端开发工程师。",
        "prompt": "请用原生 HTML、CSS 和少量的 JS 实现一个极简的暗黑模式/白天模式切换按钮（Toggle），点击时需要有平滑的颜色过渡动画。"
    },
    {
        "name": "语境理解与文本润色",
        "system": "你是一个在硅谷工作多年的中美文化沟通桥梁专家。",
        "prompt": "请解释英文俚语 'bite the bullet' 的历史由来，并分别给出在【职场背锅】、【看牙医】、【艰难创业】三个不同语境下的高级中文翻译及中英双语例句。"
    }
]

def run_v25_base_tests():
    print("🚀 开启 MiMo-V2.5 (标准版) 模型能力与速度评测...\n")
    
    for idx, test in enumerate(TEST_CASES, 1):
        print(f"==================================================")
        print(f"▶ [标准版测试] 维度 {idx}/3: {test['name']}")
        print(f"❓ Prompt: {test['prompt']}")
        print(f"--------------------------------------------------")
        
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
                model="mimo-v2.5", # 这里明确指定标准版模型
                messages=[
                    {"role": "system", "content": test["system"]},
                    {"role": "user", "content": test["prompt"]}
                ],
                max_completion_tokens=32768, # 文档中 v2.5 的默认最大 token 为 32768
                temperature=0.7,
                extra_body={"thinking": {"type": "enabled"}}
            )
            elapsed = time.time() - start_time
            
            message = completion.choices[0].message
            content = message.content
            reasoning = getattr(message, 'reasoning_content', None)
            
            if reasoning:
                print(f"🧠 [思考过程] (耗费 {getattr(completion.usage.completion_tokens_details, 'reasoning_tokens', 0)} tokens):")
                trunc_reasoning = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
                print(trunc_reasoning.replace('\n', ' '))
                print("- " * 25)
                
            print(f"🤖 [模型输出]:")
            print(f"{content}\n")
            
            # 计算包含推理 token 在内的综合生成速度
            speed = completion.usage.completion_tokens / elapsed if elapsed > 0 else 0
            print(f"⏱ 耗时: {elapsed:.2f}秒 | ⚡ Tokens消耗: {completion.usage.total_tokens}")
            print(f"🚀 综合生成速度: {speed:.2f} Tokens/秒")
            print(f"==================================================\n")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}\n")

if __name__ == "__main__":
    run_v25_base_tests()
