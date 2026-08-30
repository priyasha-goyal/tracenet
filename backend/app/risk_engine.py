from datetime import datetime
import networkx as nx

def compute_sub_signals(graph: nx.MultiDiGraph, finding: dict) -> dict:
    """
    Computes four sub-signals (each in 0..1, except receiver_dampening which is -1..0)
    for a given detection finding on the NetworkX graph.
    """
    pt = finding["pattern_type"]
    primary_acc = finding["primary_account"]
    primary_attrs = graph.nodes[primary_acc] if primary_acc in graph.nodes else {}

    # Extract involved transactions, senders, amounts
    tx_ids = set(finding.get("involved_transactions", []))
    senders = set()
    amounts = []

    for u, v, k, d in graph.edges(keys=True, data=True):
        if d.get("transaction_id") in tx_ids:
            senders.add(u)
            amounts.append(d.get("amount", 0.0))

    if not senders:
        senders.add(primary_acc)

    # 1. Structural Strength (0-1)
    w_start = datetime.fromisoformat(finding["window_start"])
    w_end = datetime.fromisoformat(finding["window_end"])
    duration_mins = max(1.0, (w_end - w_start).total_seconds() / 60.0)

    if pt == "fan_out":
        c_ratio = min(1.0, len(finding.get("involved_accounts", [])) / 6.0)
        t_tight = max(0.0, 1.0 - (duration_mins / 120.0) * 0.5)
        structural_strength = 0.6 * c_ratio + 0.4 * t_tight
    elif pt == "fan_in":
        c_ratio = min(1.0, len(finding.get("involved_accounts", [])) / 6.0)
        t_tight = max(0.0, 1.0 - (duration_mins / 180.0) * 0.5)
        structural_strength = 0.6 * c_ratio + 0.4 * t_tight
    elif pt == "circular":
        num_hops = max(1, len(tx_ids))
        avg_hop_mins = duration_mins / num_hops
        s_ratio = max(0.0, 1.0 - (avg_hop_mins / 30.0) * 0.5)
        l_ratio = min(1.0, num_hops / 3.0)
        structural_strength = 0.5 * s_ratio + 0.5 * l_ratio
    elif pt == "smurfing":
        c_ratio = min(1.0, len(tx_ids) / 8.0)
        t_tight = max(0.0, 1.0 - (duration_mins / 360.0) * 0.5)
        structural_strength = 0.6 * c_ratio + 0.4 * t_tight
    elif pt == "pass_through":
        gap_sec = (w_end - w_start).total_seconds()
        s_ratio = max(0.0, 1.0 - (gap_sec / (15.0 * 60.0)) * 0.5)
        in_amt = min(amounts) if amounts else 1.0
        out_amt = max(amounts) if amounts else 1.0
        f_pct = min(1.0, out_amt / in_amt) if in_amt > 0 else 1.0
        p_ratio = min(1.0, f_pct / 0.7)
        structural_strength = 0.5 * s_ratio + 0.5 * p_ratio
    else:
        structural_strength = 0.5

    structural_strength = round(max(0.0, min(1.0, structural_strength)), 3)

    # 2. Sender Freshness (0-1)
    # Evaluates account freshness of involved accounts (senders & counterparties)
    involved_accs = set(finding.get("involved_accounts", [])) | {primary_acc}
    fresh_scores = []
    for acc in involved_accs:
        if acc in graph.nodes:
            age = graph.nodes[acc].get("account_age_days", 999)
            if age < 30:
                fresh_scores.append(1.0)
            else:
                fresh_scores.append(max(0.4, 1.0 - (age / 1500.0)))
        else:
            fresh_scores.append(0.5)

    sender_freshness = round(sum(fresh_scores) / len(fresh_scores), 3) if fresh_scores else 0.5

    # 3. Amount Band Signal (0-1)
    # High score for amounts in smurfing/reporting threshold band (8500-9999) or large lump sums (>= 10,000)
    band_signals = []
    for amt in amounts:
        if 8500 <= amt < 10000:
            band_signals.append(1.0)
        elif amt >= 10000:
            band_signals.append(0.9)
        elif 4000 <= amt < 8500:
            band_signals.append(0.7 + 0.3 * ((amt - 4000) / 4500.0))
        else:
            band_signals.append(max(0.0, amt / 4000.0 * 0.1))

    amount_band_signal = round(sum(band_signals) / len(band_signals), 3) if band_signals else 0.0

    # 4. Receiver Dampening (0 to -1)
    # Reduces score for established merchants or payroll accounts (> 180 days old)
    acc_type = primary_attrs.get("account_type", "personal")
    acc_age = primary_attrs.get("account_age_days", 0)

    if acc_type in ["merchant", "payroll"] and acc_age > 180:
        receiver_dampening = -1.0
    else:
        receiver_dampening = 0.0

    return {
        "structural_strength": structural_strength,
        "sender_freshness": sender_freshness,
        "amount_band_signal": amount_band_signal,
        "receiver_dampening": receiver_dampening
    }

def get_risk_bucket(score: float) -> str:
    if score <= 30.0:
        return "Low"
    elif score <= 60.0:
        return "Medium"
    elif score <= 80.0:
        return "High"
    else:
        return "Critical"

def compute_risk_scores(graph: nx.MultiDiGraph, findings: list[dict] = None) -> list[dict]:
    """
    Computes risk score (0-100) and risk bucket for a list of findings on graph.
    Supports both compute_risk_scores(graph, findings) and compute_risk_scores(findings, graph).
    """
    if isinstance(graph, list) and isinstance(findings, nx.MultiDiGraph):
        graph, findings = findings, graph
    elif findings is None and isinstance(graph, list):
        raise ValueError("graph object is required to compute risk scores.")

    scored_findings = []
    for f in findings:
        sub = compute_sub_signals(graph, f)
        
        # Weighted combination equation
        raw_score = (
            (sub["structural_strength"] * 40) +
            (sub["sender_freshness"] * 30) +
            (sub["amount_band_signal"] * 20) +
            (sub["receiver_dampening"] * 25)
        )
        
        final_score = round(max(0.0, min(100.0, raw_score)), 1)
        bucket = get_risk_bucket(final_score)
        
        scored_findings.append({
            "finding": f,
            "sub_signals": sub,
            "final_score": final_score,
            "risk_bucket": bucket
        })

    return scored_findings
