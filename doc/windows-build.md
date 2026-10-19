# Windows 自动构建

推送到 `master` / `main` 且涉及构建文件时，或在 GitHub 的 **Actions → Build Windows EXE → Run workflow** 手动执行，会在 Windows Server 2022 x64、Python 3.13 和 Node.js 22 上构建。

成功后在对应运行的 **Artifacts** 中下载 `wx-assist-windows-x64`，解压并运行 `wx-assist_no_rag.exe`。附件含 exe 的 SHA-256、源码提交号、实际 Python 依赖版本、组件来源及打包后的冒烟测试结果。没有自动发布 Release，也没有自动安装到本机。

## 版本范围

构建沿用项目精简版（不含 ChromaDB / fastembed / RAG 模型），保留微信密钥自动提取及图片解密资源，不是去掉自动取密钥的纯源码版本。

Windows 需要 WebView2 Runtime；WASM 图片处理仍按原程序要求使用系统 `node`，建议安装 Node.js 22。没有微信客户端/真实微信数据库的 CI 只能验证打包运行时、DLL 加载、静态资源及本地 HTTP API，不能证明用户电脑上的微信版本与 DLL 取密钥逻辑兼容，也未验证完整 GUI 交互。

## DLL 和 WASM 从哪里来

Git 仓库缺少 `lib/wx_key.dll` 与 WASM 文件。构建通过 `scripts/fetch_native_assets.py` 从原作者 [wx-assist v1.7.0](https://github.com/MaleleStudySpace/wx-assist/releases/tag/v1.7.0) 的 `wx-assist_no_rag.exe` **静态提取**以下 4 个文件，不运行原作者的 exe：

- `lib/wx_key.dll`
- `lib/wasm/wasm_decrypt_service.js`
- `lib/wasm/wasm_video_decode.js`
- `lib/wasm/wasm_video_decode.wasm`

原 exe 及每个组件的 SHA-256 均固定在 `scripts/native-assets.json`。任何变动都会使构建失败，不会静默下载最新版。原包中的测试脚本、调试数据、解密示例、WAT 文件以及其他 DLL 均不提取，也不作为应用源码使用。

`wx_key.dll` 大小为 195,072 字节，SHA-256 为 `9a2f2c6a09a3219afa4748a5e7e513d99c607173c3112c5afcc888996b98248c`，为 Windows x64 PE。静态导出表含本项目需要的 `InitializeHook`、`PollKeyData`、`CleanupHook`；导入表未发现 WinHTTP、WinINet、Winsock 网络库，ASCII/UTF-16 字符串检查未发现远程 URL。REA/Hopper 对初始化及轮询导出进行了静态检查（概要证据 `ev_dca292496d7c78fc63e250bc191b6750b81efdaed5a5432840180ecbd7d7ec49`；轮询证据 `ev_3ec180d250126580f5f94b2fea862a733516c476b8e96e23c76eb11930841b96`）。这些是有限范围的静态证据，不能保证二进制运行时没有动态加载、注入后行为或隐藏的网络能力。

原 `ycccccccy/wx_key` 仓库在本次核查时仅有删除代码后的 README，WeFlow 的 Releases 也为空；因此当前采用能够取得、可追溯且与本项目发布版本相同的组件来源。此做法不意味着这些组件已经恢复开源或获得可复现的源码构建链。

## 本地隐私边界

新创建配置默认 `AUTO_CHECK_UPDATE=false`，避免启动时自动访问原作者 GitHub 更新服务；已有 `.env` 不会被覆盖。手动点击检查更新仍会访问原作者仓库，接受安装更新会切换成原作者的二进制。

没有发现足以认定隐藏窃密服务的源码证据，但本程序不是强制离线软件。启用云端 AI 会发送对应聊天等上下文，语音、搜索、微信/飞书/QQ 推送、公众号/图片下载会与各自服务通信；首次引导后的功能演示还包含远程示例图片。局域网鉴权等已知漏洞也未在这次构建工作中修复。只打算本机使用时不要打开局域网访问，也不要把控制台端口映射到公网。

## 在 Windows 上手动构建

```powershell
python -m pip install -r requirements-build.txt
npm --prefix ui ci
npm --prefix ui run build
python scripts/fetch_native_assets.py
python -m PyInstaller --clean --noconfirm build.spec
python scripts/smoke_windows_exe.py dist/wx-assist_no_rag.exe
```

获取组件必须能访问 GitHub。前端使用已提交的 npm lockfile；Python 仍遵循原项目大部分下限约束，并把每次实际安装版本随产物记录，尚未形成所有传递依赖均带哈希的跨次完全可复现构建。
