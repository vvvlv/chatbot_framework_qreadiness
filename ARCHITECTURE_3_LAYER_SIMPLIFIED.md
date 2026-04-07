# 3-Layer Architecture (Simplified, Diagram-Ready)

This framework is organized into **three layers** so we can build many chatbot “apps” on top of one reusable platform.

- **Layer 1 (Core / Platform)**: owns the global execution loop and streaming
- **Layer 2 (Apps / Use cases)**: owns the “what are we trying to do?” workflow
- **Layer 3 (Tools)**: owns reusable building blocks the apps call (collector/analyzer/presenter/etc.)

The key idea: **Layer 1 runs the show**, **Layer 2 chooses the app flow**, **Layer 3 does the work**.

---

## 1) The three layers (what each box is)

### Layer 1 — Core (Platform-owned)

**Purpose:** One consistent runtime for *all* chatbots.

**Responsibilities (simple):**
- Receives user messages (API entrypoint)
- Loads / resumes conversation state (per `thread_id`)
- Decides **which app** (Layer 2) should handle the message
- Streams events back to the UI (SSE: tokens + tool events)

**Think of it as:** the “operating system” for chat apps.

**Where in repo:** `backend/core/` + `backend/api/`

---

### Layer 2 — Apps (Use-case subgraphs)

**Purpose:** Define the workflow for one product/use case.

**Responsibilities (simple):**
- Orchestrates **which tools run, in what order**
- Decides branching (e.g., “if missing info → go back to collector”)
- Hands outputs from one tool to the next

**Think of it as:** the “business process” (the app’s flowchart).

**Where in repo:** `backend/apps/<app_name>/`

Example: `backend/apps/quantum_readiness/subgraph.py`

---

### Layer 3 — Tools (Reusable capabilities)

**Purpose:** Reusable subgraphs/patterns that do one kind of job well.

**Responsibilities (simple):**
- Perform a focused task (e.g., collect fields, analyze, present report)
- Ask the user questions when needed
- Validate and rewrite user input into structured field values
- Emit tool-specific events (question/progress/complete) for the UI

**Think of it as:** “components” the apps assemble.

**Where in repo:** `backend/tools/`

Examples:
- `tools/quantum_data_collector/` (fills fields via adaptive Q&A)
- `tools/quantum_analyzer/` (turns fields into assessment results)
- `tools/quantum_presenter/` (formats a report)

---

## 2) How execution flows (boxes and arrows)

Use this as the main diagram:

```text
User (UI)
  |
  | 1) message + thread_id
  v
Layer 1: Core Runtime (API + Core Graph)
  |
  | 2) load/resume state for thread_id
  | 3) route to an App
  v
Layer 2: App Subgraph (Use case flow)
  |
  | 4) call Tool A -> Tool B -> Tool C ...
  v
Layer 3: Tools (reusable subgraphs)
  |
  | 5) emit events (question/progress/complete)
  | 6) sometimes pause for user input
  v
SSE Stream back to UI (live updates)
```

---

## 3) The most important concept: STATE (what to diagram)

If you only diagram one thing, diagram this:

- There is **one shared state object** per conversation (keyed by `thread_id`)
- Each layer “owns” part of that state
- When a tool pauses, the whole state is checkpointed
- On the next user message, the state is restored and execution continues

### 3.1 “State envelope” (boxes inside boxes)

```text
Conversation State (per thread_id)
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Core-owned state                                   │
│ - messages (chat history)                                   │
│ - routing (active_subgraph, subgraph_status, intent)         │
│ - output (final text)                                       │
│ - metadata (session info for UI / streaming)                 │
│                                                             │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ Layer 2: App-owned state                               │ │
│   │ - which tool is active                                 │ │
│   │ - app progress / orchestration flags                   │ │
│   │                                                       │ │
│   │   ┌─────────────────────────────────────────────────┐ │ │
│   │   │ Layer 3: Tool-owned state                        │ │ │
│   │   │ - step / retries                                 │ │ │
│   │   │ - step_data (collected fields, intermediate data) │ │ │
│   │   │ - is_complete / error                             │ │ │
│   │   └─────────────────────────────────────────────────┘ │ │
│   └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Caption idea for the diagram:** “Each layer can only write to the part it owns.”

### 3.2 Why state ownership matters

- **Reusability**: tools don’t depend on one specific app
- **Safety**: core doesn’t need to know tool internals
- **Resume correctness**: the system can stop mid-tool and continue later without losing its place

---

## 4) How “pause and resume” works (state + checkpoint)

Tools can ask a question and **pause** until the user answers.

**Diagram snippet (pause/resume loop):**

```text
Tool asks a question
  |
  | emits: tool_question
  | pauses: interrupt(question)
  v
