# tagmanager-mcp

Python 实现的 Google Tag Manager MCP server（stdio 传输，官方 `mcp` SDK 的 FastMCP）。
v0.1（只读）已交付并验收；v0.2（写操作）已交付：共 19 个工具（10 读 + 9 写）、58 个离线测试、
真实容器 CRUD 冒烟通过、已接入 Claude Code（server key: `gtm`）。

## 常用命令

```bash
.venv/bin/pip install -e ".[dev]"            # 安装依赖（本项目不用 uv，用 venv + pip）
.venv/bin/nox -s tests                       # 单测（stdlib unittest，tests/*_test.py）
.venv/bin/nox -s lint                        # black --check
.venv/bin/nox -s format                      # black 格式化
.venv/bin/mcp dev tagmanager_mcp/server.py   # MCP Inspector 本地调试
```

已注册到 Claude Code（user scope）：`claude mcp add gtm -- <绝对路径>/.venv/bin/tagmanager-mcp`

## 架构

```
tagmanager_mcp/
├── coordinator.py   # mcp = FastMCP(...) —— 全项目唯一实例
├── server.py        # import tools 各模块触发 @mcp.tool() 注册 → mcp.run()（stdio）
└── tools/
    ├── client.py    # ADC 凭据单例（threading.Lock 懒加载）+ 每次调用新建 discovery client；
    │                # execute()：所有 API 调用的必经层 —— 429/配额 403/5xx 指数退避重试、
    │                # 首触限流后 4 秒节流、HttpError → 可执行错误消息；写请求传
    │                # mutating=True（只重试限流、不重试 5xx）；prevent_stdio_inheritance()
    ├── utils.py     # construct_*_path()（宽容解析 int/数字串/完整 path）、slim_*()、
    │                # merge_patch()（顶层浅合并、null 删键）、paginate()
    ├── structure.py # list_accounts / list_containers / list_workspaces / get_workspace_status
    ├── tags.py      # list_tags（瘦身）/ get_tag（全量）/ create / update / delete
    ├── triggers.py  # 与 tags.py 同构
    └── variables.py # 与 tags.py 同构
```

改代码必须遵守的规则：

- 新工具一律 `async def` + `asyncio.to_thread(_sync)` 包装阻塞调用；docstring 即 tool
  description，参数格式宽容性写进 Args 段
- 所有 API 调用必须经 `client.execute()`，禁止直接 `request.execute()`（会丢失重试与错误转换）
- `list_*` 只回骨架字段（utils 里的 slim_*），`get_*` 才给全量；GTM 的 tag JSON 极啰嗦，
  一个 GA4 event tag 全量几百行
- 所有 list 方法必须经 `paginate()`；API 对空列表会整体省略数组键，任何响应取值都要 `.get()` 兜底
- 每个工具声明 annotations：读 `readOnlyHint=True`、create/update `destructiveHint=False`、
  delete `destructiveHint=True`
- 写操作三条铁律：所有写调用走 `execute(request, mutating=True)`（只重试限流、不重试 5xx——
  API 无幂等键，5xx 重试可能重复写入）；update 一律"get 当前 → `merge_patch` 浅合并（null 删键、
  list 整替）→ 带 fingerprint 提交"，模型只传要改的字段；`delete_*` 必须显式 `confirm=True`，
  不为 True 时在触 API 前直接报错
- stdout 只属于 MCP 协议，日志/调试输出一律走 stderr

## 编码约定

- black：line-length 80、skip-string-normalization（保单引号，见 pyproject）
- 注释英文；函数加 type hints；Python >= 3.10（本机 venv 3.13）
- 测试：stdlib unittest（不是 pytest），文件模式 `tests/*_test.py`，全部离线不触网

## 硬约束（各有真实事故背景，勿放宽）

- `mcp>=1.28,<2`：v2.0 beta 已发布且 API 全变（MCPServer 取代 FastMCP），官方要求钉 `<2`。
  要官方 `mcp` 包，不要第三方 `fastmcp` 2.x
