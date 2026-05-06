"""
统一的 LLM 工具类
提供 JSON 解析、清洗和健壮性处理
"""
import json
import re
import time
import requests
from typing import Optional, Dict, Any
from shared import config


def extract_json(content: str) -> Optional[Dict]:
    """
    从 LLM 响应中提取 JSON (支持多种格式)

    使用更健壮的三重解析策略:
    1. 直接解析整个内容
    2. 提取 markdown ```json ... ``` 块
    3. 括号深度追踪，找出所有合法 JSON 块并返回最大最完整的一个 (防止被 <think> 内的无用 JSON 干扰)

    Args:
        content: LLM 响应文本

    Returns:
        解析后的字典，如果失败返回 None
    """
    if not content:
        return None

    # 清洗内容
    content = sanitize_json(content)

    # 方法1: 直接解析
    try:
        res = json.loads(content, strict=False)
        if isinstance(res, dict): return res
    except json.JSONDecodeError:
        pass

    # 方法2: 提取 markdown ```json ... ``` 块
    md_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content)
    if md_match:
        try:
            res = json.loads(md_match.group(1), strict=False)
            if isinstance(res, dict): return res
        except json.JSONDecodeError:
            pass

    # 方法3: 括号深度追踪，找出所有合法的 JSON 块，选择最大的一个
    valid_jsons = []
    depth, start_idx = 0, -1
    for i, char in enumerate(content):
        if char == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    json_str = content[start_idx:i+1]
                    parsed = json.loads(json_str, strict=False)
                    if isinstance(parsed, dict):
                        valid_jsons.append(parsed)
                except json.JSONDecodeError:
                    pass
                start_idx = -1  # Reset to find the next block
                
    if valid_jsons:
        # 启发式：真正的 JSON 通常是最大的那个
        return max(valid_jsons, key=lambda x: len(str(x)))

    return None


def sanitize_json(text: str) -> str:
    """
    修复 LLM 生成的非法转义字符

    常见问题:
    - 非法反斜杠 (如 "10\20" 应该是 "10\\20")
    - 控制字符 (0x00-0x1f)

    Args:
        text: 待清洗的文本

    Returns:
        清洗后的文本
    """
    # 1. 修复非法转义 (保留合法的 \\ \" \/ \b \f \n \r \t \u)
    text = re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', text)

    # 2. 移除非法控制字符 (但保留换行符和制表符)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

    return text


def extract_json_array(content: str) -> Optional[list]:
    """
    从 LLM 响应中提取 JSON 数组

    Args:
        content: LLM 响应文本

    Returns:
        解析后的列表，如果失败返回 None
    """
    if not content:
        return None

    content = sanitize_json(content)

    # 方法1: 直接解析
    try:
        result = json.loads(content, strict=False)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 方法2: 提取 markdown 块
    md_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', content)
    if md_match:
        try:
            result = json.loads(md_match.group(1), strict=False)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 方法3: 括号深度追踪
    valid_jsons = []
    depth, start_idx = 0, -1
    for i, char in enumerate(content):
        if char == '[':
            if depth == 0:
                start_idx = i
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    json_str = content[start_idx:i+1]
                    parsed = json.loads(json_str, strict=False)
                    if isinstance(parsed, list):
                        valid_jsons.append(parsed)
                except json.JSONDecodeError:
                    pass
                start_idx = -1
                
    if valid_jsons:
        return max(valid_jsons, key=lambda x: len(str(x)))

    return None


