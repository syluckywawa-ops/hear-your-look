# 听见妆容：受保护线上版部署

## 评委免登录模式

设置 `HYL_PUBLIC_ACCESS=1` 后，网页、预设演示、配置接口和真实检查均无需账号或访问码。默认 `0` 仍保留原来的团队密码保护；保留强会话密钥。公开网站地址为 `https://hear-your-look.onrender.com`。开启匿名访问是有意的公开展示，不是身份验证。

匿名检查仍要求发送同意、正确 HTTPS 来源和浏览器会话 CSRF token；这些措施不能阻止使用脚本的陌生人，真正的消费保护来自服务端持久限额、并发限制以及 OpenRouter 的专用 key 总额上限。所有匿名访问者共享一个检查限额，换浏览器不会重置。公共页面不依赖额度数据库，数据库不可用时 API 停止，不会降级为不限额调用。

本次公开版目标配置：`HYL_DAILY_MODEL_CALLS=20`、`HYL_ACCOUNT_PER_MINUTE=3`、`HYL_GLOBAL_PER_MINUTE=3`、单任务并发。每次检查保守预留两次模型调用，因此每天最多接受 10 次检查（首次检查和复查各算一次），按 UTC 日期重置；模型失败或照片不合格不退还预留额度。整个网站共用这些额度，不是每位评委各有一份。

用户已选择不设置此次建议的 `$1` key 总额上限。当前只使用每天重置的模型调用限额，不能将其当作累计美元保证；OpenRouter 现有余额仍可能随日期持续消耗。建议日后为 **Render 实际使用的专用 key** 设置不自动重置的美元总额上限。如果该 key 还用于本地或其他项目，那些调用不受本网站限额约束。不得自动充值。额度耗尽后不声称成功，提示使用预设演示。公开模式代码正在准备，线上匿名访问和模型验收完成前不得宣称公开 AI 已验证。

新增 4 项匿名访问测试，现共 49 项 Python 测试；真实云端模型调用须另行获得照片发送同意并记录结果。

## 当前状态

受保护部署版已上传至团队仓库的 `beauty-accessibility-upgrade` 分支，当前改为免费托管方案：Render Free + Upstash Free。尚未完成云端数据库连接、创建网站或开启线上模型调用。上传代码不等于网站已经上线。

本机运行继续使用 `python3 start.py`；线上使用独立的 Flask/Gunicorn 入口，不再用本机 HTTP 服务承担公开流量。线上服务不读取 `.env.local`，密钥只来自云平台环境变量。

## 架构与使用

网页、图片资产与模型接口由同一个 Render Web Service 提供，通过同一个 HTTPS 链接访问。除了不含配置的 `/healthz` 健康探针，所有页面与接口均需团队账号和密码。浏览器会弹出原生账号密码窗口；账号默认为 `team`。密码和网站链接分开分享，勿写进链接或聊天公开频道。

这是有限人数试用版：一个共享账号，不是每位用户独立账号体系。每分钟账号限额合并计算，浏览器可能缓存 Basic 登录信息；共用设备请使用私密窗口并在使用后关闭全部私密窗口。撤销访问需更换服务端密码并重新部署，不保证关闭普通标签页即可退出。未来大量用户试用需改为可撤销的独立账号／邀请系统。

## 上线前需要确认

1. 有写入权限的 GitHub 仓库、分支；若原团队仓库无权限，使用自己的新仓库。
2. Render 选择 Free 单实例、Singapore、不附加磁盘；Upstash 选择 Free，不选择按量付费、自动升级或付费附加项。创建页面必须明确显示 $0。
3. 部署专用 OpenRouter key 的消费上限，建议先选择小额测试预算；不要直接复用无额度限制的日常 key。
4. 访问账号的分享范围及正式 HTTPS 域名。

