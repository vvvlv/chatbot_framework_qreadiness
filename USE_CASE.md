# Use Case: Quantum Readiness Chatbot

This document specifies the problem domain and requirements for a Quantum Readiness Chatbot. This chatbot helps companies assess their readiness for quantum technologies through a structured conversational workflow, evaluating both cryptographic security risks and quantum opportunity potential.

## Overview

**Purpose**: Guide companies through a structured diagnostic conversation to assess:
1. **Cryptographic Risk**: Exposure to quantum computing threats (post-quantum cryptography readiness)
2. **Quantum Opportunity**: Potential competitive advantages from adopting quantum technologies

**Workflow Pattern**: **Multi-turn conversational workflow** that guides users step-by-step through a 5-stage assessment process. Each stage asks **one question at a time**, waits for the user's response, processes the answer, and then asks the next question. The conversation can span multiple API calls with state persisting between turns.

**Key Characteristics**:
- **One question per turn**: Each API call processes one user answer and asks the next question
- **State persistence**: Conversation state persists across API calls
- **Adaptive questioning**: Language adapts to user expertise level
- **Resumable**: Can resume from any stage if conversation is interrupted
- **Progressive data collection**: Each stage collects data incrementally before moving to the next

**Key Features**:
- Two separate scoring systems (Cryptographic Risk Score and Quantum Opportunity Score)
- Weighted dimensions with confidence adjustments
- RAG integration for benchmark documents (NIST, CISA, GRI timelines)
- Conversational, adaptive questioning (one question at a time)
- Resume capability for multi-session assessments
- Structured report generation with prioritized actions

---

## 1. Use Case Overview

### 1.1 Scenario

A chatbot that conducts a structured diagnostic conversation to assess a company's quantum readiness across two dimensions:

1. **Cryptographic Risk Assessment**: Evaluates exposure to quantum computing threats
   - Data sensitivity & longevity
   - Cryptographic visibility
   - Migration progress
   - Compliance exposure

2. **Quantum Opportunity Assessment**: Evaluates potential competitive advantages
   - Problem-solution fit
   - Organizational readiness
   - Tech & data maturity
   - Strategic horizon

### 1.2 Workflow Architecture (Tool-Based)

According to the framework architecture (`app_definition.md`), this use case is implemented as a **Layer 2 subgraph** that orchestrates **Layer 3 tools**. The workflow follows a tool-based pattern:

1. **Data Collection Tool** (Multi-turn, uses `interrupt()`)
   - Collects all required information through conversational questioning
   - Handles onboarding, cryptographic risk assessment, and quantum opportunity assessment
   - Uses `interrupt()` to pause execution and wait for user responses
   - Adapts questions based on user expertise level and previous answers

2. **Analyzer/Assessment Tool** (Single-pass, no user input)
   - Processes collected data to calculate scores
   - Applies weighted scoring with confidence adjustments
   - Maps results to archetype matrix
   - Generates archetype narrative

3. **Presenter/RAG Tool** (Single-pass, no user input)
   - Retrieves benchmark documents via RAG
   - Generates prioritized action list
   - Formats final readiness report

**Tool Flow**:

**Phase 1: Data Collection** (Multi-turn conversational flow)
- **Onboarding Questions** (2 questions minimum):
  - "To start, what industry are you working in?"
  - "What makes you interested in quantum technologies right now for your organization?"
  - After both answers: Set expertise level (default: intermediate)

- **Cryptographic Risk Assessment Questions** (4+ questions, one per dimension):
  - `data_sensitivity`: "How long does sensitive data need to remain confidential?"
  - `crypto_visibility`: "Do you have an inventory of where cryptography is used?"
  - `migration_progress`: "Have you begun using any post-quantum cryptography standards?"
  - `compliance_exposure`: "Are any systems subject to compliance requirements?"
  - Each answer is processed: extracts info, assigns score (0-1 normalized), assesses confidence
  - If answer is unclear, asks follow-up clarification question
  - Tool completes when all 4 dimensions have medium/high confidence data

- **Quantum Opportunity Assessment Questions** (4+ questions, one per dimension):
  - `problem_solution_fit`: Multiple questions about use case fit
  - `org_readiness`: Questions about internal capabilities
  - `tech_maturity`: Questions about infrastructure
  - `strategic_horizon`: Questions about budget and planning
  - Supports multiple answers per dimension (e.g., multiple use cases)
  - Tool completes when all dimensions are assessed

**Phase 2: Analysis** (Single-pass, no user input)
- Calculates Crypto Risk Score (0–100) and Opportunity Score (0–100)
- Applies weighted scoring with confidence penalties
- Maps to 2x2 archetype matrix
- Generates archetype narrative

**Phase 3: Presentation** (Single-pass, no user input)
- Retrieves benchmark documents via RAG
- Generates: score summary, narrative explanation, top 3 priority actions
- Lists "unknowns to resolve" based on low-confidence answers
- Provides timeline guidance using RAG-retrieved benchmark documents
- Returns final readiness report

**Important**: The Data Collection Tool uses `interrupt()` for each question. This means:
- Tool execution suspends after asking a question
- State is checkpointed automatically
- Next API call resumes the tool with the user's answer
- Tool logic stays in one function (ask and validate together)

### 1.3 Outputs

1. **Risk Level**: Cryptographic Risk Score (0-100) with risk category
2. **Readiness Score**: Quantum Opportunity Score (0-100) across dimensions
3. **Prioritized Action List**: Top 3 actions with references (NIST FIPS 203, CISA advisory, GRI Timeline Report)
4. **Timeline Guidance**: Roadmap suggestions based on benchmark documents

