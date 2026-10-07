# 听见妆容：受保护线上版部署

## 当前状态

代码与部署配置已准备；尚未创建云服务、推送仓库、公开网站或开启线上模型调用。账户连接、具体收费方案、部署目的地和正式开放需要项目所有者确认。

本机运行继续使用 `python3 start.py`；线上使用独立的 Flask/Gunicorn 入口，不再用本机 HTTP 服务承担公开流量。线上服务不读取 `.env.local`，密钥只来自云平台环境变量。

## 架构与使用

网页、图片资产与模型接口由同一个 Render Web Service 提供，通过同一个 HTTPS 链接访问。除了不含配置的 `/healthz` 健康探针，所有页面与接口均需团队账号和密码。浏览器会弹出原生账号密码窗口；账号默认为 `team`。密码和网站链接分开分享，勿写进链接或聊天公开频道。

这是有限人数试用版：一个共享账号，不是每位用户独立账号体系。每分钟账号限额合并计算，浏览器可能缓存 Basic 登录信息；共用设备请使用私密窗口并在使用后关闭全部私密窗口。撤销访问需更换服务端密码并重新部署，不保证关闭普通标签页即可退出。未来大量用户试用需改为可撤销的独立账号／邀请系统。

## 上线前需要确认

1. 有写入权限的 GitHub 仓库、分支；若原团队仓库无权限，使用自己的新仓库。
2. 是否接受 Render 付费单实例和 1GB 持久盘。具体价格以创建时账单界面为准，不自动购买。模板暂用 starter、Singapore；区域可在创建前调整。
3. 部署专用 OpenRouter key 的消费上限，建议先选择小额测试预算；不要直接复用无额度限制的日常 key。
4. 访问账号的分享范围及正式 HTTPS 域名。

持久盘是本模板的要求：SQLite 额度计数保存在 `/var/data`，重启后仍保留。Render 免费服务不能附加此持久盘，不能直接选免费并移除盘来冒充同等保护；如必须免费，需要另选受确认的持久额度存储。Render 持久盘只支持单实例，并且重新部署时会短暂中断服务。

## Render 配置

连接获授权的 GitHub 仓库，创建 Web Service（不是 Static Site）或从 `render.yaml` 创建 Blueprint。不要在尚未确认收费时点击最终创建。

