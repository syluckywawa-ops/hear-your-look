# 本地真实模型检查配置

网页体验可直接使用 https://hear-your-look.onrender.com/#studio 。本文件仅适用于本地开发；公开部署见 [DEPLOYMENT.md](DEPLOYMENT.md)。GitHub Pages 不能运行 Python 服务端。

1. 安装并配置好可信 CA 证书的 Python 3.11 或更新版本。
2. 在仓库根目录创建 `.env.local`，填写自己的配置：

```dotenv
OPENROUTER_API_KEY=在本机填写自己的密钥
OPENROUTER_MODEL=google/gemini-2.5-flash
```

3. 在仓库根目录运行 `python3 start.py`，打开 http://127.0.0.1:8765 。若修改密钥，停止后重新启动；不要关闭 TLS 验证来绕过证书错误。
4. 选择真实检查，上传有权使用的照片，确认镜像方向并逐张同意发送。

不要提交 `.env.local` 或真实密钥。不要将本地开发服务暴露到公网。静态 `http.server` 只支持演示，不能调用模型。

模型通过同源服务端调用 OpenRouter，照片在内存中转发、不落盘保存；外部处理与留存受供应商政策约束。质量通过后会进行第二次外溢分析并产生调用费用。失败不自动回退到假结果；复查只观察新照片，不比较前后改善。模型能力未经系统验证。
