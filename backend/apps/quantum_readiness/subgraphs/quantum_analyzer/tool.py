"""
Quantum Readiness Analyzer Tool - Layer 3.

Processes collected data to calculate scores.
Applies weighted scoring with confidence adjustments.
Maps results to archetype matrix.
Generates archetype narrative.
"""
import json
from typing import Any, Dict, Literal, TypedDict

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
    branch_b_topics: Dict
    
    # Output scores
    crypto_risk_score: float  # 0-100
    crypto_risk_level: Literal["low", "medium", "high", "critical"]
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
            "branch_b_topics": state["stepData"]["branch_b_topics"],
            "crypto_risk_score": None,
            "crypto_risk_level": None,
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
        branch_b_topics = state["stepData"].get("branch_b_topics", {}) or {}

        branch_a_weights = {
            "use_case_identification": 35,
            "technical_infrastructure_baseline": 25,
            "strategic_organizational_maturity": 25,
            "roadmap_ecosystem": 15,
        }
        branch_b_weights = {
            "data_exposure_profile": 35,
            "migration_readiness": 30,
            "supply_chain_ecosystem": 20,
            "governance": 15,
        }

        branch_a_result = await self._score_branch("Branch A", branch_a_topics, branch_a_weights)
        branch_b_result = await self._score_branch("Branch B", branch_b_topics, branch_b_weights)

        branch_a_score = float(branch_a_result["total"])
        branch_b_score = float(branch_b_result["total"])

        # Compatibility mapping:
        quantum_opportunity_score = branch_a_score
        crypto_risk_score = 100.0 - branch_b_score  # Branch B high => lower risk exposure
        state["stepData"]["quantum_opportunity_score"] = quantum_opportunity_score
        state["stepData"]["crypto_risk_score"] = crypto_risk_score
        print(f"[ANALYZER] Branch A score: {branch_a_score:.1f}")
        print(f"[ANALYZER] Branch B score: {branch_b_score:.1f}")

        # Preserve existing risk-level semantics for compatibility.
        if crypto_risk_score >= 70:
            state["stepData"]["crypto_risk_level"] = "critical"
        elif crypto_risk_score >= 50:
            state["stepData"]["crypto_risk_level"] = "high"
        elif crypto_risk_score >= 30:
            state["stepData"]["crypto_risk_level"] = "medium"
        else:
            state["stepData"]["crypto_risk_level"] = "low"
        print(f"[ANALYZER] Derived risk level: {state['stepData']['crypto_risk_level']}")
        
        # Map to archetype (2x2 matrix)
        risk_high = crypto_risk_score >= 50
        opportunity_high = quantum_opportunity_score >= 50
        
        print(f"[ANALYZER] Mapping to archetype - risk_high: {risk_high}, opportunity_high: {opportunity_high}")
        
        if risk_high and opportunity_high:
            archetype = "Act Now + Explore"
        elif risk_high and not opportunity_high:
            archetype = "Act Now + Secure"
        elif not risk_high and opportunity_high:
            archetype = "Wait + Explore"
        else:
            archetype = "Wait + Monitor"
        
        state["stepData"]["archetype"] = archetype
        print(f"[ANALYZER] Determined archetype: {archetype}")
        
        # Generate archetype narrative
        print(f"[ANALYZER] Generating archetype narrative...")
        # TODO : "company name" not in data...
        narrative_prompt = f"""Generate a 2-3 sentence narrative explaining what the "{archetype}" archetype means for this company.

Context:
- Company: {state['stepData'].get('company_name', 'Unknown')}
- Industry: {state['stepData'].get('user_industry', 'Unknown')}
- Branch A (Quantum Competitiveness): {branch_a_score:.1f}/100
- Branch B (PQC Readiness): {branch_b_score:.1f}/100
- Derived crypto risk exposure: {crypto_risk_score:.1f}/100 ({state['stepData']['crypto_risk_level']})

Be specific and actionable."""
        
        narrative = await self._model_gateway.chat(
            messages=[{"role": "user", "content": narrative_prompt}],
            temperature=0.7,
        )
        
        state["stepData"]["archetype_narrative"] = narrative.strip()
        print(f"[ANALYZER] ✓ Analysis complete - archetype: {archetype}")
        
        # Store results in step_data for presenter tool
        risk_breakdown = {
            topic: {
                "weighted_points": float(data["score"]),
                "weight_points": int(data["max_score"]),
                "raw_score": float(data["score"]),
                "confidence": data["confidence"],
            }
            for topic, data in branch_b_result["topic_scores"].items()
        }
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
            ("branch_b", branch_b_result["topic_scores"]),
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
            "branch_b_score": branch_b_score,
            "branch_a_band": self._branch_a_band(branch_a_score),
            "branch_b_band": self._branch_b_band(branch_b_score),
            "risk_breakdown": risk_breakdown,
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
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = (raw or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end]) if start >= 0 and end > start else {}
            for item in data.get("scores", []):
                if isinstance(item, dict) and item.get("topic"):
                    parsed_scores[str(item["topic"])] = {
                        "score": int(item.get("score", 0)),
                        "reason": str(item.get("reason", "")),
                    }
        except Exception:
            parsed_scores = {}

        topic_scores = {}
        total = 0.0
        for topic, max_score in weights.items():
            answer = topics.get(topic)
            has_answer = bool(str(answer).strip()) if answer is not None else False
            fallback = int(round(max_score * 0.5)) if has_answer else 0
            score = parsed_scores.get(topic, {}).get("score", fallback)
            score = max(0, min(int(max_score), int(score)))
            topic_scores[topic] = {
                "score": score,
                "max_score": max_score,
                "details": answer or "No response",
                "reason": parsed_scores.get(topic, {}).get("reason", ""),
                "confidence": "medium" if has_answer else "low",
            }
            total += score
        return {"total": total, "topic_scores": topic_scores}
    
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

    def _branch_b_band(self, score: float) -> Dict[str, str]:
        if score <= 25:
            return {"name": "Critical Exposure", "recommended_focus": "Run an urgent cryptographic audit and develop a CBOM."}
        if score <= 45:
            return {"name": "High Risk", "recommended_focus": "Build inventory, evaluate NIST PQC, and assess vendor roadmaps."}
        if score <= 65:
            return {"name": "Moderate Risk", "recommended_focus": "Set migration timelines and enforce cryptographic agility."}
        if score <= 80:
            return {"name": "Managing", "recommended_focus": "Accelerate supply-chain alignment and stress-test response plans."}
        return {"name": "Post-Quantum Ready", "recommended_focus": "Maintain agility and extend PQC requirements across partners."}