import email
import email.utils
import imaplib
import json
import logging
import os
import re
import threading
from datetime import date, datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import Gauge, generate_latest, REGISTRY

import fund_parser
import gist_store
import nav_fetcher

logger = logging.getLogger("fund_exporter")

# ── Prometheus Metrics ──────────────────────────────────────────
fund_cost = Gauge("fund_cost", "累計申購成本", ["fund_name"])
fund_units = Gauge("fund_units", "累計單位數", ["fund_name"])
fund_nav = Gauge("fund_nav", "最新淨值", ["fund_name"])
fund_value = Gauge("fund_value", "市值 (units * nav)", ["fund_name"])
fund_cost_value_ratio = Gauge("fund_cost_value_ratio", "市值/成本比", ["fund_name"])

# ── 狀態 ────────────────────────────────────────────────────────
records: dict[str, dict] = {}
records_lock = threading.Lock()

mapping: dict[str, str] = {}
mapping_lock = threading.Lock()

# ── 設定 ────────────────────────────────────────────────────────
GMAIL_FOLDER = os.environ.get("GMAIL_FOLDER", "money/bank/line bank/fund")
NAV_CRON_HOUR = int(os.environ.get("NAV_CRON_HOUR", "22"))
NAV_CRON_MINUTE = int(os.environ.get("NAV_CRON_MINUTE", "0"))
FETCH_INTERVAL_HOURS = int(os.environ.get("FETCH_INTERVAL_HOURS", "1"))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "8000"))
INDEX_HTML = os.path.join(os.path.dirname(__file__), "index.html")


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


# ── 初始化從 Gist 載入 ──────────────────────────────────────────
def init_from_gist():
    global records, mapping
    try:
        h, m = gist_store.load()
    except Exception as e:
        logger.error("從 Gist 載入失敗: %s", e)
        h, m = {}, {}

    with records_lock:
        records = {}
        for name, data in h.items():
            records[name] = {
                "cost": float(data.get("cost", 0)),
                "units": float(data.get("units", 0)),
                "nav": 0.0,
                "nav_date": "",
            }
    with mapping_lock:
        mapping = m
    logger.info("初始化: %d 筆持倉, %d 筆對照", len(records), len(mapping))


def _sync_gist():
    with records_lock:
        holdings = {name: {"cost": r["cost"], "units": r["units"]} for name, r in records.items()}
    with mapping_lock:
        mp = dict(mapping)
    try:
        gist_store.save_both(holdings, mp)
    except Exception as e:
        logger.error("同步至 Gist 失敗: %s", e)


# ── 對照表管理 ──────────────────────────────────────────────────
def ensure_fund_code(fund_name: str) -> str | None:
    with mapping_lock:
        code = mapping.get(fund_name)
    if code:
        return code

    logger.info("發現新基金，自動搜尋代碼: %s", fund_name)
    code = nav_fetcher.search_fund_code(fund_name)
    if code:
        with mapping_lock:
            mapping[fund_name] = code
        _sync_gist()
        logger.info("已找到代碼 %s → %s", fund_name, code)
        return code

    logger.warning("找不到基金代碼: %s", fund_name)
    return None


# ── 郵件處理 ────────────────────────────────────────────────────
def decode_header(val):
    if val is None:
        return ""
    parts = email.header.decode_header(val)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_text(msg):
    if msg.is_multipart():
        text_content = None
        for part in msg.walk():
            ct = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except LookupError:
                decoded = payload.decode("utf-8", errors="replace")
            if ct == "text/plain":
                return decoded
            elif ct == "text/html" and text_content is None:
                text_content = strip_html(decoded)
        return text_content or ""
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload is None:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if ct == "text/plain":
            return decoded
        elif ct == "text/html":
            return strip_html(decoded)
        return ""


def quote_folder(name):
    return f'"{name}"'


