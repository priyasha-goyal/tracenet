from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
import networkx as nx
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.core.state import GLOBAL_GRAPH, resolve_account_id
from app.core.risk_engine import get_risk_bucket
from app.schemas.responses import NetworkClusterResponse, TraceResponse

router = APIRouter(tags=["Networks"])


@router.get("/networks", response_model=List[NetworkClusterResponse])
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
            "cases": formatted_cases,
        })

    # Sort clusters by highest_risk_score descending
    result.sort(key=lambda x: x["highest_risk_score"], reverse=True)
    return result


@router.get("/trace/{account_id}", response_model=TraceResponse)
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
            "account_age_days": ndata.get("account_age_days", 0),
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
                    "cluster_id": d.get("cluster_id", ""),
                })

    return {
        "center_account_id": resolved_id,
        "center_upi_id": GLOBAL_GRAPH.nodes[resolved_id].get("upi_id", account_id),
        "hops": hops,
        "nodes": nodes_data,
        "edges": edges_data,
    }
