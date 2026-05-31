# Sextant 工程实现技术设计

> 本文档定义 Sextant 从现有产品体验契约、Memory 宏观设计和 Agent 宏观设计进入工程实现阶段时的技术设计。
>
> 本文是技术设计，不是执行计划、任务拆分或里程碑排期。后续实施可以另开 planning 文档，但不得在计划文档中重新定义本文的工程边界、source-of-truth 顺序、AI coding 围栏或 CI/CD 质量门。

## 1. 设计定位

Sextant 的工程实现不应围绕“聊天生成小说”或“单个大 prompt”组织，而应围绕稳定的写作与记忆链条组织：

```text
ActionRequest
  -> ContextPack / Story Skill / Agent
  -> DraftCandidate / MemoryAnswer / AgentReviewFinding
  -> AcceptedFragment
  -> SourceDelta
  -> SourceSpan
  -> MemoryExtraction
  -> Evidence / Log Writeback
  -> Conflict Policy Gate
  -> Canon Promotion / ReviewItem
  -> MemoryPage / GraphProjection / ContextPack Readiness
```

工程实现必须保护以下硬边界：

```text
DraftCandidate != Manuscript Text
Manuscript Text != SourceDelta
SourceDelta != SourceSpan
SourceSpan != Memory
Memory != Canon
GraphProjection / ContextPack 是 read model，不是 source of truth
```

本文的核心结论：Sextant 第一阶段采用 Python 模块化单体，保留现有 Vite + React 前端原型方向，以 Postgres 为主库，以 Story Skills 为领域处理协议，以 CI/CD、tach、ty、ruff、semgrep 和 contract tests 给 100% AI coding 建立硬围栏。

## 2. 总体架构决策

### 2.1 Python 模块化单体

后端采用 Python modular monolith，第一阶段不拆微服务。

理由：

1. 当前复杂度主要来自领域状态、证据链、增量回写、冲突策略、Story Skill 编排和 Agent 边界，而不是高并发分布式系统。
2. 模块化单体可以用 import boundary、domain tests、contract tests 和 CI 门禁强制边界，避免微服务过早引入网络、部署、版本协商和分布式事务复杂度。
3. Python 适合文本处理、LLM harness、结构化抽取、评测、脚本化数据迁移和快速迭代。
4. 100% AI coding 场景下，速度不是瓶颈；真正要控制的是越界写入、隐式状态污染和契约漂移。

### 2.2 前端继续 Vite + React

现有 `web/` 已经是 Vite + React + TypeScript 原型。第一阶段继续保留该方向，不切换到 Next.js。

理由：

1. Sextant 写作工作台更接近 SPA / app-like workbench，不依赖 SSR 或 SEO。
2. 当前重点是用户动作、候选生命周期、Memory 回写和 Review 状态的交互闭环。
3. 技术迁移不应发生在核心领域契约尚未落库之前。

### 2.3 Postgres 是主库，Graph 是投影

第一阶段主库采用 PostgreSQL。GraphProjection 不能成为 source of truth。

故事图谱必须从以下对象重建：

```text
RawSource / SourceSpan
  -> Mention / AliasRecord / EventCandidate
  -> CanonicalEntity / CanonicalEvent / FactAssertion
  -> EvidenceLogEntry / ReviewItem
  -> MemoryPage
  -> GraphProjection
```

工程约束：

1. 不引入图数据库作为主事实源。
2. 不允许业务代码把 GraphProjection 当作事实源。
3. 不允许 ContextPack 或 GraphProjection 反写 Canon。
4. 图谱可以缓存、索引、展示、辅助检索，但必须可重建。

### 2.4 LLM 是端口，不是领域核心

LLM 调用只能发生在 infrastructure adapter 或受控 harness 中。Domain 层不能依赖具体模型 provider。

模型输出默认是候选，不是事实。任何模型输出进入 Memory 前必须经过：

```text
structured output
  -> validation
  -> evidence binding
  -> policy check
  -> proposed state
  -> promotion / review
```

禁止路径：

```text
model output -> MemoryPage.current_canon
model output -> canon FactAssertion
model output -> canon graph edge
```

