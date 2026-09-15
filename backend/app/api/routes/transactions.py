from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import PayerEvent
from app.core.state import (
    GLOBAL_GRAPH,
    FINDINGS_BY_ACCOUNT,
    SCORED_FINDINGS,
    resolve_account_id,
    sync_upi_mapping,
    finding_tx_key,
    dedup_passthrough_inside_circular,
    index_scored_finding,
    create_case_if_needed,
)
from app.core.graph_engine import add_transaction_to_graph, rescan_account
from app.core.risk_engine import compute_risk_scores
from app.schemas.requests import SimulateTransactionRequest, ResolveTransactionRequest
from app.schemas.responses import SimulateTransactionResponse, ResolveTransactionResponse

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/simulate", response_model=SimulateTransactionResponse)
def simulate_transaction(req: SimulateTransactionRequest, db: Session = Depends(get_db)):
    payer_id = resolve_account_id(req.payer_account_id)
    payee_id = resolve_account_id(req.payee_account_id)

    # Log PayerEvent first so we have a stable transaction_id
    event = PayerEvent(
        payer_account_id=payer_id,
        payee_account_id=payee_id,
        amount=req.amount,
        risk_score_at_time=0.0,
        risk_bucket_at_time="Low",
        user_action=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    tx_id = f"sim-{event.id}"
    add_transaction_to_graph(
        GLOBAL_GRAPH,
        payer_id,
        payee_id,
        req.amount,
        event.timestamp,
        tx_id,
    )
    sync_upi_mapping(payer_id)
    sync_upi_mapping(payee_id)

    raw_new = rescan_account(GLOBAL_GRAPH, payee_id)
    if payer_id != payee_id:
        raw_new.extend(rescan_account(GLOBAL_GRAPH, payer_id))

    seen_raw_keys = set()
    unique_raw = []
    for f in raw_new:
        k = finding_tx_key(f)
        if k in seen_raw_keys:
            continue
        seen_raw_keys.add(k)
        unique_raw.append(f)

    extra_circular = [
        sf["finding"] for sf in SCORED_FINDINGS if sf["finding"]["pattern_type"] == "circular"
    ]
    filtered_raw = dedup_passthrough_inside_circular(unique_raw, extra_circular=extra_circular)

    existing_keys = {finding_tx_key(sf["finding"]) for sf in SCORED_FINDINGS}
    novel_raw = [f for f in filtered_raw if finding_tx_key(f) not in existing_keys]

    new_scored = compute_risk_scores(GLOBAL_GRAPH, novel_raw) if novel_raw else []
    for sf in new_scored:
        SCORED_FINDINGS.append(sf)
        index_scored_finding(sf)
        create_case_if_needed(db, sf)
    if new_scored:
        db.commit()

    # Look up payee risk from live-updated findings
    if payee_id in FINDINGS_BY_ACCOUNT and FINDINGS_BY_ACCOUNT[payee_id]:
        tf = FINDINGS_BY_ACCOUNT[payee_id][0]
        payee_score = tf["final_score"]
        payee_bucket = tf["risk_bucket"]
        payee_evidence = tf["finding"]["evidence_summary"]
    else:
        payee_score = 0.0
        payee_bucket = "Low"
        payee_evidence = "No suspicious activity detected for payee."

    event.risk_score_at_time = payee_score
    event.risk_bucket_at_time = payee_bucket
    db.commit()

    # Intercept decision logic
    if payee_bucket in ["High", "Critical"]:
        return {
            "decision": "intercept",
            "payer_event_id": event.id,
            "risk_score": payee_score,
            "risk_bucket": payee_bucket,
            "evidence_summary": payee_evidence,
            "options": ["cancel", "review", "proceed_anyway"],
        }
    else:
        return {
            "decision": "allow",
            "payer_event_id": event.id,
            "risk_score": payee_score,
            "risk_bucket": payee_bucket,
            "evidence_summary": payee_evidence,
        }


@router.post("/{payer_event_id}/resolve", response_model=ResolveTransactionResponse)
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
        "user_action": req.action,
    }
