from fastapi import APIRouter

from app.core.state import GLOBAL_GRAPH, FINDINGS_BY_ACCOUNT, resolve_account_id
from app.schemas.responses import AccountRiskResponse

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/{account_id}/risk", response_model=AccountRiskResponse)
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
            "sub_signals": tf["sub_signals"],
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
            "receiver_dampening": 0.0,
        },
    }
