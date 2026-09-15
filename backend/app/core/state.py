import os
import networkx as nx
from sqlalchemy.orm import Session

from app.db.session import engine, Base, SessionLocal
from app.db.models import Case
from app.core.graph_engine import (
    load_graph,
    detect_fan_out,
    detect_fan_in,
    detect_circular_flow,
    detect_smurfing,
    detect_rapid_passthrough,
)
from app.core.risk_engine import compute_risk_scores

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_CSV = os.path.join(BASE_DIR, "..", "data_generator", "output", "accounts.csv")
TRANSACTIONS_CSV = os.path.join(BASE_DIR, "..", "data_generator", "output", "transactions.csv")

# Global in-memory state (mutated in-place so all imported references remain valid)
GLOBAL_GRAPH: nx.MultiDiGraph = nx.MultiDiGraph()
UPI_TO_UUID: dict = {}
FINDINGS_BY_ACCOUNT: dict = {}
SCORED_FINDINGS: list = []


def finding_tx_key(finding: dict) -> tuple:
    return (
        finding.get("pattern_type"),
        tuple(sorted(finding.get("involved_transactions", []))),
    )


def dedup_passthrough_inside_circular(raw_findings: list, extra_circular: list = None) -> list:
    circular_findings = [f for f in raw_findings if f["pattern_type"] == "circular"]
    if extra_circular:
        circular_findings.extend(extra_circular)
    circular_account_sets = [
        set(f["involved_accounts"]) | {f["primary_account"]} for f in circular_findings
    ]

    filtered_raw = []
    for f in raw_findings:
        if f["pattern_type"] == "pass_through":
            pt_nodes = set(f["involved_accounts"]) | {f["primary_account"]}
            if any(pt_nodes.issubset(c_set) for c_set in circular_account_sets):
                continue
        filtered_raw.append(f)
    return filtered_raw


def cluster_id_for_finding(finding: dict):
    cid = finding.get("cluster_id")
    if cid:
        return cid
    tx_set = set(finding.get("involved_transactions", []))
    for u, v, k, d in GLOBAL_GRAPH.edges(keys=True, data=True):
        if d.get("transaction_id") in tx_set and d.get("cluster_id"):
            return d["cluster_id"]
    return cid


def index_scored_finding(sf: dict):
    f = sf["finding"]
    involved = set(f.get("involved_accounts", [])) | {f["primary_account"]}
    for acc in involved:
        if acc not in FINDINGS_BY_ACCOUNT:
            FINDINGS_BY_ACCOUNT[acc] = []
        FINDINGS_BY_ACCOUNT[acc].append(sf)
        FINDINGS_BY_ACCOUNT[acc].sort(key=lambda x: x["final_score"], reverse=True)


def create_case_if_needed(db: Session, sf: dict) -> bool:
    bucket = sf["risk_bucket"]
    if bucket not in ["High", "Critical"]:
        return False

    f = sf["finding"]
    acc_id = f["primary_account"]
    ptype = f["pattern_type"]
    cid = cluster_id_for_finding(f)

    existing = db.query(Case).filter(
        Case.account_id == acc_id,
        Case.pattern_type == ptype,
    ).first()

    if existing:
        return False

    db.add(Case(
        account_id=acc_id,
        pattern_type=ptype,
        cluster_id=cid,
        risk_score=sf["final_score"],
        risk_bucket=bucket,
        evidence_summary=f["evidence_summary"],
        status="open",
    ))
    return True


def sync_upi_mapping(account_id: str):
    """Keep UPI_TO_UUID in sync if a node (possibly new) has a upi_id."""
    if account_id not in GLOBAL_GRAPH.nodes:
        return
    upi = GLOBAL_GRAPH.nodes[account_id].get("upi_id")
    if upi:
        UPI_TO_UUID[upi] = account_id


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


def initialize_app_data():
    # 1. Create DB tables if not present
    Base.metadata.create_all(bind=engine)

    # 2. Load Graph from CSVs
    print(f"[STARTUP] Loading graph from {ACCOUNTS_CSV} and {TRANSACTIONS_CSV}...")
    loaded = load_graph(ACCOUNTS_CSV, TRANSACTIONS_CSV)
    GLOBAL_GRAPH.clear()
    GLOBAL_GRAPH.add_nodes_from(loaded.nodes(data=True))
    GLOBAL_GRAPH.add_edges_from(loaded.edges(keys=True, data=True))
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

    filtered_raw = dedup_passthrough_inside_circular(all_raw)

    # 4. Compute risk scores
    scored = compute_risk_scores(GLOBAL_GRAPH, filtered_raw)
    SCORED_FINDINGS.clear()
    SCORED_FINDINGS.extend(scored)
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
            if create_case_if_needed(db, sf):
                cases_created += 1

        db.commit()
        print(f"[STARTUP] Auto-created {cases_created} new Case records in database.")
    finally:
        db.close()


# Initialize state on module load
initialize_app_data()
