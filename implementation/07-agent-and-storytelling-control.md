# 07. Agent and Storytelling Control

This document engineers the full Agent path from `goals/20-33`. The implementation target is complete production behavior, not a minimal continuation bot.

## Owner Model

```text
WritingContextPack Builder
  -> CharacterAgencyPass
  -> StorytellingControlLayer
  -> NextPageAgent
  -> AgentReview
  -> Author decision
  -> SourceDelta
  -> Memory ingest
```

| Stage | Writes Memory | Output |
|---|---:|---|
| WritingContextPack Builder | no | WritingContextPack |
| CharacterAgencyPass | no | agency conclusions |
| StorytellingControlLayer | no | control objects |
| NextPageAgent | no | BeatCandidate / DraftCandidate |
| AgentReview | no | AgentReviewFinding |
| Author accept | no direct memory | AcceptedFragment / SourceDelta |
| Memory ingest | yes | SourceSpan, Memory, ReviewItem |

## WritingContextPack

Required sections:

```text
current_position
canonical_context
pov_constraint
active_characters
character_agency_state
recent_events
character_knowledge
object_location_state
open_threads
risk_context
style_memory
evidence_refs
```

Rules:

1. Canonical context can be used as fact.
2. Risk context cannot be written as fact.
3. POV constraint must include forbidden knowledge.
4. Style memory is prose support, not story fact.
5. Character agency state is derived from Memory/Review context for behavior
   guidance, including active CharacterKnowledge as read-only knowledge state,
   and cannot create or replace facts.
6. Token-budget truncation is a snapshot retrieval policy only: it may remove
   lower-relevance context entries from a WritingContextPack, but it must not
   mutate Memory, ReviewItem, Canon, GraphProjection, SourceDelta, or provider
   state.
7. Semantic recall is a read-only vocabulary-expansion retrieval policy. It
   may use AliasRecord text and MemoryPage titles/open threads to rank existing
   evidence-backed entries, but it cannot write facts, canon, reviews, memory,
   graph state, SourceDelta, or provider state.

## CharacterAgencyPass

Inputs:

```text
WritingContextPack
active characters
current text window
author intent
```

Outputs:

```text
natural_action
likely_dialogue_move
hidden_pressure
forbidden_action
agency_rationale
conflict_opportunity
```

Rules:

1. It reasons about character behavior, not plot outline.
2. Non-POV inner state may inform constraints but cannot be directly written into prose.
3. proposed/disputed memory can only create caution, not action fact.

## StorytellingControlLayer

Execution profiles:

| Profile | When | Required output |
|---|---|---|
| `full_storytelling` | new beat, new passage, scene progression | RoleSlot, casting, mode, dramatic plan, ProseRenderingContract |
| `rewrite_light` | rewrite current page | dramatic plan, ProseRenderingContract |
| `line_polish` | local line/style edit | minimal ProseRenderingContract |
| `risk_review_only` | risk check | AgentReviewFinding inputs only |

The layer produces control objects only. It cannot generate prose.

## RoleSlot

RoleSlot fields:

```text
role_slot_id
function
scene_need
required_traits
required_knowledge
risk_level
can_use_existing_character
reason_not_existing
```

Common functions:

```text
witness
gatekeeper
messenger
pressure_source
contrast_character
clue_holder
local_color
antagonist_proxy
emotional_mirror
complication
```

## CharacterCastingDecision

Decision types:

```text
reuse_existing
create_new
avoid_character
```

Rules:

1. Reuse requires natural presence and matching motivation.
2. Create new is allowed for low-risk local functions.
3. Major-character creation requires author-visible risk.
4. Avoid decisions prevent convenient but contrived reuse.

## NewCharacterSeed

NewCharacterSeed is draft-local.

Fields:

```text
seed_id
role_function
display_hint
scope
traits
voice_hint
knowledge_boundary
narrative_purpose
promotion_hint
risk
```

Rules:

1. Seed does not create CanonicalEntity.
2. If accepted in text, Memory ingest extracts Mention and decides entity/memory depth.
3. `major_candidate` must create high or medium AgentReviewFinding.

## SceneSequelMode

Modes:

```text
scene
sequel
mixed
```

Required decision output:

