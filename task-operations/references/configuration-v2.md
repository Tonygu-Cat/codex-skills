# 编码 Agent 自主推进默认配置方案 V2.2

## 1. 目标

让 Codex 对需要修改文件或多步执行的任务直接加载任务运营要求（用户可按任务拒绝）；加载后，Agent 应持续推进到已验证的最终结果。只有在明确需要授权、关键方案选择、用户专属信息或不可逆外部操作时，才暂停并主动告诉用户需要做什么。

本方案以 Codex 为主，Claude Code 与 DeepSeek Harness 仅作为兼容适配。本仓库的 `task-operations/` 目录是唯一可编辑规则源。

## 2. V2.2 架构

V2 将“是否启用”“启用后的行为”“机器权限”和“强制检查”拆成四层，避免把整套规则永久塞进全局提示词，也避免用过宽权限换取自动化。

| 层 | 作用 | 默认状态 |
| --- | --- | --- |
| 启动门 | 改文件或多步执行的任务直接加载，用户可按任务拒绝 | 开启 |
| `task-operations` Skill | 定义持续推进、阻塞请求和完成审计 | 由启动门显式启用 |
| 权限配置 | 允许工作区内日常操作，危险动作继续审批 | 保守开启 |
| Stop Hook | 检查启用后的结束回复是否明确用户操作；失败、待办、待授权或待选择时还须说明目标和下一步 | 验收并信任后启用 |

## 3. GitHub 单一事实源

仓库中以下内容应作为唯一可编辑源：

```text
task-operations/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── autonomy-rules.md
│   ├── configuration-v2.md
│   ├── acceptance-tests.md
│   └── stop-hook.md
├── scripts/stop_guard.py
└── tests/test_stop_guard.py
```

- 通过功能分支和 Pull Request 修改规则，合并后再打版本标签。
- 安装或更新时固定到已审核的提交或标签；不要长期跟随未经审核的分支头。
- 全局文件只保存启动门，不复制完整规则。这样规则升级不需要同步多份正文。
- `agents/openai.yaml` 设置 `allow_implicit_invocation: false`，确保只通过启动门显式加载，不被隐式触发。

## 4. Codex 启动门

把下面的最小规则放入用户级 `~/.codex/AGENTS.md`。若文件已有内容，合并而不是覆盖。

```md
# Task operations startup gate

需要修改文件或多步执行的任务，开始实质工作前直接显式使用 `$task-operations`，不再询问用户，然后继续处理用户原始任务。
一次性问答、简单状态查询不加载；用户说本任务不用任务运营时也不加载。
同一任务只加载一次；不要因压缩上下文或后续消息重复加载或重复回执。
```

加载后不要让用户重复原始请求，直接从原请求继续。

Skill 确实加载并读取合同后，必须只输出一次激活回执：

```text
任务运营：已加载 task-operations（TASK_OPS_ACTIVE=1）
```

该回执既用于用户核验，也用于可选 Stop Hook 判断当前任务是否 opt-in。没有读到完整合同不得声称“已加载”；上下文压缩后不得重复加载或重复回执。

