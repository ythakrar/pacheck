import os, sys, logging, traceback
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"/tmp/pacheck-scraper-{datetime.now().strftime('%Y%m%d')}.log"),
    ],
)
log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))

SCRAPERS = [
    ("UHC",   "uhc",   "scrape_uhc"),
    ("Aetna", "aetna", "scrape_aetna"),
    ("BCBS",  "bcbs",  "scrape_bcbs"),
]

def run_all():
    start_time = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info(f"PACheck Nightly Scraper — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)
    results = {}
    for display_name, module_name, func_name in SCRAPERS:
        log.info(f"\nStarting: {display_name}")
        try:
            module = __import__(module_name)
            func   = getattr(module, func_name)
            stats  = func()
            results[display_name] = {"status": "success", "stats": stats}
            log.info(f"✓ {display_name} completed.")
        except Exception as e:
            log.error(f"✗ {display_name} failed: {e}")
            log.error(traceback.format_exc())
            results[display_name] = {"status": "failed", "error": str(e)}
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).seconds
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    for name, result in results.items():
        if result["status"] == "success":
            s = result["stats"]
            log.info(f"  {name:<10} ✓  found={s.get('found',0)}  new={s.get('inserted',0)}  updated={s.get('updated',0)}")
        else:
            log.info(f"  {name:<10} ✗  FAILED: {result.get('error','unknown')}")
    log.info(f"\n  Duration: {duration}s")
    log.info("=" * 60)
    return results

if __name__ == "__main__":
    run_all()
