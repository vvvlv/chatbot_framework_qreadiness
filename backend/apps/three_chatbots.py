"""
Three subchatbots for the quantum journey:
1) quantum_competitiveness
2) cryptographic_risk_security
3) roadmap_chatbot
"""
import json
from typing import Any, Dict, List, Optional

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.model_gateway import ModelGateway
from core.protocols import SubgraphProtocol, ToolProtocol
from core.state import SubgraphState


def _normalize_answer(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("text", "")).strip()
    return str(raw or "").strip()


class StructuredJourneySubgraph(SubgraphProtocol):
    """Reusable interrupt-based conversational subchatbot."""

    def __init__(
        self,
        *,
        name: str,
        title: str,
        description: str,
        intro_text: str,
        questions: List[str],
        next_chatbot: Optional[str],
        model_gateway: ModelGateway,
        interrupt_tool: ToolProtocol,
    ):
        self.name = name
        self._title = title
        self._description = description
        self._intro_text = intro_text
        self._questions = questions
        self._next_chatbot = next_chatbot
        self._model_gateway = model_gateway
        self._interrupt_tool = interrupt_tool

    def describe(self) -> str:
        return self._description

    def build(self):
        g = StateGraph(SubgraphState)
        g.add_node("init", self._init_node)
        g.add_node("ask", self._ask_node)
        g.add_node("interrupt", self._interrupt_tool.build())
        g.add_node("process", self._process_node)
        g.add_node("finalize", self._finalize_node)

        g.add_edge(START, "init")
        g.add_edge("init", "ask")
        g.add_edge("ask", "interrupt")
        g.add_edge("interrupt", "process")
        g.add_conditional_edges("process", self._route_after_process, {"ask": "ask", "finalize": "finalize"})
        g.add_edge("finalize", END)
        return g.compile()

    async def _init_node(self, state: SubgraphState) -> SubgraphState:
        state["stepData"] = {
            "chatbot_name": self.name,
            "chatbot_title": self._title,
            "question_idx": 0,
            "answers": [],
            "context_message": (state.get("metadata") or {}).get("context_message"),
        }
        state["currentStep"] = f"{self.name}_collecting"
        state["nextNode"] = "ask"
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None
        state["common_tool_input"] = None
        await adispatch_custom_event(
            "tool_start",
            {"tool_name": self.name, "total_steps": len(self._questions)},
        )
        await adispatch_custom_event(
            "tool_intro",
            {
                "tool_name": self.name,
                "title": self._title,
                "text": self._intro_text,
            },
        )
        return state

    async def _ask_node(self, state: SubgraphState) -> SubgraphState:
        idx = int(state["stepData"].get("question_idx", 0))
        question = self._questions[idx]
        context_message = state["stepData"].get("context_message")
        if idx == 0 and context_message:
            question = f"Provided context: {context_message}\n\n{question}"

        prompt_id = state.get("pending_prompt_id") or f"{self.name}-q{idx + 1}"
        state["pending_prompt_id"] = prompt_id
        state["common_tool_input"] = {
            "nextNode": "process",
            "args": {
                "text": f"[{self._title}] Question {idx + 1}/{len(self._questions)}: {question}",
                "prompt_id": prompt_id,
                "step": idx + 1,
                "input_type": "free_text",
                "can_skip": True,
            },
        }
        state["nextNode"] = "interrupt"
        await adispatch_custom_event(
            "tool_question",
            {
                "tool_name": self.name,
                "text": state["common_tool_input"]["args"]["text"],
                "prompt_id": prompt_id,
                "step": idx + 1,
            },
        )
        return state

    async def _process_node(self, state: SubgraphState) -> SubgraphState:
        idx = int(state["stepData"].get("question_idx", 0))
        raw_answer = (state.get("common_tool_output") or {}).get("answer")
        answer_text = _normalize_answer(raw_answer)
        if answer_text.lower() == "/skip":
            answer_text = "SKIPPED"

        state["stepData"]["answers"].append(
            {"question": self._questions[idx], "answer": answer_text}
        )
        state["stepData"]["question_idx"] = idx + 1
        state["pending_prompt_id"] = None
        state["nextNode"] = "ask" if idx + 1 < len(self._questions) else "finalize"
        await adispatch_custom_event(
            "tool_progress",
            {"step": idx + 1, "total": len(self._questions)},
        )
        return state

    async def _finalize_node(self, state: SubgraphState) -> SubgraphState:
        answers = state["stepData"].get("answers", [])
        chatbot_summary = await self._build_structured_report(state, answers)

        metadata = state.get("metadata", {})
        completed = list(metadata.get("completed_chatbots", []))
        if self.name not in completed:
            completed.append(self.name)
        metadata["completed_chatbots"] = completed

        summaries = dict(metadata.get("chatbot_summaries", {}))
        summaries[self.name] = chatbot_summary
        metadata["chatbot_summaries"] = summaries
        metadata["context_message"] = None
        if self._next_chatbot:
            metadata["recommended_next_chatbot"] = self._next_chatbot
            handoff = (
                f"\n\n### Suggested Next Step\n"
                f"Continue with `{self._next_chatbot}` to keep the recommended flow."
            )
        else:
            metadata["recommended_next_chatbot"] = None
            ordered_chatbots = [
                "quantum_competitiveness",
                "cryptographic_risk_security",
                "roadmap_chatbot",
            ]
            recap_sections: List[str] = []
            for chatbot in ordered_chatbots:
                section = str(summaries.get(chatbot, "")).strip()
                if section and section not in recap_sections:
                    recap_sections.append(section)
            recap = "\n\n".join(recap_sections).strip()
            handoff = (
                "\n\n## Final Recap Across the Journey\n"
                "You can revisit each chatbot summary from the UI at any time.\n\n"
                f"{recap}"
            )

        state["metadata"] = metadata
        state["output"] = f"{chatbot_summary}{handoff}"
        state["nextNode"] = END
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": {"summary": chatbot_summary}},
        )
        return state

    async def _route_after_process(self, state: SubgraphState) -> str:
        return str(state.get("nextNode", "finalize"))

    async def _build_structured_report(self, state: SubgraphState, answers: List[Dict[str, str]]) -> str:
        if self.name == "quantum_competitiveness":
            return await self._competitiveness_report(answers)
        if self.name == "cryptographic_risk_security":
            return await self._risk_report(answers)
        return await self._roadmap_report(answers)

    async def _competitiveness_report(self, answers: List[Dict[str, str]]) -> str:
        prompt = f"""You are scoring a quantum competitiveness assessment.

Answers:
{json.dumps(answers, ensure_ascii=False)}

Return STRICT JSON:
{{
  "quantum_opportunity_score": 0-100 integer,
  "opportunity_level": "Low Opportunity|Emerging Opportunity|Moderate Opportunity|High Opportunity",
  "archetype": "Act Now + Explore|Act Now + Secure|Wait + Explore|Wait + Monitor",
  "archetype_narrative": "2-3 concise sentences",
  "breakdown": {{
    "problem_solution_fit": 0-40 integer,
    "organizational_readiness": 0-30 integer,
    "tech_data_maturity": 0-20 integer,
    "strategic_horizon": 0-10 integer
  }}
}}
Only JSON."""
        data = await self._safe_json_response(prompt)
        breakdown = data.get("breakdown", {}) if isinstance(data, dict) else {}
        psf = int(breakdown.get("problem_solution_fit", 0))
        org = int(breakdown.get("organizational_readiness", 0))
        tech = int(breakdown.get("tech_data_maturity", 0))
        strat = int(breakdown.get("strategic_horizon", 0))
        total = int(data.get("quantum_opportunity_score", max(0, min(100, psf + org + tech + strat)))) if isinstance(data, dict) else 0
        level = (data.get("opportunity_level") if isinstance(data, dict) else None) or self._opportunity_level(total)
        archetype = (data.get("archetype") if isinstance(data, dict) else None) or ("Act Now + Explore" if total >= 60 else "Wait + Explore")
        narrative = (data.get("archetype_narrative") if isinstance(data, dict) else None) or "This indicates meaningful opportunity, with execution quality depending on capability and operating maturity."
        return (
            "## Quantum Competitiveness Chatbot - Results\n\n"
            "### 1. SCORES AT A GLANCE\n"
            f"Quantum Opportunity Score: **{total} / 100**  📈 **{level}**\n\n"
            "### 2. YOUR ARCHETYPE\n"
            f"→ **\"{archetype}\"**\n"
            f"{narrative}\n\n"
            "### 3. SCORE BREAKDOWN\n"
            "Quantum Opportunity\n"
            f"- Problem-Solution Fit: **{psf} / 40**\n"
            f"- Organizational Readiness: **{org} / 30**\n"
            f"- Tech & Data Maturity: **{tech} / 20**\n"
            f"- Strategic Horizon: **{strat} / 10**\n"
        )

    async def _risk_report(self, answers: List[Dict[str, str]]) -> str:
        prompt = f"""You are scoring a cryptographic risk and post-quantum security assessment.

Answers:
{json.dumps(answers, ensure_ascii=False)}

Return STRICT JSON:
{{
  "risk_exposure_score": 0-100 integer,
  "risk_level": "Low|Moderate|High|Critical",
  "archetype": "Act Now + Secure|Act Now + Explore|Wait + Secure|Wait + Monitor",
  "archetype_narrative": "2-3 concise sentences",
  "breakdown": {{
    "data_exposure_profile": 0-35 integer,
    "migration_readiness": 0-30 integer,
    "supply_chain_ecosystem": 0-20 integer,
    "governance": 0-15 integer
  }}
}}
Only JSON."""
        data = await self._safe_json_response(prompt)
        breakdown = data.get("breakdown", {}) if isinstance(data, dict) else {}
        d = int(breakdown.get("data_exposure_profile", 0))
        m = int(breakdown.get("migration_readiness", 0))
        s = int(breakdown.get("supply_chain_ecosystem", 0))
        g = int(breakdown.get("governance", 0))
        readiness = max(0, min(100, d + m + s + g))
        risk = int(data.get("risk_exposure_score", 100 - readiness)) if isinstance(data, dict) else 100 - readiness
        risk_level = (data.get("risk_level") if isinstance(data, dict) else None) or self._risk_level(risk)
        archetype = (data.get("archetype") if isinstance(data, dict) else None) or ("Act Now + Secure" if risk >= 50 else "Wait + Monitor")
        narrative = (data.get("archetype_narrative") if isinstance(data, dict) else None) or "This is an estimate based on provided responses and should be validated with detailed technical inventories."
        return (
            "## Cryptographic Risk & Security Chatbot - Results\n\n"
            "### 1. SCORES AT A GLANCE\n"
            f"Risk Exposure Score: **{risk} / 100**  🔐 **{risk_level}**\n\n"
            "### 2. YOUR ARCHETYPE\n"
            f"→ **\"{archetype}\"**\n"
            f"{narrative}\n\n"
            "### 3. SCORE BREAKDOWN\n"
            "Post-Quantum Security Readiness Inputs\n"
            f"- Data & Exposure Profile: **{d} / 35**\n"
            f"- Migration Readiness: **{m} / 30**\n"
            f"- Supply Chain & Ecosystem: **{s} / 20**\n"
            f"- Governance: **{g} / 15**\n"
        )

    async def _roadmap_report(self, answers: List[Dict[str, str]]) -> str:
        prompt = f"""Draft a concise roadmap summary from these answers:
{json.dumps(answers, ensure_ascii=False)}
Return STRICT JSON:
{{
  "strategic_focus": "short sentence",
  "next_30_days": ["item1","item2","item3"],
  "next_90_days": ["item1","item2","item3"],
  "watchouts": ["item1","item2"]
}}
Only JSON."""
        data = await self._safe_json_response(prompt)
        focus = (data.get("strategic_focus") if isinstance(data, dict) else None) or "Build a staged, low-regret roadmap with measurable checkpoints."
        next30 = data.get("next_30_days", []) if isinstance(data, dict) else []
        next90 = data.get("next_90_days", []) if isinstance(data, dict) else []
        watchouts = data.get("watchouts", []) if isinstance(data, dict) else []
        return (
            "## Quantum Roadmap Chatbot - Results\n\n"
            "### Strategic Focus\n"
            f"{focus}\n\n"
            "### Next 30 Days\n"
            f"{self._bullet_lines(next30, fallback='Define one high-value pilot and owner.')}\n\n"
            "### Next 90 Days\n"
            f"{self._bullet_lines(next90, fallback='Run pilot, review outcomes, and update roadmap.')}\n\n"
            "### Watchouts\n"
            f"{self._bullet_lines(watchouts, fallback='Avoid over-committing before baseline capability is validated.')}\n"
        )

    async def _safe_json_response(self, prompt: str) -> Dict[str, Any]:
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            text = (raw or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end])
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
        return {}

    def _bullet_lines(self, items: Any, *, fallback: str) -> str:
        if not isinstance(items, list) or not items:
            return f"- {fallback}"
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        if not cleaned:
            return f"- {fallback}"
        return "\n".join(f"- {x}" for x in cleaned[:5])

    def _opportunity_level(self, score: int) -> str:
        if score >= 75:
            return "High Opportunity"
        if score >= 55:
            return "Emerging Opportunity"
        if score >= 35:
            return "Moderate Opportunity"
        return "Low Opportunity"

    def _risk_level(self, score: int) -> str:
        if score >= 75:
            return "Critical"
        if score >= 55:
            return "High"
        if score >= 35:
            return "Moderate"
        return "Low"


