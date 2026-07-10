# tagmanager-mcp

Python 实现的 Google Tag Manager MCP server（stdio 传输，官方 `mcp` SDK 的 FastMCP）。
v0.1（只读）、v0.2（写操作）、v0.3（版本与发布）均已交付并真机验收：v0.3 的 5 个工具
（list/get/get_live_version + create_version/publish_version）2026-07-09 在测试容器全链冒烟通过
（create_version 销毁 workspace→新建、publish 上线、get_live 复核）。共 24 个工具（13 读 + 11 写）、
71 个离线测试、已接入 Claude Code（server key: `gtm`；改代码后需重启 Claude Code 才加载新工具）。
以 `tagmanager-mcp` 分发到 PyPI，推 `v*` tag 由 GitHub Actions Trusted Publishing 上传
（见「发布（PyPI）」）。

## 常用命令

```bash
.venv/bin/pip install -e ".[dev]"            # 安装依赖（本项目不用 uv，用 venv + pip）
.venv/bin/nox -s tests                       # 单测（stdlib unittest，tests/*_test.py）
.venv/bin/nox -s lint                        # black --check
.venv/bin/nox -s format                      # black 格式化
.venv/bin/mcp dev tagmanager_mcp/server.py   # MCP Inspector 本地调试
.venv/bin/python -m build                    # 构建 sdist + wheel（产物在 dist/，已 gitignore）
.venv/bin/twine check dist/*                 # 校验包元数据 + README 能否在 PyPI 渲染
```

开发时接入 Claude Code（user scope，指向 checkout 而非已发布版本）：
`claude mcp add gtm -- <绝对路径>/.venv/bin/tagmanager-mcp`

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
    ├── variables.py # 与 tags.py 同构
    └── versions.py  # container version 读（list/get/get_live）+ create_version / publish_version；
                     # version 是 container 作用域（不在 workspace 下）；create_version 会销毁
                     # workspace；返回一律瘦身（内嵌实体过 slim_*），非全量嵌套
```

仓库其余部分：

```
.github/workflows/ci.yml       # push main / PR：nox tests（3.10–3.13 矩阵）+ lint（只在 3.13 跑一次）
.github/workflows/release.yml  # 推 v* tag：tests → build → publish（OIDC），见「发布（PyPI）」
noxfile.py                     # session 用 venv_backend='none'，跑在当前解释器，不嵌套建 venv
.claude/settings.json          # 项目级 Bash 允许清单（已入库）
```

改代码必须遵守的规则：

- 新工具一律 `async def` + `asyncio.to_thread(_sync)` 包装阻塞调用；docstring 即 tool
  description，参数格式宽容性写进 Args 段
- 所有 API 调用必须经 `client.execute()`，禁止直接 `request.execute()`（会丢失重试与错误转换）
- `list_*` 只回骨架字段（utils 里的 slim_*），`get_*` 才给全量；GTM 的 tag JSON 极啰嗦，
  一个 GA4 event tag 全量几百行
- 所有 list 方法必须经 `paginate()`；API 对空列表会整体省略数组键，任何响应取值都要 `.get()` 兜底
- 每个工具声明 annotations：读 `readOnlyHint=True`、create/update `destructiveHint=False`、
  delete `destructiveHint=True`（例外：`create_version`/`publish_version` 均 `destructiveHint=True`——
  前者销毁 workspace、后者上线）
- 写操作三条铁律：所有写调用走 `execute(request, mutating=True)`（只重试限流、不重试 5xx——
  API 无幂等键，5xx 重试可能重复写入）；update 一律"get 当前 → `merge_patch` 浅合并（null 删键、
  list 整替）→ 带 fingerprint 提交"，模型只传要改的字段；`delete_*` 与 `publish_version`
  必须显式 `confirm=True`，不为 True 时在触 API 前直接报错
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
- v0.3 discovery 事实（2026-07-08 对 live discovery doc 实测确认）：方法名是 **snake_case**——
  `workspaces.create_version`、`versions.set_latest`；集合名 `version_headers`（非 versionHeaders）；
  version_headers.list 响应数组键 `containerVersionHeader`。离线 mock 测不出方法名拼错，但**不必靠
  真机写操作兜底**：discovery client 的方法是从 discovery doc 动态生成的，`hasattr(ws(), 'create_version')`
  即可零调用、零变更地验证名字与签名（实测 create_version 收 `path`/`body`，publish 收 `path`/`fingerprint`）
- v0.3 scope 实测：`create_version` 需 `edit.containerversions`（**不是** edit.containers；reference 页
  与 discovery doc 摘要冲突，以 reference 页为准）；`publish` 单认 `tagmanager.publish`。但
  `versions.get` / `versions.live` / `version_headers.list` **只需 readonly**——`get_live_version`
  实测用旧 scope（readonly+edit.containers）即可跑通
- container version 的 JSON 极其庞大：测试容器 211 tags 的 version 全量 **688KB**（约 17 万 token，
  直接撑爆上下文），故 `get_version`/`get_live_version` 有意**偏离**「get_* 返回全量」惯例，把内嵌
  tag/trigger/variable 过 `slim_*`（实测压到 75KB，9.1x）。version header 的 numTags 等计数回的是
  **字符串**不是 int；零值字段（如空版本的 numTags）整个省略，故 `_slim` 必须 `if key in entity`
- **PyPI 发布不可逆**：版本号一次性，`0.3.0` 一旦有文件上传就永远不能重传（删掉 release 也不行）；
  release 的元数据（`description`、README 即 long_description）**上传后不可修改**，写错只能靠发新
  版本号纠正。故 README / pyproject 的任何文案改动都必须落在**打 tag 之前**。发错版本用
  `yank`（PEP 592）而不是 delete —— delete 会让包名重新开放给他人
- 终端用户装法是 `pipx install tagmanager-mcp`（这是可执行程序不是库，系统 Python 受 PEP 668
  保护会拒绝裸 `pip install`）。README 的 Setup 反映这一点，别改回 `git clone` + `pip install -e .`
  ——那是 Development 段的事。Claude Desktop 由 OS 启动、**不继承 shell PATH**，配置里必须写绝对路径
- GTM 没有"撤销发布"API：**回滚 = publish 一个旧 version**（`publish_version` 对任意 version 都有效）。
  `set_latest_version` 改的是新建 workspace 的**同步基线**，不是线上版本——望文生义拿它当回滚会出事

## 认证（ADC）

gcloud 默认 OAuth client 对 tagmanager scope 会被 Google "This app is blocked" 硬拦，
必须用自建 Desktop OAuth client（GCP Console → Auth Platform → Clients → Desktop app，
consent screen 发布到 production 以避免 refresh token 7 天过期）：

```bash
gcloud services enable tagmanager.googleapis.com --project=YOUR_PROJECT
gcloud auth application-default login \
  --client-id-file=YOUR_DESKTOP_CLIENT.json \
  --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/cloud-platform