## 3. 后端分层设计

后端代码采用 6 层结构：

```text
api layer
application layer
domain layer
skills layer
ports layer
infra layer
```

### 3.1 API Layer

职责：HTTP routing、auth/session、request/response DTO、OpenAPI schema、错误码映射。

不负责：领域判断、直接写数据库、直接调用 LLM、直接创建 Canon / ReviewItem / MemoryPage。

### 3.2 Application Layer

职责：use case 编排、transaction boundary、调用 repository port、调用 Story Skill resolver、幂等、权限、版本冲突、job dispatch。

典型 use case：

```text
SubmitActionRequest
RunActionRequest
AcceptCandidate
CreateSourceDelta
BuildMemoryWritebackPreview
ConfirmMemoryWritebackItem
ResolveReviewItem
BuildWritingContextPack
AnswerWithEvidence
```

### 3.3 Domain Layer

职责：领域对象、枚举、状态机、不变量、policy、value object、domain service。

Domain 层必须是纯业务层，不知道 FastAPI、SQLAlchemy、模型 provider、Redis、对象存储或 GitHub Actions。

核心 domain package：

```text
source
manuscript
memory
review
agent
context
common
```

Domain 层负责表达：Candidate 状态机、SourceDelta 版本规则、SourceSpan 证据规则、FactAssertion promotion、ReviewItem 生命周期、Conflict Policy Gate、source-of-truth 顺序。

### 3.4 Skills Layer

职责：Story Skills 的实现、输入 contract、输出 contract、deterministic rules、model judgment boundary、review policy hook、writeback policy hook。

每个 skill 都必须是小而明确的处理协议，不允许出现全能 `process_everything`。

第一组 skill：

```text
split-structure
source-normalization
detect-pov
extract-mentions
resolve-alias
extract-events
aggregate-events
derive-facts
check-continuity
rewrite-current-canon
build-next-page-context
answer-with-evidence
next-page-agent
```

### 3.5 Ports Layer

职责：定义外部依赖接口，让 application / skills 面向接口编程，隔离 infra 实现。

Port 类型：

```text
SourceRepository
MemoryRepository
ReviewRepository
CandidateRepository
JobRepository
ObjectStore
LLMClient
EmbeddingClient
SearchIndex
EventBus
Clock
IdGenerator
```

### 3.6 Infra Layer

职责：Postgres repository、Alembic migrations、object store adapter、LLM provider adapter、embedding adapter、worker、search/pgvector adapter、observability。

Infra 可以 import domain 和 ports，但 domain 不能反向 import infra。

## 4. 仓库目录设计

建议结构：

```text
sextantlabs/
  AGENTS.md
  README.md
  docker-compose.yml
  pyproject.toml
  pnpm-workspace.yaml

  goals/
  experience/

  docs/
    adr/
    tech-design/
      engineering-implementation-design.md
      module-boundaries.md
      ci-cd-and-csab.md
      ai-coding-guardrails.md
      persistence-schema.md
      llm-harness.md
      frontend-integration.md

  web/
    package.json
    src/
    components/
    lib/
    generated/

  backend/
    pyproject.toml
    uv.lock
    tach.toml
    src/sextant/
      api/
      application/
      domain/
      skills/
      ports/
      infra/
      contracts/
    tests/
      unit/
      integration/
      contract/
      golden/
      evals/

  prompts/
    skills/

  evals/
    datasets/
    expected/
    reports/

  .github/
    workflows/
    pull_request_template.md
    CODEOWNERS
```

`goals/` 和 `experience/` 继续作为产品、Memory 和 Agent 逻辑设计源；`docs/tech-design/` 承接工程实现设计；`backend/` 和 `web/` 承接实现代码。

## 5. 技术栈设计

### 5.1 后端

```text
Python:         3.12 或 3.13，仓库内锁定一个版本
Runtime:        uv
API:            FastAPI
Schema:         Pydantic v2
DB:             PostgreSQL
ORM:            SQLAlchemy 2.x
Migration:      Alembic
Vector:         pgvector
Object store:   S3 / R2 / MinIO compatible
Worker:         DB-backed worker first; Temporal later if needed
Cache:          Redis optional, not source of truth
Test:           pytest
Lint/format:    ruff
Type check:     ty
Import boundary:tach
Security:       semgrep
```

