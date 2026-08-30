import os
from datetime import datetime, timedelta
import pandas as pd
import networkx as nx

# ---------------------------------------------------------
# Step 1: Build the Graph
# ---------------------------------------------------------
def load_graph(accounts_csv_path, transactions_csv_path) -> nx.MultiDiGraph:
    """
    Loads accounts and transactions from CSV files and builds a NetworkX MultiDiGraph.
    """
    graph = nx.MultiDiGraph()
    
    # 1. Load accounts (nodes)
    if os.path.exists(accounts_csv_path):
        df_accounts = pd.read_csv(accounts_csv_path)
        for _, row in df_accounts.iterrows():
            graph.add_node(
                row['account_id'],
                upi_id=row['upi_id'],
                account_type=row['account_type'],
                account_age_days=int(row['account_age_days']),
                created_at=datetime.fromisoformat(row['created_at'])
            )
            
    # 2. Load transactions (edges)
    if os.path.exists(transactions_csv_path):
        df_tx = pd.read_csv(transactions_csv_path)
        # Parse timestamp column
        df_tx['parsed_timestamp'] = pd.to_datetime(df_tx['timestamp'])
        
        # Sort by timestamp to ensure chronological order in the graph edge lists
        df_tx = df_tx.sort_values('parsed_timestamp')
        
        for _, row in df_tx.iterrows():
            # Add edge
            graph.add_edge(
                row['sender_id'],
                row['receiver_id'],
                amount=float(row['amount']),
                timestamp=row['parsed_timestamp'].to_pydatetime(),
                transaction_id=row['transaction_id'],
                is_injected=bool(row['is_injected']) if 'is_injected' in row else False,
                pattern_type=row['pattern_type'] if pd.notna(row['pattern_type']) else "",
                cluster_id=row['cluster_id'] if pd.notna(row['cluster_id']) else ""
            )
            
    return graph

# ---------------------------------------------------------
# Step 2: Detection Functions
# ---------------------------------------------------------

def detect_fan_out(graph, window_hours=2, min_receivers=6) -> list[dict]:
    """
    Flags an account if it sends to at least min_receivers distinct new accounts
    within any window_hours rolling window.
    """
    findings = []
    
    # Pre-calculate the earliest transaction time from u to v
    earliest_tx = {}
    for u, v, data in graph.edges(data=True):
        ts = data['timestamp']
        if (u, v) not in earliest_tx or ts < earliest_tx[(u, v)]:
            earliest_tx[(u, v)] = ts

    for u in graph.nodes():
        # Get all outgoing transactions from u
        out_edges = []
        for _, v, data in graph.out_edges(u, data=True):
            out_edges.append((v, data))
        
        if len(out_edges) < min_receivers:
            continue
            
        # Sort outgoing edges by timestamp
        out_edges.sort(key=lambda x: x[1]['timestamp'])
        
        # Sliding window search
        best_window = None
        max_distinct_new = 0
        
        for i in range(len(out_edges)):
            t_start = out_edges[i][1]['timestamp']
            t_end = t_start + timedelta(hours=window_hours)
            
            # Find all edges within this window
            window_edges = []
            for j in range(i, len(out_edges)):
                if out_edges[j][1]['timestamp'] <= t_end:
                    window_edges.append(out_edges[j])
                else:
                    break
            
            # Identify distinct receivers that are "new" (earliest transaction is in this window)
            new_receivers = set()
            for v, data in window_edges:
                # Check if this window contains the first transaction from u to v
                if earliest_tx[(u, v)] >= t_start:
                    new_receivers.add(v)
            
            if len(new_receivers) >= min_receivers and len(new_receivers) > max_distinct_new:
                max_distinct_new = len(new_receivers)
                best_window = {
                    "receivers": list(new_receivers),
                    "tx_ids": [data['transaction_id'] for _, data in window_edges],
                    "start": t_start,
                    "end": max(data['timestamp'] for _, data in window_edges),
                    "amounts": [data['amount'] for _, data in window_edges]
                }
        
        if best_window:
            duration_mins = int((best_window["end"] - best_window["start"]).total_seconds() / 60)
            min_amt = min(best_window["amounts"])
            max_amt = max(best_window["amounts"])
            
            findings.append({
                "pattern_type": "fan_out",
                "primary_account": u,
                "involved_accounts": best_window["receivers"],
                "involved_transactions": best_window["tx_ids"],
                "window_start": best_window["start"].isoformat(),
                "window_end": best_window["end"].isoformat(),
                "evidence_summary": f"Sent to {max_distinct_new} new accounts within {duration_mins} minutes, amounts range INR {min_amt:.2f}-INR {max_amt:.2f} each."
            })
            
    return findings

