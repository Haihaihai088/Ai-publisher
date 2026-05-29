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

```bash
# 1. 安装依赖
pip install -r ai_publisher/requirements.txt

# 2. 安装 Playwright 浏览器
playwright install chromium

# 3. 配置环境变量
cp ai_publisher/.env.example ai_publisher/.env
# 编辑 .env，填入 OPENAI_API_KEY 等必要配置

# 4. 启动 Streamlit 界面
streamlit run ai_publisher/app.py
```

## 平台支持

| 平台 | 状态 | 说明 |
|------|------|------|
| 小红书 | 开发中 | 图文发布 |
| 知乎 | 开发中 | 文章/回答发布 |
| 贴吧 | 开发中 | 帖子发布 |
| 微信公众号 | 开发中 | 文章发布 |
