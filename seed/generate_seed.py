"""Write seed/accounts.csv, seed/orders.csv, and seed/tickets.csv deterministically.

    python3 seed/generate_seed.py

24 accounts (12 East owned by alice, 12 West owned by bob), 120 orders over the
four calendar quarters Q4 2025 to Q3 2026, and 40 support tickets. Every account
has at least one order in Q3 2026, the "last quarter" for a demo run in Q4 2026.
Contacts use the reserved .example TLD and 555-01xx phone numbers.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261023
OUT = Path(__file__).resolve().parent

OWNERS = {"East": "alice@example.com", "West": "bob@example.com"}
PERIOD_START, PERIOD_END = date(2025, 10, 1), date(2026, 9, 30)
LAST_QUARTER_START = date(2026, 7, 1)

COMPANIES = [
    "Acme Logistics", "Birchwood Foods", "Cobalt Robotics", "Dunmore Textiles",
    "Evergreen Clinics", "Foxglove Media", "Granite Insurance", "Harbor Freight Lines",
    "Ironvale Mining", "Juniper Hotels", "Kestrel Aviation", "Lumen Pharmacy",
    "Maple Street Bank", "Northwind Outfitters", "Orchid Analytics", "Pinecrest Schools",
    "Quarry Building Supply", "Redwood Solar", "Sable Security", "Tidewater Marine",
    "Umber Coffee Roasters", "Vantage Telecom", "Willow Health", "Yellowtail Seafood",
]
FIRST = ["Avery", "Blake", "Casey", "Devon", "Emerson", "Finley", "Gray", "Harper",
         "Indy", "Jordan", "Kai", "Logan", "Morgan", "Noel", "Oakley", "Parker",
         "Quinn", "Reese", "Sage", "Taylor", "Umi", "Val", "Wren", "Zion"]
LAST = ["Abbott", "Brooks", "Chen", "Diaz", "Ellis", "Foster", "Garcia", "Hughes",
        "Ito", "James", "Khan", "Lopez", "Moreno", "Nash", "Olsen", "Patel",
        "Reyes", "Shah", "Tran", "Usman", "Vega", "Walsh", "Young", "Zhou"]
SUMMARIES = [
    "Login fails after password reset", "Invoice total does not match order",
    "Shipment arrived damaged", "API returns timeout errors", "Dashboard loads slowly",
    "Request to add a new user seat", "Data export missing columns", "Billing address change",
    "Integration sync stopped overnight", "Report shows wrong currency",
]


def slug(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch == " ").replace(" ", "")


def rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def main() -> None:
    rng = random.Random(SEED)

    accounts = []
    for i, company in enumerate(COMPANIES):
        region = "East" if i < 12 else "West"
        first, last = FIRST[i], LAST[(i * 7) % len(LAST)]
        domain = f"{slug(company)}.example"
        accounts.append({
            "account_id": f"A{i + 1:03d}",
            "account_name": company,
            "region": region,
            "owner_email": OWNERS[region],
            "contact_name": f"{first} {last}",
            "contact_email": f"{first.lower()}.{last.lower()}@{domain}",
            "contact_phone": f"+1-202-555-01{i:02d}",
            "annual_revenue": f"{rng.randint(500, 50_000) * 1000:.2f}",
            "status": "at_risk" if rng.random() < 0.15 else "active",
        })

    orders = []
    for acct in accounts:
        dates = [rand_date(rng, LAST_QUARTER_START, PERIOD_END)]
        dates += [rand_date(rng, PERIOD_START, PERIOD_END) for _ in range(4)]
        for d in dates:
            orders.append({"account_id": acct["account_id"], "order_date": d.isoformat(),
                           "amount": f"{rng.randint(1_000, 250_000)}.{rng.randint(0, 99):02d}"})
    orders.sort(key=lambda o: (o["order_date"], o["account_id"]))
    for n, o in enumerate(orders, 1):
        o["order_id"] = f"O{n:04d}"

    # Guarantee open high-severity tickets in both regions for the cross-space question.
    pinned = ["A002", "A005", "A014", "A019"]
    tickets = []
    for n in range(40):
        acct = accounts[int(pinned[n][1:]) - 1] if n < len(pinned) else rng.choice(accounts)
        opened = rand_date(rng, PERIOD_START, date(2026, 10, 20))
        if n < len(pinned):
            severity, status = "high", "open"
        else:
            severity = rng.choices(["low", "medium", "high"], weights=[5, 4, 2])[0]
            status = "open" if opened >= date(2026, 9, 1) or rng.random() < 0.2 else "closed"
        reporter = rng.choice(FIRST).lower()
        tickets.append({
            "account_id": acct["account_id"],
            "opened_date": opened.isoformat(),
            "severity": severity,
            "status": status,
            "reporter_email": f"{reporter}@{acct['contact_email'].split('@')[1]}",
            "summary": rng.choice(SUMMARIES),
        })
    tickets.sort(key=lambda t: (t["opened_date"], t["account_id"]))
    for n, t in enumerate(tickets, 1):
        t["ticket_id"] = f"T{n:04d}"

    write(OUT / "accounts.csv", accounts, ["account_id", "account_name", "region", "owner_email",
          "contact_name", "contact_email", "contact_phone", "annual_revenue", "status"])
    write(OUT / "orders.csv", orders, ["order_id", "account_id", "order_date", "amount"])
    write(OUT / "tickets.csv", tickets, ["ticket_id", "account_id", "opened_date", "severity",
          "status", "reporter_email", "summary"])
    print(f"accounts={len(accounts)} orders={len(orders)} tickets={len(tickets)}")


def write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()
