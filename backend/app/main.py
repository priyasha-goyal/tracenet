import os
import sys
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import networkx as nx
from sqlalchemy.orm import Session

# Local imports
from database import engine, Base, get_db, SessionLocal
from models import Case, PayerEvent
from graph_engine import (
    load_graph,
    detect_fan_out,
    detect_fan_in,
    detect_circular_flow,
    detect_smurfing,
    detect_rapid_passthrough,
)
from risk_engine import compute_risk_scores, get_risk_bucket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_CSV = os.path.join(BASE_DIR, "..", "data_generator", "output", "accounts.csv")
TRANSACTIONS_CSV = os.path.join(BASE_DIR, "..", "data_generator", "output", "transactions.csv")

# Global in-memory state
GLOBAL_GRAPH: nx.MultiDiGraph = nx.MultiDiGraph()
UPI_TO_UUID: dict = {}
FINDINGS_BY_ACCOUNT: dict = {}
SCORED_FINDINGS: list = []

def initialize_app_data():
    global GLOBAL_GRAPH, UPI_TO_UUID, FINDINGS_BY_ACCOUNT, SCORED_FINDINGS

    # 1. Create DB tables
    Base.metadata.create_all(bind=engine)

    # 2. Load Graph from CSVs
    print(f"[STARTUP] Loading graph from {ACCOUNTS_CSV} and {TRANSACTIONS_CSV}...")
    GLOBAL_GRAPH = load_graph(ACCOUNTS_CSV, TRANSACTIONS_CSV)
    print(f"[STARTUP] Graph loaded with {GLOBAL_GRAPH.number_of_nodes()} nodes and {GLOBAL_GRAPH.number_of_edges()} edges.")

    # Build UPI -> UUID map
    UPI_TO_UUID.clear()
    for node, data in GLOBAL_GRAPH.nodes(data=True):
        if "upi_id" in data:
            UPI_TO_UUID[data["upi_id"]] = node

    # 3. Run all 5 detectors
    all_raw = []
    all_raw.extend(detect_fan_out(GLOBAL_GRAPH))
    all_raw.extend(detect_fan_in(GLOBAL_GRAPH))
    all_raw.extend(detect_circular_flow(GLOBAL_GRAPH))
    all_raw.extend(detect_smurfing(GLOBAL_GRAPH))
    all_raw.extend(detect_rapid_passthrough(GLOBAL_GRAPH))

    # Dedup pass_through findings contained in circular flow
    circular_findings = [f for f in all_raw if f["pattern_type"] == "circular"]
    circular_account_sets = [set(f["involved_accounts"]) | {f["primary_account"]} for f in circular_findings]

    filtered_raw = []
    for f in all_raw:
        if f["pattern_type"] == "pass_through":
            pt_nodes = set(f["involved_accounts"]) | {f["primary_account"]}
            if any(pt_nodes.issubset(c_set) for c_set in circular_account_sets):
                continue
        filtered_raw.append(f)

    # 4. Compute risk scores
    SCORED_FINDINGS = compute_risk_scores(GLOBAL_GRAPH, filtered_raw)
    print(f"[STARTUP] Scored {len(SCORED_FINDINGS)} findings.")

    # 5. Build FINDINGS_BY_ACCOUNT map
    FINDINGS_BY_ACCOUNT.clear()
    for sf in SCORED_FINDINGS:
        f = sf["finding"]
        primary = f["primary_account"]
        involved = set(f.get("involved_accounts", [])) | {primary}
        for acc in involved:
            if acc not in FINDINGS_BY_ACCOUNT:
                FINDINGS_BY_ACCOUNT[acc] = []
            FINDINGS_BY_ACCOUNT[acc].append(sf)

    # Sort findings for each account by score descending
    for acc in FINDINGS_BY_ACCOUNT:
        FINDINGS_BY_ACCOUNT[acc].sort(key=lambda x: x["final_score"], reverse=True)

    # 6. Auto-create Case rows for High/Critical findings
    db = SessionLocal()
    try:
        cases_created = 0
        for sf in SCORED_FINDINGS:
            bucket = sf["risk_bucket"]
            if bucket in ["High", "Critical"]:
                f = sf["finding"]
                acc_id = f["primary_account"]
                ptype = f["pattern_type"]

                cid = f.get("cluster_id")
                if not cid:
                    tx_set = set(f.get("involved_transactions", []))
                    for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True):
                        if d.get("transaction_id") in tx_set and d.get("cluster_id"):
                            cid = d["cluster_id"]
                            break

                existing = db.query(Case).filter(
                    Case.account_id == acc_id,
                    Case.pattern_type == ptype
                ).first()

                if not existing:
                    new_case = Case(
                        account_id=acc_id,
                        pattern_type=ptype,
                        cluster_id=cid,
                        risk_score=sf["final_score"],
                        risk_bucket=bucket,
                        evidence_summary=f["evidence_summary"],
                        status="open"
                    )
                    db.add(new_case)
                    cases_created += 1

        db.commit()
        print(f"[STARTUP] Auto-created {cases_created} new Case records in database.")
    finally:
        db.close()