gcloud auth application-default set-quota-project YOUR_PROJECT
```

`cloud-platform` 供 `set-quota-project` 校验用；若本机还有其他依赖这份 ADC 的 Google 工具，
重登时要把它们的 scope 一并带上（OAuth scope 在同意时固化，重登即整体替换）。自检：
`curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" https://tagmanager.googleapis.com/tagmanager/v2/accounts`
应返回 200。本机的具体 GCP 项目、OAuth client 文件、测试容器 ID 等环境信息在 Claude 的项目记忆里，
不写进本文件（本文件将随 repo 公开）。

## 发布（PyPI）

分发名 `tagmanager-mcp`，Python 模块 `tagmanager_mcp`，MCP server key `gtm`。
发布全部由 CI 完成，本地构建的 `dist/` 只用于校验，**不参与上传**：

```bash
# 前提：main 干净、nox 全绿、文案改动都已提交（元数据上传后不可改）
git tag -a v0.3.0 -m "v0.3.0: ..."
git push origin v0.3.0     # 触发 release.yml：tests → build → publish
```

- **认证走 Trusted Publishing（OIDC），仓库里不存在任何 API token。** PyPI 侧配置的 publisher
  三要素必须与 workflow 完全一致：repo `jinchliu/tagmanager-mcp`、workflow 文件名 `release.yml`、
  environment `pypi`。改动其中任何一个，都要同步改 PyPI 的配置，否则 OIDC 被拒
- 只有 `publish` job 持 `id-token: write`，`build` 过程碰不到 OIDC 凭据
- **`release.yml` 里那个 tests job 是刻意的**：推 tag 不触发 `ci.yml`，没有它，一棵红树也能发上
  PyPI。别为了"提速"把它删掉
- 发布失败不烧版本号（只要没有文件真正上传）。撤销 tag 重来：
  `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`

## 版本沿革与遗留 API 事实

- **v0.2 写操作（2026-07-07）**：scope 追加 `tagmanager.edit.containers`，9 个写工具落地，
  设计细节见上文"写操作三条铁律"。遗留的 API 事实：delete 方法**不接受 fingerprint**；
  `workspaces.delete` 需要的是 `tagmanager.delete.containers` scope（不是 edit，故未做 workspace
  管理）；免费容器最多 3 个并发 workspace，不要设计"每操作开临时 workspace"
- **v0.3 版本与发布（2026-07-09 真机全链验收）**：scope 追加 `tagmanager.edit.containerversions`
  + `tagmanager.publish`（publish 只认后者）。versions.py 独立文件（架构上强调 workspace 编辑
  ≠ 上线）；`create_version` 销毁 workspace 并返回 newWorkspacePath（destructiveHint=True 但不强制
  confirm）、把 compilerError/syncStatus 顶到顶层供发布前检查；`publish_version` 要求 `confirm=True`。
  版本管理（`update`/`delete`/`undelete`/`set_latest_version`）未做——现有 scope 已够，想加随时可加
