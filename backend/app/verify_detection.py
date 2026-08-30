import os
import pandas as pd
from graph_engine import (
    load_graph,
    detect_fan_out,
    detect_fan_in,
    detect_circular_flow,
    detect_smurfing,
    detect_rapid_passthrough
)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_CSV = os.path.join(BASE_DIR, "data_generator", "output", "accounts.csv")
TRANSACTIONS_CSV = os.path.join(BASE_DIR, "data_generator", "output", "transactions.csv")

def main():
    print("=" * 60)
    print("                TRACE_NET DETECTION VERIFIER                 ")
    print("=" * 60)
    
    # 1. Load Graph
    print(f"Loading graph from {ACCOUNTS_CSV} and {TRANSACTIONS_CSV}...")
    graph = load_graph(ACCOUNTS_CSV, TRANSACTIONS_CSV)
    print(f"Graph loaded successfully with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.\n")
    
    # 2. Load Ground Truth Cluster Transactions
    df_tx = pd.read_csv(TRANSACTIONS_CSV)
    ground_truth = {}
    for cid in ['C_FAN_OUT_1', 'C_FAN_IN_1', 'C_CIRCULAR_1', 'C_SMURFING_1', 'C_PASSTHROUGH_1']:
        tx_ids = set(df_tx[df_tx['cluster_id'] == cid]['transaction_id'].tolist())
        ground_truth[cid] = tx_ids
        print(f"Ground Truth: Cluster {cid} contains {len(tx_ids)} transactions.")

    # Resolve the legit burst merchant account ID from the CSV
    legit_burst_txs = df_tx[df_tx['cluster_id'] == 'C_LEGIT_BURST_1']
    legit_burst_merchant_id = legit_burst_txs['receiver_id'].iloc[0] if not legit_burst_txs.empty else None
    legit_burst_merchant_upi = graph.nodes[legit_burst_merchant_id].get('upi_id', '?') if legit_burst_merchant_id else '?'
    print(f"Legit Burst: C_LEGIT_BURST_1 has {len(legit_burst_txs)} transactions to merchant {legit_burst_merchant_upi}")
    print("-" * 60)
    
    # 3. Run Detectors
    print("Running detectors...")
    
    detectors = {
        "fan_out": (detect_fan_out, "C_FAN_OUT_1"),
        "fan_in": (detect_fan_in, "C_FAN_IN_1"),
        "circular": (detect_circular_flow, "C_CIRCULAR_1"),
        "smurfing": (detect_smurfing, "C_SMURFING_1"),
        "pass_through": (detect_rapid_passthrough, "C_PASSTHROUGH_1"),
    }
    
    all_findings = {}
    correctly_detected_count = 0
    
    for pattern_name, (detector_fn, expected_cluster_id) in detectors.items():
        print(f"  * Running detector: {pattern_name}...")
        findings = detector_fn(graph)
        all_findings[pattern_name] = findings
        
        # Verify if expected cluster was captured
        expected_txs = ground_truth[expected_cluster_id]
        detected_expected = False
        
        for f in findings:
            found_txs = set(f["involved_transactions"])
            # If the finding overlaps with the ground truth cluster transactions
            if found_txs.intersection(expected_txs):
                detected_expected = True
                break
                
        status = "PASS" if detected_expected else "FAIL"
        if detected_expected:
            correctly_detected_count += 1
            
        print(f"    -> Expected Cluster {expected_cluster_id}: {status} (found {len(findings)} candidates)")
        for f in findings[:2]: # print sample evidence
            print(f"       Evidence summary: {f['evidence_summary']}")
            
    print("-" * 60)
    
    # 4. Check for False Positives on Merchant/Payroll Accounts
    print("Checking for false positives among legitimate High-Volume Accounts (Merchants / Payrolls)...")
    false_positives = []
    
    for pattern_name, findings in all_findings.items():
        for f in findings:
            primary = f["primary_account"]
            # Look up account attributes from graph
            node_attrs = graph.nodes[primary]
            acc_type = node_attrs.get("account_type", "")
            upi_id = node_attrs.get("upi_id", "")
            
            if acc_type in ["merchant", "payroll"]:
                false_positives.append({
                    "pattern": pattern_name,
                    "account_id": primary,
                    "upi_id": upi_id,
                    "account_type": acc_type,
                    "evidence": f["evidence_summary"]
                })
                
    if false_positives:
        print(f"  WARNING: Found {len(false_positives)} false positive flags!")
        for fp in false_positives:
            print(f"    - [{fp['pattern']}] Account {fp['upi_id']} ({fp['account_type']}) was flagged as fraud!")
            print(f"      Evidence: {fp['evidence']}")
    else:
        print("  PASS: No false positives flagged for legitimate high-volume merchants or payroll accounts.")
        
    print("-" * 60)

    # 5. Dedicated false-positive check: does fan_in flag C_LEGIT_BURST_1's merchant?
    print("Dedicated False-Positive Check: C_LEGIT_BURST_1 (Merchant Flash-Sale Burst)...")
    if legit_burst_merchant_id is None:
        print("  SKIP: C_LEGIT_BURST_1 not found in dataset.")
    else:
        fan_in_findings = all_findings.get("fan_in", [])
        burst_merchant_flagged = any(
            f["primary_account"] == legit_burst_merchant_id
            for f in fan_in_findings
        )
        if burst_merchant_flagged:
            flagging_finding = next(
                f for f in fan_in_findings
                if f["primary_account"] == legit_burst_merchant_id
            )
            print(f"  WARN: detect_fan_in incorrectly flagged the flash-sale merchant ({legit_burst_merchant_upi})")
            print(f"        Evidence: {flagging_finding['evidence_summary']}")
            print(f"        => Threshold needs adjustment or account-type allowlisting required.")
        else:
            print(f"  PASS: detect_fan_in correctly ignored the flash-sale merchant ({legit_burst_merchant_upi}).")

    print("=" * 60)
    print("                          SUMMARY                            ")
    print("=" * 60)
    print(f"Injected patterns correctly detected: {correctly_detected_count}/5")
    print(f"False positives among merchant/payroll (general): {len(false_positives)}")
    legit_burst_fp = (
        legit_burst_merchant_id is not None and
        any(f["primary_account"] == legit_burst_merchant_id for f in all_findings.get("fan_in", []))
    )
    print(f"False positive on C_LEGIT_BURST_1 merchant: {'YES (threshold too sensitive)' if legit_burst_fp else 'NO (correctly ignored)'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
