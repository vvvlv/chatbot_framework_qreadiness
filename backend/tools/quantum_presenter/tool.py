"""
Quantum Readiness Presenter/RAG Tool - Layer 3.

Retrieves benchmark documents via RAG.
Generates prioritized action list.
Formats final readiness report.
"""
from datetime import date
from typing import Dict, List, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.protocols import ToolProtocol
from core.state import ToolState
from core.model_gateway import ModelGateway
from tools.rag.retriever_base import RetrieverBase


class QuantumPresenterState(ToolState, total=False):
    """State for Quantum Readiness Presenter Tool."""
    
    # Input data (from analyzer)
    user_industry: str
    crypto_risk_score: float
    crypto_risk_level: str
    quantum_opportunity_score: float
    archetype: str
    archetype_narrative: str
    crypto_risk_dimensions: Dict[str, Dict]
    quantum_opportunity_dimensions: Dict[str, Dict]
    
    # Output
    benchmark_documents: List[Dict]
    priority_actions: List[Dict]
    timeline_guidance: str
    readiness_report: str
    next_step: str


class QuantumPresenterTool(ToolProtocol):
    """
    Presenter/RAG Tool for Quantum Readiness assessment.
    
    Formats results and retrieves benchmark documents.
    Generates prioritized action list and final report.
    """
    
    name = "quantum_presenter"
    
    def __init__(self, model_gateway: ModelGateway, retriever: RetrieverBase):
        self._model_gateway = model_gateway
        self._retriever = retriever
    
    def describe(self) -> str:
        return "Formats quantum readiness results and generates prioritized action list with benchmark references."
    
    def build(self):
        """Build the presenter tool graph."""
        
        async def present(state: QuantumPresenterState) -> QuantumPresenterState:
            """
            Format results and generate final report.
            
            Single-pass function - no user input needed.
            """
            session_id = state.get("session_id", "unknown")
            print(f"[PRESENTER] Generating report for session: {session_id}")
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
            
            crypto_score = step_data.get("crypto_risk_score", 0)
            opp_score = step_data.get("quantum_opportunity_score", 0)
            archetype = step_data.get("archetype", "Unknown")
            print(f"[PRESENTER] Scores - Risk: {crypto_score:.1f}, Opportunity: {opp_score:.1f}, Archetype: {archetype}")
            
            # Retrieve benchmark documents via RAG
            benchmark_query = f"""Quantum computing timelines, roadmaps, and qubit estimates for {step_data.get('user_industry', 'general')} industry.
Include NIST FIPS 203, CISA advisories, and GRI timeline reports."""
            
            print(f"[PRESENTER] Retrieving benchmark documents...")
            try:
                benchmark_docs = await self._retriever.retrieve(query=benchmark_query, top_k=5)
                state["benchmark_documents"] = benchmark_docs
                print(f"[PRESENTER] Retrieved {len(benchmark_docs)} benchmark documents")
            except Exception as e:
                print(f"[PRESENTER] ⚠ Error retrieving benchmarks: {e}")
                state["benchmark_documents"] = []
            
            # Format benchmark context
            benchmark_context = "\n---\n".join(
                doc.get("content", str(doc)) for doc in state["benchmark_documents"]
            ) if state["benchmark_documents"] else "No benchmark documents available."
            
            # Generate prioritized actions
            print(f"[PRESENTER] Generating prioritized actions...")
            actions_prompt = f"""Generate a prioritized action list for quantum readiness.

Company context:
- Industry: {step_data.get('user_industry', 'Unknown')}
- Archetype: {step_data.get('archetype', 'Unknown')}

Scores:
- Cryptographic Risk: {step_data.get('crypto_risk_score', 0):.1f}/100 ({step_data.get('crypto_risk_level', 'Unknown')})
- Quantum Opportunity: {step_data.get('quantum_opportunity_score', 0):.1f}/100

Benchmark documents:
{benchmark_context[:1000]}  # Truncate for context

Generate:
1. Top 3 priority actions (most urgent first)
2. For each action, provide:
   - Specific, concrete action item
   - Reference (NIST FIPS 203, CISA advisory, GRI Timeline Report, etc.)
   - Urgency level

Return JSON:
{{
    "priority_actions": [
        {{
            "action": "...",
            "priority": 1,
            "reference": "NIST FIPS 203",
            "urgency": "high"
        }},
        ...
    ],
    "next_step": "One concrete action for next 30 days"
}}"""
            
            try:
                actions_response = await self._model_gateway.chat(
                    messages=[{"role": "user", "content": actions_prompt}],
                    temperature=0.3,
                )
                
                # Try to parse JSON
                import json
                if "{" in actions_response and "}" in actions_response:
                    json_start = actions_response.find("{")
                    json_end = actions_response.rfind("}") + 1
                    json_str = actions_response[json_start:json_end]
                    actions_result = json.loads(json_str)
                    state["priority_actions"] = actions_result.get("priority_actions", [])
                    state["next_step"] = actions_result.get("next_step", "")
                    print(f"[PRESENTER] ✓ Generated {len(state['priority_actions'])} priority actions")
                else:
                    print(f"[PRESENTER] ⚠ Could not parse actions JSON from LLM response")
                    state["priority_actions"] = []
                    state["next_step"] = ""
            except Exception as e:
                print(f"[PRESENTER] ✗ Error generating actions: {e}")
                import traceback
                traceback.print_exc()
                state["priority_actions"] = []
                state["next_step"] = ""
            
            # Generate timeline guidance
            print(f"[PRESENTER] Generating timeline guidance...")
            timeline_prompt = f"""Based on the benchmark documents and company context, provide timeline guidance.

Benchmark context:
{benchmark_context[:1000]}

Company: {step_data.get('user_industry', 'Unknown')}
Current scores: Risk {step_data.get('crypto_risk_score', 0):.1f}, Opportunity {step_data.get('quantum_opportunity_score', 0):.1f}

Provide specific timeline recommendations based on the benchmarks."""
            
            try:
                timeline_response = await self._model_gateway.chat(
                    messages=[{"role": "user", "content": timeline_prompt}],
                    temperature=0.3,
                )
                state["timeline_guidance"] = timeline_response.strip()
                print(f"[PRESENTER] ✓ Timeline guidance generated")
            except Exception as e:
                print(f"[PRESENTER] ⚠ Error generating timeline: {e}")
                state["timeline_guidance"] = "Timeline guidance unavailable."
            
            # Generate final report
            print(f"[PRESENTER] Formatting final report...")
            state["readiness_report"] = self._format_report(step_data, state)
            
            # Set output for core graph
            state["output"] = state["readiness_report"]
            print(f"[PRESENTER] ✓ Report generated ({len(state['readiness_report'])} chars)")
            
            state["is_complete"] = True
            state["tool_status"] = "done"
            state["tool_output"] = {"step_data": state.get("step_data", {}), "is_complete": True}
            await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
            await adispatch_custom_event(
                "tool_complete",
                {"tool_name": self.name, "report_len": len(state["readiness_report"])},
            )
            return state
        
        g = StateGraph(QuantumPresenterState)
        g.add_node("present", present)
        g.add_edge(START, "present")
        g.add_edge("present", END)
        return g.compile()
    
    def _format_report(self, step_data: Dict, state: QuantumPresenterState) -> str:
        """Format the final quantum readiness report."""
        company = step_data.get("company_name") or "Your Company"
        industry = step_data.get("user_industry") or "Unknown Sector"
        today = date.today().isoformat()
        risk = step_data.get("crypto_risk_score", 0.0)
        opp = step_data.get("quantum_opportunity_score", 0.0)
        archetype = step_data.get("archetype", "Unknown")
        narrative = step_data.get("archetype_narrative", "")
        risk_breakdown = step_data.get("risk_breakdown", {})
        opp_breakdown = step_data.get("opportunity_breakdown", {})
        unknowns = step_data.get("unknowns", [])
        
        report = f"""
────────────────────────────────────────────
QUANTUM READINESS REPORT
Company: {company} | Sector: {industry} | Date: {today}
────────────────────────────────────────────

1. SCORES AT A GLANCE
   Cryptographic Risk Score:   {risk:.0f} / 100  {self._get_risk_emoji(step_data.get('crypto_risk_level', 'low'))} {step_data.get('crypto_risk_level', 'Low').title()} Risk
   Quantum Opportunity Score:  {opp:.0f} / 100  📈 {self._get_opportunity_level(opp)}

2. YOUR ARCHETYPE
   → "{archetype}"
   {narrative}

3. SCORE BREAKDOWN
   Cryptographic Risk
   - Data Sensitivity & Longevity   {risk_breakdown.get('data_sensitivity', {}).get('weighted_points', 0):>4.0f} / 35   {self._confidence_marker(risk_breakdown.get('data_sensitivity', {}).get('confidence', 'low'))}
   - Cryptographic Visibility       {risk_breakdown.get('crypto_visibility', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(risk_breakdown.get('crypto_visibility', {}).get('confidence', 'low'))}
   - Migration Progress             {risk_breakdown.get('migration_progress', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(risk_breakdown.get('migration_progress', {}).get('confidence', 'low'))}
   - Compliance Exposure            {risk_breakdown.get('compliance_exposure', {}).get('weighted_points', 0):>4.0f} / 15   {self._confidence_marker(risk_breakdown.get('compliance_exposure', {}).get('confidence', 'low'))}

   Quantum Opportunity
   - Problem-Solution Fit           {opp_breakdown.get('problem_solution_fit', {}).get('weighted_points', 0):>4.0f} / 40   {self._confidence_marker(opp_breakdown.get('problem_solution_fit', {}).get('confidence', 'low'))}
   - Organizational Readiness       {opp_breakdown.get('org_readiness', {}).get('weighted_points', 0):>4.0f} / 30   {self._confidence_marker(opp_breakdown.get('org_readiness', {}).get('confidence', 'low'))}
   - Tech & Data Maturity           {opp_breakdown.get('tech_maturity', {}).get('weighted_points', 0):>4.0f} / 20   {self._confidence_marker(opp_breakdown.get('tech_maturity', {}).get('confidence', 'low'))}
   - Strategic Horizon              {opp_breakdown.get('strategic_horizon', {}).get('weighted_points', 0):>4.0f} / 10   {self._confidence_marker(opp_breakdown.get('strategic_horizon', {}).get('confidence', 'low'))}

4. TOP 3 PRIORITY ACTIONS
"""
        for i, action in enumerate(state.get("priority_actions", [])[:3], start=1):
            report += f"   {i}. {action.get('action', 'N/A')} — ref: {action.get('reference', 'N/A')}\n"
        
        report += "\n5. UNKNOWNS TO RESOLVE\n"
        if unknowns:
            for item in unknowns[:3]:
                dim = str(item.get("dimension", "unknown")).replace("_", " ").title()
                report += f"   ⚠️ You were unsure about {dim} — {item.get('details', 'Requires follow-up')}\n"
        else:
            report += "   None detected. Confidence was medium/high across all dimensions.\n"
        
        if state.get("timeline_guidance"):
            report += f"\n6. TIMELINE GUIDANCE\n   {state['timeline_guidance']}\n"
        
        if state.get("next_step"):
            report += f"\n7. SUGGESTED NEXT STEP\n   {state['next_step']}\n"
        
        report += "────────────────────────────────────────────\n"
        
        return report

    def _confidence_marker(self, level: str) -> str:
        if level == "low":
            return "⚠️"
        if level == "medium":
            return "•"
        return ""
    
    def _get_risk_emoji(self, level: str) -> str:
        """Get emoji for risk level."""
        emoji_map = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }
        return emoji_map.get(level, "⚪")
    
    def _get_opportunity_level(self, score: float) -> str:
        """Get opportunity level description."""
        if score >= 70:
            return "High Opportunity"
        elif score >= 50:
            return "Moderate Opportunity"
        else:
            return "Low Opportunity"
