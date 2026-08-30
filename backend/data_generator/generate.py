import random
import uuid
import csv
import os
from datetime import datetime, timedelta
import numpy as np
from faker import Faker

# ---------------------------------------------------------
# Configurations and Seed Setup
# ---------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
fake.seed_instance(SEED)

START_DATE = datetime(2026, 8, 1, 0, 0, 0)
END_DATE = datetime(2026, 8, 30, 23, 59, 59)
TOTAL_DAYS = 30

# Output Paths
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
ACCOUNTS_CSV = os.path.join(OUTPUT_DIR, "accounts.csv")
TRANSACTIONS_CSV = os.path.join(OUTPUT_DIR, "transactions.csv")

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
used_upi_ids = set()

def generate_unique_upi(name):
    # Sanitize name to make alphanumeric upi handle
    clean_name = "".join(c for c in name if c.isalnum()).lower()
    if not clean_name:
        clean_name = "user"
    base = f"{clean_name}{random.randint(10, 99)}"
    upi_id = f"{base}@upi"
    while upi_id in used_upi_ids:
        base = f"{clean_name}{random.randint(100, 9999)}"
        upi_id = f"{base}@upi"
    used_upi_ids.add(upi_id)
    return upi_id

def get_random_timestamp_within_range(start, end):
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)

def get_random_timestamp_across_30_days():
    return get_random_timestamp_within_range(START_DATE, END_DATE)

# ---------------------------------------------------------
# Step 1: Generate 300 Background Accounts
# ---------------------------------------------------------
accounts = []
accounts_by_id = {}

# Quantities
NUM_MERCHANT = 30    # ~10%
NUM_PAYROLL = 15     # ~5%
NUM_PERSONAL = 255   # Rest

def create_account(account_type):
    account_id = str(uuid.UUID(int=random.getrandbits(128)))
    
    # Generate name using faker based on account type
    if account_type == "merchant":
        name = fake.company()
        # Bias older: 300 to 1500 days
        age_days = random.randint(300, 1500)
    elif account_type == "payroll":
        name = f"{fake.company()} Payroll"
        age_days = random.randint(300, 1500)
    else:
        name = fake.name()
        # 1 to 1000 days
        age_days = random.randint(1, 1000)
        
    created_at = START_DATE - timedelta(days=age_days)
    upi_id = generate_unique_upi(name)
    
    acc = {
        "account_id": account_id,
        "upi_id": upi_id,
        "account_type": account_type,
        "account_age_days": age_days,
        "created_at": created_at.isoformat()
    }
    accounts.append(acc)
    accounts_by_id[account_id] = acc
    return acc

for _ in range(NUM_MERCHANT):
    create_account("merchant")
for _ in range(NUM_PAYROLL):
    create_account("payroll")
for _ in range(NUM_PERSONAL):
    create_account("personal")

# Filter groups for background traffic
merchants = [a for a in accounts if a["account_type"] == "merchant"]
payrolls = [a for a in accounts if a["account_type"] == "payroll"]
personals = [a for a in accounts if a["account_type"] == "personal"]

# ---------------------------------------------------------
# Step 2: Generate ~3000 Normal Background Transactions
# ---------------------------------------------------------
transactions = []

# Helper to add transaction
def add_transaction(sender_id, receiver_id, amount, timestamp, is_injected=False, pattern_type="", cluster_id=""):
    tx_id = str(uuid.UUID(int=random.getrandbits(128)))
    tx = {
        "transaction_id": tx_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "amount": round(float(amount), 2),
        "timestamp": timestamp.isoformat(),
        "is_injected": is_injected,
        "pattern_type": pattern_type,
        "cluster_id": cluster_id
    }
    transactions.append(tx)
    return tx

NUM_BACKGROUND_TX = 3000

for _ in range(NUM_BACKGROUND_TX):
    # Choose transaction category:
    # 50% Personal-to-Personal (P2P)
    # 40% Purchase (Personal-to-Merchant - Fan-in)
    # 10% Salary (Payroll-to-Personal - Fan-out)
    choice = random.random()
    timestamp = get_random_timestamp_across_30_days()
    
    # Amount distribution: mostly ₹100–₹15000
    # Let's use log-normal centered around ₹1000, capped at 15000, minimum 100
    amount = float(np.clip(np.random.lognormal(mean=7.0, sigma=1.0), 100, 15000))
    
    if choice < 0.50:
        # P2P
        sender = random.choice(personals)
        receiver = random.choice(personals)
        while receiver["account_id"] == sender["account_id"]:
            receiver = random.choice(personals)
        add_transaction(sender["account_id"], receiver["account_id"], amount, timestamp)
    elif choice < 0.90:
        # Purchase (Personal to Merchant)
        sender = random.choice(personals)
        receiver = random.choice(merchants)
        add_transaction(sender["account_id"], receiver["account_id"], amount, timestamp)
    else:
        # Salary (Payroll to Personal)
        sender = random.choice(payrolls)
        receiver = random.choice(personals)
        add_transaction(sender["account_id"], receiver["account_id"], amount, timestamp)

