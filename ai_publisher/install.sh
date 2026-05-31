#!/bin/bash
# install.sh - 首次运行执行一次
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt

echo "🌐 安装 Patchright 浏览器..."
patchright install chromium

echo "📁 创建数据目录..."
mkdir -p data/tasks data/cookies data/uploads

echo "⚙️  复制配置文件..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ 已创建 .env，请编辑填入你的 API Key"
else
    echo "✅ .env 已存在，跳过"
fi

echo ""
echo "🎉 安装完成！运行 ./start.sh 启动应用"