def fetch_new_emails():
    email_account = os.environ.get("GMAIL_ACCOUNT")
    email_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not email_account or not email_password:
        return

    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(email_account, email_password)
        conn._simple_command("ENABLE", "UTF8=ACCEPT")
        conn.utf8_enabled = True
        conn._encoding = "utf-8"

        r = conn.select(quote_folder(GMAIL_FOLDER))
        if r[0] != "OK":
            conn.logout()
            return

        today = date.today().strftime("%d-%b-%Y")
        search_criteria = f'SINCE {today}'
        r = conn.uid("SEARCH", search_criteria.encode("utf-8"))
        if r[0] != "OK" or not r[1][0]:
            conn.logout()
            return

        all_uids = r[1][0].split()
        if not all_uids:
            conn.logout()
            return

        selected_uids = all_uids[-5:]
        new_records: list[dict] = []
        for uid in reversed(selected_uids):
            r = conn.uid("FETCH", uid, "(BODY[])")
            if r[0] != "OK":
                continue
            raw_email = r[1][0][1]
            msg = email.message_from_bytes(raw_email)
            body = get_text(msg)
            parsed = fund_parser.parse_email_body(body)
            new_records.extend(parsed)

        conn.close()
        conn.logout()

        if not new_records:
            return

        changed = False
        with records_lock:
            for rec in new_records:
                name = rec["fund_name"]
                if name not in records:
                    records[name] = {"cost": 0.0, "units": 0.0, "nav": 0.0, "nav_date": ""}
                records[name]["cost"] += rec["amount"]
                records[name]["units"] += rec["units"]
                changed = True

                code = ensure_fund_code(name)
                if code and records[name]["nav"] == 0.0:
                    nav_data = nav_fetcher.fetch_nav(code)
                    if nav_data:
                        records[name]["nav"] = nav_data[1]
                        records[name]["nav_date"] = nav_data[0]

        if changed:
            _sync_gist()
        logger.info("已處理 %d 筆新申購紀錄", len(new_records))

    except Exception as e:
        logger.error("郵件擷取失敗: %s", e)


# ── 淨值更新 ────────────────────────────────────────────────────
def update_navs():
    with records_lock:
        fund_names = list(records.keys())
    with mapping_lock:
        current_mapping = dict(mapping)

    for name in fund_names:
        code = current_mapping.get(name)
        if not code:
            code = ensure_fund_code(name)
        if not code:
            continue
        nav_data = nav_fetcher.fetch_nav(code)
        if nav_data:
            with records_lock:
                if name in records:
                    records[name]["nav"] = nav_data[1]
                    records[name]["nav_date"] = nav_data[0]
            logger.info("淨值更新 %s → %.4f (%s)", name, nav_data[1], nav_data[0])


# ── Metrics 更新 ────────────────────────────────────────────────
def refresh_metrics():
    with records_lock:
        snapshot = {k: dict(v) for k, v in records.items()}
    for name, data in snapshot.items():
        fund_cost.labels(fund_name=name).set(data["cost"])
        fund_units.labels(fund_name=name).set(data["units"])
        nav_val = data["nav"]
        fund_nav.labels(fund_name=name).set(nav_val)
        market_value = data["units"] * nav_val
        fund_value.labels(fund_name=name).set(market_value)
        ratio = market_value / data["cost"] if data["cost"] > 0 else 0.0
        fund_cost_value_ratio.labels(fund_name=name).set(ratio)


# ── API 回傳資料組裝 ────────────────────────────────────────────
def _holdings_list() -> list[dict]:
    with records_lock:
        names = sorted(records.keys())
        return [
            {
                "name": name,
                "cost": round(records[name]["cost"], 2),
                "units": records[name]["units"],
                "nav": records[name]["nav"],
                "nav_date": records[name]["nav_date"],
                "value": round(records[name]["units"] * records[name]["nav"], 2),
            }
            for name in names
        ]


# ── HTTP Handler ────────────────────────────────────────────────
_INDEX_CACHE: str | None = None
_INDEX_LOCK = threading.Lock()


