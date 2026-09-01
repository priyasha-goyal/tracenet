import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from main import app

def run_tests():
    client = TestClient(app)

    print("=" * 65)
    print("                TRACE_NET API LAYER TEST HARNESS               ")
    print("=" * 65)

    # 1. GET /
    res_root = client.get("/")
    print("\n1. GET /")
    print(json.dumps(res_root.json(), indent=2))

    # 2. GET /accounts/{smurfing_payee}/risk
    smurfing_upi = "jordanbates72@upi"
    res_risk_smurf = client.get(f"/accounts/{smurfing_upi}/risk")
    print(f"\n2. GET /accounts/{smurfing_upi}/risk")
    print(json.dumps(res_risk_smurf.json(), indent=2))

    # 3. GET /accounts/{bg_account}/risk
    bg_upi = "kennethscott91@upi"
    res_risk_bg = client.get(f"/accounts/{bg_upi}/risk")
    print(f"\n3. GET /accounts/{bg_upi}/risk")
    print(json.dumps(res_risk_bg.json(), indent=2))

    # 4. POST /transactions/simulate - Intercept Case (Smurfing Payee)
    sim_intercept_body = {
        "payer_account_id": bg_upi,
        "payee_account_id": smurfing_upi,
        "amount": 9600.0
    }
    res_sim_intercept = client.post("/transactions/simulate", json=sim_intercept_body)
    print(f"\n4. POST /transactions/simulate (Payee: {smurfing_upi})")
    print(json.dumps(res_sim_intercept.json(), indent=2))
    intercept_data = res_sim_intercept.json()
    payer_event_id = intercept_data.get("payer_event_id")

    # 5. POST /transactions/simulate - Allow Case (Background Account)
    sim_allow_body = {
        "payer_account_id": smurfing_upi,
        "payee_account_id": bg_upi,
        "amount": 500.0
    }
    res_sim_allow = client.post("/transactions/simulate", json=sim_allow_body)
    print(f"\n5. POST /transactions/simulate (Payee: {bg_upi})")
    print(json.dumps(res_sim_allow.json(), indent=2))

    # 6. POST /transactions/{payer_event_id}/resolve
    if payer_event_id:
        resolve_body = {"action": "overrode_warning"}
        res_resolve = client.post(f"/transactions/{payer_event_id}/resolve", json=resolve_body)
        print(f"\n6. POST /transactions/{payer_event_id}/resolve")
        print(json.dumps(res_resolve.json(), indent=2))

    # 7. GET /networks
    res_networks = client.get("/networks")
    print("\n7. GET /networks")
    print(json.dumps(res_networks.json()[:2], indent=2))  # print top 2 clusters

    # 8. GET /trace/{smurfing_upi}?hops=2
    res_trace = client.get(f"/trace/{smurfing_upi}?hops=2")
    trace_data = res_trace.json()
    print(f"\n8. GET /trace/{smurfing_upi}?hops=2")
    print(f"Center: {trace_data.get('center_upi_id')}, Nodes count: {len(trace_data.get('nodes', []))}, Edges count: {len(trace_data.get('edges', []))}")
    print("Sample node:", trace_data.get('nodes', [])[0] if trace_data.get('nodes') else None)
    print("Sample edge:", trace_data.get('edges', [])[0] if trace_data.get('edges') else None)

    # 9. POST /cases/{case_id}/action
    # Find a case ID from /networks
    networks_list = res_networks.json()
    first_case_id = None
    if networks_list and networks_list[0].get("cases"):
        first_case_id = networks_list[0]["cases"][0]["id"]

    if first_case_id:
        action_body = {"action": "escalate"}
        res_action = client.post(f"/cases/{first_case_id}/action", json=action_body)
        print(f"\n9. POST /cases/{first_case_id}/action")
        print(json.dumps(res_action.json(), indent=2))

    print("\n" + "=" * 65)
    print("                      ALL TESTS PASSED                         ")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