# Run initialization at module load time so data is immediately available
initialize_app_data()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="TraceNet Fraud Engine API",
    description="Backend graph engine, pattern detection, risk scoring & case management API.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware setup for Vite dev server (http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class SimulateTransactionRequest(BaseModel):
    payer_account_id: str = Field(..., description="Account ID or UPI ID of the sender")
    payee_account_id: str = Field(..., description="Account ID or UPI ID of the recipient")
    amount: float = Field(..., gt=0, description="Transaction amount")

class ResolveTransactionRequest(BaseModel):
    action: str = Field(..., description="Action taken: proceeded_normally, cancelled, or overrode_warning")

class CaseActionRequest(BaseModel):
    action: str = Field(..., description="Case action: mark_legitimate or escalate")

def resolve_account_id(acc_input: str) -> str:
    """Helper to resolve UPI ID handle to UUID if input is a UPI handle."""
    if acc_input in GLOBAL_GRAPH.nodes:
        return acc_input
    if acc_input in UPI_TO_UUID:
        return UPI_TO_UUID[acc_input]
    for node, data in GLOBAL_GRAPH.nodes(data=True):
        if data.get("upi_id") == acc_input:
            return node
    return acc_input

# Routes

@app.get("/")
def root():
    return {
        "service": "TraceNet Fraud Engine API",
        "status": "online",
        "nodes_loaded": GLOBAL_GRAPH.number_of_nodes(),
        "edges_loaded": GLOBAL_GRAPH.number_of_edges(),
        "findings_cached": len(SCORED_FINDINGS)
    }

@app.get("/accounts/{account_id}/risk")
def get_account_risk(account_id: str):
    resolved_id = resolve_account_id(account_id)
    upi_id = GLOBAL_GRAPH.nodes[resolved_id].get("upi_id", account_id) if resolved_id in GLOBAL_GRAPH.nodes else account_id

    if resolved_id in FINDINGS_BY_ACCOUNT and FINDINGS_BY_ACCOUNT[resolved_id]:
        tf = FINDINGS_BY_ACCOUNT[resolved_id][0]  # highest score finding
        f = tf["finding"]
        
        cid = f.get("cluster_id")
        if not cid:
            tx_set = set(f.get("involved_transactions", []))
            for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True):
                if d.get("transaction_id") in tx_set and d.get("cluster_id"):
                    cid = d["cluster_id"]
                    break

        return {
            "account_id": resolved_id,
            "upi_id": upi_id,
            "risk_score": tf["final_score"],
            "risk_bucket": tf["risk_bucket"],
            "evidence_summary": f["evidence_summary"],
            "pattern_type": f["pattern_type"],
            "cluster_id": cid,
            "sub_signals": tf["sub_signals"]
        }

    return {
        "account_id": resolved_id,
        "upi_id": upi_id,
        "risk_score": 0.0,
        "risk_bucket": "Low",
        "evidence_summary": "No suspicious activity detected.",
        "pattern_type": None,
        "cluster_id": None,
        "sub_signals": {
            "structural_strength": 0.0,
            "sender_freshness": 0.0,
            "amount_band_signal": 0.0,
            "receiver_dampening": 0.0
        }
    }