| 设置 | 值 |
| --- | --- |
| 根目录 | 部署文件所在的仓库目录；若使用部署包上传至仓库根目录，则留空 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --config gunicorn.conf.py 'hosted:create_app()'` |
| Health Check | `/healthz` |
| 实例数／worker | 1 实例、1 worker；不要开启自动扩容 |
| 持久盘 | 1GB，挂载 `/var/data` |
| 自动部署 | 关闭；修复审核后主动部署 |

必须设置的环境变量：

| 变量 | 要求 |
| --- | --- |
| `PUBLIC_ORIGIN` | 实际 HTTPS 域名，如 `https://实际服务名.onrender.com`，不加末尾 `/` |
| `OPENROUTER_API_KEY` | 有消费上限的部署专用密钥；私下填写云控制台 |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash` |
| `HYL_ACCESS_USER` | 默认 `team` |
| `HYL_ACCESS_PASSWORD` | 独立随机访问密码，至少 24 个字符；不等于 API key |
| `HYL_SESSION_SECRET` | 独立随机值，至少 32 个字符；Blueprint 自动生成；后续不要随意轮换 |
| `HYL_QUOTA_DB` | `/var/data/hyl-quota.sqlite3` |
| `HYL_PERSISTENT_STORAGE` | 仅确认盘已挂载后设置 `1` |
| `HYL_AI_ENABLED` | 初次发布保持 `0`；验收、预算确认后改为 `1` 并部署 |
| `HYL_DAILY_MODEL_CALLS` | 默认 `120`，按 UTC 日期恢复 |
| `HYL_ACCOUNT_PER_MINUTE` | 默认 `3` 次图片检查，共享账号合并计算 |
| `HYL_GLOBAL_PER_MINUTE` | 默认 `12` 次图片检查 |

`PORT` 由平台提供。网站域名确定后更新 PUBLIC_ORIGIN；错误域名会安全拒绝访问，而不是放宽所有域名。健康探针通过不代表模型已配置或网站已完成验收。

## 保护规则

- HTTPS、准确 Host 和 Origin 校验；会话 CSRF token，不接受静态公用 token。
- Secure、HttpOnly、SameSite=Strict 会话 cookie；Basic 登录在服务端检查，不依赖前端隐藏按钮。
- 4MB 请求上限；只开放指定网页文件和 assets，配置／源代码不提供下载。
- 每次检查保守预留最多两次模型调用预算：每日 120 单位最多允许 60 次图片检查；失败和质量不通过也不退款，宁可提前停用。
- 单次仅处理一张照片；账号、全站分钟限额与每日预留额度写入 SQLite。数据库只含时间、计数和不可逆账号摘要，不含照片、模型返回、原始账号或 IP。
- 每分钟最多 180 次访问认证尝试（包括资产请求），防止无限猜测；达到后可能暂时影响全团队访问。
- 不记录访问日志或请求体；外部平台／提供商自己的日志策略需另行了解。本服务不落盘保存照片，不保证外部服务不留存。
- OpenRouter key 的消费硬上限是独立金额保护；图片请求次数上限并不等于美元上限。限制图片调用数也不保证提供商内部计费方式不变。

如果超过限额或真实服务关闭，用户必须主动选择预设演示，不能自动冒充真实结果。紧急情况先将 `HYL_AI_ENABLED=0` 并重新部署；如疑似 key 泄漏，立即在 OpenRouter 撤销部署 key，停止计费调用。不要只靠隐藏网站按钮。

## 上线验收与证据

代码自动化已验证：未登录不能访问页面／资产／配置；域名／来源／CSRF 错误拒绝；日预算跨应用重建仍生效；模型失败仍消耗保守预留；超大请求拒绝；紧急开关和脱敏错误返回；共享账号分钟限额及受保护下载。

上线后仍需实际测试：

1. 无登录打开正式链接，必须出现账号密码要求；错误密码不能调用模型。
2. 登录后全部图片、页面、JS 和导出可用。`/server.py`、`/.env.local` 返回 404。
3. 真实调用关闭时展示清晰原因；确认预算后开启，使用合成测试图完成检查和重拍。真实照片必须另有发送授权。
4. 同一浏览器同意与方向不确定时不能发送；新照片必须重新同意。
5. 手机移动网络打开 HTTPS，验收摄像头、中文语音、结束释放与辅助功能。
6. 检查 Render 错误日志和 OpenRouter 使用量，不保存照片或密钥截图。确认重启后预算仍在。
7. 记录正式 URL、部署提交版本、日期、已知限制后，才分享给队友和评委。

自动化不替代真正的 Render 反向代理、浏览器 Basic 登录、移动端和真实模型线上验收。

## 文件与官方参考

- `hosted.py`：受保护线上服务；复用 `server.py` 分析逻辑。
- `gunicorn.conf.py`：生产启动、端口、单 worker、等待时长及关闭访问日志。
- `requirements.txt`：本次安装并验证的锁定依赖版本。
- `render.yaml`：有持久盘的部署模板，初次不启用真实调用。
- `tests/test_hosted.py`：部署保护回归。
- `scripts/package_deployment.py`：仅打包明确允许的发布文件与网页资产，不包含密钥或工作目录。

[Render Flask 部署](https://render.com/docs/deploy-flask) · [持久盘](https://render.com/docs/disks) · [Blueprint 配置](https://render.com/docs/blueprint-spec) · [OpenRouter key 额度管理](https://openrouter.ai/docs/guides/overview/auth/management-api-keys)
