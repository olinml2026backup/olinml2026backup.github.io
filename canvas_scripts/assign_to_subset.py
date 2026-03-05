#!/usr/bin/env python3
import argparse, csv, os, re, sys
import requests

def next_link(link_header):
    if not link_header: return None
    for part in link_header.split(","):
        m = re.search(r'<([^>]+)>\s*;\s*rel="next"', part)
        if m: return m.group(1)
    return None

def paginated_get(session, url, params=None):
    out = []
    while url:
        r = session.get(url, params=params)
        r.raise_for_status()
        out.extend(r.json())
        url = next_link(r.headers.get("Link"))
        params = None
    return out

def read_ids(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows: return []
    # accept header or no header, take first column
    start = 1 if any("sis" in c.lower() for c in rows[0]) else 0
    ids = [r[0].strip() for r in rows[start:] if r and r[0].strip()]
    # de-dupe preserve order
    seen, out = set(), []
    for x in ids:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("CANVAS_BASE","https://olin.instructure.com"))
    ap.add_argument("--course", type=int, required=True)
    ap.add_argument("--assignment", type=int, required=True)
    ap.add_argument("--csv", required=True, help="CSV of SIS user IDs (first column)")
    ap.add_argument("--token", default=os.environ.get("CANVAS_TOKEN"))
    ap.add_argument("--title", default="Assessment B")
    ap.add_argument("--only-visible", action="store_true")
    args = ap.parse_args()

    if not args.token:
        print("Missing token: set CANVAS_TOKEN or pass --token", file=sys.stderr)
        sys.exit(2)

    base = args.base.rstrip("/")
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {args.token}"})

    # Build map: sis_user_id -> canvas_user_id using *course users* endpoint
    roster_url = f"{base}/api/v1/courses/{args.course}/users"
    roster = paginated_get(session, roster_url, params={
        "enrollment_type[]": "student",
        "include[]": "sis_user_id",
        "per_page": 100
    })

    sis_to_canvas = {}
    for u in roster:
        sis = u.get("sis_user_id")
        cid = u.get("id")
        if sis and cid:
            sis_to_canvas[str(sis)] = int(cid)

    sis_list = read_ids(args.csv)

    missing = [s for s in sis_list if s not in sis_to_canvas]
    if missing:
        print("These SIS IDs were not found in the course roster:", file=sys.stderr)
        for m in missing[:20]:
            print("  ", m, file=sys.stderr)
        if len(missing) > 20:
            print(f"  ... and {len(missing)-20} more", file=sys.stderr)
        print("Fix: confirm they are enrolled in THIS course, and that the CSV values match Canvas sis_user_id exactly.", file=sys.stderr)
        sys.exit(2)

    student_ids = [sis_to_canvas[s] for s in sis_list]

    # Create override (student_ids must be Canvas user IDs)
    ov_url = f"{base}/api/v1/courses/{args.course}/assignments/{args.assignment}/overrides"
    data = [("assignment_override[title]", args.title)] + \
           [("assignment_override[student_ids][]", str(cid)) for cid in student_ids]

    r = session.post(ov_url, data=data)
    r.raise_for_status()
    ov = r.json()
    print(f"Created override id={ov.get('id')} for {len(student_ids)} students")

    if args.only_visible:
        asn_url = f"{base}/api/v1/courses/{args.course}/assignments/{args.assignment}"
        r2 = session.put(asn_url, data={"assignment[only_visible_to_overrides]":"true"})
        r2.raise_for_status()
        print("Set assignment[only_visible_to_overrides]=true")

if __name__ == "__main__":
    main()
