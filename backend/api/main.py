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
from core.registry import SubgraphRegistry, CommonToolRegistry
from core.checkpointer import get_checkpointer
from core.llm import get_model_gateway
from core.interaction_logger import InteractionLogger

# Common Tools (Layer 3)
from common_tools.Interrupt_tool import InterruptTool
from common_tools.RAG_tool import RAGTool

# Apps main graphs (Layer 2)
from apps.three_chatbots import build_journey_subgraphs

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
    Application startup: register subgraphs and common tools and build core graph.
    
    According to app_definition.md, this is where all subgraphs and common tools are
    instantiated and registered. Adding a new use case means adding
    lines here — nothing else changes.
    """
    print("\n" + "="*60)
    print("Starting Universal Chatbot Framework")
    print("="*60)
    
    # Initialize core shared services
    model_gateway = get_model_gateway()
    
    # Instanciate and register common tools
    commonToolRegistry = CommonToolRegistry()

    # Register common tools
    interrupt_tool = InterruptTool()
    rag_tool = RAGTool()
    commonToolRegistry.register(interrupt_tool)
    commonToolRegistry.register(rag_tool)
    
    # Instantiate and register subgraphs (Layer 2)
    subgraphRegistry = SubgraphRegistry()
    
    # Register journey subchatbots
    journey_subgraphs = build_journey_subgraphs(
        model_gateway=model_gateway,
        interrupt_tool=interrupt_tool,
    )
    for subgraph in journey_subgraphs:
        subgraphRegistry.register(subgraph)
    
    # Build and store the compiled graph
    checkpointer = await get_checkpointer()
    app.state.graph = build_core_graph(
        registry=subgraphRegistry,
        model_gateway=model_gateway,
        checkpointer=checkpointer,
    )
    
    app.state.interaction_logger = InteractionLogger()

    print(f"\n✓ Core graph built with {len(subgraphRegistry)} subgraph(s)")
    print("✓ Interaction logger initialized")
    print("="*60 + "\n")


@app.on_event("shutdown")
async def shutdown():
    """Close runtime services on shutdown."""
    interaction_logger = getattr(app.state, "interaction_logger", None)
    if interaction_logger:
        await interaction_logger.close()

# Include routes
from api.routes.chat import router as chat_router
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "framework": "universal-chatbot-v1.0"}