State is checkpointed (saved) for this thread_id
HTTP response ends (UI shows the question)

User answers later (same thread_id)
  |
  v
Checkpoint is loaded (restores state exactly)
Core resumes the exact paused tool step
```

**Why this matters:** the UI feels conversational, but the system is still executing a structured workflow.

---

## 5) The “steps” of each layer (graph nodes)

This section is the most diagrammable: it’s the **actual node sequence**.

### 5.1 Layer 1 — Core Graph nodes (platform steps)

Core graph (simplified):

```text
session_manager
  -> intent_router
  -> (dispatch)
      -> app_subgraph (Layer 2)   OR
      -> fallback_llm
  -> output_formatter
```

What each node does (1 line each):
- **`session_manager`**: loads/resumes state for `thread_id`, trims history, sets metadata
- **`intent_router`**: chooses which app to run (or locks to the active app when resuming)
- **`dispatch`**: jumps into the chosen app subgraph, or uses fallback LLM
- **`output_formatter`**: normalizes the final output for streaming completion

Where in repo: `backend/core/nodes/` and `backend/core/graph.py`

---

### 5.2 Layer 2 — App Subgraph nodes (use-case steps)

Example: **Quantum Readiness App** (simplified):

```text
collector_tool
  -> collector_to_analyzer (handoff/cleanup)
  -> analyzer_tool
  -> analyzer_to_presenter (handoff/cleanup)
  -> presenter_tool
```

What the app subgraph is responsible for:
- picking the **order** of tools
- deciding **which tool runs next**
- clearing/handoffs of tool inputs/outputs between tools

Where in repo: `backend/apps/quantum_readiness/subgraph.py`

---

### 5.3 Layer 3 — Tool graph nodes (tool-internal steps)

Tools are also graphs. They typically follow a pattern like:

```text
tool_start
  -> maybe_emit_question
      -> interrupt()   (pause here)
  -> resume_with_user_answer
  -> validate_and_rewrite_answer
      -> (ok?) store_field_value
      -> (not ok?) ask_followup_question -> interrupt() (pause again)
  -> tool_complete
```

Notes for the diagram:
- A tool can “loop” internally by asking follow-ups until the field is filled
- Every `interrupt()` is a checkpoint boundary (save state → wait → resume)

Where in repo: `backend/tools/<tool_name>/tool.py`

---

### 5.4 One compact “call stack” view (end-to-end)

This is a great central diagram:

```text
Layer 1 Core:
  session_manager -> intent_router -> dispatch

Layer 2 App:
  collector -> analyzer -> presenter

Layer 3 Tool (inside collector):
  ask_question -> interrupt -> resume -> validate/rewrite -> store -> next_field ...
```

---

## 6) State ownership rule (prevents spaghetti)

Simple rule for a diagram caption:

- **Core (L1)** owns “global” state and routing.
- **Apps (L2)** own “workflow” state (which step of the use case we’re in).
- **Tools (L3)** own “task” state (step-by-step progress, collected fields, etc.).

This keeps tools reusable across apps, and keeps apps reusable inside the same platform.

---

## 7) Concrete example (Quantum Readiness)

This is a diagram-friendly example flow:

```text
Layer 1 (Core) routes to:
  Layer 2 (Quantum Readiness App), which runs:
    Layer 3 Tools:
      1) Data Collector (fills fields)
      2) Analyzer (scores + insights)
      3) Presenter (final report)
```

---

## 8) Suggested diagram layout for a designer (state-first)

If you want a clean visual:

- **Center the diagram around the “State envelope”** (boxes-inside-boxes).
- On the left, show **User message + thread_id** entering Core.
- In the middle, show **Core loading state** and routing to an App.
- In the App lane, show **active_tool** switching between tools.
- In the Tool lane, show a tool writing **step_data** and sometimes calling **interrupt()**.
- On the right, show **SSE stream** of events back to the UI.
- Add a small **checkpoint icon** at the interrupt point: “save state” → “load state”.

