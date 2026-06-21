# X / Twitter Platform Workflow

适用场景：用户要求搜 X、找推文、读 tweet、收集 X 资讯、根据关键词在 X 上找资料。

X 是特殊平台。不要用普通 web search、公开搜索片段、单条 OG 片段冒充 X 搜索完成。用户要 X，就必须实际跑 `search-platform x` 或 MCP `search_platform(platform="x")`。

## Standard Provider

默认走 `edge_cdp_profile`。

这是 pyaireader 自己管理的专用 Edge profile，默认目录：

```text
%USERPROFILE%\.pyaireader\edge-cdp-profiles\default
```

默认端口是 `9334`。第一次让用户在这个专用 Edge 窗口里登录一次，后续复用同一份登录态。不要打开或复用用户日常 Edge 窗口，避免抢焦点、串窗口、污染用户正在使用的标签页。

`persistent_profile` 不是 X 的标准路径。它只作为备用诊断路径；如果平台登录或 OAuth 拒绝这类自动化 profile，不要继续在这条路上反复让用户登录。

## 1. Preflight

```powershell
uv run pyaireader browser-status --provider edge_cdp_profile --pretty
```

如果 `active_provider=edge_cdp_profile`，继续做登录态 smoke。

`browser-status` 里的 cookie 诊断只能作辅助参考。专用 Edge 窗口运行时，Cookies 数据库可能被 Edge 锁住，出现 `x_cookie_db_unreadable` 或 `logged_in=false`。这不是登录失败的充分证据。是否真的登录成功，以后面的真实 `search-platform x` smoke 为准。

如果 `available=false`，先启动专用 profile：

```powershell
uv run pyaireader edge-cdp-profile-launch --url https://x.com/home --pretty
```

如果返回 `edge_executable_not_found`，说明这台机器没找到 Edge 可执行文件，不能继续跑 X 搜索。需要先修 Edge 路径。

## 2. First-Time Login

第一次使用、登录态过期、搜索结果显示登录页、或不确定是否已登录时，打开 pyaireader profile 让用户登录：

```powershell
uv run pyaireader browser-login x --provider edge_cdp_profile --pretty
```

登录规则：

- 告诉用户：请在打开的专用 Edge 窗口里登录 X，登录完成后保持窗口开着，回复“已登录”。
- 给足时间。不要刚打开窗口就判失败；命令超时至少按 10 分钟估算。
- 用户还没说登录完成，不能继续判定失败。
- 用户说已登录后，再跑 preflight 和 smoke。
- `browser-login` 返回 `success=true` 只代表专用 Edge-CDP profile 已打开；必须检查 `browser-status` 可连，再用真实 `search-platform x` smoke 确认 X 登录态接上。

## 3. Login Smoke

用低成本搜索确认真的能访问 X，不是登录页、空页、JS shell：

```powershell
$env:PYAIREADER_BROWSER_PROVIDER='edge_cdp_profile'
uv run pyaireader search-platform x "AI infrastructure" --auth-strategy user_session_fallback --max-results 3 --max-pages 1 --time-range 7d --pretty
```

失败处理：

- 读到登录页：继续引导用户登录。
- 返回 `x_login_required`：说明打开的是登录页，不能当成搜索无结果。
- 读到空页或 X shell：报告 smoke 未通过，不要降级。
- 命令报浏览器 provider 不可用：先运行 `edge-cdp-profile-launch`，不要改用日常 Edge。

## 4. Search

```powershell
$env:PYAIREADER_BROWSER_PROVIDER='edge_cdp_profile'
uv run pyaireader search-platform x "<query>" --auth-strategy user_session_fallback --max-results 20 --max-pages 2 --time-range 7d --follow-links same_platform_and_article_links --pretty
```

查询词要贴近用户任务。例：AI 基建股资讯。

```text
AI infrastructure stocks OR data center power OR VRT OR ETN OR GEV OR PWR OR AAOI OR LITE OR COHR OR MRVL
```

## 5. Fallback Paths

只有这些情况才考虑其他路径：

- 用户明确要求复用当前日常 Edge 登录态。
- 专用 Edge-CDP profile 无法启动，且用户接受临时方案。
- 需要诊断浏览器自动化问题。

普通 CDP 命令：

```powershell
uv run pyaireader edge-cdp-launch --pretty
uv run pyaireader browser-status --pretty
```

如果仍然没有 CDP，不要解释半天。回到标准 `edge_cdp_profile` 登录流程，或报告平台任务未完成。

## 6. Filter

只收这些结果：

- 有明确正文或推文文本
- 有作者、时间、URL
- 跟任务关键词直接相关
- 信息密度高，最好包含公司、产业链、数据、事件、观点或链接文章

剔除这些结果：

- 只有 X shell、登录页、空页面
- 只有一小段断裂片段
- 只有情绪喊单，没有事实或逻辑
- 重复转述同一条新闻

## 7. Output Contract

用户要“收集资讯”时，输出必须包含：

- 使用的 provider：`edge_cdp_profile` / `cdp` / `persistent_profile` / 未接入
- 检索词和时间范围
- 高价值结果列表：标题或首句、作者/来源、URL、为什么有价值、关键内容摘要
- 总结：主线、分歧、可继续跟踪的公司/关键词
- 质量说明：哪些是完整读取，哪些是弱读取或失败

如果 X 搜索没有实际跑通，最终答案不能说“完成”。必须写：

```text
这轮没有完成 X 搜索，原因是 ...
已完成的部分是 ...
要完成原任务，还需要 ...
```