```text
passage_mode
mode_rationale
current_pressure
scene_goal
opposition
tactic
escalation
setback_or_turn
reaction
dilemma
evaluation
decision
new_goal
required_turn
inner_state_budget
ending_shape
```

Rules:

1. Scene mode needs goal, opposition, turn or setback.
2. Sequel mode needs reaction, dilemma, decision.
3. Mixed mode still needs a small change or choice.
4. No-turn output triggers AgentReviewFinding.

## DramaticBehaviorPlan

Purpose: turn internal state into writeable behavior.

Allowed channels:

```text
action
dialogue
silence
object
sensory
choice
thought
```

Rules:

1. POV character can have limited direct thought within budget.
2. Non-POV character cannot have direct mind-reading.
3. Important emotion should appear through action, dialogue, object, silence, or choice.

## ProseRenderingContract

This is the final contract given to prose generation.

Required fields:

```text
passage_mode
pov_character
pov_mode
target_position
scene_goal
opposition
required_turn
allowed_cast
new_character_policy
role_slots
character_casting_decisions
dramatic_behavior_plan
inner_state_budget
forbidden_knowledge
risk_context
style_constraints
ending_shape
hard_no
```

Hard constraints:

```text
no non-POV inner mind
no proposed/disputed fact as canon
no forbidden knowledge leak
no target range overwrite
no new character beyond policy
no automatic ReviewItem resolution
```

## NextPageAgent Modes

| Mode | Input | Output |
|---|---|---|
| suggest_next_beat | context + agency + control | BeatCandidate list |
| draft_next_passage | selected beat + ProseRenderingContract | DraftCandidate |
| rewrite_current_page | current text + ProseRenderingContract | DraftCandidate |

All outputs are candidates. None become manuscript text without author acceptance.

## AgentReview

AgentReview checks:

```text
POV
canon
forbidden knowledge
character agency
cast policy
dramatic behavior
scene/sequel mode
prose contract
style
overreach
target range
```

Current production gates include draft-local `no_turn_risk` for passages that
lack a detectable turn, draft-local `scene_mode_risk` for scene-mode passages
that lack detectable goal or opposition signals, draft-local
`mode_mixing_risk` for mixed-mode passages that lack a detectable small action,
short reaction, or small decision, draft-local `sequel_mode_risk` for
sequel-mode passages that lack detectable dilemma or decision signals, and
draft-local `telling_over_action` when a DramaticBehaviorPlan disallows direct
thought but the draft directly states inner state. Paragraphs that pack at
least three direct inner-state sentences create draft-local
`inner_state_overload`, unless an explicit inner-state budget violation has
higher priority. A DramaticBehaviorPlan that requires visible choice also
creates draft-local `choice_missing` when the candidate lacks a detectable
choice signal. Show-not-tell targets create draft-local `exposition_risk` when
the draft relies on explanatory sentences without observable scene behavior.
Subtext targets create draft-local `subtext_missing` when dialogue states
information directly instead of carrying the requested subtext. Explicit
dramatic rendering targets create draft-local `dramatization_risk` when the
draft lacks detectable visible behavior, dialogue, or choice signals. Large
story-scope jumps and finality language create draft-local `control_risk` when
the candidate appears to decide major story direction for the author, including
elapsed-time jumps, generic case/thread closure, public truth spread, and
irreversible departure/finality language. These findings do not create formal
`ReviewItem` rows before author acceptance.

It emits `AgentReviewFinding`, using `goals/26` risk_type.

AgentReview cannot create `ReviewItem`; accepted text must first become SourceDelta and SourceSpan.

## Blocked Candidate Override

`blocked` means not safe to offer as normal prose. It is not absolute censorship.

Override rules:

1. Author must explicitly override.
2. `override_reason` must be stored.
3. High-risk findings stay attached.
4. If accepted, Memory gate may still block canon promotion.

## Acceptance

Agent/storytelling implementation is complete when:

1. Contract tests prove candidate generation does not create SourceDelta.
2. AgentReviewFinding cannot become ReviewItem pre-acceptance.
3. ProseRenderingContract hard_no violation creates high risk finding.
4. NewCharacterSeed accepted into text goes through normal Memory ingest.
5. Risk context proposed fact cannot be written as canon in generated prose without finding.
