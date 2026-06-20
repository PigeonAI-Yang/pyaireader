# pyaireader MCP 正规化方案

这份文档记录 `pyaireader` MCP 层的升级方案和 v0.3 落地状态。

目标不是重写抓取能力，也不是把工具做复杂，而是让主流 MCP 客户端更容易正确调用它：

- 调用前知道每个 tool 会返回什么。
- 调用后能直接拿到结构化结果，不需要再从文本里解析 JSON。
- 客户端能知道哪些 tool 只读，哪些 tool 会清 cache。
- 除 stdio 之外，提供标准 MCP Streamable HTTP endpoint。
- 为后续官方 registry / marketplace 发布准备干净的元数据。

## 当前状态

当前 `pyaireader` 已经是一个可用的本地 MCP tools server。

已具备：

- `stdio` MCP transport。
- `reader_health`
- `read_url`
- `read_url_for_ai`
- `batch_read_urls`
- `batch_read_urls_for_ai`
- `inspect_url`
- `clear_reader_cache`
- 稳定的业务 schema version，例如 `pyaireader.read_result.v1`。
- 标准错误载荷：`success=false` + `error.code/message/retryable/suggested_next_action`。

v0.2 留下的 MCP 合同缺口：

- MCP tool list 里的显式 `outputSchema`。
- tool call 结果里的 `structuredContent`。
- tool annotations，例如 `readOnlyHint`、`destructiveHint`。
- MCP Streamable HTTP transport。
- 可提交到官方 registry / marketplace 的 `server.json` 元数据。

v0.3 已落地：

- 给 MCP tools 补显式 `outputSchema`。
- 让 tool call 返回 `structuredContent`，同时保留文本 JSON。
- 给 tools 补 `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`。
- 增加 `pyaireader-mcp-http`，提供本机 MCP Streamable HTTP endpoint。
- 在 PyPI 发布前，只保留 registry metadata candidate，不提交官方 registry。

## 原则

先把 MCP 边界打硬，再考虑发布。

顺序必须是：

```text
outputSchema -> structuredContent -> tool annotations -> Streamable HTTP -> registry metadata
```

原因很简单：registry / marketplace 描述的是别人怎么安装、启动、调用这个 server。如果前面的 tool contract 和 transport 还没稳定，先写元数据只会制造过期说明。

## 非目标

这轮不做：

- 不重构 reader pipeline。
- 不改抓取策略。
- 不新增内容抽取能力。
- 不删除兼容 tool 名称。
- 不默认把本机服务暴露到公网。
- 不把普通 HTTP API 伪装成 MCP HTTP。

`pyaireader-api` 仍然是普通业务 HTTP API。

新增的 MCP HTTP 入口必须是单独的 MCP Streamable HTTP transport。

## 1. explicit outputSchema

### 问题

现在 MCP tool 返回的是裸 `dict`。

这能跑，但客户端只能看到比较松的返回形状。Agent 往往需要从 tool 描述和返回样例里猜字段，容易出现：

- 不知道 `quality` 是否一定存在。
- 不知道失败时 `error` 的结构。
- 不知道 `evidence`、`numbers`、`dates`、`entities` 的字段名。
- 不知道 `reader_health` 返回哪些能力信息。

### 方案

新增 MCP 边界层 schema 文件：

```text
src/pyaireader/mcp/schemas.py
```

用 Pydantic 定义 MCP 输出模型：

- `ReaderHealthMcpResult`
- `ReadUrlMcpResult`
- `BatchReadUrlsMcpResult`
- `InspectUrlMcpResult`
- `ClearCacheMcpResult`
- `ReaderErrorMcpPayload`
- `ReaderQualityMcpPayload`
- `ReaderTraceMcpPayload`
- `EvidenceSnippetMcpPayload`
- `NumberMentionMcpPayload`
- `DateMentionMcpPayload`
- `EntityMentionMcpPayload`
- `FinancialEventMcpPayload`

不要急着把底层 dataclass 全部改掉。

底层继续返回现有 dict，MCP 层做一次边界转换：

```python
payload = get_pipeline().read(request).to_dict()
return ReadUrlMcpResult.model_validate(payload)
```

### 依赖要求

当前本机已验证的 SDK 版本支持这些能力：

```text
mcp 1.28.0
```