- `cryptography<49`：49+ 不再发 Intel macOS wheel，本机（x86_64 Mac、无 Rust 工具链）源码构建会失败
- GTM API 配额：每 GCP 项目 0.25 QPS（25 次/100 秒滑窗）+ 10,000 次/天，per-user 调高无效；
  限流实际返回 429（官方错误文档只写 403，两种形态 execute() 都重试）。不要设计跨容器扇出型工具
- 工具返回注解必须写 `dict[str, Any]`：裸 `dict` 不会生成 structured output schema
- 内置 trigger（ID 21474795xx，如 All Pages / Initialization / Consent Init）不出现在
  list_triggers 结果里，做 trigger 引用分析时必须考虑
- fingerprint 失配实测（2026-07-07，测试容器）返回 **400** `badRequest`，message 为
  "The provided entity fingerprint is not valid."（官方无文档；未观察到 412，但 412 分支保留兜底）

## 认证（ADC）

gcloud 默认 OAuth client 对 tagmanager scope 会被 Google "This app is blocked" 硬拦，
必须用自建 Desktop OAuth client（GCP Console → Auth Platform → Clients → Desktop app，
consent screen 发布到 production 以避免 refresh token 7 天过期）：

```bash
gcloud services enable tagmanager.googleapis.com --project=YOUR_PROJECT
gcloud auth application-default login \
  --client-id-file=YOUR_DESKTOP_CLIENT.json \
  --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/cloud-platform
gcloud auth application-default set-quota-project YOUR_PROJECT
```

`cloud-platform` 供 `set-quota-project` 校验用；若本机还有其他依赖这份 ADC 的 Google 工具，
重登时要把它们的 scope 一并带上（OAuth scope 在同意时固化，重登即整体替换）。自检：
`curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" https://tagmanager.googleapis.com/tagmanager/v2/accounts`
应返回 200。本机的具体 GCP 项目、OAuth client 文件、测试容器 ID 等环境信息在 Claude 的项目记忆里，
不写进本文件（本文件将随 repo 公开）。

## 路线图（scope 分级即版本线）

- **v0.2 写操作（已交付，2026-07-07）**：scope 追加了 `tagmanager.edit.containers`。
  9 个写工具落地，设计细节见上文"写操作三条铁律"。遗留的 API 事实：delete 方法不接受
  fingerprint；`workspaces.delete` 需要的是 `tagmanager.delete.containers` scope（不是 edit，
  故 v0.2 未做 workspace 管理）；免费容器最多 3 个并发 workspace，不要设计"每操作开临时 workspace"
- **v0.3 发布**：scope 再追加 `tagmanager.edit.containerversions` + `tagmanager.publish`
  （publish 只认后者）。versions.py 独立文件（架构上强调 workspace 编辑 ≠ 上线）；
  `create_version` 会**销毁 workspace** 并返回 newWorkspacePath（必须回传给模型）；
  publish 前检查 syncStatus 与 compilerError；`publish_version` 同样要求 `confirm=True`

## 已知问题（搁置）

- Windows + v2rayN 代理环境的 stdio 连接问题：`prevent_stdio_inheritance()` 已落位（防句柄死锁）；
  出站代理需在 MCP 配置 env 块传 `HTTPS_PROXY`（httplib2 读取，可能还需 pysocks）。待 Windows 实机验证

## 命名与参考（已定，勿改）

- PyPI 分发名 `tagmanager-mcp` / Python 模块 `tagmanager_mcp` / MCP server key `gtm`。
  PEP 503 提醒：`tagmanager-mcp` 与 `tag-manager-mcp` 归一化后是两个不同的包，勿写混
- GA 官方参考实现（架构"形状"来源，实现已分道）：https://github.com/googleanalytics/google-analytics-mcp
- Notion 项目页：https://app.notion.com/p/386b3385a69380159aabe9dab7620250
