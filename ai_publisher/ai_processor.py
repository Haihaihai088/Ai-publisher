# ai_processor.py - AI 分析 + 各平台内容生成
#
# 职责：
#   1. analyze()       — 提取主题、关键词、情感、推荐热词
#   2. generate_all()  — 为所有目标平台批量生成内容（一次调用）
#   3. regenerate()    — 重新生成某单个平台的内容
#
# 设计要点：
#   - 使用 response_format=json_object 强制 JSON 输出，避免 markdown 包裹
#   - 分析和生成分两次调用：分析结果复用，生成时注入热词
#   - 所有 Prompt 都内联在此文件，方便调优

import json
import time
import subprocess
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

import config
from config import TaskStatus
import task_manager
from platform_registry import PlatformRegistry


# ─────────────────────────────────────────────
# 初始化 OpenAI / DeepSeek 客户端
# ─────────────────────────────────────────────

def _get_client() -> OpenAI:
    if not config.AI_API_KEY:
        raise ValueError("未配置 AI API Key，请在 .env 文件中设置 OPENAI_API_KEY")
    return OpenAI(api_key=config.AI_API_KEY, base_url=config.AI_BASE_URL)


def _call(client: OpenAI, prompt: str, system: str = None, max_retries: int = 3) -> dict:
    """
    封装一次 AI 调用，返回解析后的 JSON dict。

    防护点：
    - 90秒超时，防止 API 无响应导致子进程永久阻塞
    - 自动重试（指数退避），处理间歇性网络波动
    - JSON 解析失败时携带原始返回片段，方便排查
    - 区分 API 错误（超时/限流/连接失败）并给出明确提示
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=config.AI_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
                timeout=90,
            )
            raw = resp.choices[0].message.content
            if not raw:
                raise ValueError("AI 返回了空内容")

            # 防御：有些模型会在 json_object 模式下仍然加 ```json 包裹
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw)

        except json.JSONDecodeError as e:
            snippet = raw[:200] if 'raw' in dir() and raw else "(无内容)"
            last_error = f"JSON 解析失败(第{attempt}次): {e}\n返回片段: {snippet}"
        except APITimeoutError:
            last_error = f"API 超时(第{attempt}次): 90秒内未返回结果"
        except APIConnectionError:
            last_error = f"API 连接失败(第{attempt}次): 无法连接到 {config.AI_BASE_URL}"
        except APIError as e:
            last_error = f"API 错误(第{attempt}次): {e}"
        except Exception as e:
            last_error = f"AI 调用失败(第{attempt}次): {type(e).__name__}: {e}"

        if attempt < max_retries:
            wait = 2 ** attempt  # 2s, 4s, 8s
            time.sleep(wait)

    raise RuntimeError(f"AI 调用经过 {max_retries} 次重试后仍然失败:\n{last_error}")


# ─────────────────────────────────────────────
# Step 1: 内容分析
# ─────────────────────────────────────────────

_ANALYZE_SYSTEM = "你是一个专业的内容分析师，擅长提炼文章核心信息。只输出合法 JSON，不要任何额外说明。"

_ANALYZE_PROMPT = """
分析以下内容，提取核心信息。

内容：
---
{content}
---

输出 JSON 格式（严格按此结构）：
{{
  "topic": "一句话概括核心主题，15字以内",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "emotion": "positive 或 neutral 或 negative",
  "content_type": "教程 或 测评 或 观点 或 资讯 或 故事 中选一个",
  "summary": "不超过80字的摘要，用于各平台改写的参考",
  "hot_words": ["平台热搜词1", "平台热搜词2", "平台热搜词3"],
  "tieba_candidates": ["最相关的吧名1", "最相关的吧名2", "最相关的吧名3"]
}}

hot_words 要求：结合内容主题，推测在小红书/知乎/贴吧上当前可能流行的搜索词，要具体（如"2024年最值得买的平板"而不是"平板推荐"）。
tieba_candidates 要求：推荐3个最适合发布此内容的百度贴吧名称，只写吧名不带"吧"字（如"数码"而不是"数码吧"）。
"""


def analyze(content: str) -> dict:
    """分析原始内容，返回 analysis dict"""
    client = _get_client()
    # 超长内容截断，避免 token 超限（保留前 3000 字）
    truncated = content[:3000] if len(content) > 3000 else content
    prompt = _ANALYZE_PROMPT.format(content=truncated)
    return _call(client, prompt, system=_ANALYZE_SYSTEM)


# ─────────────────────────────────────────────
# Step 2: 批量生成各平台内容
# ─────────────────────────────────────────────

_GENERATE_SYSTEM = """
你是一个深度熟悉各平台用户习惯的内容创作者。
禁止使用"首先""其次""综上所述""总的来说"等套话。
去掉 AI 味，用真实人类的自然语言写作。
只输出合法 JSON，不要任何额外说明。
"""

# _PLATFORM_SPECS 已移除，平台规范现在从 PlatformRegistry 获取
# 每个 publisher 模块注册时自带 ai_spec 和 output_schema

_GENERATE_PROMPT = """
原始内容：
---
{content}
---

