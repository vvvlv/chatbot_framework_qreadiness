# Branch comparison: `alex` vs `chloe`

**Generated:** 2026-05-15  
**Repository:** `chatbot_framework_qreadiness`  
**Commit (both branches):** `c4020c7` — *Conversational data collection, usage tracking, and report persistence.*

---

## Executive summary

| Item | Value |
|------|--------|
| **`alex` HEAD** | `c4020c7` — all new work lives here (`origin/alex`) |
| **`chloe` HEAD** | `1a0ab21` — **unchanged** (`origin/chloe`) |
| **Diff `chloe..alex`** | 12 files, **+1,187 / −130** lines |
| **Previous `alex` tip (before overwrite)** | `27cb08e` — *question division test1* |

`chloe` was **not** pushed with the feature commit. A mistaken local commit on `chloe` was reverted with `git reset --hard origin/chloe`.

This document covers:

1. Everything on **`alex`** that is not on **`chloe`** (`1a0ab21..c4020c7`).
2. How the **previous** `alex` line (`27cb08e`) differed from current `alex` (historical context).

---

## 1. Changes on `alex` only (`1a0ab21` → `c4020c7`)

**Baseline (`chloe`):** `1a0ab21` — *merging API_URL and VALIDATOR_MODEL factorizations from vercel branch*  
**Tip (`alex`):** `c4020c7` — *Conversational data collection, usage tracking, and report persistence.*  
**Scope:** 12 files, **+1,187 / −130** lines

### 1.1 Quantum data collector — conversational one-question flow

**File:** `backend/apps/quantum_readiness/subgraphs/quantum_data_collector/tool.py`

| Area | Before | After |
|------|--------|--------|
| Question model | Grouped / field-level default questions | **Section intro** + **ordered atomic questions** per field (9 questions across 4 fields) |
| Turn structure | Multi-part prompts per field | **One question per turn**, conversational section intros |
| Clarifications | Unbounded / ad hoc | **Max 1 auto-clarification** per atomic question; `/clarify` with preset then LLM rephrase |
| State tracking | Minimal | `current_question_index`, `section_intro_sent`, `clarification_count_by_question`, `awaiting_clarification`, etc. |
| Short answers | Often rejected as “no information” | Task 1 treats yes/no/not-yet as valid; `_short_answer_information()` fallback |
| Summaries | Verbose | `_compact_information_summary()` — deduped, capped (~90 words) |
| AI completion (“pretend to be me”) | Existing | Tighter prompt (≤25 words, one sentence) + post-truncation |
| Post-collection | — | Two-step wrap-up: optional **company name**, then **report save opt-out** (`post_collection_stage` 1→2→3) |

**User-facing effect:** The assessment feels like a guided interview (intro → single question → optional clarification) instead of a form-like block of questions.

### 1.2 LLM usage tracking (new)

**New files:**

- `backend/core/usage_context.py` — request-scoped `session_id` / `user_id` / `caller` via `contextvars`
- `backend/core/usage_tracker.py` — Postgres table `llm_usage_events`, LiteLLM token/cost extraction, aggregates

**Wiring:**

| File | Change |
|------|--------|
| `backend/core/model_gateway.py` | Records usage after each `litellm.acompletion` |
| `backend/core/llm.py` | `configure_model_gateway(usage_tracker=...)` |
| `backend/api/main.py` | Instantiates `UsageTracker`, closes pool on shutdown |
| `backend/api/routes/chat.py` | Sets usage context per chat request; **`GET /api/debug/usage`** with `start`, `end`, `session_id`, `user_id` filters |

**Example SQL (last hour cost):**

```sql
SELECT COALESCE(SUM(cost_usd), 0) AS cost_usd_last_hour
FROM llm_usage_events
WHERE created_at >= NOW() - INTERVAL '1 hour';
```

**Requires:** `DATABASE_URL`, `INTERACTION_LOG_DB_URL`, or `USAGE_TRACKER_DB_URL`.

