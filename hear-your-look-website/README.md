# 听见妆容 · Hear Your Look

欧莱雅第二届美妆科技黑客松赛题三：社会与企业责任方向。首批目标用户是有基础化妆经验的低视力用户。先专注出门前的口红唇线检查。纯 HTML/CSS/JavaScript，无构建、框架或安装依赖，非赛事官方产品。

## 本地运行

```sh
cd ~/Documents/hear-your-look/hear-your-look-website
python3 -m http.server 8000 --bind 127.0.0.1
```

浏览器打开 http://localhost:8000。若该端口已有本项目的服务器，直接刷新。

## 当前流程与能力边界

准备照片 → 预设口红结果 → 一条行动指引 → 新照片或明确的无照片演示 → 预设复查 → 用户结束。

- 评委演示设置单独折叠，可选择首次外溢、无明显问题、无法判断；复查可选仍需确认（默认）、已改善、无法判断。设置不是用户自我诊断。
- 支持 JPG/PNG/WebP（10 MB 上限、40MP 分辨率上限）、有效图片解码、预览、移除。
- 摄像头预览与可取消的三秒拍摄倒计时，完成拍摄、暂停、结束或清除时释放摄像头。
- 本机实际计算照片整体亮度与尺寸，提供启发式提示；阈值未经用户/模型验证，不检测嘴唇、人脸、模糊或妆容，不是唇线识别的可判断性门槛。
- 没有照片时主操作不可提交，须明确选择无照片演示。复查要重新准备；不会固定返回改善。
- **所有口红判断、位置与复查结果均为预设，没有接入真实 AI。** 不上传照片、不持久保存照片；不能把模拟流程作为模型效果证明。
- 独立取景、中文位置指引和复查是待验证假设，未宣称优于现有产品、未提供用户研究结果或准确率。

## 文件

- index.html：主页、工作台、评委设置与项目介绍。
- style.css / polish.css：基础及 premium beauty-tech 设计，无障碍和响应式设置。
- analysis.js：`analyzeMakeup(image, options)` 预设适配器、结果校验和 `assessPhotoQuality(image)` 本机像素提示。
- app.js：照片、语音、摄像头、流程、异步取消、日志与偏好。
- polish.js：语速、高对比度和专注模式。

## 真实 AI 接入位置

`analysis.js` 的 `analyzeMakeup(image, options)`：image 为 Blob，明确的无照片演示为 null。options 含 scenario、recheck、recheckOutcome、previousResult。返回 `{mode, status, quality, smudging, title, guidance, evidence}`；status 为 adjust/clear/unchanged/uncertain。

后续增加同源服务端接口，由服务器调用 multimodal vision API，密钥只放服务端。不得把密钥写进 JS 或 GitHub。真实模式须取得照片发送同意、要求照片、校验返回结构、统一用户左右与图片方向、基于新照片和必要的上次观察做复查。当前 `validateMakeupResult` 仅允许 demo；添加真实模式时同时更新校验与 app.js 中来源、状态和朗读文案。不要仅替换一个请求就保留预设提示，也不要遇到 API 失败静默返回 mock。

目前的本机亮度阈值不能替代真实的脸部/嘴唇完整性检测或质量模型。

## 无障碍与隐私

skip link、原生键盘控件、可见 focus、步骤标题焦点、大字、高对比度、reduced motion、polite status 与语音异常文字回退。VoiceOver/TalkBack 用户可关闭自动播报，避免重复语音。偏好仅保存 voice/speed/large/contrast，可在浏览器站点数据中清除；不保存照片、历史或测试日志。

流程日志可手动导出 JSON，只含事件、用时、重听次数，无照片、姓名或原始文件名。它是个人流程记录，不是用户研究证据。清除按钮释放照片并清空本次记录。

完整 WCAG AA、真实设备摄像头、屏幕阅读器与目标用户试用仍需验证。研究与评审准备见 VALIDATION.md。