### 1.4 Requirements

**Core Workflow Requirements**:
- **Tool-based architecture**: Uses Layer 3 tools (DataCollectorTool, AnalyzerTool, PresenterTool) orchestrated by Layer 2 subgraph
- **Multi-turn conversation**: Data Collection Tool uses `interrupt()` for each question-answer pair
- **State persistence**: State persists across API calls via checkpointer
- **Sequential tool execution**: Tools execute in order (Data Collection → Analysis → Presentation)
- **One question at a time**: Data Collection Tool asks exactly one question per turn using `interrupt()`
- **Progressive data collection**: Data Collection Tool collects required data incrementally before completing

**Functional Requirements**:
- Score accumulation with confidence tracking
- RAG integration for benchmark documents (timelines, roadmaps, qubit estimates)
- Adaptive questioning based on user expertise level
- Resume capability if conversation is interrupted
- Streaming intermediate results to frontend
- Report generation with structured output

**Scoring Requirements**:

**Cryptographic Risk Dimensions** (weighted):
- `data_sensitivity`: 35% weight
- `crypto_visibility`: 25% weight
- `migration_progress`: 25% weight
- `compliance_exposure`: 15% weight

**Quantum Opportunity Dimensions** (weighted):
- `problem_solution_fit`: 40% weight
- `org_readiness`: 30% weight
- `tech_maturity`: 20% weight
- `strategic_horizon`: 10% weight

**Confidence Penalties**:
- High confidence: 1.0 multiplier
- Medium confidence: 0.9 multiplier
- Low confidence: 0.7 multiplier

**Archetype Mapping** (2x2 matrix):
- High Risk + High Opportunity = "Act Now + Explore"
- High Risk + Low Opportunity = "Act Now + Secure"
- Low Risk + High Opportunity = "Wait + Explore"
- Low Risk + Low Opportunity = "Wait + Monitor"

**Why This Example Matters**:

This Quantum Readiness Chatbot demonstrates how the framework handles **conversational multi-step workflows** using the tool-based architecture:
- **Data Collection Tool** uses `interrupt()` for multi-turn question-answer interactions
- **Analyzer Tool** processes collected data to generate scores and insights
- **Presenter/RAG Tool** formats results and retrieves benchmark documents
- Tools are orchestrated by a Layer 2 subgraph without modifying core framework
- Demonstrates how `interrupt()` keeps multi-step logic in one function (ask and validate together)
- Shows tool reusability (same DataCollectorTool pattern can be used for other assessments)
- Combines RAG (benchmark documents) with LLM (adaptive questioning and analysis)
- Tracks confidence levels and adjusts scores accordingly
- Adapts to user expertise level dynamically

**Tool-Based Workflow Pattern**:

According to `app_definition.md`, this workflow follows the three-layer architecture:
- **Layer 1 (Core)**: Handles session management, intent routing, and output formatting
- **Layer 2 (Subgraph)**: Orchestrates the tool sequence (Data Collection → Analysis → Presentation)
- **Layer 3 (Tools)**: Implements reusable interaction patterns using `interrupt()`

The Data Collection Tool demonstrates the `interrupt()` pattern:
- Tool asks a question and calls `interrupt(question)` to suspend execution
- Graph checkpoints state automatically
- Next API call uses `Command(resume=user_answer)` to continue
- Tool logic stays in one function (ask and validate together)

This pattern applies to **any diagnostic chatbot**: health assessments, financial readiness calculators, compliance checkers, technology adoption advisors, etc. - any use case where you need to guide users through a structured conversation step-by-step using reusable tools.

**Example Conversation Flow**:

```
API Call 1:
  User: "Hello"
  System: "To start, what industry are you working in?"

API Call 2 (same session_id):
  User: "I work in the AI industry"
  System: "What makes you interested in quantum technologies right now for your organization?"

API Call 3 (same session_id):
  User: "We need quantum-resistant cryptography"
  System: "Thanks, I have enough context... Next we'll look at your cryptographic risk posture."

API Call 4 (same session_id):
  User: "Our data needs to remain confidential for 10+ years"
  System: "Do you have an inventory of where cryptography is used across your infrastructure?"
  
... continues until all stages complete ...
```

---

## 2. Open Questions & Considerations

### 2.1 Domain Questions

1. **Should cryptographic assessment be separate?**
   - Option A: Keep as part of quantum readiness (current design)
   - Option B: Separate into two chatbots (crypto risk + quantum opportunity)
   - **Recommendation**: Keep together — they're complementary assessments

2. **Benchmark document selection**
   - Need to identify specific documents for RAG index
   - NIST FIPS 203, CISA advisories, GRI reports are good starting points
   - May need to curate and update regularly

3. **Weight and trait finalization**
   - Current weights are placeholders
   - Need domain expert validation
   - Should be configurable

### 2.2 User Experience Considerations

1. **Question sequencing**: Current design asks questions sequentially, but could be optimized based on user answers
2. **Confidence thresholds**: Need to determine when to probe vs. accept "don't know"
3. **Report formatting**: Final report structure may need refinement based on user feedback
4. **Timeline accuracy**: RAG-retrieved timelines need validation against authoritative sources

---

## 3. Next Steps

1. **Refine scoring weights** with domain experts
2. **Curate benchmark documents** for RAG index
3. **Test conversational flow** with real users
4. **Validate archetype mapping** logic
5. **Design report formatting** with proper styling
6. **Plan resume capability** for multi-session scenarios
