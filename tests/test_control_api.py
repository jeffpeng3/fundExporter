import io
import threading
from unittest.mock import patch

import fund_exporter as fe


class StubHandler(fe.Handler):
    def __init__(self, path: str = "/", body: bytes = b"{}"):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {}
        self.wfile = io.BytesIO()
        self._status = None

    def send_response(self, code, message=None):
        self._status = code

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass


def body_json(handler) -> dict:
    import json
    return json.loads(handler.wfile.getvalue().decode())


def test_run_action_runs_in_background():
    fe.actions.clear()
    done = threading.Event()

    def work():
        done.set()

    started = fe._run_action("test_action", work)
    assert started is True
    assert done.wait(timeout=2) is True
    assert fe.actions["test_action"]["running"] is False
    assert fe.actions["test_action"]["last_ok"] is True


def test_run_action_dedupe_while_running():
    fe.actions.clear()
    release = threading.Event()

    def work():
        release.wait()

    fe._run_action("blocked", work)
    try:
        started = fe._run_action("blocked", work)
        assert started is False
        assert fe.actions["blocked"]["running"] is True
    finally:
        release.set()


def test_run_action_records_failure():
    fe.actions.clear()

    def work():
        raise RuntimeError("boom")

    fe._run_action("failing", work)
    for _ in range(100):
        with fe.actions_lock:
            running = fe.actions.get("failing", {}).get("running")
        if not running:
            break
        threading.Event().wait(0.05)
    assert fe.actions["failing"]["running"] is False
    assert fe.actions["failing"]["last_ok"] is False
    assert fe.actions["failing"]["last_detail"] == "boom"


def test_status_endpoint_returns_actions():
    fe.actions.clear()
    fe._mark_action("sync_gist", True)
    handler = StubHandler("/api/status")
    handler.do_GET()
    payload = body_json(handler)
    assert handler._status == 200
    assert "actions" in payload
    assert "sync_gist" in payload["actions"]
    assert payload["actions"]["sync_gist"]["last_ok"] is True
    assert "holdings_count" in payload
    assert "processed_uids" in payload


def test_post_refresh_triggers_update_navs():
    with patch.object(fe, "_run_action", return_value=True) as mock_run:
        handler = StubHandler("/api/refresh")
        handler.do_POST()
        payload = body_json(handler)
    assert handler._status == 200
    assert payload["ok"] is True
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == "refresh_navs"
    assert mock_run.call_args.args[1] is fe.update_navs


def test_daily_job_refreshes_navs_and_marks_success():
    fe.actions.clear()
    with patch.object(fe, "_run_action", return_value=True) as mock_run, \
         patch.object(fe, "update_navs") as mock_nav:
        fe.daily_job()
    mock_nav.assert_called_once()
    mock_run.assert_called_once_with("fetch_emails", fe.fetch_new_emails)
    with fe.actions_lock:
        assert fe.actions["refresh_navs"]["last_ok"] is True
        assert fe.actions["refresh_navs"]["last_detail"] == "每日排程"


def test_daily_job_records_nav_failure():
    fe.actions.clear()
    with patch.object(fe, "_run_action", return_value=True) as mock_run, \
         patch.object(fe, "update_navs", side_effect=RuntimeError("boom")):
        fe.daily_job()
    mock_run.assert_called_once_with("fetch_emails", fe.fetch_new_emails)
    with fe.actions_lock:
        assert fe.actions["refresh_navs"]["last_ok"] is False
        assert fe.actions["refresh_navs"]["last_detail"] == "boom"


def test_post_fetch_emails_triggers_fetch():
    with patch.object(fe, "_run_action", return_value=True) as mock_run:
        handler = StubHandler("/api/fetch-emails")
        handler.do_POST()
        payload = body_json(handler)
    assert handler._status == 200
    assert payload["ok"] is True
    assert mock_run.call_args.args[0] == "fetch_emails"
    assert mock_run.call_args.args[1] is fe.fetch_new_emails


def test_post_sync_gist_triggers_sync():
    with patch.object(fe, "_run_action", return_value=True) as mock_run:
        handler = StubHandler("/api/sync-gist")
        handler.do_POST()
        payload = body_json(handler)
    assert handler._status == 200
    assert payload["ok"] is True
    assert mock_run.call_args.args[0] == "sync_gist"
    assert mock_run.call_args.args[1] is fe._sync_gist


def test_post_reload_gist_triggers_init():
    with patch.object(fe, "_run_action", return_value=True) as mock_run:
        handler = StubHandler("/api/reload-gist")
        handler.do_POST()
        payload = body_json(handler)
    assert handler._status == 200
    assert payload["ok"] is True
    assert mock_run.call_args.args[0] == "reload_gist"
    assert mock_run.call_args.args[1] is fe.init_from_gist