建议把 `pyproject.toml` 从宽松依赖：

```toml
mcp>=1.0.0
```

收紧成：

```toml
mcp>=1.28.0
pydantic>=2.0.0
```

### 验收

真实 MCP `tools/list` 里，每个核心 tool 都应该出现 `outputSchema`。

必须覆盖：

- `reader_health`
- `read_url`
- `batch_read_urls`
- `inspect_url`
- `clear_reader_cache`

兼容 alias：

- `read_url_for_ai`
- `batch_read_urls_for_ai`

它们的 `outputSchema` 应该和对应短名一致。

## 2. structuredContent

### 问题

现在 tool call 结果主要表现为文本内容块，里面包一段 JSON。

这对老客户端兼容，但对现代 MCP 客户端不够友好。客户端应该能直接从 `structuredContent` 取结构化对象。

### 方案

在 MCP tool 注册时启用结构化输出：

```python
@mcp.tool(structured_output=True)
def read_url(...) -> ReadUrlMcpResult:
    ...
```

所有主要读取 tool 都返回 Pydantic 模型，而不是裸 dict。

需要覆盖：

- `reader_health`
- `read_url`
- `read_url_for_ai`
- `batch_read_urls`
- `batch_read_urls_for_ai`
- `inspect_url`
- `clear_reader_cache`

### Markdown 返回边界

`return_format=markdown` 不应该让同一个 MCP tool 的返回形状变来变去。

建议：

- MCP `read_url` 默认并长期保证结构化 JSON 返回。
- CLI 可以继续支持 Markdown 输出。
- 如确实需要 MCP Markdown，后续单独新增 `read_url_markdown`，不要污染 `read_url` 的结构化 contract。

### 验收

真实 MCP `tools/call read_url` 结果必须同时包含：

- `structuredContent`
- `content[0].text`

保留 `content[0].text` 是为了兼容老客户端。

`structuredContent` 必须符合 `outputSchema`。

失败场景也要返回结构化对象：

```json
{
  "success": false,
  "error": {
    "code": "...",
    "message": "...",
    "retryable": false,
    "suggested_next_action": "..."
  }
}
```

## 3. tool annotations

### 问题

客户端现在只能通过 tool 名称和描述猜副作用。

这对 `clear_reader_cache` 尤其不清楚，因为它不是读取网页，而是会修改本地 cache。

### 方案

使用 MCP SDK 的 `ToolAnnotations`。

建议标注如下：

| Tool | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | 原因 |
| --- | --- | --- | --- | --- | --- |
| `reader_health` | true | false | true | false | 只读本机配置和能力信息 |
| `read_url` | true | false | false | true | 读取公网 URL，可能写 cache，网页内容会变化 |
| `read_url_for_ai` | true | false | false | true | `read_url` 兼容 alias |
| `batch_read_urls` | true | false | false | true | 读取多个公网 URL，可能写 cache |
| `batch_read_urls_for_ai` | true | false | false | true | `batch_read_urls` 兼容 alias |
| `inspect_url` | true | false | false | true | 访问公网 URL 并返回诊断 |
| `clear_reader_cache` | false | true | false | false | 会删除本地 cache |

注意：`read_url` 虽然不修改远端网页，但会访问公网，也可能写本地 cache。它不是纯粹的 deterministic 只读函数，所以 `idempotentHint=false` 更诚实。

### 验收

真实 MCP `tools/list` 里，每个 tool 都应该带 `annotations`。

重点检查：

- `read_url.annotations.openWorldHint == true`
- `clear_reader_cache.annotations.destructiveHint == true`
- `reader_health.annotations.idempotentHint == true`

## 4. MCP Streamable HTTP endpoint

### 问题

当前 MCP 入口是 stdio。

stdio 适合 Codex Desktop、Codex CLI、Claude Code CLI 这类本机 Agent。但有些 MCP host 或集成场景更适合 HTTP transport。

普通 `pyaireader-api` 不是 MCP HTTP。它只是业务 API。

### 方案

新增 MCP HTTP entry point：

```toml
[project.scripts]
pyaireader-mcp-http = "pyaireader.mcp.server:http_main"
```

`src/pyaireader/mcp/server.py` 增加：

