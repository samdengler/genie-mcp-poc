# /// script
# requires-python = ">=3.11"
# dependencies = ["databricks-sdk>=0.60"]
# ///
"""Create or update the Sales and Support Genie spaces from genie/*_space.json.

    uv run genie/create_spaces.py            # uses the admin profile

Writes the space ids and MCP URLs to genie/spaces.json. A space already listed
there is updated in place (PATCH) instead of created again. Both groups get
CAN RUN on each space.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dbsql  # noqa: E402

SPACES = {"sales": "genie/sales_space.json", "support": "genie/support_space.json"}
GROUPS = ["account_managers", "finance_analysts"]
OUT = ROOT / "genie" / "spaces.json"


def item_id(space: str, kind: str, text: str) -> str:
    # Stable 32-hex ids, so rerunning the script does not churn the space definition.
    return uuid.uuid5(uuid.NAMESPACE_URL, f"genie-mcp-poc/{space}/{kind}/{text}").hex


def serialize(space: str, d: dict) -> str:
    """Build the serialized_space document (version 2) from the readable definition."""
    by_id = lambda items: sorted(items, key=lambda i: i["id"])  # noqa: E731
    doc = {
        "version": 2,
        "config": {
            "sample_questions": by_id(
                {"id": item_id(space, "sample", q), "question": [q]} for q in d["sample_questions"]
            ),
        },
        "data_sources": {
            "tables": [{"identifier": t} for t in sorted(d["tables"])],
            "metric_views": [{"identifier": m} for m in sorted(d["metric_views"])],
        },
        "instructions": {
            "text_instructions": [
                {"id": item_id(space, "text", "instructions"), "content": ["\n".join(d["instructions"])]}
            ],
            "example_question_sqls": by_id(
                {"id": item_id(space, "example", e["question"]), "question": [e["question"]],
                 "sql": [line + "\n" for line in e["sql"].splitlines()]}
                for e in d["example_sqls"]
            ),
        },
    }
    if not doc["data_sources"]["metric_views"]:
        del doc["data_sources"]["metric_views"]
    return json.dumps(doc)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="admin")
    args = ap.parse_args()

    w = dbsql.client(args.profile)
    wid = dbsql.warehouse_id(w)
    host = w.config.host.rstrip("/")
    known = json.loads(OUT.read_text()) if OUT.exists() else {}

    for key, path in SPACES.items():
        d = json.loads((ROOT / path).read_text())
        body = {"warehouse_id": wid, "title": d["title"], "description": d["description"],
                "serialized_space": serialize(key, d)}
        space_id = known.get(key, {}).get("space_id")
        if space_id:
            w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=body)
            print(f"{key}: updated {space_id}")
        else:
            space_id = w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)["space_id"]
            print(f"{key}: created {space_id}")
        w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{space_id}", body={
            "access_control_list": [{"group_name": g, "permission_level": "CAN_RUN"} for g in GROUPS]})
        known[key] = {
            "title": d["title"],
            "space_id": space_id,
            "space_url": f"{host}/genie/rooms/{space_id}",
        }

    OUT.write_text(json.dumps(known, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