### 5.2 前端

```text
Build:          Vite
UI:             React + TypeScript
Server state:   TanStack Query
API client:     generated from OpenAPI
Validation:     zod at UI boundary only
Test:           vitest + playwright
Package manager:pnpm
```

前端不重复维护后端领域 schema。前端使用生成的 API client 和必要的 UI-local schema。

### 5.3 数据存储

```text
Postgres:
  source metadata, source versions, source spans
  mentions, aliases, canonical entities
  event candidates, canonical events, fact assertions
  evidence logs, review items, memory pages
  graph projection metadata, jobs

Object store:
  raw source text
  processed markdown view
  raw offset maps
  large prompt input snapshots
  LLM raw output audit records

pgvector:
  SourceSpan embeddings
  Scene summary embeddings
  MemoryPage embeddings
  Style sample embeddings
```

第一阶段不引入微服务、图数据库作为主事实源、重度 agent 框架、Kafka、Kubernetes-only 部署假设或全自动长篇小说生成 pipeline。

## 6. 核心数据契约设计

### 6.1 ActionRequest

ActionRequest 是自然语言、选中文本、按钮动作进入系统的结构化入口。

规则：

1. 开放聊天不能直接调用 Agent。
2. 所有写作动作必须先转成 ActionRequest。
3. 写作类 ActionRequest 必须有 target。
4. ActionRequest.actor_intent 不是 canon 事实。
5. ActionRequest.constraints 只能约束生成，不自动写 Memory。

### 6.2 Candidate Lifecycle

候选生命周期由状态机控制：

```text
proposed
  -> explained
  -> rerolled
  -> discarded
  -> partially_accepted
  -> fully_accepted
```

规则：

1. DraftCandidate 可以包含 rationale、memory refs、risk finding。
2. DraftCandidate 不能直接写正文。
3. DraftCandidate 不能直接写 Memory。
4. DraftCandidate 不能直接创建 SourceSpan。
5. 只有 AcceptedFragment 代表作者采纳了候选中的具体文本。
6. AcceptedFragment 不等于作者确认所有可推断事实。

### 6.3 SourceDelta

SourceDelta 是正文实际变化，不是长期事实源。

规则：

1. 只有 SourceDelta 可以触发 Memory 增量回写。
2. SourceDelta 必须包含 base_hash 或 previous_version_id，避免并发覆盖。
3. SourceDelta 必须产生新 SourceVersion 或 append/replace 语义。
4. SourceDelta 不替代 RawSource / SourceVersion。

### 6.4 SourceSpan

SourceSpan 是 Memory 证据锚点。

规则：

1. FactAssertion、CharacterKnowledge、ReviewItem、MemoryPage source_refs 都必须能回到 SourceSpan 或明确的用户输入。
2. 没有 SourceSpan 的模型判断只能是候选或临时风险，不能成为正式 canon evidence。
3. ProcessedMarkdownView 必须保留 raw offset map，使 SourceSpan 能回到 RawSource。

### 6.5 MemoryWritebackPreview

MemoryWritebackPreview 是“准备记住这些”的工程对象，不是强制确认弹窗，也不是数据库编辑器。

```text
SourceDelta
  -> SourceSpan
  -> MemoryExtraction
  -> ProposedFact / ProposedKnowledgeState / ProposedThreadUpdate / ProposedReviewItem
  -> auto promote / review / reject
```

规则：

1. low risk 可以轻提示并自动进入 evidence/log 或 promotion policy。
2. medium risk 应进入可展开 preview 或 Review。
3. high risk 必须阻断自动 canon promotion。
4. 作者否定抽取结果时，系统必须保存纠错信号，但不能写入对应事实。

### 6.6 ReviewItem

ReviewItem 是统一风险对象。

规则：

