import csv, pathlib

D = pathlib.Path("dataset")


def rows(n):
    with open(D / n, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


for n in [
    "deletion_requests",
    "sample_deletion_requests",
    "sample_output",
    "deletion_rules",
    "evidence_files",
    "system_activity",
    "user_audit_log",
    "user_identities",
]:
    print(n, len(rows(n + ".csv")))

manifest = {r["file_id"]: r for r in rows("evidence_files.csv")}
reqs = {r["case_id"]: r for r in rows("deletion_requests.csv")}
reqs.update({r["case_id"]: r for r in rows("sample_deletion_requests.csv")})


def show(case, ev, needles):
    r, m = reqs[case], manifest[ev]
    text = (D / m["file_path"]).read_text(encoding="utf-8", errors="ignore")
    print(
        f"{case} audit_at={r['audit_at']} | {ev} captured={m['captured_at']} "
        f"| eligible={m['captured_at'] <= r['audit_at']}"
    )
    for n in needles:
        print("   ", n, text.count(n))


show("case_05", "evidence_54", ["account_005", "leila.haddad@yahoo.com"])
show("case_19", "evidence_01", ["search_6083", "support_9553"])
show("case_31", "evidence_51", ["tombstone_440", "audit_record_6909"])
show(
    "case_28",
    "evidence_92",
    ["account_5482", "audit_record_9265", "support_2351", "backup_838"],
)

for r in rows("user_audit_log.csv"):
    if r["audit_id"] in {"audit_121", "audit_122", "audit_238", "audit_239"}:
        print(r)
for r in rows("user_identities.csv"):
    if r["user_id"] == "user_10":
        print(r)
for c in range(533, 543):
    print(f"case_{c}", reqs[f"case_{c}"]["request_text"])
