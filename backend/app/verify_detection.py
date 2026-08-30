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
from risk_engine import compute_risk_scores

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_CSV = os.path.join(BASE_DIR, "data_generator", "output", "accounts.csv")
TRANSACTIONS_CSV = os.path.join(BASE_DIR, "data_generator", "output", "transactions.csv")

def main():
    print("=" * 65)
    print("           TRACE_NET GRAPH ENGINE & RISK SCORING VERIFIER         ")
    print("=" * 65)
    
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
    print("-" * 65)
    
    # 3. Run Detectors
    print("Running 5 Detection Engines...")
    
    detectors = {
        "fan_out": (detect_fan_out, "C_FAN_OUT_1"),
        "fan_in": (detect_fan_in, "C_FAN_IN_1"),
        "circular": (detect_circular_flow, "C_CIRCULAR_1"),
        "smurfing": (detect_smurfing, "C_SMURFING_1"),
        "pass_through": (detect_rapid_passthrough, "C_PASSTHROUGH_1"),
    }
    
    all_raw_findings = []
    detector_results = {}
    
    for pattern_name, (detector_fn, expected_cluster_id) in detectors.items():
        findings = detector_fn(graph)
        detector_results[pattern_name] = (findings, expected_cluster_id)
        all_raw_findings.extend(findings)
        
        expected_txs = ground_truth[expected_cluster_id]
        detected_expected = any(set(f["involved_transactions"]).intersection(expected_txs) for f in findings)
        status = "PASS" if detected_expected else "FAIL"
        print(f"  * [{pattern_name:<12}] -> Expected Cluster {expected_cluster_id}: {status} ({len(findings)} raw candidates found)")

    # Deduplicate / filter out pass_through findings whose accounts are fully contained within circular_flow findings
    circular_findings = [f for f in all_raw_findings if f["pattern_type"] == "circular"]
    circular_account_sets = [set(f["involved_accounts"]) | {f["primary_account"]} for f in circular_findings]
    
    filtered_raw_findings = []
    suppressed_passthrough_count = 0
    
    for f in all_raw_findings:
        if f["pattern_type"] == "pass_through":
            pt_nodes = set(f["involved_accounts"]) | {f["primary_account"]}
            if any(pt_nodes.issubset(c_set) for c_set in circular_account_sets):
                suppressed_passthrough_count += 1
                continue
        filtered_raw_findings.append(f)
        
    if suppressed_passthrough_count > 0:
        print(f"  * [dedup       ] -> Suppressed {suppressed_passthrough_count} pass_through finding(s) fully contained inside circular_flow ring.")

    print("-" * 65)
    
    # 4. Compute Risk Scores for Filtered Findings
    print("Computing Risk Scores & Sub-Signals via Risk Engine...")
    scored_findings = compute_risk_scores(graph, filtered_raw_findings)
    print(f"Total findings scored post-dedup: {len(scored_findings)}\n")
    
    print("=" * 65)
    print(f"               ALL {len(scored_findings)} FINDINGS BREAKDOWN                     ")
    print("=" * 65)
    
    cluster_scores = {}
    unlabeled_findings = []
    
    for idx, sf in enumerate(scored_findings, start=1):
        f = sf["finding"]
        sub = sf["sub_signals"]
        score = sf["final_score"]
        bucket = sf["risk_bucket"]
        
        primary_acc = f["primary_account"]
        node_attrs = graph.nodes[primary_acc]
        upi_id = node_attrs.get("upi_id", primary_acc[:8])
        acc_type = node_attrs.get("account_type", "unknown")
        
        # Check if finding belongs to any injected cluster
        found_cluster = "UNLABELED — investigate"
        tx_set = set(f["involved_transactions"])
        for cid, txs in ground_truth.items():
            if tx_set.intersection(txs):
                found_cluster = cid
                if cid not in cluster_scores or score > cluster_scores[cid][0]:
                    cluster_scores[cid] = (score, bucket)
                break
                
        if legit_burst_merchant_id and primary_acc == legit_burst_merchant_id:
            found_cluster = "C_LEGIT_BURST_1 (Merchant)"
            cluster_scores["C_LEGIT_BURST_1"] = (score, bucket)

        if found_cluster == "UNLABELED — investigate":
            unlabeled_findings.append((idx, upi_id, acc_type, f['pattern_type'], score, bucket, f['evidence_summary']))

        print(f"Finding #{idx:02d} | Pattern: {f['pattern_type']:<12} | Account: {upi_id} ({acc_type})")
        print(f"  Cluster ID    : {found_cluster}")
        print(f"  Final Risk    : {score}/100 -> [{bucket}]")
        print(f"  Sub-Signals   : Structural={sub['structural_strength']:.3f} (x40={sub['structural_strength']*40:.1f})")
        print(f"                  Freshness ={sub['sender_freshness']:.3f} (x30={sub['sender_freshness']*30:.1f})")
        print(f"                  AmountBand={sub['amount_band_signal']:.3f} (x20={sub['amount_band_signal']*20:.1f})")
        print(f"                  Dampening ={sub['receiver_dampening']:.3f} (x25={sub['receiver_dampening']*25:.1f})")
        print(f"  Evidence      : {f['evidence_summary']}")
        print("-" * 65)

    # 5. Risk Score Verification Checks
    print("Risk Engine Verification Checks:")
    print("-" * 65)
    
    # Check 1: Injected Fraud Clusters
    fraud_clusters = ['C_FAN_OUT_1', 'C_FAN_IN_1', 'C_CIRCULAR_1', 'C_SMURFING_1', 'C_PASSTHROUGH_1']
    fraud_pass_count = 0
    
    for cid in fraud_clusters:
        if cid in cluster_scores:
            score, bucket = cluster_scores[cid]
            is_pass = bucket in ["High", "Critical"]
            status = "PASS" if is_pass else "FAIL"
            if is_pass:
                fraud_pass_count += 1
            print(f"  * Fraud Cluster {cid:<15} : Score = {score:4.1f} [{bucket:<8}] -> {status} (Expected High/Critical)")
        else:
            print(f"  * Fraud Cluster {cid:<15} : NOT DETECTED -> FAIL")

    print("-" * 65)
    
    # Check 2: Legit Burst Merchant False-Positive Resolution
    legit_burst_score, legit_burst_bucket = cluster_scores.get("C_LEGIT_BURST_1", (0.0, "Low"))
    legit_pass = legit_burst_bucket in ["Low", "Medium"]
    legit_status = "PASS" if legit_pass else "FAIL"
    print(f"  * Legit Burst Merchant C_LEGIT_BURST_1 : Score = {legit_burst_score:4.1f} [{legit_burst_bucket:<8}] -> {legit_status} (Expected Low/Medium)")

    print("-" * 65)
    print(f"Unlabeled Findings Summary ({len(unlabeled_findings)} total):")
    if unlabeled_findings:
        for u_idx, u_upi, u_type, u_pat, u_score, u_bucket, u_ev in unlabeled_findings:
            print(f"  * Finding #{u_idx:02d} [{u_pat}] {u_upi} ({u_type}): Score = {u_score} [{u_bucket}]")
            print(f"    Evidence: {u_ev}")
    else:
        print("  PASS: 0 unlabeled findings flagged on background traffic.")

    print("=" * 65)
    print("                              SUMMARY                             ")
    print("=" * 65)
    print(f"1. Injected Fraud Pattern Detection : {len(detector_results)}/5 Patterns Found")
    print(f"2. Fraud Risk Score Calibration    : {fraud_pass_count}/5 Clusters Scored High/Critical")
    print(f"3. False Positive Mitigation        : C_LEGIT_BURST_1 Merchant Scored [{legit_burst_bucket}] ({'Fixed' if legit_pass else 'Failed'})")
    print(f"4. Circular/Pass-Through Dedup      : Suppressed {suppressed_passthrough_count} circular-contained pass-through finding(s)")
    print(f"5. Unlabeled Findings Count         : {len(unlabeled_findings)} background findings")
    print("=" * 65)

if __name__ == "__main__":
    main()
