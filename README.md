# AI 多平台发布工具

基于 AI 的内容生成与多平台自动化发布工具。**本地运行，数据不上传第三方（AI 处理除外）。**

支持平台：小红书 | 知乎 | 贴吧 | 微信公众号

## 功能

- **AI 内容分析** — 提取主题、关键词、情感倾向，推荐热词
- **多平台适配** — 自动生成各平台适配标题、正文、标签
- **审核队列** — 发布前逐平台审查和编辑 AI 生成内容
- **一键发布** — 通过 Playwright 在各平台自动发布
- **任务看板** — 发布任务生命周期管理与状态追踪

## 安装

```bash
# 1. 进入目录
cd ai_publisher

# 2. 一键安装
./install.sh

# 3. 编辑 .env，填入 API Key
# OPENAI_API_KEY=sk-your-key-here
```

也可以手动安装：

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # 然后编辑 .env 填入 API Key
```

## 启动

```bash
./start.sh
# 浏览器打开 http://localhost:8080
```

或手动启动：

```bash
streamlit run app.py --server.port 8080 --server.address localhost
```

## 使用流程

```
新建任务 → 粘贴内容 + 选平台 + 上传图片
    ↓
AI 处理  → 自动分析内容 + 生成各平台适配文案
    ↓
审核队列 → 逐平台审查编辑标题正文
    ↓
一键发布 → Playwright 自动打开浏览器发布
    ↓
任务看板 → 查看发布结果和链接
```

## 平台说明

| 平台 | 发布方式 | Cookie 持久化 | 说明 |
|------|---------|-------------|------|
| 小红书 | 创作者平台图文发布 | 扫码一次，长期有效 | 自动追加话题标签 |
| 知乎 | 专栏文章发布 | 扫码一次，长期有效 | Draft.js 编辑器适配 |
| 贴吧 | 百度贴吧发帖 | 扫码一次，长期有效 | AI 推荐候选吧名 |
| 公众号 | 后台文章发布 | 每次均需扫码 | mp.weixin.qq.com 强制扫码 |

## 隐私说明

- **所有代码本地运行**，Streamlit 仅监听 `localhost`
- **数据文件本地存储**：任务、Cookie、图片均保存在本机，不会上传
- **AI API 调用**：只有原始内容会发送到 AI 服务商（默认 DeepSeek）进行内容生成
- **浏览器发布**：通过本地 Playwright 浏览器在您的电脑上完成操作

## 项目结构

```
├── ai_publisher/
│   ├── app.py              # Streamlit 主界面
│   ├── config.py           # 全局配置
│   ├── task_manager.py     # 任务状态机
│   ├── ai_processor.py     # AI 分析与内容生成
│   ├── publisher_runner.py # 发布流程编排
│   ├── publishers/         # 各平台发布器
│   │   ├── base.py         # 发布器基类
│   │   ├── xiaohongshu.py  # 小红书
│   │   ├── zhihu.py        # 知乎
│   │   ├── tieba.py        # 贴吧
│   │   └── wechat.py       # 公众号
│   ├── data/               # 运行时数据（不上传 Git）
│   └── requirements.txt
├── tests/                  # 单元测试
└── CLAUDE.md               # AI 开发规范
```

## 依赖

| 库 | 版本 | 用途 |
|------|------|------|
| streamlit | >=1.32 | Web UI 框架 |
| playwright | >=1.44 | 浏览器自动化 |
| openai | >=1.30 | AI API 调用（兼容 DeepSeek） |
| python-dotenv | >=1.0.0 | 环境变量管理 |
| pillow | >=10.0.0 | 图片处理 |

## API 配置

默认使用 DeepSeek（便宜，中文效果好）：

```bash
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

也可用 OpenAI：

```bash
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```