1. 连续性警告、alias conflict、event merge conflict、state conflict、canon promotion risk 都进入 ReviewItem。
2. ReviewItem.status 只能通过 Review Policy 或 Review Service 改变。
3. ReviewItem.review_type 必须来自白名单。
4. 新增 review_type 必须先更新设计文档或 ADR。
5. ReviewItem 不是写作阻塞器；它只阻断高风险自动升格。

## 7. Story Skill 工程协议

每个 Story Skill 必须包含：

```text
name
version
Trigger
Inputs
Transform
Outputs
Deterministic Rules
Model Judgment
Review Policy
Writeback Policy
Tests
Prompt Version
Output Schema
```

Skill 只暴露受控能力：project/request context、clock、id generator、repository ports、LLM port、audit sink。

禁止：

```text
skill 直接 commit 数据库事务
skill 直接创建 canon fact
skill 直接覆盖 MemoryPage.current_canon
skill 直接写 GraphProjection canon edge
skill 直接绕过 Conflict Policy Gate
```

## 8. LLM 与 Prompt 管理设计

LLM provider 只提供能力，不表达领域语义。

每个 prompt 必须有：

```text
skill name
prompt version
input schema version
output schema version
model constraints
golden cases
failure examples
```

Prompt 修改必须触发 golden tests。

LLM 审计记录应保存 request id、skill name/version、prompt version、model/provider、input object hash、structured output、raw output ref、validation result、retry count、latency/cost metadata。

审计记录不能成为 Memory source-of-truth，只用于 debug、replay、eval 和质量追踪。

## 9. 数据库边界设计

表设计原则：

1. RawSource 和 SourceVersion 保留原始材料版本。
2. ProcessedMarkdownView 可重建，但必须记录 cleaning profile 和 offset map ref。
3. SourceSpan 是后续事实、事件、风险、Memory 引用的证据根。
4. FactAssertion 是事实断言，不等于 Current Canon。
5. EvidenceLogEntry 先写，Canon Promotion 后写。
6. ReviewItem 不阻断 ingest，只阻断高风险 promotion。
7. MemoryPage 是面向作者和 Agent 的综合记忆，不覆盖底层证据。
8. GraphProjection 是可重建 read model。

JSONB 可以保存 schema-versioned payload、skill structured output、LLM trace metadata、review side effects、context pack snapshot，但不能替代 SourceSpan identity、FactAssertion core relation、ReviewItem lifecycle state、SourceVersion relation、CanonicalEntity identity 或 CanonicalEvent identity。

Migration 规则：

1. 所有 schema 变更必须走 Alembic。
2. Migration 文件名必须描述领域对象。
3. 删除列必须先 deprecate，再后续迁移删除。
4. 影响 source-of-truth 的 migration 必须在 PR body 标记。
5. Migration 必须在 CI 中跑 upgrade。

## 10. CI/CD 设计

CI/CD 的设计目标不是只保证能 build，而是保护领域边界。

### 10.1 PR 快速质量门

每个 PR 必跑：

```text
backend:
  uv sync --locked
  ruff format --check
  ruff check
  ty check
  tach check
  pytest tests/unit tests/contract

web:
  pnpm install --frozen-lockfile
  pnpm lint
  pnpm typecheck
  pnpm build
  vitest

repo:
  check generated OpenAPI client is up to date
  check no forbidden files
  check no oversized prompt dumps
  check no direct mutation of protected generated files
```

### 10.2 慢速质量门

按路径或 label 触发：

```text
Postgres integration tests
worker pipeline tests
LLM mock replay tests
golden tests
Playwright user journey tests
migration upgrade tests
```

### 10.3 安全门

```text
semgrep
secret scanning
dependency review
CodeQL optional
Docker image scan optional
```

GitHub Actions 默认最小权限；只有需要写 PR comment、publish artifact、deploy 的 job 才提升权限。

### 10.4 Release / CD

第一阶段部署单元：backend API container、worker container、Postgres、object store、Redis optional、static web hosting。

`main` merge 后构建 staging；release tag 后部署 production，并要求环境审批、migration、smoke test 和部署记录。

## 11. CSAB：Code Safety & Automation Boundary