@app.post("/transactions/simulate")
def simulate_transaction(req: SimulateTransactionRequest, db: Session = Depends(get_db)):
    payer_id = resolve_account_id(req.payer_account_id)
    payee_id = resolve_account_id(req.payee_account_id)

    # Look up payee risk
    if payee_id in FINDINGS_BY_ACCOUNT and FINDINGS_BY_ACCOUNT[payee_id]:
        tf = FINDINGS_BY_ACCOUNT[payee_id][0]
        payee_score = tf["final_score"]
        payee_bucket = tf["risk_bucket"]
        payee_evidence = tf["finding"]["evidence_summary"]
    else:
        payee_score = 0.0
        payee_bucket = "Low"
        payee_evidence = "No suspicious activity detected for payee."

    # Log PayerEvent in SQLite DB
    event = PayerEvent(
        payer_account_id=payer_id,
        payee_account_id=payee_id,
        amount=req.amount,
        risk_score_at_time=payee_score,
        risk_bucket_at_time=payee_bucket,
        user_action=None
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Intercept decision logic
    if payee_bucket in ["High", "Critical"]:
        return {
            "decision": "intercept",
            "payer_event_id": event.id,
            "risk_score": payee_score,
            "risk_bucket": payee_bucket,
            "evidence_summary": payee_evidence,
            "options": ["cancel", "review", "proceed_anyway"]
        }
    else:
        return {
            "decision": "allow",
            "payer_event_id": event.id,
            "risk_score": payee_score,
            "risk_bucket": payee_bucket,
            "evidence_summary": payee_evidence
        }

@app.post("/transactions/{payer_event_id}/resolve")
def resolve_transaction(payer_event_id: int, req: ResolveTransactionRequest, db: Session = Depends(get_db)):
    valid_actions = ["proceeded_normally", "cancelled", "overrode_warning"]
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of {valid_actions}")

    event = db.query(PayerEvent).filter(PayerEvent.id == payer_event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Payer event not found.")

    event.user_action = req.action
    db.commit()

    return {
        "status": "updated",
        "payer_event_id": payer_event_id,
        "user_action": req.action
    }

@app.get("/networks")
def get_networks(status: str = "open", db: Session = Depends(get_db)):
    cases = db.query(Case).filter(Case.status == status).all()

    # Group cases by cluster_id
    clusters_map = {}
    for c in cases:
        cid = c.cluster_id or "Unclustered"
        if cid not in clusters_map:
            clusters_map[cid] = []
        clusters_map[cid].append(c)

    result = []
    for cid, case_list in clusters_map.items():
        highest_score = max(c.risk_score for c in case_list)
        highest_bucket = get_risk_bucket(highest_score)

        # Collect unique accounts in cluster
        cluster_accounts = set()
        for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True):
            if d.get("cluster_id") == cid:
                cluster_accounts.add(u)
                cluster_accounts.add(v)
        for c in case_list:
            cluster_accounts.add(c.account_id)

        # Total transaction amount
        total_amount = sum(
            d.get("amount", 0.0)
            for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True)
            if d.get("cluster_id") == cid
        )

        formatted_cases = []
        for c in case_list:
            cdict = c.to_dict()
            cdict["upi_id"] = GLOBAL_GRAPH.nodes[c.account_id].get("upi_id", "") if c.account_id in GLOBAL_GRAPH.nodes else ""
            formatted_cases.append(cdict)

        result.append({
            "cluster_id": cid,
            "highest_risk_score": highest_score,
            "highest_risk_bucket": highest_bucket,
            "account_count": len(cluster_accounts),
            "total_transaction_amount": round(total_amount, 2),
            "cases": formatted_cases
        })

    # Sort clusters by highest_risk_score descending
    result.sort(key=lambda x: x["highest_risk_score"], reverse=True)
    return result

@app.get("/trace/{account_id}")
def trace_subgraph(account_id: str, hops: int = Query(2, ge=1, le=5)):
    resolved_id = resolve_account_id(account_id)
    if resolved_id not in GLOBAL_GRAPH.nodes:
        raise HTTPException(status_code=404, detail="Account not found in graph.")

    undirected = GLOBAL_GRAPH.to_undirected()
    try:
        lengths = nx.single_source_shortest_path_length(undirected, resolved_id, cutoff=hops)
        subnode_ids = set(lengths.keys())
    except Exception:
        subnode_ids = {resolved_id}

    nodes_data = []
    for nid in subnode_ids:
        ndata = GLOBAL_GRAPH.nodes[nid]
        nodes_data.append({
            "account_id": nid,
            "upi_id": ndata.get("upi_id", ""),
            "account_type": ndata.get("account_type", "personal"),
            "account_age_days": ndata.get("account_age_days", 0)
        })

    edges_data = []
    seen_tx_ids = set()
    for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True):
        if u in subnode_ids and v in subnode_ids:
            tx_id = d.get("transaction_id")
            if tx_id not in seen_tx_ids:
                seen_tx_ids.add(tx_id)
                ts = d.get("timestamp")
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                edges_data.append({
                    "transaction_id": tx_id,
                    "sender_id": u,
                    "receiver_id": v,
                    "amount": round(float(d.get("amount", 0.0)), 2),
                    "timestamp": ts_str,
                    "pattern_type": d.get("pattern_type", ""),
                    "cluster_id": d.get("cluster_id", "")
                })

    return {
        "center_account_id": resolved_id,
        "center_upi_id": GLOBAL_GRAPH.nodes[resolved_id].get("upi_id", account_id),
        "hops": hops,
        "nodes": nodes_data,
        "edges": edges_data
    }

@app.post("/cases/{case_id}/action")
def take_case_action(case_id: int, req: CaseActionRequest, db: Session = Depends(get_db)):
    case_item = db.query(Case).filter(Case.id == case_id).first()
    if not case_item:
        raise HTTPException(status_code=404, detail="Case not found.")

    if req.action == "mark_legitimate":
        case_item.status = "reviewed_legitimate"
    elif req.action == "escalate":
        case_item.status = "escalated"
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'mark_legitimate' or 'escalate'")

    db.commit()
    db.refresh(case_item)

    res = case_item.to_dict()
    res["upi_id"] = GLOBAL_GRAPH.nodes[case_item.account_id].get("upi_id", "") if case_item.account_id in GLOBAL_GRAPH.nodes else ""
    return res