def build_journey_subgraphs(
    *,
    model_gateway: ModelGateway,
    interrupt_tool: ToolProtocol,
) -> List[StructuredJourneySubgraph]:
    return [
        StructuredJourneySubgraph(
            name="quantum_competitiveness",
            title="Quantum Competitiveness Chatbot",
            description=(
                "Evaluate quantum competitiveness readiness: strategic value, technical "
                "baseline, organizational maturity, and ecosystem positioning."
            ),
            intro_text=(
                "This chatbot evaluates your organization's quantum competitiveness posture. "
                "It will collect information about high-value use cases, technical baseline, "
                "organizational maturity, and ecosystem/roadmap signals."
            ),
            questions=[
                "Quantum Competitiveness - Use Case Identification: Tell us your industry and the most computationally intensive problems where quantum could matter, including optimization or intrinsic quantum research, and any current classical bottlenecks.",
                "Quantum Competitiveness - Technical & Infrastructure Baseline: Summarize your compute footprint, classical solution maturity, any quantum vendor relationships, and whether you have internal quantum expertise.",
                "Quantum Competitiveness - Strategic & Organizational Maturity: Describe your technology adoption posture, IP sensitivity, and whether budget for quantum exploration is dedicated or competing with other initiatives.",
                "Quantum Competitiveness - Roadmap & Ecosystem: Describe any internal quantum assessments/pilots, ecosystem or academic partnerships, and how you track competitor activity.",
            ],
            next_chatbot="cryptographic_risk_security",
            model_gateway=model_gateway,
            interrupt_tool=interrupt_tool,
        ),
        StructuredJourneySubgraph(
            name="cryptographic_risk_security",
            title="Cryptographic Risk & Security Chatbot",
            description=(
                "Assess cryptographic risk exposure and post-quantum security readiness "
                "across inventory, migration planning, and governance."
            ),
            intro_text=(
                "This chatbot assesses cryptographic and post-quantum security risk. "
                "It will collect information about data exposure horizon, crypto inventory, "
                "migration readiness, third-party risk, and governance ownership."
            ),
            questions=[
                "Cryptographic Risk & PQ Security - Data & Exposure Profile: Summarize how long sensitive data must remain confidential, how well you know your current encryption standards and cryptography inventory, key compliance drivers, and any long-lived public-key dependencies.",
                "Cryptographic Risk & PQ Security - Migration Readiness: Describe your current PQC migration status (NIST algorithms), vendor readiness checks, cryptographic agility in new systems, and your migration timeline/budget.",
                "Cryptographic Risk & PQ Security - Supply Chain & Ecosystem: Explain your third-party encryption exposure, expected contractual PQC pressure from customers/partners, and incident response preparedness for sudden cryptographic compromise.",
                "Cryptographic Risk & PQ Security - Governance: Describe executive-level ownership of quantum cryptographic risk and whether budget for PQC migration is dedicated.",
            ],
            next_chatbot="roadmap_chatbot",
            model_gateway=model_gateway,
            interrupt_tool=interrupt_tool,
        ),
        StructuredJourneySubgraph(
            name="roadmap_chatbot",
            title="Quantum Roadmap Chatbot",
            description=(
                "Turn readiness insights into an actionable roadmap with short-term "
                "priorities, decision milestones, and execution sequencing."
            ),
            intro_text=(
                "This chatbot builds a practical roadmap from your readiness context. "
                "It will collect information about strategic objectives, constraints, and "
                "near-term milestones to propose 30/90-day actions."
            ),
            questions=[
                "What is the main outcome you want from your quantum strategy in the next 12 months?",
                "Which constraints matter most right now (budget, skills, risk tolerance, vendor readiness)?",
                "What first pilot or migration milestone would be most realistic in the next quarter?",
            ],
            next_chatbot=None,
            model_gateway=model_gateway,
            interrupt_tool=interrupt_tool,
        ),
    ]
