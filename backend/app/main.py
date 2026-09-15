from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.state import GLOBAL_GRAPH, SCORED_FINDINGS, initialize_app_data
from app.api.routes import accounts, transactions, networks, cases
from app.schemas.responses import RootResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_app_data()
    yield


app = FastAPI(
    title="TraceNet Fraud Engine API",
    description="Backend graph engine, pattern detection, risk scoring & case management API.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware setup for Vite dev server (http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(networks.router)
app.include_router(cases.router)


@app.get("/", response_model=RootResponse)
def root():
    return {
        "service": "TraceNet Fraud Engine API",
        "status": "online",
        "nodes_loaded": GLOBAL_GRAPH.number_of_nodes(),
        "edges_loaded": GLOBAL_GRAPH.number_of_edges(),
        "findings_cached": len(SCORED_FINDINGS),
    }