def detect_fan_in(graph, window_hours=3, min_senders=6) -> list[dict]:
    """
    Flags an account if it receives from at least min_senders distinct accounts
    within any window_hours rolling window.
    """
    findings = []
    
    for v in graph.nodes():
        # Get all incoming transactions to v
        in_edges = []
        for u, _, data in graph.in_edges(v, data=True):
            in_edges.append((u, data))
            
        if len(in_edges) < min_senders:
            continue
            
        # Sort incoming edges by timestamp
        in_edges.sort(key=lambda x: x[1]['timestamp'])
        
        # Sliding window search
        best_window = None
        max_distinct_senders = 0
        
        for i in range(len(in_edges)):
            t_start = in_edges[i][1]['timestamp']
            t_end = t_start + timedelta(hours=window_hours)
            
            # Find all edges within this window
            window_edges = []
            for j in range(i, len(in_edges)):
                if in_edges[j][1]['timestamp'] <= t_end:
                    window_edges.append(in_edges[j])
                else:
                    break
            
            # Gather unique senders
            senders = set(u for u, _ in window_edges)
            
            if len(senders) >= min_senders and len(senders) > max_distinct_senders:
                max_distinct_senders = len(senders)
                best_window = {
                    "senders": list(senders),
                    "tx_ids": [data['transaction_id'] for _, data in window_edges],
                    "start": t_start,
                    "end": max(data['timestamp'] for _, data in window_edges),
                    "amounts": [data['amount'] for _, data in window_edges]
                }
                
        if best_window:
            duration_mins = int((best_window["end"] - best_window["start"]).total_seconds() / 60)
            min_amt = min(best_window["amounts"])
            max_amt = max(best_window["amounts"])
            
            findings.append({
                "pattern_type": "fan_in",
                "primary_account": v,
                "involved_accounts": best_window["senders"],
                "involved_transactions": best_window["tx_ids"],
                "window_start": best_window["start"].isoformat(),
                "window_end": best_window["end"].isoformat(),
                "evidence_summary": f"Received from {max_distinct_senders} distinct accounts within {duration_mins} minutes, amounts range INR {min_amt:.2f}-INR {max_amt:.2f} each."
            })
            
    return findings

def detect_circular_flow(graph, max_hop_gap_minutes=30, max_chain_length=6) -> list[dict]:
    """
    Finds temporal cycles: a path returning to start account where each hop occurs 
    within max_hop_gap_minutes of the previous hop, cycle length 3 to max_chain_length.
    """
    findings = []
    detected_cycles_keys = set()
    
    # Pre-index outgoing edges by sender to make traversal fast
    adj = {node: [] for node in graph.nodes()}
    for u, v, data in graph.edges(data=True):
        adj[u].append((v, data))
    
    # Sort adjacency lists by timestamp
    for u in adj:
        adj[u].sort(key=lambda x: x[1]['timestamp'])
        
    def dfs(current_node, start_node, path_edges, last_time):
        # Base Case: Closed cycle of length >= 3
        if current_node == start_node and len(path_edges) >= 3:
            # Create a unique key of transaction IDs sorted to avoid duplicates
            tx_ids = sorted([e['transaction_id'] for e in path_edges])
            cycle_key = tuple(tx_ids)
            if cycle_key not in detected_cycles_keys:
                detected_cycles_keys.add(cycle_key)
                
                # Extract involved accounts (unique nodes in the cycle)
                all_nodes = [path_edges[0]['sender_id']] + [e['receiver_id'] for e in path_edges]
                involved_accounts = list(dict.fromkeys(all_nodes))  # preserve order, deduplicate
                
                # Build a readable chain: Node0 -> Node1 -> ... -> Node0
                chain_upis = [graph.nodes[n].get('upi_id', n[:8]) for n in involved_accounts]
                chain_str = " -> ".join(chain_upis)
                amount_sample = path_edges[0]['amount']
                    
                total_duration_mins = int((path_edges[-1]['timestamp'] - path_edges[0]['timestamp']).total_seconds() / 60)
                
                findings.append({
                    "pattern_type": "circular",
                    "primary_account": start_node,
                    "involved_accounts": involved_accounts[:-1],  # exclude repeated start
                    "involved_transactions": [e['transaction_id'] for e in path_edges],
                    "window_start": path_edges[0]['timestamp'].isoformat(),
                    "window_end": path_edges[-1]['timestamp'].isoformat(),
                    "evidence_summary": f"{len(path_edges)}-hop circular flow: {chain_str} — INR {amount_sample:.0f} cycled back to origin in {total_duration_mins} minutes."
                })
            return
            
        # Stopping criteria: exceed max chain length
        if len(path_edges) >= max_chain_length:
            return
            
        # Traverse temporal outgoing links
        # Optimization: binary search or scan since lists are sorted
        t_limit = last_time + timedelta(minutes=max_hop_gap_minutes)
        for next_node, data in adj[current_node]:
            tx_time = data['timestamp']
            
            # Hop must happen chronologically and within the gap window
            if last_time <= tx_time <= t_limit:
                # Avoid visiting same node twice (except returning to start_node)
                visited_nodes = {e['sender_id'] for e in path_edges}
                if next_node == start_node or next_node not in visited_nodes:
                    dfs(next_node, start_node, path_edges + [{
                        'sender_id': current_node,
                        'receiver_id': next_node,
                        'amount': data['amount'],
                        'timestamp': data['timestamp'],
                        'transaction_id': data['transaction_id']
                    }], tx_time)
            elif tx_time > t_limit:
                # Since list is sorted, subsequent edges are past the limit
                break

    # Start temporal cycle search from each transaction edge
    for u, v, data in graph.edges(data=True):
        start_time = data['timestamp']
        first_hop = {
            'sender_id': u,
            'receiver_id': v,
            'amount': data['amount'],
            'timestamp': start_time,
            'transaction_id': data['transaction_id']
        }
        dfs(v, u, [first_hop], start_time)
        
    return findings

