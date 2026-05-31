# 02. 模块边界

本文档定义后端 modular monolith 的包边界、导入规则和代码所有权。目标是让 100% AI coding 也无法轻易越过 source-of-truth、LLM trust boundary 和 persistence boundary。

## 顶层结构

```text
backend/src/sextant/
  api/
  application/
  contracts/
  domain/
  skills/
  ports/
  infra/
  common/
```

| 包 | 责任 | 禁止 |
|---|---|---|
| `api` | HTTP routing、auth/session、DTO 映射、OpenAPI | 领域判断、DB session commit、直接 LLM 调用 |
| `application` | use case 编排、事务边界、幂等、权限、job dispatch | 直接依赖 FastAPI、SQLAlchemy model、provider SDK |
| `contracts` | Pydantic DTO、OpenAPI schema、skill input/output schema | 调用 repository、写 DB、调用 LLM |
| `domain` | 领域对象、状态机、不变量、policy、value object | 依赖 api、infra、ORM、provider SDK |
| `skills` | Story Skill 处理协议、确定性规则、模型判断边界 | commit DB、直接改 MemoryPage.current_canon、绕过 policy |
| `ports` | repository、LLM、embedding、clock、id、object store 接口 | 具体实现、环境变量读取 |
| `infra` | SQLAlchemy、Alembic、LLM provider、worker、object store、observability | 定义领域不变量 |
| `common` | 无领域语义的基础类型和错误基类 | 反向 import domain 业务对象 |

## 允许导入矩阵

```text
api          -> application, contracts, common
application  -> domain, ports, contracts, common
contracts    -> common
domain       -> domain.common, common
skills       -> domain, ports, contracts, common
ports        -> domain, contracts, common
infra        -> domain, ports, contracts, common
```

禁止：

```text
domain -> api
domain -> infra
domain -> contracts if contracts import framework/runtime concerns
skills -> infra
api -> infra.db session
api -> infra.llm provider
application -> concrete provider SDK
contracts -> repository or service
```

## tach 目标规则

`backend/tach.toml` 必须表达至少以下规则：

```text
sextant.domain may import sextant.common
sextant.ports may import sextant.domain, sextant.contracts, sextant.common
sextant.skills may import sextant.domain, sextant.ports, sextant.contracts, sextant.common
sextant.application may import sextant.domain, sextant.ports, sextant.contracts, sextant.common
sextant.api may import sextant.application, sextant.contracts, sextant.common
sextant.infra may import sextant.domain, sextant.ports, sextant.contracts, sextant.common
```

`tach check` 是 PR 快速门，不允许跳过。

## Domain 包边界

```text
domain/
  source/
  manuscript/
  memory/
  review/
  agent/
  storytelling/
  context/
  common/
```

| 包 | 领域对象 |
|---|---|
| `source` | RawSource、SourceVersion、ProcessedMarkdownView、SourceDelta、SourceSpan |
| `manuscript` | AcceptedFragment、target range、base hash 校验 |
| `memory` | Mention、AliasRecord、CanonicalEntity、CanonicalEvent、FactAssertion、MemoryPage |
| `review` | ReviewItem、Conflict Policy Gate、review resolution |
| `agent` | ActionRequest、DraftCandidate、BeatCandidate、AgentReviewFinding |
| `storytelling` | RoleSlot、CharacterCastingDecision、NewCharacterSeed、SceneSequelMode、DramaticBehaviorPlan、ProseRenderingContract |
| `context` | WritingContextPack、MemoryAnswer、ContextPackReadiness |

Domain 层只能表达规则，不能选择数据库事务或模型 provider。

## Application Use Case 边界

每个 use case 必须是一个明确类或函数，命名使用动词短语：

```text
SubmitActionRequest
BuildWritingContextPack
RunStorySkill
CreateDraftCandidate
ReviewDraftCandidate
AcceptCandidate
CreateSourceDelta
RunMemoryWriteback
ResolveReviewItem
AnswerWithEvidence
```

Use case 负责：

1. 权限检查。
2. 幂等键检查。
3. 事务开启与提交。
4. 调用 repository port。
5. 调用 Story Skill 或 job dispatch。
6. 产生 audit record。

Use case 不负责：

1. 直接拼 SQL。
2. 直接调用模型 provider SDK。
3. 直接构造 GraphProjection canon edge。
4. 静默吞掉 policy failure。

## Skills 边界

Story Skill 是受控领域处理协议，不是任意 agent 函数。

Skill 可以读取：

```text
project/request context
schema pack
source spans
memory refs
review refs
clock
id generator
repository ports
LLM port
audit sink
```

Skill 输出必须是 schema-versioned structured output。

Skill 禁止：

```text
commit database transaction
set MemoryPage.current_canon directly
set FactAssertion.fact_status = canon directly
create ReviewItem outside review policy/factory
write GraphProjection canon edge directly
call concrete provider SDK
read environment secrets
```

## Infra 边界

Infra 实现 port，不拥有领域规则。

| Infra 组件 | 可做 | 禁止 |
|---|---|---|
| SQLAlchemy repository | 持久化 domain/contract 对象 | 决定 promotion policy |
| Alembic migration | 变更 schema | 修改 source-of-truth 顺序 |
| LLM adapter | 调模型并返回 structured result | 判断输出是否 canon |
| Worker | 执行 job、重试、记录状态 | 绕过 application use case |
| Object store adapter | 保存 raw text、offset map、prompt snapshot | 在热表存大文本 |

## 目录级 AGENTS.md

后续实现应新增目录级 `AGENTS.md`：

```text
backend/src/sextant/domain/AGENTS.md
backend/src/sextant/skills/AGENTS.md
backend/src/sextant/infra/AGENTS.md
backend/src/sextant/api/AGENTS.md
web/AGENTS.md
prompts/AGENTS.md
```

每份文件只声明该目录的边界和禁止行为，不重新定义业务契约。

## 验收

一个模块边界 PR 通过条件：

1. `tach check` 能阻止至少一个人工构造的非法导入示例。
2. `domain` 没有 FastAPI、SQLAlchemy、Redis、provider SDK import。
3. `api` 没有直接 DB commit 或 provider 调用。
4. `skills` 没有 concrete infra import。
5. 所有包有明确 public exports 或文档化入口。