```python
def main() -> None:
    server = _build_server(transport_label="stdio")
    server.run(transport="stdio")


def http_main() -> None:
    server = _build_server(transport_label="streamable-http")
    server.run(transport="streamable-http")
```

实际 endpoint path 通过 `FastMCP(..., streamable_http_path="/mcp")` 设置。当前 SDK 的 `run(transport="streamable-http")` 不读取 `mount_path` 参数。

`reader_health.transport` 根据启动方式返回：

```text
stdio
streamable-http
```

### 默认监听

默认只监听本机：

```text
127.0.0.1
```

不要默认监听：

```text
0.0.0.0
```

原因：这是一个能读取公网 URL、能写本地 cache 的本机工具，不该默认暴露到局域网或公网。

实现上要拒绝非 loopback host，例如 `0.0.0.0`。

### 安全要求

Streamable HTTP 必须做本地防护：

- 默认 host 为 `127.0.0.1`。
- MCP endpoint 为 `/mcp`。
- 检查 Origin，默认只允许 localhost / 127.0.0.1 / ::1。
- 文档明确不要直接暴露到公网。

### 启动方式

```powershell
uv run pyaireader-mcp-http --host 127.0.0.1 --port 8000
```

预期 endpoint：

```text
http://127.0.0.1:8000/mcp
```

### 验收

必须跑真实 Streamable HTTP smoke test：

- initialize
- tools/list
- tools/call reader_health
- tools/call read_url

检查：

- `/mcp` 可用。
- `reader_health.transport == "streamable-http"`。
- `tools/list` 能看到 `outputSchema` 和 `annotations`。
- `tools/call` 能返回 `structuredContent`。

## 5. 官方 registry / marketplace 元数据

### 前置条件

这一步必须放最后。

提交 registry / marketplace 前，至少满足：

- stdio MCP 可用。
- Streamable HTTP 可用。
- outputSchema 已稳定。
- structuredContent 已稳定。
- annotations 已稳定。
- README 没有本机路径。
- README 没有内部开发文档链接。
- 包发布方式已确定。

如果还没有发布到 PyPI，不要声称可通过 PyPI 安装。

### 方案

PyPI 发布之后，再新增根目录文件：

```text
server.json
```

初始元数据建议：

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.pigeonai-yang/pyaireader",
  "title": "pyaireader",
  "description": "Read public web pages locally for AI agents, extracting clean text and key content while removing page UI noise.",
  "repository": {
    "url": "https://github.com/PigeonAI-Yang/pyaireader",
    "source": "github"
  },
  "version": "0.3.0",
  "packages": [
    {
      "registryType": "pypi",
      "registryBaseUrl": "https://pypi.org",
      "identifier": "pyaireader",
      "version": "0.3.0",
      "runtimeHint": "uvx",
      "transport": {
        "type": "stdio"
      }
    }
  ]
}
```

如果 PyPI 还没发布，只保留候选文件：

```text
docs/registry-server-json-candidate.json
```

不要把它提交成根目录 `server.json` 冒充可安装。

### README 更新

发布后 README 应该补：

- MCP stdio 安装方式。
- MCP Streamable HTTP 启动方式。
- registry / marketplace 安装方式。
- 明确普通 HTTP API 与 MCP HTTP 的区别。

## 测试清单

每次实现后都要跑：

```powershell
uv run pytest -q
uv run ruff check .
git diff --check
```

还要跑真实 MCP 验证：

```text
stdio tools/list
stdio tools/call reader_health
stdio tools/call read_url
streamable-http initialize
streamable-http tools/list
streamable-http tools/call reader_health
streamable-http tools/call read_url
```

文档扫描：

```text
不能出现本机绝对路径
不能链接内部开发文档
不能把普通 HTTP API 写成 MCP HTTP
不能声称未发布的 PyPI / registry 能安装
```

## 交付标准

这轮完成后，`pyaireader` 的 MCP 层应该达到：

- 主流 MCP host 能通过 `tools/list` 直接理解返回结构。
- Agent 不需要猜 JSON 字段。
- 调用结果同时兼容新老 MCP 客户端。
- 客户端能识别只读 tool 和 destructive tool。
- stdio 与 Streamable HTTP 两种 MCP transport 都有真实验证路径。
- registry / marketplace 元数据只在发布条件满足后再合入。
