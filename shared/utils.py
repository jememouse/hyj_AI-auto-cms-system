import sys
import os
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import config


def call_llm(prompt: str, system_prompt: str = None, model: str = None, temperature: float = 1.0) -> str:
    """
    统一的 LLM 调用工具 (代理到 llm_utils.call_llm_with_retry)

    注意: 此函数为兼容性保留接口，实际调用已统一路由到
    llm_utils.call_llm_with_retry()，支持三级通道回退和 Thinking 模式。
    """
    from shared.llm_utils import call_llm_with_retry

    return call_llm_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=1  # 标题压缩等轻量任务，降低重试次数
    )

