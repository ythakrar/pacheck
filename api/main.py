import os, logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/pacheck")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

app = FastAPI(title="PACheck API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def db_row_to_dict(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/lookup")
def lookup(
    cpt:       str           = Query(...),
    payer:     Optional[str] = Query(None),
    plan_type: Optional[str] = Query(None),
    state:     Optional[str] = Query(None),
    db = Depends(get_db),
):
    cpt_codes   = [c.strip().upper() for c in cpt.split(",") if c.strip()]
    payer_slugs = [p.strip().lower() for p in payer.split(",")] if payer else []
    plan_types  = [p.strip().lower() for p in plan_type.split(",")] if plan_type else []
    state_code  = state.upper()[:2] if state else None

    conditions = ["c.code = ANY(%s)", "c.is_active = true", "r.is_active = true", "p.is_active = true"]
    params = [cpt_codes]

    if payer_slugs:
        conditions.append("p.slug = ANY(%s)")
        params.append(payer_slugs)
    if plan_types:
        conditions.append("pt.slug = ANY(%s)")
        params.append(plan_types)
    if state_code:
        conditions.append("(r.state = %s OR r.state IS NULL)")
        params.append(state_code)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT c.code, c.description, c.specialty, c.category,
               p.slug AS payer_slug, p.name AS payer_name,
               p.short_name AS payer_short, p.color_hex AS payer_color,
               p.portal_url AS payer_portal,
               pt.slug AS plan_type, pt.label AS plan_label,
               r.state, r.status, r.notes, r.turnaround_days,
               r.submission_portal, r.confidence, r.source_type,
               r.updated_at, r.scraped_at
        FROM pa_rules r
        JOIN cpt_codes  c  ON c.id  = r.cpt_id
        JOIN payers     p  ON p.id  = r.payer_id
        JOIN plan_types pt ON pt.id = r.plan_type_id
        WHERE {where}
        ORDER BY c.code, p.slug, pt.slug
    """
    with db.cursor() as cur:
        cur.execute(sql, params)
        rows = db_row_to_dict(cur)

    grouped = {}
    for r in rows:
        key = r["code"]
        if key not in grouped:
            grouped[key] = {"cpt": key, "description": r["description"],
                            "specialty": r["specialty"], "category": r["category"], "rules": []}
        grouped[key]["rules"].append({
            "payer":            {"slug": r["payer_slug"], "name": r["payer_name"],
                                 "short": r["payer_short"], "color": r["payer_color"],
                                 "portal": r["payer_portal"]},
            "planType":         r["plan_type"],
            "planLabel":        r["plan_label"],
            "state":            r["state"],
            "status":           r["status"],
            "notes":            r["notes"],
            "turnaroundDays":   r["turnaround_days"],
            "submissionPortal": r["submission_portal"],
            "lastUpdated":      r["updated_at"].isoformat() if r["updated_at"] else None,
        })

    return {"results": list(grouped.values()),
            "meta": {"cptCodes": cpt_codes, "ruleCount": len(rows),
                     "queryTime": datetime.now(timezone.utc).isoformat()}}

@app.get("/search")
def search_cpt(q: str = Query(..., min_length=2), limit: int = Query(20), db = Depends(get_db)):
    sql = "SELECT code, description, specialty, category FROM cpt_codes WHERE code ILIKE %s OR description ILIKE %s AND is_active = true ORDER BY code LIMIT %s"
    with db.cursor() as cur:
        cur.execute(sql, (f"{q}%", f"%{q}%", limit))
        rows = db_row_to_dict(cur)
    return {"results": rows}

@app.get("/stats")
def stats(db = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cpt_codes WHERE is_active = true")
        total_codes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM pa_rules WHERE is_active = true")
        total_rules = cur.fetchone()[0]
        cur.execute("SELECT MAX(scraped_at) FROM pa_rules")
        last_updated = cur.fetchone()[0]
    return {"totalCptCodes": total_codes, "totalRules": total_rules,
            "lastUpdated": last_updated.isoformat() if last_updated else None}

@app.get("/recent-changes")
def recent_changes(days: int = Query(7), db = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute("""
            SELECT c.code, c.description, p.short_name AS payer,
                   pt.label AS plan_type, ch.old_status, ch.new_status, ch.changed_at
            FROM pa_rule_changelog ch
            JOIN pa_rules    r  ON r.id  = ch.pa_rule_id
            JOIN cpt_codes   c  ON c.id  = r.cpt_id
            JOIN payers      p  ON p.id  = r.payer_id
            JOIN plan_types  pt ON pt.id = r.plan_type_id
            WHERE ch.changed_at >= NOW() - (%s || ' days')::INTERVAL
            ORDER BY ch.changed_at DESC LIMIT 200
        """, (days,))
        rows = db_row_to_dict(cur)
    return {"changes": rows, "days": days}