# ---------------------------------------------------------
# Step 3: Inject 5 Known Fraud Patterns
# ---------------------------------------------------------

# Helper to create an isolated personal account for fraud clusters
def create_isolated_personal_account():
    acc = create_account("personal")
    return acc["account_id"]

# 1. Fan-out Cluster: C_FAN_OUT_1
# 1 sender sends to 7 new personal accounts within a 2-hour window, amounts ₹8000-9500 each
sender_fo = create_isolated_personal_account()
receivers_fo = [create_isolated_personal_account() for _ in range(7)]
fo_start_time = datetime(2026, 8, 10, 14, 0, 0)
for r_id in receivers_fo:
    tx_time = fo_start_time + timedelta(seconds=random.randint(0, 7200)) # within 2 hours
    amount = random.randint(8000, 9500)
    add_transaction(
        sender_id=sender_fo,
        receiver_id=r_id,
        amount=amount,
        timestamp=tx_time,
        is_injected=True,
        pattern_type="fan_out",
        cluster_id="C_FAN_OUT_1"
    )

# 2. Fan-in Cluster: C_FAN_IN_1
# 7 personal accounts send to the same single account within 3 hours, amounts ₹8000-9500 each
senders_fi = [create_isolated_personal_account() for _ in range(7)]
receiver_fi = create_isolated_personal_account()
fi_start_time = datetime(2026, 8, 14, 9, 30, 0)
for s_id in senders_fi:
    tx_time = fi_start_time + timedelta(seconds=random.randint(0, 10800)) # within 3 hours
    amount = random.randint(8000, 9500)
    add_transaction(
        sender_id=s_id,
        receiver_id=receiver_fi,
        amount=amount,
        timestamp=tx_time,
        is_injected=True,
        pattern_type="fan_in",
        cluster_id="C_FAN_IN_1"
    )

# 3. Circular Flow Cluster: C_CIRCULAR_1
# Chain of 5 accounts: A -> B -> C -> D -> E -> A, each hop within 30 minutes of the previous
nodes = [create_isolated_personal_account() for _ in range(5)]
circ_start_time = datetime(2026, 8, 18, 16, 0, 0)
current_time = circ_start_time
amount = 5000.00
for i in range(5):
    sender_c = nodes[i]
    receiver_c = nodes[(i + 1) % 5]
    current_time += timedelta(minutes=random.randint(5, 25)) # hop within 30 mins
    add_transaction(
        sender_id=sender_c,
        receiver_id=receiver_c,
        amount=amount,
        timestamp=current_time,
        is_injected=True,
        pattern_type="circular",
        cluster_id="C_CIRCULAR_1"
    )

# 4. Smurfing Cluster: C_SMURFING_1
# 11 accounts send just under ₹10,000 (e.g. ₹9500-9900) to the same receiver, spread across 4 hours
senders_sm = [create_isolated_personal_account() for _ in range(11)]
receiver_sm = create_isolated_personal_account()
sm_start_time = datetime(2026, 8, 22, 11, 0, 0)
for s_id in senders_sm:
    tx_time = sm_start_time + timedelta(seconds=random.randint(0, 14400)) # within 4 hours
    amount = random.randint(9500, 9900)
    add_transaction(
        sender_id=s_id,
        receiver_id=receiver_sm,
        amount=amount,
        timestamp=tx_time,
        is_injected=True,
        pattern_type="smurfing",
        cluster_id="C_SMURFING_1"
    )

# 5. Rapid Pass-through Cluster: C_PASSTHROUGH_1
# Account A sends lump sum to B, B forwards ~90% of it onward to C within 10 minutes
acc_a = create_isolated_personal_account()
acc_b = create_isolated_personal_account()
acc_c = create_isolated_personal_account()
pt_start_time = datetime(2026, 8, 25, 18, 15, 0)

# Hop 1: A -> B (Lump sum)
lump_sum = 50000.00
add_transaction(
    sender_id=acc_a,
    receiver_id=acc_b,
    amount=lump_sum,
    timestamp=pt_start_time,
    is_injected=True,
    pattern_type="pass_through",
    cluster_id="C_PASSTHROUGH_1"
)

