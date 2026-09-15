from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.core.state import GLOBAL_GRAPH
from app.schemas.requests import CaseActionRequest
from app.schemas.responses import CaseResponse

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("/{case_id}/action", response_model=CaseResponse)
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
