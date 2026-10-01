# promptdrift

**看清你的 prompt 改动到底改了什么。**

Prompt 回归测试 + CI 门禁。快照 diff 优先，统计抗抖动，Python 原生。

[![CI](https://github.com/ritaprieto900/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/ritaprieto900/promptdrift/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)](https://pypi.org/project/promptdrift-py/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

[English](README.md) · 中文文档
> **关于 PyPI 包名：** 发行包发布为 `promptdrift-py`——PyPI 的防混淆策略拦下了裸名
> （有人注册了空项目 `prompt-drift`，编辑距离为 1）。安装命令、CLI、Python 导入名
> 仍然是 `promptdrift`。


做 LLM 应用的团队都在频繁改 prompt，而每次改动都可能悄悄破坏原本正常的行为。promptdrift
解决的就是这件事：对同一组用例重新执行，和提交在仓库里的基线快照比较通过率，行为统计显著
变差时让 CI 失败。纯噪声永远卡不住合并。

## 30 秒体验，不需要 API key

```bash
pipx install promptdrift-py
promptdrift demo
```

demo 在离线的 mock provider 上跑完一个完整闭环：

1. `run` 执行套件（每个用例 3 个样本）
2. `approve` 把当前行为记录为基线
3. mock 回答被"优化"，丢掉了结构化步骤
4. `diff` 抓到漂移，退出码 1，CI 里就是这次合并被卡住

```text
step 4/4 — diff: catch the drift
┌──────────────┬─────────────────────┬────────┬───────┬────────────────┐
│ case         │ assertion           │ before │ after │ verdict        │
├──────────────┼─────────────────────┼────────┼───────┼────────────────┤
│ refund-steps │ contains-申请退款    │ 3/3    │ 0/3   │ 🔴 regressed   │
│              │ regex-3-5-个工作日   │ 3/3    │ 0/3   │ 🔴 regressed   │
│ invoice-json │ is_json-yes         │ 3/3    │ 3/3   │ ✅ stable      │
└──────────────┴─────────────────────┴────────┴───────┴────────────────┘
❌ gate FAILED — 1 regressed case(s)
```

## 为什么不能直接断言输出

LLM 输出天然非确定。"输出必须包含 X" 这种 CI 检查会随机失败，然后被重试，最后被禁用。
判定引擎直接把噪声纳入模型：

| 判定 | 含义 | 门禁行为 |
|---|---|---|
| 🔴 `regressed` | 通过率下降超出抽样噪声（Wilson 区间分离） | `regression`（默认）下失败 |
| ⚠️ `unstable` | 基线原本稳定，本轮样本之间自相矛盾 | 仅 `flaky` 下失败 |
| 🟢 `improved` | 通过率显著上升 | 永不失败 |
| ✅ `stable` | 噪声范围内 | 通过 |
| 🆕 `new` / ➖ `removed` | 用例或断言相对基线新增或删除 | 不完整时 `any-fail` 失败 |

具体数字：`samples: 3` 时 3/3 → 2/3 只是 ⚠️ unstable（警告）；`samples: 10` 时
10/10 → 3/10 才是 🔴 regressed。想锐化统计就提高样本数，跑之前先用 `promptdrift cost`
看看要花多少钱。

## 工作方式

```
promptest.yaml ──► Runner ──► Run ──► Differ ◄── Snapshot (.promptest/baselines/*.snap.yaml)
                       │                          ▲
                       └── provider ──► sqlite 缓存
```

基线是提交进 git 的 YAML 文件。PR 里基线文件的 diff 就是这次评审的行为变更，思路和 jest
snapshot 一样。配置指纹（模型、采样参数、样本数、评审模型）保护可比性：换了模型，旧基线
自动判为过期，而不是被悄悄错误比较。改 prompt 文本、vars、mock 回答永远不算过期，那正是
diff 应该度量的东西。

一个适配器覆盖所有 OpenAI 兼容端点（OpenAI、GLM、DeepSeek、Qwen、Moonshot、vLLM、
Ollama），配 `base_url` 即可。

## 套件文件

```yaml
$schema: https://raw.githubusercontent.com/ritaprieto900/promptdrift/main/schema/promptest.schema.json
suite: support-agent
provider:
  openai_compat:
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    pricing: {prompt_per_1m: 1.0, completion_per_1m: 8.0}
judge:                          # 可选：给 judge 断言打分的评审模型
  openai_compat:
    model: glm-4.7-flash
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    temperature: 0.1
samples: 3
cases:
  - id: refund-steps
    messages:
      - role: user
        content: "订单有点问题，我想申请{{topic}}"
    vars:
      topic: 退款
    assertions:
      - contains: "申请退款"
      - regex: "3-5 个工作日"
      - not_contains: "抱歉"
      - latency_under: 3000
      - judge:
          rubric: |
            回复是否包含明确的退款步骤（入口、操作、时限）？
            5 = 步骤完整且语气友好；1 = 没有回答问题。
          min_score: 4
```

确定性断言：`equals`、`contains`、`not_contains`、`regex`、`is_json`、`json_schema`、
`latency_under`、`completion_tokens_under`。`judge` 断言把每个样本连同你的量表发给评审模型，
要求返回 1-5 分，`min_score` 是及格线。评审模型自己也会抖，所以它的打分同样进入多样本统计：
摇摆的评审表现为 ⚠️ unstable，而不是误伤合并。

## 命令

| 命令 | 作用 |
|---|---|
| `promptdrift init` | 生成入门套件（mock provider，离线可跑） |
| `promptdrift run` | 执行一次；有断言失败退出码 1 |
| `promptdrift approve` | 把当前行为记录为基线 |
| `promptdrift diff` | 执行并与基线比较；CI 门禁就是它 |
| `promptdrift show` | 查看最近一次运行或基线 |
| `promptdrift cost` | 估算调用数与成本（配置了 pricing 时） |
| `promptdrift demo` | 离线端到端演示 |
| `promptdrift schema` | 输出套件文件的 JSON Schema（编辑器补全） |

CI 里常用的 `diff` 选项：`--fail-on regression|flaky|any-fail`、`--require-baseline`、
`--md report.md`（生成可直接贴 PR 的 markdown 报告）。

退出码：0 通过，1 门禁或断言失败，2 配置或运行错误。

```yaml
# GitHub Actions 最小用法（完整版见 docs/ci.md）
- run: uv tool install promptdrift-py
- run: promptdrift diff --require-baseline --md pr-report.md
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## 横向对比

| | promptdrift | promptfoo | DeepEval |
|---|---|---|---|
| 语言 | Python | Node/TypeScript | Python |
| 核心原语 | 基线快照 diff | eval 运行 + 网页查看器 | pytest 指标 |
| 非确定性处理 | 多样本 + 区间统计 | 单次运行断言 | 指标阈值 |
| 评审流程 | PR 里的快照 diff | 打开 Web UI | 阅读 pytest 输出 |

promptfoo 是更全面的 eval 平台，DeepEval 强在指标研究。这个项目只做窄的一件事：在 CI 里
卡住 prompt 变更，并且给出可信的判定。

## 路线图

- 只重跑有改动的用例；embedding 相似度断言
- PyPI 发布后补 composite GitHub Action 和 PR 粘性评论
- 多套件工程、跨模型比较模式

## 开发

```bash
git clone https://github.com/ritaprieto900/promptdrift
cd promptdrift
uv sync
uv run pytest              # 150+ 测试，完全离线
uv run ruff check .
uv run pyright
```

整套测试跑在 mock provider 上，CI 不会碰真实端点。CONTRIBUTING.md 里有架构图和设计约定。

## 许可证

[Apache-2.0](LICENSE)