### 1.3 Final report persistence

| File | Change |
|------|--------|
| `backend/core/interaction_logger.py` | `final_reports` table + `log_final_report()` |
| `backend/api/streaming.py` | On `text_done`, if output contains `QUANTUM READINESS REPORT` and user did not opt out → persist report |
| `backend/apps/quantum_readiness/subgraphs/quantum_presenter/tool.py` | Uses `company_name_for_report` when rendering the report |

### 1.4 Fallback LLM guardrails

**File:** `backend/core/nodes/fallback_llm.py`

- Strict system prompt: not a general chatbot; redirect to assessment only
- Heuristic off-topic detection before/after LLM call
- Lower temperature (0.2); canned redirect messages when guardrails trigger

### 1.5 Frontend

**File:** `frontend/app/components/ChatWindow.tsx`

- **Session ID** shown top-right above the Feedback button (plain text, no border)
- Layout tweaks for header / responsive behavior

---

## 2. File-level diff (`1a0ab21` → `c4020c7`)

| File | Δ lines (approx.) | Role |
|------|-------------------|------|
| `quantum_data_collector/tool.py` | +554 | Atomic questions, clarification, post-collection |
| `usage_tracker.py` | +307 (new) | Usage DB + stats API backing |
| `fallback_llm.py` | +158 | Guardrails |
| `api/routes/chat.py` | +65 | Usage context, debug endpoint |
| `interaction_logger.py` | +57 | Final report logging |
| `api/streaming.py` | +34 | Report save on stream complete |
| `model_gateway.py` | +33 | Usage recording |
| `ChatWindow.tsx` | +40 | Session ID UI |
| `api/main.py`, `llm.py`, `usage_context.py`, `quantum_presenter/tool.py` | smaller | Wiring / naming |

---

## 3. Historical: previous `alex` (`27cb08e`) vs current `alex` (`c4020c7`)

When `alex` was overwritten, it dropped a divergent line of work. Compared to **current** `alex`:

| Area | Previous `alex` | Current (`c4020c7`) |
|------|-----------------|---------------------|
| Data collector | Large experimental rewrite (“question division test1”) | Production conversational atomic flow on `chloe` base |
| Dashboard | Local `dashboard/` app + `docker-compose` service | **Removed** from current tree |
| Interaction logger | Different / slimmer implementation | Unified logger + `final_reports` |
| Streaming / chat routes | Divergent | Aligned with usage tracking + report persistence |
| Frontend | Partial overlap | `chloe` UI (palette, feedback, help) + session ID placement |

**Diff stat `27cb08e..c4020c7`:** 23 files, **+1,505 / −2,110** lines (net reduction; dashboard and old collector paths removed).

---

## 4. API additions (current branch)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/debug/usage` | LLM usage totals, by session/model/day, recent events |
| `GET` | `/api/debug/interactions` | *(existing)* Interaction event tail |

Query params for usage: `session_id`, `user_id`, `start`, `end` (ISO-8601), `limit`.

---

## 5. Operational notes

- **Checkpointer:** Runtime may still use `InMemorySaver` unless Postgres checkpointer is configured — conversation state is lost on backend restart.
- **Usage costs:** `cost_usd` comes from LiteLLM `completion_cost`; zero cost usually means missing model pricing in LiteLLM’s cost map.
- **Branches:** `git diff chloe..alex` shows alex-only changes; `git diff alex..chloe` should be empty on `chloe`’s side.

---

## 6. How to regenerate this comparison

```bash
# Alex-only diff (chloe unchanged at 1a0ab21)
git diff chloe..alex

# Same as above, explicit commits
git diff 1a0ab21..c4020c7 --stat

# What old alex had vs current alex
git diff 27cb08e..c4020c7 --stat
git log --oneline 27cb08e..c4020c7
```

---

*Document reflects: `chloe` @ `1a0ab21`, `alex` @ `c4020c7` on `origin/alex`.*
