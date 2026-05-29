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
import subprocess
from openai import OpenAI

import config
from config import TaskStatus
import task_manager


# ─────────────────────────────────────────────
# 初始化 OpenAI / DeepSeek 客户端
# ─────────────────────────────────────────────

def _get_client() -> OpenAI:
    if not config.AI_API_KEY:
        raise ValueError("未配置 AI API Key，请在 .env 文件中设置 OPENAI_API_KEY")
    return OpenAI(api_key=config.AI_API_KEY, base_url=config.AI_BASE_URL)


def _call(client: OpenAI, prompt: str, system: str = None) -> dict:
    """封装一次 AI 调用，返回解析后的 JSON dict"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=config.AI_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    raw = resp.choices[0].message.content
    # 防御：有些模型会在 json_object 模式下仍然加 ```json 包裹
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


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

# 各平台的写作规范（注入到统一 Prompt 中）
_PLATFORM_SPECS = {
    "xiaohongshu": """
小红书规范：
- title：20字以内，带1-2个 Emoji，制造好奇心或情绪共鸣，不能太广告
- body：300-500字，段落极短（每段1-3行），段落间空行，穿插 Emoji，结尾自然带入2-4个#话题标签，像真人在分享日常或经验
- tags：3-5个精准标签（不带#号）""",

    "zhihu": """
知乎规范：
- title：问题式或观点式，引发思考，40字以内，不用感叹号
- body：800-1500字，逻辑严密，可用"**小标题**"分段，语言专业但口语化，可引用数据或案例，结尾给出明确结论，不要"我认为""笔者认为"
- tags：2-3个知乎话题标签（不带#号）""",

    "tieba": """
贴吧规范：
- title：口语化帖子标题，可带疑问或感叹，50字以内
- body：300-600字，楼主视角，接地气，段落短，开头可用"说真的""来跟大家聊聊"等自然引入，结尾引导其他人跟帖讨论（如"你们怎么看？""有没有同款？"）
- tags：2-3个相关词（不带#号，用于搜索）""",

    "wechat": """
公众号规范：
- title：64字以内，可带数字和情绪词，有悬念感，避免标题党
- body：800-1200字，结构清晰，用【小标题】分段，语气亲切专业，结尾引导关注或留言，第一段要抓住读者注意力
（注意：body 中的换行用 \\n 表示）""",
}

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

def _build_output_schema(platforms: list[str]) -> str:
    """构建 JSON 输出结构的示例（用于 Prompt 中说明格式）"""
    schemas = {
        "xiaohongshu": '"xiaohongshu": {"title": "...", "body": "...", "tags": [...]}',
        "zhihu":       '"zhihu": {"title": "...", "body": "...", "tags": [...]}',
        "tieba":       '"tieba": {"title": "...", "body": "...", "tags": [...]}',
        "wechat":      '"wechat": {"title": "...", "body": "..."}',
    }
    return ",\n".join(schemas[p] for p in platforms if p in schemas)


def generate_all(content: str, platforms: list[str], analysis: dict) -> dict:
    """
    批量为所有平台生成内容。
    返回 dict，key 是平台 key，value 是该平台的内容 dict。
    """
    client = _get_client()

    # 只取指定平台的规范
    platform_specs = "\n".join(
        f"【{p}】{_PLATFORM_SPECS[p]}"
        for p in platforms if p in _PLATFORM_SPECS
    )
    output_schema = _build_output_schema(platforms)

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

    # 把贴吧的候选吧名从 analysis 注入到 ai_results 里，方便审核时读取
    if "tieba" in result and "tieba_candidates" in analysis:
        result["tieba"]["tieba_candidates"] = analysis["tieba_candidates"]
        result["tieba"]["tieba_selected"] = None  # 等用户审核时选择

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