def _serve_index() -> bytes:
    global _INDEX_CACHE
    with _INDEX_LOCK:
        if _INDEX_CACHE is None:
            try:
                with open(INDEX_HTML, "rb") as f:
                    _INDEX_CACHE = f.read()
            except Exception:
                _INDEX_CACHE = b"index.html not found"
        return _INDEX_CACHE


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            data = _serve_index()
            self._send(200, data, "text/html; charset=utf-8")

        elif path == "/metrics":
            refresh_metrics()
            self._send(200, generate_latest(REGISTRY), "text/plain; charset=utf-8")

        elif path == "/api/holdings":
            self._send(200, json.dumps({"holdings": _holdings_list()}, ensure_ascii=False).encode(), "application/json")

        elif path == "/api/search":
            q = qs.get("q", [None])[0]
            if not q or len(q.strip()) < 1:
                self._send(200, json.dumps({"results": []}).encode(), "application/json")
            else:
                results = nav_fetcher.search_suggestions(q.strip())
                self._send(200, json.dumps({"results": results}, ensure_ascii=False).encode(), "application/json")

        else:
            self._send(404, b"Not Found")

    def do_POST(self):
        if self.path == "/api/holdings":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body)
            fund_name = data.get("fund_name", "").strip()
            cost = float(data.get("cost", 0))
            units = float(data.get("units", 0))
            original_name = data.get("original_name", "").strip()

            if not fund_name or cost <= 0 or units <= 0:
                self._send(400, b"Invalid data")
                return

            with records_lock:
                if original_name and original_name != fund_name:
                    old_data = records.pop(original_name, None)
                    old_cost = old_data["cost"] if old_data else 0.0
                    old_units = old_data["units"] if old_data else 0.0
                    records[fund_name] = {"cost": old_cost, "units": old_units, "nav": 0.0, "nav_date": ""}
                if fund_name not in records:
                    records[fund_name] = {"cost": 0.0, "units": 0.0, "nav": 0.0, "nav_date": ""}
                records[fund_name]["cost"] = cost
                records[fund_name]["units"] = units

            code = ensure_fund_code(fund_name)
            if code and records.get(fund_name, {}).get("nav", 0) == 0:
                nav_data = nav_fetcher.fetch_nav(code)
                if nav_data:
                    with records_lock:
                        if fund_name in records:
                            records[fund_name]["nav"] = nav_data[1]
                            records[fund_name]["nav_date"] = nav_data[0]

            _sync_gist()
            self._send(200, json.dumps({"ok": True}).encode(), "application/json")
        else:
            self._send(404, b"Not Found")

    def do_DELETE(self):
        if self.path.startswith("/api/holdings"):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            fund_name = unquote(qs.get("fund_name", [None])[0] or "")
            if not fund_name:
                self._send(400, b"Missing fund_name")
                return
            with records_lock:
                records.pop(fund_name, None)
            with mapping_lock:
                mapping.pop(fund_name, None)
            _sync_gist()
            self._send(200, json.dumps({"ok": True}).encode(), "application/json")
        else:
            self._send(404, b"Not Found")

    def _send(self, status: int, body: bytes, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.info("HTTP %s", fmt % args)


# ── Main ────────────────────────────────────────────────────────
def main():
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    init_from_gist()

    if records:
        logger.info("啟動時立即更新淨值…")
        update_navs()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        fetch_new_emails,
        "interval",
        hours=FETCH_INTERVAL_HOURS,
        id="fetch_emails",
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    scheduler.add_job(
        update_navs,
        "cron",
        hour=NAV_CRON_HOUR,
        minute=NAV_CRON_MINUTE,
        id="update_navs",
    )
    scheduler.start()
    logger.info("排程已啟動（郵件每 %d 小時 → 淨值每天 %02d:%02d）", FETCH_INTERVAL_HOURS, NAV_CRON_HOUR, NAV_CRON_MINUTE)

    server = HTTPServer(("0.0.0.0", EXPORTER_PORT), Handler)
    logger.info("HTTP server listening on port %d", EXPORTER_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