def call_llm_with_retry(
    prompt: str,
    system_prompt: str = None,
    model: str = None,
    temperature: float = 1.0,
    max_retries: int = 2,
    retry_delay: float = 1.0
) -> str:
    """
    带重试 + 自动回退的 LLM 调用

    调用策略 (优先级从高到低):
      1. 主通道: DeepSeek 官方 (支持 Thinking 模式)
      2. 二级备用: Google GenAI
      3. 三级兜底: OpenRouter

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        model: 模型名称 (默认使用 config.LLM_MODEL)
        temperature: 温度参数
        max_retries: 每个通道的最大重试次数
        retry_delay: 重试延迟（秒）

    Returns:
        LLM 响应内容
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    def _build_headers(api_key: str, api_url: str) -> dict:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        if "deepseek" in api_url or "openrouter" in api_url or "xiaomimimo" in api_url:
            headers["HTTP-Referer"] = "https://github.com/jememouse/AI-auto-cms-system"
            headers["X-Title"] = "AI CMS System Agent"
        return headers

    def _try_channel(api_key: str, api_url: str, api_model: str, channel_name: str, enable_thinking: bool = False) -> Optional[str]:
        """尝试在单个通道上完成请求，成功返回内容，失败返回 None"""
        headers = _build_headers(api_key, api_url)
        payload = {
            "model": api_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 16384
        }

        # Thinking 模式参数注入 (MiMo / DeepSeek 兼容)
        if enable_thinking:
            if getattr(config, 'LLM_THINKING_ENABLED', False) or getattr(config, 'DEEPSEEK_THINKING_ENABLED', False):
                reasoning_effort = getattr(config, 'LLM_REASONING_EFFORT', getattr(config, 'DEEPSEEK_REASONING_EFFORT', 'high'))
                payload["thinking"] = {"type": "enabled"}
                payload["reasoning_effort"] = reasoning_effort
                # Thinking 模式下需要更大的 max_tokens (包含思维链输出)
                payload["max_tokens"] = 16384
                # Thinking 模式下 temperature 参数不生效，但不会报错
                print(f"   🧠 [Thinking] 已开启思考模式 (effort={reasoning_effort})")
            else:
                # 明确关闭思考模式 (防止部分模型如 MiMo 默认开启)
                payload["thinking"] = {"type": "disabled"}

        # Thinking 模式需要更长超时 (思维链输出耗时较长)
        request_timeout = 180 if enable_thinking else 90

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(api_url, headers=headers, json=payload, timeout=request_timeout)

                if resp.status_code == 200:
                    data = resp.json()
                    if 'choices' in data:
                        msg = data['choices'][0]['message']
                        # 提取 reasoning_content (思维链，仅日志打印用)
                        reasoning = msg.get('reasoning_content', '')
                        if reasoning:
                            # 截取前 200 字作为日志预览
                            preview = reasoning[:200] + '...' if len(reasoning) > 200 else reasoning
                            print(f"   💭 [Thinking] 思维链预览: {preview}")
                        print(f"   ✨ [{channel_name}] 调用成功")
                        return msg.get('content', '')
                    else:
                        print(f"   ⚠️ [{channel_name}] 响应格式异常: {data}")
                else:
                    print(f"   ⚠️ [{channel_name}] 错误 [{resp.status_code}]: {resp.text[:200]}")

            except requests.exceptions.Timeout:
                print(f"   ⚠️ [{channel_name}] 请求超时 (尝试 {attempt + 1}/{max_retries + 1}, timeout={request_timeout}s)")

            except Exception as e:
                print(f"   ❌ [{channel_name}] 请求异常: {e}")

            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))

        return None  # 该通道所有重试均失败

    def _try_google_genai(api_model: str, channel_name: str) -> Optional[str]:
        if not (hasattr(config, 'GOOGLE_GENAI_API_KEY') and config.GOOGLE_GENAI_API_KEY):
            return None
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=config.GOOGLE_GENAI_API_KEY)
            
            prompt_text = ""
            if system_prompt:
                prompt_text += f"{system_prompt}\n\n"
            prompt_text += prompt

            for attempt in range(max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=api_model,
                        contents=prompt_text,
                        config=types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=16384
                        )
                    )
                    if response and response.text:
                        print(f"   ✨ [{channel_name}] 调用成功")
                        return response.text
                    else:
                        print(f"   ⚠️ [{channel_name}] 响应为空")
                except Exception as e:
                    print(f"   ❌ [{channel_name}] 请求异常 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
        except ImportError:
            print(f"   ⚠️ [{channel_name}] 未检测到 google-genai 库，请先执行 `pip install google-genai`。")
        except Exception as e:
            print(f"   ⚠️ [{channel_name}] 客户端初始化异常: {e}")
        return None

    # ── 动态通道路由 (根据模型名称前缀判定) ──
    target_model = model or getattr(config, 'LLM_MODEL', 'mimo-v2.5')
    is_gemini = "gemini" in target_model.lower() or "gemma" in target_model.lower()
    
    if is_gemini:
        # Gemini 优先模式
        print(f"   🚀 [动态路由] 检测到 Gemini 模型，优先走 Google GenAI 通道 ({target_model})...")
        result = _try_google_genai(target_model, "Google GenAI 官方")
        if result: return result
        
        # 降级到 MiMo
        fallback_mimo = getattr(config, 'MIMO_MODEL', 'mimo-v2.5')
        print(f"   🔄 Gemini 主通道失败，降级到 MiMo 主通道 ({fallback_mimo})...")
        result = _try_channel(config.MIMO_API_KEY, getattr(config, 'MIMO_API_URL', 'https://token-plan-cn.xiaomimimo.com/v1/chat/completions'), fallback_mimo, "MiMo官方", enable_thinking=True)
        if result: return result
        
    else:
        # 默认路由：MiMo -> DeepSeek -> Gemini -> OpenRouter
        is_mimo = "mimo" in target_model.lower()
        
        # 1. 尝试 MiMo
        if getattr(config, 'MIMO_API_KEY', None):
            print(f"   🚀 [动态路由] 优先走 MiMo 主通道 ({target_model})...")
            result = _try_channel(config.MIMO_API_KEY, getattr(config, 'MIMO_API_URL', 'https://token-plan-cn.xiaomimimo.com/v1/chat/completions'), target_model, "MiMo官方", enable_thinking=is_mimo)
            if result: return result
            
        # 2. 降级到 DeepSeek
        if getattr(config, 'DEEPSEEK_API_KEY', None):
            ds_model = getattr(config, 'DEEPSEEK_MODEL', 'deepseek-v4-flash')
            print(f"   🔄 MiMo 主通道失败，降级到 DeepSeek 备用通道 ({ds_model})...")
            result = _try_channel(config.DEEPSEEK_API_KEY, getattr(config, 'DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions'), ds_model, "DeepSeek官方", enable_thinking=True)
            if result: return result
            
        # 3. 降级到 Gemini
        fallback_gemini = getattr(config, 'GOOGLE_GENAI_MODEL', 'gemini-3.1-flash-lite-preview')
        print(f"   🔄 DeepSeek 通道失败，降级到 Google GenAI 备用通道 ({fallback_gemini})...")
        result = _try_google_genai(fallback_gemini, "Google GenAI 官方")
        if result: return result

    # ── 🥉 三级兜底通道: OpenRouter ──
    if config.FALLBACK_API_KEY:
        print("   🔄 所有主/备通道失败，切换到 OpenRouter 兜底通道...")
        result = _try_channel(config.FALLBACK_API_KEY, config.FALLBACK_API_URL, config.FALLBACK_MODEL, "OpenRouter兜底")
        if result: return result

    print("   ❌ 所有通道均已失败")
    return ""


def call_llm_json(
    prompt: str,
    system_prompt: str = None,
    model: str = None,
    temperature: float = 1.0,
    max_retries: int = 2
) -> Optional[Dict]:
    """
    调用 LLM 并自动解析 JSON 响应

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        model: 模型名称
        temperature: 温度参数
        max_retries: 最大重试次数

    Returns:
        解析后的 JSON 字典，失败返回 None
    """
    content = call_llm_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=max_retries
    )

    if not content:
        return None

    return extract_json(content)


def call_llm_json_array(
    prompt: str,
    system_prompt: str = None,
    model: str = None,
    temperature: float = 1.0,
    max_retries: int = 2
) -> Optional[list]:
    """
    调用 LLM 并自动解析 JSON 数组响应

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        model: 模型名称
        temperature: 温度参数
        max_retries: 最大重试次数

    Returns:
        解析后的 JSON 列表，失败返回 None
    """
    content = call_llm_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=max_retries
    )

    if not content:
        return None

    return extract_json_array(content)