本文将 CSAB 定义为 Code Safety & Automation Boundary，即用于约束 AI coding、自动化修复、批量重构、CI/CD 和安全扫描的工程边界。

CSAB 的目标：

1. AI 可以高速写代码，但不能绕过 source-of-truth。
2. AI 可以新增 skill，但必须提供 contract、schema、golden case。
3. AI 可以重构目录，但不能破坏 import boundary。
4. AI 可以修复 lint，但不能改变领域语义。
5. AI 可以更新 prompt，但必须更新 version 和测试。
6. AI 不得把模型输出直接升格为 canon。

CSAB 由四类机制组成：

```text
文档边界: AGENTS.md / ADR / design docs
代码边界: domain policy / value object / state machine
工具边界: tach / ruff / ty / semgrep
流程边界: PR template / CODEOWNERS / CI gates
```

### 11.1 Semgrep 规则方向

需要自定义规则禁止：

```text
api layer 直接调用模型 provider
api layer 直接提交数据库事务
domain layer 依赖 web framework、ORM 或 provider SDK
skills layer 直接提交数据库事务
skills layer 直接修改 MemoryPage.current_canon
绕过 promotion policy 直接设置 canon fact
绕过 review policy/factory 直接创建 ReviewItem
把 model_suggestion 自动改成 user_draft 或 user_published
从 GraphProjection 反写 FactAssertion
```

### 11.2 Tach import boundary

建议边界：

```text
sextant.domain -> sextant.domain.common only
sextant.application -> sextant.domain, sextant.ports, sextant.contracts
sextant.skills -> sextant.domain, sextant.ports, sextant.contracts
sextant.api -> sextant.application, sextant.contracts
sextant.infra -> sextant.domain, sextant.ports, sextant.contracts
```

禁止：

```text
domain -> infra
domain -> api
skills -> infra.db
api -> infra.llm
api -> SQL session
```

## 12. AI Coding 围栏设计

根目录 `AGENTS.md` 应定义：

```text
项目 source-of-truth 顺序
不可压缩的 Candidate -> SourceDelta -> SourceSpan -> Memory 链条
禁止直接把模型输出写入 canon
禁止绕过 ActionRequest 调用 Agent
禁止把 GraphProjection / ContextPack 当事实源
新增领域枚举必须修改设计文档或 ADR
新增 prompt 必须附 golden case
```

建议目录级说明：

```text
backend/src/sextant/domain/AGENTS.md
backend/src/sextant/skills/AGENTS.md
backend/src/sextant/infra/AGENTS.md
web/AGENTS.md
prompts/AGENTS.md
```

AI 可以做：新增符合 contract 的 domain model、补充 repository implementation、新增 migration、新增 API endpoint shell、新增 skill skeleton、新增 golden test、修复 lint/type/import boundary。

AI 不可直接做：改变 source-of-truth 顺序、新增 review_type、新增 source_scope、让 candidate 自动进入 Memory、让 model output 自动成为 canon、删除 evidence chain、让 GraphProjection 成为事实源、把 prompt 输出 schema 改成自由文本。

## 13. PR 与堆叠式 PR 设计

PR 应围绕一个工程边界或一个 contract 组织，而不是围绕“AI 一次能生成多少代码”。

好的 PR：

```text
Add ActionRequest contract and tests
Add Candidate lifecycle state machine
Add SourceDelta and SourceSpan models
Add MemoryWritebackPreview contract
Add tach boundary config
Add split-structure skill skeleton
```

不好的 PR：

```text
Implement backend
Add memory system
Connect all AI
Refactor everything
```

允许堆叠式 PR，但每个 PR 必须可以单独 review。

建议 stack 依赖形态：

```text
base tooling
  -> domain contracts
    -> persistence
      -> application use case
        -> api endpoint
          -> frontend integration
```

PR body 必须回答：

```text
本 PR 是否修改 source-of-truth 对象？
本 PR 是否修改 ActionRequest / Candidate / SourceDelta / SourceSpan / ReviewItem contract？
本 PR 是否新增或修改 migration？
本 PR 是否新增或修改 prompt？
本 PR 是否新增 golden case？
本 PR 是否触碰 Memory promotion / Conflict Policy Gate？
本 PR 是否需要 ADR？
本 PR 是否修改 AI coding guardrails？
```

