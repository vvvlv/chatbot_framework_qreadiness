"""
FastAPI application startup and subgraph registration.

According to app_definition.md Section 12, the application is assembled here.
Subgraphs are instantiated, injected with their dependencies, and registered
into the core graph in one place.
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

# Core framework imports
from core.graph import build_core_graph
from core.registry import SubgraphRegistry
from core.checkpointer import get_checkpointer
from core.llm import get_model_gateway

# Tools (Layer 3)
from tools.quantum_data_collector.tool import QuantumDataCollectorTool
from tools.quantum_analyzer.tool import QuantumAnalyzerTool
from tools.quantum_presenter.tool import QuantumPresenterTool
from tools.rag.retriever_base import DummyRetriever

# Use-case subgraphs (Layer 2)
from apps.quantum_readiness.subgraph import QuantumReadinessSubgraph



app = FastAPI(title="Universal Chatbot Framework - Quantum Readiness")

def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if origins:
        return origins
    if os.getenv("ENV", "dev").lower() == "dev":
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return []


allowed_origins = _parse_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
async def startup():
    """
    Application startup: register subgraphs and build core graph.
    
    According to app_definition.md, this is where all subgraphs are
    instantiated and registered. Adding a new use case means adding
    lines here — nothing else changes.
    """
    print("\n" + "="*60)
    print("Starting Universal Chatbot Framework")
    print("="*60)
    
    # Initialize core shared services
    model_gateway = get_model_gateway()
    
    # Instantiate tools (Layer 3)
    retriever = DummyRetriever()  # TODO: Replace with LlamaIndex + pgvector
    data_collector = QuantumDataCollectorTool(model_gateway=model_gateway)
    analyzer = QuantumAnalyzerTool(model_gateway=model_gateway)
    presenter = QuantumPresenterTool(model_gateway=model_gateway, retriever=retriever)
    
    # Instantiate and register subgraphs (Layer 2)
    registry = SubgraphRegistry()
    
    # Register Quantum Readiness subgraph
    quantum_subgraph = QuantumReadinessSubgraph(
        data_collector=data_collector,
        analyzer=analyzer,
        presenter=presenter,
    )
    registry.register(quantum_subgraph)
    
    # Build and store the compiled graph
    checkpointer = await get_checkpointer()
    app.state.graph = build_core_graph(
        registry=registry,
        model_gateway=model_gateway,
        checkpointer=checkpointer,
    )
    
    print(f"\n✓ Core graph built with {len(registry)} subgraph(s)")
    print("="*60 + "\n")


# Include routes
from api.routes.chat import router as chat_router
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "framework": "universal-chatbot-v1.0"}
