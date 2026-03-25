"""
Quantum Readiness Analyzer Tool - Layer 3.

Processes collected data to calculate scores.
Applies weighted scoring with confidence adjustments.
Maps results to archetype matrix.
Generates archetype narrative.
"""
from typing import Dict, Literal, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.protocols import ToolProtocol
from core.state import ToolState
from core.model_gateway import ModelGateway


class QuantumAnalyzerState(ToolState, total=False):
    """State for Quantum Readiness Analyzer Tool."""
    
    # Input data (from data collector)
    user_industry: str
    user_interest_driver: str
    crypto_risk_dimensions: Dict[str, Dict]
    quantum_opportunity_dimensions: Dict[str, Dict]
    
    # Output scores
    crypto_risk_score: float  # 0-100
    crypto_risk_level: Literal["low", "medium", "high", "critical"]
    quantum_opportunity_score: float  # 0-100
    
    # Archetype
    archetype: str
    archetype_narrative: str


class QuantumAnalyzerTool(ToolProtocol):
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
        
        async def analyze(state: QuantumAnalyzerState) -> QuantumAnalyzerState:
            """
            Analyze collected data and calculate scores.
            
            Single-pass function - no user input needed.
            """
            session_id = state.get("session_id", "unknown")
            print(f"[ANALYZER] Starting analysis for session: {session_id}")
            await adispatch_custom_event(
                "tool_start",
                {"tool_name": self.name, "total_steps": 1},
            )
            
            # Get data from explicit subgraph handoff only.
            tool_input = state.get("tool_input", {})
            if tool_input and isinstance(tool_input, dict) and "step_data" in tool_input:
                step_data = tool_input.get("step_data", {})
            else:
                step_data = tool_input if isinstance(tool_input, dict) else {}
            print(f"[ANALYZER] Input data keys: {list(step_data.keys())}")
            
            # Extract dimensions
            crypto_dims = step_data.get("crypto_risk_dimensions", {})
            opp_dims = step_data.get("quantum_opportunity_dimensions", {})
            
            # Calculate Cryptographic Risk Score
            crypto_weights = {
                "data_sensitivity": 0.35,
                "crypto_visibility": 0.25,
                "migration_progress": 0.25,
                "compliance_exposure": 0.15,
            }
            
            print(f"[ANALYZER] Calculating crypto risk score from {len(crypto_dims)} dimensions...")
            crypto_risk_score = 0.0
            for dimension, weight in crypto_weights.items():
                if dimension in crypto_dims:
                    dim_data = crypto_dims[dimension]
                    raw_score = dim_data.get("score", 0)
                    confidence = dim_data.get("confidence", "medium")
                    
                    # Apply confidence penalty
                    confidence_multiplier = {
                        "high": 1.0,
                        "medium": 0.9,
                        "low": 0.7,
                    }.get(confidence, 0.7)
                    
                    adjusted_score = (raw_score / 100.0) * confidence_multiplier
                    contribution = adjusted_score * weight * 100
                    crypto_risk_score += contribution
                    print(f"[ANALYZER]   {dimension}: {raw_score} (raw) * {confidence_multiplier} (confidence) * {weight} (weight) = {contribution:.1f}")
            
            state["crypto_risk_score"] = crypto_risk_score
            print(f"[ANALYZER] Total crypto risk score: {crypto_risk_score:.1f}/100")
            
            # Determine risk level
            if crypto_risk_score >= 70:
                state["crypto_risk_level"] = "critical"
            elif crypto_risk_score >= 50:
                state["crypto_risk_level"] = "high"
            elif crypto_risk_score >= 30:
                state["crypto_risk_level"] = "medium"
            else:
                state["crypto_risk_level"] = "low"
            print(f"[ANALYZER] Crypto risk level: {state['crypto_risk_level']}")
            
            # Calculate Quantum Opportunity Score
            opportunity_weights = {
                "problem_solution_fit": 0.40,
                "org_readiness": 0.30,
                "tech_maturity": 0.20,
                "strategic_horizon": 0.10,
            }
            
            print(f"[ANALYZER] Calculating quantum opportunity score from {len(opp_dims)} dimensions...")
            quantum_opportunity_score = 0.0
            for dimension, weight in opportunity_weights.items():
                if dimension in opp_dims:
                    dim_data = opp_dims[dimension]
                    raw_score = dim_data.get("score", 0)
                    confidence = dim_data.get("confidence", "medium")
                    
                    # Apply confidence penalty
                    confidence_multiplier = {
                        "high": 1.0,
                        "medium": 0.9,
                        "low": 0.7,
                    }.get(confidence, 0.7)
                    
                    adjusted_score = (raw_score / 100.0) * confidence_multiplier
                    contribution = adjusted_score * weight * 100
                    quantum_opportunity_score += contribution
                    print(f"[ANALYZER]   {dimension}: {raw_score} (raw) * {confidence_multiplier} (confidence) * {weight} (weight) = {contribution:.1f}")
            
            state["quantum_opportunity_score"] = quantum_opportunity_score
            print(f"[ANALYZER] Total quantum opportunity score: {quantum_opportunity_score:.1f}/100")
            
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
            
            state["archetype"] = archetype
            print(f"[ANALYZER] Determined archetype: {archetype}")
            
            # Generate archetype narrative
            print(f"[ANALYZER] Generating archetype narrative...")
            narrative_prompt = f"""Generate a 2-3 sentence narrative explaining what the "{archetype}" archetype means for this company.

Context:
- Company: {step_data.get('company_name', 'Unknown')}
- Industry: {step_data.get('user_industry', 'Unknown')}
- Crypto Risk Score: {crypto_risk_score:.1f}/100 ({state['crypto_risk_level']})
- Quantum Opportunity Score: {quantum_opportunity_score:.1f}/100

Be specific and actionable."""
            
            narrative = await self._model_gateway.chat(
                messages=[{"role": "user", "content": narrative_prompt}],
                temperature=0.7,
            )
            
            state["archetype_narrative"] = narrative.strip()
            print(f"[ANALYZER] ✓ Analysis complete - archetype: {archetype}")
            
            # Store results in step_data for presenter tool
            risk_breakdown = {}
            for dimension, weight in crypto_weights.items():
                dim_data = crypto_dims.get(dimension, {})
                raw_score = float(dim_data.get("score", 0))
                confidence = dim_data.get("confidence", "low")
                confidence_multiplier = {"high": 1.0, "medium": 0.9, "low": 0.7}.get(confidence, 0.7)
                weighted_points = (raw_score / 100.0) * confidence_multiplier * (weight * 100.0)
                risk_breakdown[dimension] = {
                    "weighted_points": round(weighted_points, 2),
                    "weight_points": int(weight * 100),
                    "raw_score": raw_score,
                    "confidence": confidence,
                }

            opportunity_breakdown = {}
            for dimension, weight in opportunity_weights.items():
                dim_data = opp_dims.get(dimension, {})
                raw_score = float(dim_data.get("score", 0))
                confidence = dim_data.get("confidence", "low")
                confidence_multiplier = {"high": 1.0, "medium": 0.9, "low": 0.7}.get(confidence, 0.7)
                weighted_points = (raw_score / 100.0) * confidence_multiplier * (weight * 100.0)
                opportunity_breakdown[dimension] = {
                    "weighted_points": round(weighted_points, 2),
                    "weight_points": int(weight * 100),
                    "raw_score": raw_score,
                    "confidence": confidence,
                }

            unknowns = []
            for section_name, section in (
                ("crypto_risk", crypto_dims),
                ("quantum_opportunity", opp_dims),
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

            state["step_data"] = {
                **step_data,
                "crypto_risk_score": crypto_risk_score,
                "crypto_risk_level": state["crypto_risk_level"],
                "quantum_opportunity_score": quantum_opportunity_score,
                "archetype": archetype,
                "archetype_narrative": state["archetype_narrative"],
                "risk_breakdown": risk_breakdown,
                "opportunity_breakdown": opportunity_breakdown,
                "unknowns": unknowns,
            }
            
            # Mark tool as complete and set tool_output for subgraph
            state["is_complete"] = True
            state["tool_status"] = "done"
            state["tool_output"] = {"step_data": state["step_data"], "is_complete": True}
            await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
            await adispatch_custom_event(
                "tool_complete",
                {"tool_name": self.name, "step_data": state["step_data"]},
            )
            print(f"[ANALYZER] ✓ Tool complete, output ready for presenter")
            
            return state
        
        g = StateGraph(QuantumAnalyzerState)
        g.add_node("analyze", analyze)
        g.add_edge(START, "analyze")
        g.add_edge("analyze", END)
        return g.compile()