默认使用 squash merge，保持 main 线性可读。对于 stack PR，上游 PR 先合并，下游 PR rebase 到 main，每层 PR 保持 CI 绿。

## 14. Testing Strategy

单元测试覆盖：candidate lifecycle、source versioning、source span range validation、fact promotion policy、review item lifecycle、conflict policy gate、source-of-truth order invariants。

Contract tests 覆盖：ActionRequest、DraftCandidate、AcceptedFragment、SourceDelta、MemoryWritebackPreview、ReviewItem、ContextPack、OpenAPI compatibility。

Golden tests 覆盖 Story Skills：input fixture、expected structured output、expected review finding、expected writeback preview、expected non-promotion behavior。

Integration tests 覆盖：SourceDelta -> SourceSpan -> MemoryWritebackPreview、low risk promotion、medium risk ReviewItem、high risk block promotion、ContextPack build with canon/risk separation。

End-to-end tests 覆盖最小用户旅程：作者选中一段文本，发起 ActionRequest，获得 DraftCandidate，采纳一句，生成 SourceDelta，看到 MemoryWritebackPreview，低风险自动记住或中风险进入 Review。

## 15. Observability 与审计

必须记录：request id、action request id、source delta id、source version id、skill run id、prompt version、model/provider、structured output validation result、review item creation reason、promotion policy decision、latency/cost。

日志中不得记录完整用户手稿明文，除非写入受控 object store 并通过 ref 引用。

审计目标：能解释为什么某个事实进入 Memory；能追到它的 SourceSpan；能知道是否经过 Conflict Policy Gate；能重放某次 skill run；能判断某个 ReviewItem 是由哪个新证据触发。

## 16. 安全与数据边界

用户手稿、设定集、角色卡、导入材料属于敏感内容。

工程规则：

1. 不在普通日志打印全文。
2. Prompt input snapshot 存 object store，并有访问控制。
3. LLM raw output 存 ref，不在数据库热表存大文本。
4. Debug endpoint 默认关闭。
5. 生产环境不允许使用 mock auth。
6. Provider credentials 只从受控运行环境读取，不进入仓库。
7. CI 需要凭据扫描和依赖检查。

第一阶段权限模型可以采用 project-level ownership：user owns project，project owns sources，project owns memory objects，project owns review items。后续再扩展 collaboration、workspace 和 role-based permission。

## 17. 关键不变量

以下不变量必须由代码、测试和 CI 共同保护：

1. RawSource / SourceSpan 是证据根。
2. ProcessedMarkdownView 可重建，不是最终证据源。
3. Mention 先于 CanonicalEntity 稳定合并。
4. EventCandidate 先于 CanonicalEvent。
5. FactAssertion 可以 proposed/disputed，但不能未经 policy 变 canon。
6. Evidence / Log Writeback 先于 Canon Promotion。
7. Conflict Policy Gate 不阻断 ingest，只阻断高风险自动 promotion。
8. DraftCandidate 未被作者采纳前不能进入正文。
9. AcceptedFragment 不等于所有推断事实成立。
10. SourceDelta 才能触发 Memory 增量回写。
11. SourceSpan 才能作为正式事实和 ReviewItem 证据。
12. MemoryPage.current_canon 不能覆盖底层证据链。
13. GraphProjection / ContextPack 不能反写 source-of-truth。
14. AgentReviewFinding 不等于正式 ReviewItem。
15. 模型建议不能自动成为 canon。

## 18. 后续设计文档边界

本文档定义工程实现技术设计。后续可以新增以下文档，但不得与本文冲突：

```text
docs/adr/*.md
docs/tech-design/module-boundaries.md
docs/tech-design/ci-cd-and-csab.md
docs/tech-design/persistence-schema.md
docs/tech-design/llm-harness.md
docs/tech-design/frontend-integration.md
```

执行计划、PR 顺序、任务拆分、排期应放在单独 planning 文档中，不放在本文档中。
