# AI 多平台发布工具

基于 AI 的内容生成与多平台自动化发布工具，支持小红书、知乎、贴吧、微信公众号等平台。

## 功能概述

- **AI 内容分析**：提取主题、关键词、情感倾向，推荐热词
- **多平台适配**：为不同平台自动生成适配内容（标题、正文、标签）
- **浏览器自动化发布**：通过 Playwright 在各平台自动发布内容
- **任务状态管理**：提供发布任务的生命周期管理与状态追踪
- **Web 操作界面**：基于 Streamlit 的可视化管理面板

## 依赖说明

| 库名 | 版本 | 用途 | 原创功能说明 |
|------|------|------|------------|
| streamlit | >=1.32 | Web UI 框架 | 自定义三Tab布局、任务状态轮询逻辑为原创实现 |
| playwright | >=1.44 | 浏览器自动化 | 各平台发布器的操作逻辑、重试策略为原创 |
| openai | >=1.30 | AI API 调用 | Prompt 设计、多平台适配逻辑（兼容 DeepSeek）为原创 |
| python-dotenv | >=1.0.0 | 环境变量管理 | 配置加载与类型安全访问封装 |
| pillow | >=10.0.0 | 图片处理 | 多平台图片预处理（尺寸/格式适配） |

## 项目结构

```
├── ai_publisher/
│   ├── config.py              # 全局配置管理
│   ├── task_manager.py        # 任务状态机
│   ├── ai_processor.py        # AI 分析 + 内容生成
│   ├── publisher_runner.py    # 发布流程编排
│   ├── publishers/            # 各平台发布器
│   │   ├── base.py            # 发布器基类
│   │   ├── xiaohongshu.py     # 小红书发布器
│   │   ├── zhihu.py           # 知乎发布器
│   │   ├── tieba.py           # 贴吧发布器
│   │   └── wechat.py          # 公众号发布器
│   ├── data/                  # 运行时数据
│   │   ├── tasks/             # 任务文件
│   │   ├── cookies/           # 登录凭证
│   │   └── assets/            # 静态资源
│   └── app.py                 # Streamlit 应用入口
├── tests/                     # 测试
├── docs/                      # 文档
└── CLAUDE.md                  # 开发规范
```

## 快速开始

### 方式一：一键脚本（推荐）

```bash
cd ai_publisher

# 首次使用：安装依赖 + 浏览器 + 配置
./install.sh
# 按提示编辑 .env 文件，填入 OPENAI_API_KEY

# 日常启动
./start.sh
# 浏览器打开 http://localhost:8080
```

### 方式二：手动安装

```bash
# 1. 安装依赖
pip install -r ai_publisher/requirements.txt

# 2. 安装 Playwright Chromium
playwright install chromium

# 3. 配置
cp ai_publisher/.env.example ai_publisher/.env
# 编辑 .env：
#   OPENAI_API_KEY=sk-your-key-here
#   OPENAI_BASE_URL=https://api.deepseek.com/v1   （默认 DeepSeek）
#   OPENAI_MODEL=deepseek-chat

# 4. 启动
cd ai_publisher && streamlit run app.py --server.port 8080
```

## 使用流程

```
1. 新建任务  →  粘贴内容 + 选择平台 + 上传图片
2. AI 处理   →  自动分析内容 + 生成各平台适配文案（后台子进程）
3. 审核队列  →  逐平台审查/编辑标题正文/选贴吧吧名
4. 一键发布  →  Playwright 自动打开浏览器发布
5. 任务看板  →  查看发布结果和链接
```

## 平台支持

| 平台 | 发布方式 | Cookie 持久化 | 说明 |
|------|---------|-------------|------|
| 小红书 | 创作者平台图文发布 | 扫码一次，长期有效 | 自动追加话题标签，最多20字标题 |
| 知乎 | 专栏文章发布 | 扫码一次，长期有效 | 含 Cookie 过期检测，支持 Draft.js 编辑器 |
| 贴吧 | 百度贴吧发帖 | 扫码一次，长期有效 | AI 推荐候选吧名，兼容新旧版编辑器 |
| 微信公众号 | 后台文章发布 | 每次发布均需扫码 | 因 mp.weixin.qq.com 强制微信扫码 |

## 常见问题

### 启动报错 "缺少 OPENAI_API_KEY"
`.env` 文件中未配置 API Key。确认 `ai_publisher/.env` 存在且 `OPENAI_API_KEY` 不为空。

### 登录后发布仍然提示"未登录"
Cookie 文件可能损坏或过期。在侧边栏重新点击"登录"，扫码后等待浏览器自动关闭。

### 发布超时
网络环境或被检测为自动化时可能超时。可调整 `config.py` 中 `BROWSER_SLOW_MO`（默认500ms）增加操作间隔。

### 子进程无响应
AI 处理或发布子进程可能卡死。手动删除 `data/tasks/` 中的 `.lock` 文件和对应任务 `.json` 文件即可恢复。

### DeepSeek vs OpenAI
默认使用 DeepSeek（便宜、中文效果好）。可在 `.env` 中改为 OpenAI：
```bash
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```