免费版不使用 Render 本地 SQLite 保存额度。免费服务的本地文件会在休眠、重启或重新部署时丢失；每日预算和分钟限额改存 Upstash Redis，以原子 Lua 脚本预留，进程重启不会清空。数据库断网、超额、返回错误或无凭据时停止请求，不回退到内存／临时数据库。

## 免费方案的边界（2026-10-07 核对）

- Render Free：闲置 15 分钟后休眠，再次打开可能需要约一分钟；每个工作区每月共 750 小时。流量、构建和外部请求还有平台限制，不保证始终在线。不要设置持续唤醒任务来绕过免费限制。
- 为避免超额收费，不添加支付方式；如果账户已有支付方式，先核实工作区账单与支出限制。Render 官方说明：没有支付方式时，超额流量会暂停免费服务，超额构建会停用新构建；有支付方式可能计费。不能仅因选了 Free 就承诺总账单永远为零。
- Upstash Free 当前包含 256 MB、每月 500K 命令、10 GB 流量。保持 Free，不填写银行卡，不升级到 Pay as You Go／Fixed；Lua 内部命令也可能计入用量，必须看控制台统计。免费库长期闲置可能归档；使用前确认有效。
- 不使用匿名、72 小时到期的临时 Redis。数据库须由团队账户创建和管理，以免比赛前自动过期。
- 免费托管不免除 OpenRouter 模型费用；默认 `HYL_AI_ENABLED=0`，确认部署专用 key 金额上限后才打开。数据库只存时间、计数、随机请求 ID、账号摘要，不发送照片、模型内容或模型 key 给 Upstash。

## 先建立免费额度数据库

在 Upstash 控制台登录或注册，接受条款必须由所有者确认；创建 Redis 时选 Free，确认 $0，不添加支付方式。保存 HTTPS REST URL 和普通 REST token（不是 readonly token）。只将它们填入 Render 的服务端环境变量，不上传 GitHub，不贴到聊天。

保持同一数据库与默认计数前缀 `hyl:{hear-your-look}`。更换 token 不会清空日预算；更换数据库、清空数据库或更换前缀会丢失计数，发生这些操作时保持真实模式关闭直到下一 UTC 日或另行核实已用金额。

## Render 配置

连接获授权的公开 GitHub 仓库，创建 Web Service（不是 Static Site）或从 `render.yaml` 创建 Blueprint。确认 Free／$0 和无付费磁盘后才能最终创建。

| 设置 | 值 |
| --- | --- |
| 根目录 | 部署文件所在的仓库目录；若使用部署包上传至仓库根目录，则留空 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --config gunicorn.conf.py 'hosted:create_app()'` |
| Health Check | `/healthz` |
| 实例数／worker | 1 实例、1 worker；不要开启自动扩容 |
| 方案／磁盘 | Free；不添加磁盘 |
| 自动部署 | 关闭；修复审核后主动部署 |

必须设置的环境变量：

| 变量 | 要求 |
| --- | --- |
| `PUBLIC_ORIGIN` | 实际 HTTPS 域名，如 `https://实际服务名.onrender.com`，不加末尾 `/` |
| `OPENROUTER_API_KEY` | 初次关闭真实模式时可以不填；启用前填有金额上限的部署专用密钥 |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash` |
| `HYL_ACCESS_USER` | 默认 `team` |
| `HYL_ACCESS_PASSWORD` | 独立随机访问密码，至少 24 个字符；不等于 API key |
| `HYL_SESSION_SECRET` | 独立随机值，至少 32 个字符；Blueprint 自动生成；后续不要随意轮换 |
| `HYL_QUOTA_BACKEND` | `upstash` |
| `UPSTASH_REDIS_REST_URL` | 自己免费库的 `https://实际端点.upstash.io`，不是 redis:// 连接串 |
| `UPSTASH_REDIS_REST_TOKEN` | 普通 REST token，服务器端秘密，不是 readonly token |
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
- 单次仅处理一张照片；账号、全站分钟限额与每日预留额度写入 Upstash Redis，以数据库时间为准，原子检查并预留两单位。数据库只含时间、计数、随机 ID 和不可逆账号摘要，不含照片、模型返回、原始账号或 IP。日计数 TTL 为两天、滚动分钟记录 TTL 为两分钟。
- 每分钟最多 180 次访问认证尝试（包括资产请求），防止无限猜测；达到后可能暂时影响全团队访问。
- 不记录访问日志或请求体；外部平台／提供商自己的日志策略需另行了解。本服务不落盘保存照片，不保证外部服务不留存。
- OpenRouter key 的消费硬上限是独立金额保护；图片请求次数上限并不等于美元上限。限制图片调用数也不保证提供商内部计费方式不变。

