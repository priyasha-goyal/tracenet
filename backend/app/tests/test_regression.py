import os
import sys

import pandas as pd
from fastapi.testclient import TestClient

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from main import app  # noqa: E402

BACKEND_DIR = os.path.dirname(APP_DIR)
TRANSACTIONS_CSV = os.path.join(BACKEND_DIR, "data_generator", "output", "transactions.csv")

FRAUD_CLUSTERS = [
    "C_FAN_OUT_1",
    "C_FAN_IN_1",
    "C_CIRCULAR_1",
    "C_SMURFING_1",
    "C_PASSTHROUGH_1",
]
HIGH_CRITICAL = {"High", "Critical"}

CLEAN_PAYEE_UPI = "kennethscott91@upi"
FRAUD_PAYEE_UPI = "jordanbates72@upi"

client = TestClient(app)


def _load_transactions():
    return pd.read_csv(TRANSACTIONS_CSV)


def _ground_truth_tx_ids(df):
    """Group transaction_ids by injected cluster_id (same logic as verify_detection.py)."""
    ground_truth = {}
    for cid in FRAUD_CLUSTERS:
        ground_truth[cid] = set(df[df["cluster_id"] == cid]["transaction_id"].tolist())
    return ground_truth


def test_original_five_clusters_still_detected():
    df = _load_transactions()
    ground_truth = _ground_truth_tx_ids(df)
    for cid, tx_ids in ground_truth.items():
        assert tx_ids, f"Ground truth CSV is missing transactions for {cid}"

    response = client.get("/networks")
    assert response.status_code == 200
    networks = response.json()
    by_cluster = {item["cluster_id"]: item for item in networks}

    for cid in FRAUD_CLUSTERS:
        assert cid in by_cluster, f"Injected cluster {cid} missing from GET /networks"
        assert by_cluster[cid]["highest_risk_bucket"] in HIGH_CRITICAL, (
            f"{cid} expected High/Critical, got {by_cluster[cid]['highest_risk_bucket']}"
        )


def test_legit_burst_not_flagged():
    df = _load_transactions()
    legit_burst_txs = df[df["cluster_id"] == "C_LEGIT_BURST_1"]
    assert not legit_burst_txs.empty, "C_LEGIT_BURST_1 missing from transactions.csv"
    merchant_id = legit_burst_txs["receiver_id"].iloc[0]

    response = client.get("/networks")
    assert response.status_code == 200
    networks = response.json()

    merchant_clusters = []
    for item in networks:
        if item.get("cluster_id") == "C_LEGIT_BURST_1":
            merchant_clusters.append(item)
            continue
        case_accounts = {c.get("account_id") for c in item.get("cases", [])}
        if merchant_id in case_accounts:
            merchant_clusters.append(item)

    for item in merchant_clusters:
        assert item["highest_risk_bucket"] not in HIGH_CRITICAL, (
            f"C_LEGIT_BURST_1 merchant cluster {item.get('cluster_id')} "
            f"flagged {item['highest_risk_bucket']}"
        )


def test_simulate_transaction_allow_and_intercept():
    allow_res = client.post(
        "/transactions/simulate",
        json={
            "payer_account_id": FRAUD_PAYEE_UPI,
            "payee_account_id": CLEAN_PAYEE_UPI,
            "amount": 500.0,
        },
    )
    assert allow_res.status_code == 200
    assert allow_res.json()["decision"] == "allow"

    intercept_res = client.post(
        "/transactions/simulate",
        json={
            "payer_account_id": CLEAN_PAYEE_UPI,
            "payee_account_id": FRAUD_PAYEE_UPI,
            "amount": 9600.0,
        },
    )
    assert intercept_res.status_code == 200
    assert intercept_res.json()["decision"] == "intercept"


def test_incremental_smurfing_detection():
    df = _load_transactions()
    clustered = df[df["cluster_id"].notna() & (df["cluster_id"] != "")]
    clustered_accounts = set(clustered["sender_id"]) | set(clustered["receiver_id"])

    payer = "pytest-incremental-payer@upi"
    receiver = "pytest-incremental-smurf@upi"
    assert payer not in clustered_accounts
    assert receiver not in clustered_accounts

    for i in range(8):
        amount = 9500.0 + (i * 50.0)  # 9500..9850, inside ₹9500-9900 band
        res = client.post(
            "/transactions/simulate",
            json={
                "payer_account_id": payer,
                "payee_account_id": receiver,
                "amount": amount,
            },
        )
        assert res.status_code == 200, res.text

    risk_res = client.get(f"/accounts/{receiver}/risk")
    assert risk_res.status_code == 200
    body = risk_res.json()
    assert body["risk_bucket"] in HIGH_CRITICAL, body
    assert body["pattern_type"] == "smurfing", body