# Hop 2: B -> C (~90% of it forwarded within 10 mins)
forward_amount = lump_sum * 0.90
pt_second_time = pt_start_time + timedelta(seconds=random.randint(60, 540)) # 1 to 9 minutes later
add_transaction(
    sender_id=acc_b,
    receiver_id=acc_c,
    amount=forward_amount,
    timestamp=pt_second_time,
    is_injected=True,
    pattern_type="pass_through",
    cluster_id="C_PASSTHROUGH_1"
)

# ---------------------------------------------------------
# 6. Legitimate Merchant Flash-Sale Burst: C_LEGIT_BURST_1
# A normal flash sale: 10 personal accounts buy from the SAME merchant within
# a 90-minute window, amounts ₹500–3000 each (normal purchase range).
# is_injected=False — this is NOT fraud. It is structurally similar to fan-in
# (many senders, one receiver, tight window) to stress-test false-positive rates.
# ---------------------------------------------------------
legit_merchant = merchants[0]  # deterministic: first merchant in the list
legit_buyers = random.sample(personals, 10)  # 10 distinct personal accounts
lb_start_time = datetime(2026, 8, 12, 12, 0, 0)  # midday flash sale

for buyer in legit_buyers:
    tx_time = lb_start_time + timedelta(seconds=random.randint(0, 5400))  # within 90 min
    amount = random.randint(500, 3000)
    add_transaction(
        sender_id=buyer["account_id"],
        receiver_id=legit_merchant["account_id"],
        amount=amount,
        timestamp=tx_time,
        is_injected=False,
        pattern_type="legit_burst",
        cluster_id="C_LEGIT_BURST_1"
    )

# Sort all transactions by timestamp to keep the ledger chronological
transactions.sort(key=lambda x: x["timestamp"])

# ---------------------------------------------------------
# Step 4: Output to CSV files
# ---------------------------------------------------------
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(ACCOUNTS_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["account_id", "upi_id", "account_type", "account_age_days", "created_at"])
    for acc in accounts:
        writer.writerow([
            acc["account_id"],
            acc["upi_id"],
            acc["account_type"],
            acc["account_age_days"],
            acc["created_at"]
        ])

with open(TRANSACTIONS_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["transaction_id", "sender_id", "receiver_id", "amount", "timestamp", "is_injected", "pattern_type", "cluster_id"])
    for tx in transactions:
        writer.writerow([
            tx["transaction_id"],
            tx["sender_id"],
            tx["receiver_id"],
            tx["amount"],
            tx["timestamp"],
            tx["is_injected"],
            tx["pattern_type"] if tx["pattern_type"] else "",
            tx["cluster_id"] if tx["cluster_id"] else ""
        ])

# ---------------------------------------------------------
# Step 5: Summary Output
# ---------------------------------------------------------
total_accounts = len(accounts)
acc_types = {}
for acc in accounts:
    t = acc["account_type"]
    acc_types[t] = acc_types.get(t, 0) + 1

total_tx = len(transactions)
normal_tx_count = sum(1 for tx in transactions if not tx["is_injected"])
injected_tx_count = sum(1 for tx in transactions if tx["is_injected"])

injected_by_pattern = {}
for tx in transactions:
    if tx["is_injected"]:
        pt = tx["pattern_type"]
        cid = tx["cluster_id"]
        if pt not in injected_by_pattern:
            injected_by_pattern[pt] = {}
        injected_by_pattern[pt][cid] = injected_by_pattern[pt].get(cid, 0) + 1

print("=" * 60)
print("              TRACE_NET SYNTHETIC DATA GENERATOR             ")
print("=" * 60)
print(f"Total Accounts Generated: {total_accounts}")
for t, count in acc_types.items():
    print(f"  - {t.capitalize()}: {count}")

legit_burst_count = sum(1 for tx in transactions if tx["cluster_id"] == "C_LEGIT_BURST_1")
print(f"\nTotal Transactions Generated: {total_tx}")
print(f"  - Normal Background Transactions: {normal_tx_count - legit_burst_count}")
print(f"  - Legit Burst (C_LEGIT_BURST_1, not fraud): {legit_burst_count}")
print(f"  - Injected Fraud Transactions: {injected_tx_count}")

print("\nInjected Fraud Patterns Breakdown:")
for pt, clusters in injected_by_pattern.items():
    print(f"  - Pattern: '{pt}'")
    for cid, count in clusters.items():
        print(f"    * Cluster ID: {cid} ({count} transactions)")
print("\nLegit Burst Breakdown (NOT fraud — false-positive stress test):")
print(f"  - Cluster: C_LEGIT_BURST_1 ({legit_burst_count} transactions, merchant: {legit_merchant['upi_id']})")
print("=" * 60)
print(f"Accounts saved to: {ACCOUNTS_CSV}")
print(f"Transactions saved to: {TRANSACTIONS_CSV}")
print("=" * 60)