def detect_smurfing(graph, window_hours=6, min_transactions=8, threshold=10000, band_pct=0.15) -> list[dict]:
    """
    Flags a receiving account if it gets at least min_transactions incoming payments
    within window_hours, where amounts cluster just under threshold.
    """
    findings = []
    lower_bound = threshold * (1 - band_pct)
    
    for v in graph.nodes():
        # Get all incoming transactions to v that fall in the smurfing amount band
        in_edges = []
        for u, _, data in graph.in_edges(v, data=True):
            amount = data['amount']
            if lower_bound <= amount < threshold:
                in_edges.append((u, data))
                
        if len(in_edges) < min_transactions:
            continue
            
        # Sort by timestamp
        in_edges.sort(key=lambda x: x[1]['timestamp'])
        
        # Sliding window search
        best_window = None
        max_tx_count = 0
        
        for i in range(len(in_edges)):
            t_start = in_edges[i][1]['timestamp']
            t_end = t_start + timedelta(hours=window_hours)
            
            # Count transactions in this window
            window_edges = []
            for j in range(i, len(in_edges)):
                if in_edges[j][1]['timestamp'] <= t_end:
                    window_edges.append(in_edges[j])
                else:
                    break
            
            if len(window_edges) >= min_transactions and len(window_edges) > max_tx_count:
                max_tx_count = len(window_edges)
                best_window = {
                    "senders": list(set(u for u, _ in window_edges)),
                    "tx_ids": [data['transaction_id'] for _, data in window_edges],
                    "start": t_start,
                    "end": max(data['timestamp'] for _, data in window_edges),
                    "amounts": [data['amount'] for _, data in window_edges]
                }
                
        if best_window:
            duration_hours = (best_window["end"] - best_window["start"]).total_seconds() / 3600.0
            avg_amount = sum(best_window["amounts"]) / len(best_window["amounts"])
            
            findings.append({
                "pattern_type": "smurfing",
                "primary_account": v,
                "involved_accounts": best_window["senders"],
                "involved_transactions": best_window["tx_ids"],
                "window_start": best_window["start"].isoformat(),
                "window_end": best_window["end"].isoformat(),
                "evidence_summary": f"Received {max_tx_count} structured payments (avg INR {avg_amount:.2f}) from {len(best_window['senders'])} accounts within {duration_hours:.1f} hours, all strictly under the INR {threshold} reporting limit."
            })
            
    return findings

def detect_rapid_passthrough(graph, max_gap_minutes=15, min_forward_pct=0.7) -> list[dict]:
    """
    Flags an account that receives a payment and forwards at least min_forward_pct of
    that amount onward within max_gap_minutes.
    """
    findings = []
    
    # Deduplicate findings — one finding per (primary_account, in_tx_id, out_tx_id) triple
    seen_passthrough = set()

    for u in graph.nodes():
        # Get all incoming and outgoing edges for u, capturing the sender node too
        in_edges = []  # list of (sender_node, edge_data)
        for s, _, data in graph.in_edges(u, data=True):
            in_edges.append((s, data))
            
        out_edges = []  # list of (receiver_node, edge_data)
        for _, r, data in graph.out_edges(u, data=True):
            out_edges.append((r, data))
            
        if not in_edges or not out_edges:
            continue
            
        # Match rapid pass-through pairs
        for s, in_tx in in_edges:
            t_in = in_tx['timestamp']
            amt_in = in_tx['amount']
            
            for r, out_tx in out_edges:
                t_out = out_tx['timestamp']
                amt_out = out_tx['amount']
                
                # Check timing: outgoing must happen AFTER incoming, within the gap
                if t_in < t_out <= t_in + timedelta(minutes=max_gap_minutes):
                    if amt_out >= amt_in * min_forward_pct:
                        dedup_key = (u, in_tx['transaction_id'], out_tx['transaction_id'])
                        if dedup_key in seen_passthrough:
                            continue
                        seen_passthrough.add(dedup_key)
                        
                        forward_pct = (amt_out / amt_in) * 100
                        gap_seconds = int((t_out - t_in).total_seconds())
                        
                        findings.append({
                            "pattern_type": "pass_through",
                            "primary_account": u,
                            "involved_accounts": [s, r],
                            "involved_transactions": [in_tx['transaction_id'], out_tx['transaction_id']],
                            "window_start": t_in.isoformat(),
                            "window_end": t_out.isoformat(),
                            "evidence_summary": f"Received INR {amt_in:.2f} from upstream and forwarded INR {amt_out:.2f} ({forward_pct:.1f}%) onward within {gap_seconds} seconds — {min_forward_pct*100:.0f}%+ pass-through."
                        })
                        
    return findings