Codex 会在开始工作前加载用户级 `AGENTS.md`。官方说明见 [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 与 [Build custom Skills](https://learn.chatgpt.com/docs/build-skills)。

## 5. Codex 权限基线

在用户配置中保持按需审批和工作区写权限：

```toml
approval_policy = "on-request"
approvals_reviewer = "auto_review"
sandbox_mode = "workspace-write"
```

- 如果组织策略不支持 `auto_review`，保留平台提供的审批方式。
- 不使用 `approval_policy = "never"` 追求无人值守；它不会增加权限，只会让受限操作无法请求授权。
- 网络访问默认保持受控。确需联网的可信任务可使用单独 profile，不要把全局网络和生产权限一起放开。
- 当命令确实需要提升权限时，Agent 应直接触发原生审批请求，并说明目的和尽可能窄的复用范围。

Codex 的审批与沙箱边界见 [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)。

## 6. 可选 Stop Hook 强制层

仅靠提示词不能做到数学意义上的强制。V2.2 的 [stop-hook.md](stop-hook.md) 与 `scripts/stop_guard.py` 检查启用后的结束回复是否明确用户操作（无需，或具体动作）。报告失败、待办、待授权或待选择时，还需说明当前目标与下一步；不能只说代码完成、部署尚待授权。缺项时返回一次续跑提醒。该检查不能证明语义完整性，也不能授予执行权限。

Hook 必须满足：

- 只在当次会话已 opt-in 时生效；拒绝加载时完全旁路。
- 只检查必做项，不因可选优化、低价值建议或未来工作阻止结束。
- 记录本轮已检查状态，设置最大续跑次数，防止无限循环。
- 遇到真实授权边界时允许暂停，并要求输出结构化授权请求。
- 不自行扩大作用域，也不执行命令或写入代码。
- `stop_hook_active` 为 `true` 时必须放行，最多续跑一次。
- Hook 只做结构完整性防线，不替代 Agent 对“目标是否仍可行”的判断。

建议返回协议：

```json
{
  "decision": "block",
  "reason": "Required in-scope work remains: <specific item>"
}
```

完成或需要用户授权时应放行。Hook 机制见 [Codex hooks](https://learn.chatgpt.com/docs/hooks)。

### 目标连续性

单轮执行、测试或恢复步骤失败，不等于目标结束。只要原目标仍可实现，按以下优先级运营：

1. 仍在范围和授权内：Agent 自动继续同一目标。
2. 需要新授权：保留同一目标并立即给出唯一下一步和准确授权文本。
3. 需要关键选择：保留同一目标，推荐方案并给出最短回复。
4. 仅在验收完成、用户取消或确无可行路径时结束目标。

“失败即停、不得重试”只禁止未授权的再次执行；失败关闭的同一回复仍必须告诉用户当前目标是否保留、下一步是什么，以及要准确回复什么。

## 7. Git、依赖与外部动作边界

- **Git：**不默认 commit/push。只有用户要求发布或任务明确包含 Git 交付时才执行；只暂存任务文件，默认走功能分支与 PR。
- **依赖：**依据现有 lockfile 安装依赖属于常规执行；新增或升级生产依赖属于设计变更，除非任务已明确授权，否则先说明影响。
- **外部系统：**部署、发布、付款、消息发送、删除云资源、修改生产数据均需明确在范围内并满足平台审批。
- **命令白名单：**不为 `python`、`node`、`curl`、shell 等通用解释器配置宽泛放行。按具体子命令和用途申请最窄权限。

## 8. Windows 安装与更新

Windows 优先采用“本地克隆 + 明确复制 + 哈希验证”，不要依赖管理员符号链接。

1. 克隆或更新已审核仓库。
2. 备份现有 `~/.codex/AGENTS.md` 和同名 Skill。
3. 固定同一源提交，用安装工具安装到当前 `$CODEX_HOME/skills/task-operations`（未设置时使用 `~/.codex/skills/task-operations`）。如存在旧 `~/.agents/skills/task-operations`，先备份本地差异，再同步为同一版本；不要让模型指令和 Hook 脚本来自不同版本。
4. 合并启动门，禁止覆盖用户已有规则。
5. 对源目录与安装目录计算文件哈希并比对。
6. 记录已安装版本、源提交、文件哈希、备份位置和恢复命令，保留带时间戳的回退清单。
7. 新开测试任务，执行验收清单；失败则按回退清单恢复备份。

不要让安装脚本自动改写凭据、全局 Git 配置或其他 Agent 的配置。

## 9. Claude Code 与 DeepSeek Harness 适配

### Claude Code

- 用户级启动门放在 `~/.claude/CLAUDE.md`。
- 可使用 `acceptEdits` 或窄范围 `allow` 规则降低工作区内编辑摩擦。
- `git push`、删除、`sudo`、生产部署和读取敏感环境文件继续询问或拒绝。
- 禁止为 `python`、`node`、`curl` 等配置无参数范围的通配放行。

权限模型以 [Claude Code permissions](https://code.claude.com/docs/en/permissions) 为准。

### DeepSeek Harness

- 用户级指令文件使用 `$DSH_HOME/AGENTS.md`，默认位置是 `~/.dsh/AGENTS.md`。
- 适配器只同步启动门和本 Skill 的核心合同，不猜测未确认的 CLI 配置键。
- 无头运行前固定 Harness 版本并保存实际生效配置；版本变更后重新跑验收。

路径依据 [DeepSeek Harness agent instructions](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md)。

## 10. 发布、回滚与验收

发布流程：

1. 在功能分支修改 Skill 和 V2 文档。
2. 运行 Skill 校验与 [acceptance-tests.md](acceptance-tests.md)。
3. 运行 `python -m unittest discover -s task-operations/tests -p "test_*.py"`，验证 Stop Hook 不误触发且不会无限续跑。
4. 通过 Pull Request 审核后合并。
5. 打语义版本标签，并在安装配置中固定该标签或提交。
6. 在至少一个新任务中验证启动门、目标连续性、持续推进和授权边界。

回滚只需恢复上一版本 Skill 和启动门备份；权限配置单独回滚。不要把规则回滚与代码仓库重置绑在一起。

V2 的成功标准不是“Agent 更少说话”，而是：它能自己完成所有已授权步骤；当确实需要用户时，用户第一眼就知道原因、推荐方案和最短回复。
