"""
Quantum Readiness Analyzer Tool - Layer 3.

Processes collected data to calculate scores.
Applies weighted scoring with confidence adjustments.
Maps results to archetype matrix.
Generates archetype narrative.
"""
import json
from typing import Any, Dict, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.protocols import SubgraphProtocol
from core.state import SubgraphState
from core.model_gateway import ModelGateway


class QuantumAnalyzerState(TypedDict, total=False):
    """StepData for Quantum Readiness Analyzer Tool."""
    
    # Input data (from data collector)
    user_industry: str
    branch_a_topics: Dict
    quantum_opportunity_score: float  # 0-100
    
    # Archetype
    archetype: str
    archetype_narrative: str

class QuantumAnalyzerTool(SubgraphProtocol):
    """
    Analyzer Tool for Quantum Readiness assessment.
    
    Processes collected data to:
    - Calculate weighted scores with confidence penalties
    - Map to 2x2 archetype matrix
    - Generate archetype narrative
    """
    
    name = "quantum_analyzer"
    
    def __init__(self, model_gateway: ModelGateway):
        self._model_gateway = model_gateway
    
    def describe(self) -> str:
        return "Analyzes collected quantum readiness data to calculate scores and determine archetype."
    
    def build(self):
        """Build the analyzer tool graph."""
        
        g = StateGraph(SubgraphState)
        g.add_node("analyze", self.analyze)
        g.add_node("init", self.init_step)
        g.add_edge(START, "init")
        g.add_edge("init", "analyze")
        g.add_edge("analyze", END)
        return g.compile()
    
    async def init_step(self, state: SubgraphState) -> SubgraphState:
        print(f"[ANALYZER] Input data keys: {list(state['stepData'].keys())}")

        stepData : QuantumAnalyzerState = {
            "user_industry": state["stepData"]["user_industry"],
            "branch_a_topics": state["stepData"]["branch_a_topics"],
            "quantum_opportunity_score": None,
            "archetype": None,
            "archetype_narrative": None,
        }
        state["currentStep"] = "analyzing"
        state["nextNode"] = "analyze"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None
        state["common_tool_input"] = None

        session_id = state.get("session_id", "unknown")
        print(f"[ANALYZER] Starting analysis for session: {session_id}")
        await adispatch_custom_event(
            "tool_start",
            {"tool_name": self.name, "total_steps": 1},
        )

        return state

    async def analyze(self, state: SubgraphState) -> SubgraphState:
        """
        Analyze collected data and calculate scores.
        
        Single-pass function - no user input needed.
        """
        
        branch_a_topics = state["stepData"].get("branch_a_topics", {}) or {}
        branch_a_weights = {
            "use_case_identification": 35,
            "technical_infrastructure_baseline": 25,
            "strategic_organizational_maturity": 25,
            "roadmap_ecosystem": 15,
        }

        branch_a_result = await self._score_branch("Branch A", branch_a_topics, branch_a_weights)
        branch_a_score = float(branch_a_result["total"])
        quantum_opportunity_score = branch_a_score
        state["stepData"]["quantum_opportunity_score"] = quantum_opportunity_score
        print(f"[ANALYZER] Branch A score: {branch_a_score:.1f}")

        if quantum_opportunity_score >= 70:
            archetype = "Act Now + Explore"
        elif quantum_opportunity_score >= 50:
            archetype = "Prepare + Explore"
        else:
            archetype = "Build Foundations"
        
        state["stepData"]["archetype"] = archetype
        print(f"[ANALYZER] Determined archetype: {archetype}")
        self._log_model_quality_debug_analyzer(
            branch_a_topics=branch_a_topics,
            branch_a_weights=branch_a_weights,
            branch_a_result=branch_a_result,
            branch_a_score=branch_a_score,
            archetype=archetype,
        )
        
        # Generate archetype narrative
        print(f"[ANALYZER] Generating archetype narrative...")
        # TODO : "company name" not in data...
        narrative_prompt = f"""Generate a 2-3 sentence narrative explaining what the "{archetype}" archetype means for this company.

Context:
- Company: {state['stepData'].get('company_name', 'Unknown')}
- Industry: {state['stepData'].get('user_industry', 'Unknown')}
- Branch A (Quantum Competitiveness): {branch_a_score:.1f}/100

Be specific and actionable."""
        
        narrative = await self._model_gateway.chat(
            messages=[{"role": "user", "content": narrative_prompt}],
            temperature=0.7,
        )
        
        state["stepData"]["archetype_narrative"] = narrative.strip()
        print(f"[ANALYZER] ✓ Analysis complete - archetype: {archetype}")
        
        # Store results in step_data for presenter tool
        opportunity_breakdown = {
            topic: {
                "weighted_points": float(data["score"]),
                "weight_points": int(data["max_score"]),
                "raw_score": float(data["score"]),
                "confidence": data["confidence"],
            }
            for topic, data in branch_a_result["topic_scores"].items()
        }

        unknowns = []
        for section_name, section in (
            ("branch_a", branch_a_result["topic_scores"]),
        ):
            for dim_name, dim_data in section.items():
                if dim_data.get("confidence", "low") == "low":
                    unknowns.append(
                        {
                            "section": section_name,
                            "dimension": dim_name,
                            "details": dim_data.get("details", "Low-confidence input"),
                        }
                    )

        step_data = {
            **(state["stepData"]),
            "branch_a_score": branch_a_score,
            "branch_a_band": self._branch_a_band(branch_a_score),
            "opportunity_breakdown": opportunity_breakdown,
            "unknowns": unknowns,
        }
        state["stepData"] = step_data
        state["nextNode"] = "presenter"
        
        # Mark tool as complete and expose canonical tool_result envelope.
        await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": state["stepData"]},
        )
        print(f"[ANALYZER] ✓ Tool complete, output ready for presenter")
        
        return state
    
    # -------------------- Utils funcions -------------------------------

    async def _score_branch(
        self,
        branch_name: str,
        topics: Dict[str, Any],
        weights: Dict[str, int],
    ) -> Dict[str, Any]:
        prompt = f"""Score each topic for {branch_name} from 0 to its max weight.
Output STRICT JSON:
{{
"scores": [
{{"topic":"topic_key","score":12,"reason":"short reason"}},
...
]
}}
Topics with weights and answers:
{json.dumps([{"topic": k, "max_score": w, "answer": topics.get(k)} for k, w in weights.items()], ensure_ascii=False)}
"""
        parsed_scores: Dict[str, Dict[str, Any]] = {}
        raw_model_output = ""
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            raw_model_output = (raw or "").strip()
            start = raw_model_output.find("{")
            end = raw_model_output.rfind("}") + 1
            data = json.loads(raw_model_output[start:end]) if start >= 0 and end > start else {}
            for item in data.get("scores", []):
                if isinstance(item, dict) and item.get("topic"):
                    parsed_scores[str(item["topic"])] = {
                        "score": int(item.get("score", 0)),
                        "reason": str(item.get("reason", "")),
                    }
        except Exception:
            parsed_scores = {}
            raw_model_output = raw_model_output or "ERROR: failed to parse model scoring output."

        topic_scores = {}
        total = 0.0
        scoring_trace = {}
        for topic, max_score in weights.items():
            answer = topics.get(topic)
            has_answer = bool(str(answer).strip()) if answer is not None else False
            fallback = int(round(max_score * 0.5)) if has_answer else 0
            score = parsed_scores.get(topic, {}).get("score", fallback)
            score = max(0, min(int(max_score), int(score)))
            used_fallback = topic not in parsed_scores
            topic_scores[topic] = {
                "score": score,
                "max_score": max_score,
                "details": answer or "No response",
                "reason": parsed_scores.get(topic, {}).get("reason", ""),
                "confidence": "medium" if has_answer else "low",
            }
            scoring_trace[topic] = {
                "input_answer": answer or "",
                "parsed_score": parsed_scores.get(topic, {}).get("score"),
                "fallback_score": fallback,
                "final_score": score,
                "used_fallback": used_fallback,
            }
            total += score
        return {
            "total": total,
            "topic_scores": topic_scores,
            "debug": {
                "branch_name": branch_name,
                "weights": weights,
                "raw_model_output": raw_model_output,
                "parsed_scores": parsed_scores,
                "scoring_trace": scoring_trace,
            },
        }
    
    def _branch_a_band(self, score: float) -> Dict[str, str]:
        if score <= 25:
            return {"name": "Quantum Unaware", "recommended_focus": "Build awareness and map high-value use cases before investing."}
        if score <= 45:
            return {"name": "Quantum Curious", "recommended_focus": "Validate use cases against strong classical baselines."}
        if score <= 65:
            return {"name": "Quantum Exploring", "recommended_focus": "Run internal pilots and secure a dedicated budget line."}
        if score <= 80:
            return {"name": "Quantum Preparing", "recommended_focus": "Deepen capability, formalize roadmap, monitor competitors."}
        return {"name": "Quantum Ready", "recommended_focus": "Scale validated pilots and protect quantum-derived IP."}

    def _log_model_quality_debug_analyzer(
        self,
        branch_a_topics: Dict[str, Any],
        branch_a_weights: Dict[str, int],
        branch_a_result: Dict[str, Any],
        branch_a_score: float,
        archetype: str,
    ) -> None:
        debug_payload = branch_a_result.get("debug", {})
        print(
            "\n[MODEL_QUALITY_DEBUG_ANALYZER]"
            f"\n- model: {self._model_gateway.default_model}"
            f"\n- scoring_branch: {debug_payload.get('branch_name', 'Branch A')}"
            f"\n- input_topics: {json.dumps(branch_a_topics, ensure_ascii=False)}"
            f"\n- weights: {json.dumps(branch_a_weights, ensure_ascii=False)}"
            f"\n- raw_model_output: {debug_payload.get('raw_model_output', '')}"
            f"\n- parsed_scores: {json.dumps(debug_payload.get('parsed_scores', {}), ensure_ascii=False)}"
            f"\n- scoring_trace: {json.dumps(debug_payload.get('scoring_trace', {}), ensure_ascii=False)}"
            f"\n- final_branch_a_score: {branch_a_score:.1f}"
            f"\n- final_archetype: {archetype}"
            "\n[/MODEL_QUALITY_DEBUG_ANALYZER]\n"
        )
