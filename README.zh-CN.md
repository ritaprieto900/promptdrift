# promptdrift

**看清你的 prompt 改动到底改了什么。**

面向 LLM prompt 的回归测试与 CI 门禁：快照 diff 优先、Python 原生、抗抖动。

[English](README.md) · 中文文档

---

所有团队都在持续迭代 prompt，而每一次 prompt 修改都可能悄悄破坏原本正常的行为。`promptdrift`
把这件事变得可见、可防：它对同一组用例重新执行，与**已提交到仓库的基线快照**比较通过率，只在行为
*统计显著变差* 时让 CI 失败。

## 30 秒体验（不需要任何 API key）

```bash
pipx install promptdrift
promptdrift demo
```

demo 在离线的 mock provider 上跑完一个完整闭环：

1. `run` —— 执行套件（每个用例 3 个样本）
2. `approve` —— 把当前行为记录为基线
3. 有人"优化"了一下 prompt（mock 回答失去了关键步骤）
4. `diff` —— 漂移被抓到，门禁失败，退出码 1 —— 这次合并会被卡住

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

## 为什么不能直接断言输出？

LLM 输出**天然非确定**。朴素的 CI 检查（"输出必须包含 X"）会随机失败，然后被重试、被禁用。
promptdrift 的判定引擎就是为噪声设计的：

| 判定 | 含义 | 门禁（`--fail-on`） |
|---|---|---|
| 🔴 `regressed` | 通过率下降**超出抽样噪声**（Wilson 区间分离） | `regression`（默认）下失败 |
| ⚠️ `unstable` | 基线原本稳定、本轮样本之间自相矛盾 | 仅 `flaky` 下失败 |
| 🟢 `improved` | 通过率显著上升 | 永不失败 |
| ✅ `stable` | 噪声范围内 | — |
| 🆕 `new` / ➖ `removed` | 用例或断言相对基线新增/删除 | 不完整时 `any-fail` 失败 |

实际效果：`samples: 3` 时，3/3 → 2/3 的下降会被标为 ⚠️ **unstable**（警告），而不是 🔴
regressed —— 纯噪声永远卡不住合并。提高样本数可以锐化统计，`promptdrift cost` 会在跑之前
告诉你这要花多少钱。

## 工作原理

```text
promptest.yaml ──► Runner ──► Run ──► Differ ◄── Snapshot (.promptest/baselines/*.snap.yaml)
   (用例、断言、        │                    │
   采样参数)            └── provider ──► cache (sqlite)      ▲
                         ▲                                  │
                openai_compat / mock           `promptdrift approve` 生成基线
```

- **基线快照是你提交到 git 的 YAML 文件。** 改动它的 PR 就是一次经过评审的行为变更——和 jest
  snapshot 一个思路。
- **配置指纹**（模型 + 采样参数 + 样本数）守护可比性：换了模型，基线就是 *过期的*（退出码 2），
  而不是被悄悄错误比较。改 prompt 文本、vars 或 mock 回答 *不* 算过期——那正是 diff 应该度量的
  东西。
- **一个适配器覆盖大多数厂商**：任何 OpenAI 兼容端点（OpenAI、GLM、DeepSeek、Qwen、Moonshot、
  vLLM、Ollama）改 `base_url` 即可。

## 套件文件

```yaml
$schema: https://raw.githubusercontent.com/promptdrift/promptdrift/main/schema/promptest.schema.json
suite: support-agent
provider:
  openai_compat:
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    pricing: {prompt_per_1m: 1.0, completion_per_1m: 8.0}   # 启用 `promptdrift cost` 估算
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
```

M0 支持的断言：`equals` · `contains` · `not_contains` · `regex` · `is_json` · `json_schema` ·
`latency_under` · `completion_tokens_under`。

## 命令

| 命令 | 作用 | 退出码 |
|---|---|---|
| `promptdrift init` | 生成可运行的入门套件（mock provider） | |
| `promptdrift run` | 执行一次；有断言失败则退出码 1 | 0/1/2 |
| `promptdrift approve` | 把当前行为记录为基线 | |
| `promptdrift diff` | 执行并与基线比较；**这就是 CI 门禁**（`--fail-on regression\|flaky\|any-fail`，`--md report.md` 生成 PR 评论） | 0/1/2 |
| `promptdrift show` | 查看最近一次运行或基线 | |
| `promptdrift cost` | 估算调用数与成本（配置了 pricing 时） | |
| `promptdrift demo` | 离线端到端演示 | |
| `promptdrift schema` | 输出套件文件的 JSON Schema（编辑器补全） | |

退出码：`0` 通过 · `1` 门禁或断言失败 · `2` 配置/运行错误。

CI 用法（基线快照需已提交）：

```yaml
- run: pipx install promptdrift
- run: promptdrift diff --require-baseline --md pr-report.md
```

## 定位

| | promptdrift | promptfoo | DeepEval |
|---|---|---|---|
| 语言 | Python | Node/TypeScript | Python |
| 核心原语 | **基线快照 diff** | eval 运行 + 网页查看器 | pytest 指标 |
| 非确定性处理 | 多样本 + 区间统计 | 单次运行断言 | 指标阈值 |
| 评审流程 | PR 里的快照文件 diff | 打开 Web UI | 阅读 pytest 输出 |

promptfoo 是更全面的 eval 平台，DeepEval 擅长指标研究；promptdrift 只做一件窄而深的事：
**用可信的判定在 CI 里卡住 prompt 变更。**

## 路线图

- **M1** —— `judge` 断言（LLM-as-judge 评分量表，评审模型与被测模型解耦）、更丰富的 markdown
  报告、选择性重跑
- **M2** —— GitHub Action（PR 粘性评论）、文档站（mkdocs）、PyPI 发布
- **M3** —— embedding 相似度断言、多套件工程、跨模型比较模式

## 开发

```bash
git clone https://github.com/promptdrift/promptdrift
cd promptdrift
uv sync
uv run pytest              # 120+ 测试，完全离线
uv run ruff check .        # lint
uv run pyright             # 类型
```

整套测试跑在 mock provider 上——CI 永远不会碰真实端点。架构说明见
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache-2.0](LICENSE)