内容分析：
- 主题：{topic}
- 摘要：{summary}
- 情感基调：{emotion}
- 推荐热词：{hot_words}

目标平台及规范：
{platform_specs}

请为上述每个平台生成适配内容，输出 JSON 格式（只包含指定平台的 key）：
{{
{output_schema}
}}

要求：
1. 每个平台的标题和正文必须真正针对平台特性重写，不能只改格式
2. 自然融入推荐热词，不能生硬堆砌
3. 如有图片描述，在正文中自然融入，不单独说"配图是"
"""

def generate_all(content: str, platforms: list[str], analysis: dict) -> dict:
    """
    批量为所有平台生成内容。
    返回 dict，key 是平台 key，value 是该平台的内容 dict。
    """
    client = _get_client()

    # 从 PlatformRegistry 获取平台规范（替代原来的 _PLATFORM_SPECS + _build_output_schema）
    platform_specs = PlatformRegistry.get_ai_specs(platforms)
    output_schema = PlatformRegistry.get_output_schema(platforms)

    truncated = content[:2000] if len(content) > 2000 else content
    prompt = _GENERATE_PROMPT.format(
        content=truncated,
        topic=analysis.get("topic", ""),
        summary=analysis.get("summary", ""),
        emotion=analysis.get("emotion", "neutral"),
        hot_words="、".join(analysis.get("hot_words", [])),
        platform_specs=platform_specs,
        output_schema=output_schema,
    )

    result = _call(client, prompt, system=_GENERATE_SYSTEM)

    # 把吧名候选注入到需要 bar_selection 的平台的 ai_results 里
    if "tieba_candidates" in analysis:
        for p in platforms:
            desc = PlatformRegistry.get(p)
            if desc and desc.has_bar_selection and p in result:
                result[p]["tieba_candidates"] = analysis["tieba_candidates"]
                result[p]["tieba_selected"] = None

    return result


def regenerate_single(content: str, platform: str, analysis: dict) -> dict:
    """重新生成单个平台的内容（用户点击"重来"时调用）"""
    result = generate_all(content, [platform], analysis)
    return result.get(platform, {})


# ─────────────────────────────────────────────
# 完整处理流程（在独立子进程里调用，不阻塞 Streamlit）
# ─────────────────────────────────────────────

def process_task_subprocess(task_id: str):
    """
    从命令行调用入口（被 subprocess 启动）。
    用法：python ai_processor.py <task_id>
    """
    task = task_manager.load_task(task_id)
    if task is None:
        print(f"[ERROR] Task {task_id} not found")
        return

    # 更新状态：处理中
    task_manager.update_status(task_id, TaskStatus.ANALYZING)

    try:
        # Step 1: 分析
        print(f"[{task_id}] 分析内容...")
        analysis = analyze(task["original_content"])

        # Step 2: 生成各平台内容
        print(f"[{task_id}] 生成平台内容：{task['platforms']}")
        ai_results = generate_all(
            task["original_content"],
            task["platforms"],
            analysis
        )

        # Step 3: 写入结果，状态变更为 pending_review
        task_manager.update_ai_results(task_id, analysis, ai_results)
        print(f"[{task_id}] 完成，状态 → pending_review")

    except Exception as e:
        print(f"[{task_id}] 处理失败：{e}")
        task_manager.update_status(task_id, TaskStatus.FAILED, error=str(e))


def start_processing(task_id: str):
    """
    在 Streamlit 里调用这个函数，启动独立子进程处理任务。
    立即返回，不阻塞 UI。
    """
    import sys
    subprocess.Popen(
        [sys.executable, __file__, task_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ─────────────────────────────────────────────
# 命令行入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法：python ai_processor.py <task_id>")
        sys.exit(1)
    process_task_subprocess(sys.argv[1])