如果超过限额或真实服务关闭，用户必须主动选择预设演示，不能自动冒充真实结果。紧急情况先将 `HYL_AI_ENABLED=0` 并重新部署；如疑似 key 泄漏，立即在 OpenRouter 撤销部署 key，停止计费调用。不要只靠隐藏网站按钮。

## 上线验收与证据

代码自动化已验证：45 项 Python 测试通过（含 11 项免费存储测试），原有前端断言与 Gunicorn 本地启动检查另行运行。Redis 的实际 Lua 脚本在本地 fakeredis/lupa 中执行，覆盖并发原子预留、日预算、滚动分钟限额、重建客户端、UTC 日切换和断网拒绝调用。没有把本地模拟当作已经完成云端 Upstash 验收。

上线后仍需实际测试：

1. 无登录打开正式链接，必须出现账号密码要求；错误密码不能调用模型。
2. 登录后全部图片、页面、JS 和导出可用。`/server.py`、`/.env.local` 返回 404。
3. 真实调用关闭时展示清晰原因；确认预算后开启，使用合成测试图完成检查和重拍。真实照片必须另有发送授权。
4. 同一浏览器同意与方向不确定时不能发送；新照片必须重新同意。
5. 手机移动网络打开 HTTPS，验收摄像头、中文语音、结束释放与辅助功能。
6. 检查 Render 错误日志、Upstash 用量和 OpenRouter 使用量，不保存照片或密钥截图。确认真实云端 Lua 支持、休眠／重启后预算仍在；数据库断网时不能调用模型。
7. 记录正式 URL、部署提交版本、日期、已知限制后，才分享给队友和评委。

自动化不替代真正的 Render 反向代理、浏览器 Basic 登录、移动端和真实模型线上验收。

## 文件与官方参考

- `hosted.py`：受保护线上服务；复用 `server.py` 分析逻辑。
- `redis_quota.py`：Upstash HTTPS REST、原子计数、8 秒超时、禁重定向／自动重试；失败不放行。
- `gunicorn.conf.py`：生产启动、端口、单 worker、等待时长及关闭访问日志。
- `requirements.txt`：本次安装并验证的锁定依赖版本。
- `render.yaml`：Free + Upstash 部署模板，无付费磁盘，初次不启用真实调用。
- `tests/test_hosted.py`：部署保护回归。
- `tests/test_redis_quota.py`、`requirements-test.txt`：只用于开发机的 Redis/Lua 模拟与 REST 合约测试，不用于生产依赖。
- `scripts/package_deployment.py`：仅打包明确允许的发布文件与网页资产，不包含密钥或工作目录。

[Render Flask 部署](https://render.com/docs/deploy-flask) · [Render 免费限制](https://render.com/docs/free) · [Upstash 免费额度](https://upstash.com/pricing/redis) · [Upstash REST](https://upstash.com/docs/redis/features/restapi) · [OpenRouter key 额度管理](https://openrouter.ai/docs/guides/overview/auth/management-api-keys)

旧的 SQLite 后端仅留作本地回归和经另行确认的付费持久盘方案；默认免费模板指定 `upstash`，不得在 Free 服务上使用临时 SQLite 冒充持久保护。
