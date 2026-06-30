import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

GIST_API = "https://api.github.com/gists/{gist_id}"


def _gist_id() -> str:
    gid = os.environ.get("GIST_ID")
    if not gid:
        raise RuntimeError("GIST_ID 環境變數未設定")
    return gid


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 環境變數未設定")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _get() -> dict:
    resp = httpx.get(
        GIST_API.format(gist_id=_gist_id()),
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _patch(files: dict):
    resp = httpx.patch(
        GIST_API.format(gist_id=_gist_id()),
        headers=_headers(),
        json={"files": files},
        timeout=15,
    )
    resp.raise_for_status()


def _parse_file(data: dict, filename: str) -> dict:
    files = data.get("files", {})
    content = files.get(filename, {}).get("content", "{}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("%s 不是合法的 JSON，回傳空 dict", filename)
        return {}


def load() -> tuple[dict, dict]:
    data = _get()
    holdings = _parse_file(data, "holdings.json")
    mapping = _parse_file(data, "fund_mapping.json")
    logger.info("已從 Gist 載入 %d 筆持倉、%d 筆對照", len(holdings), len(mapping))
    return holdings, mapping


def load_processed_uids() -> set[str]:
    data = _get()
    raw = _parse_file(data, "processed_uids.json")
    uids = set(raw.get("uids", []))
    logger.info("已從 Gist 載入 %d 筆已處理 UID", len(uids))
    return uids


def save_all(holdings: dict, mapping: dict, processed_uids: set[str]):
    _patch({
        "holdings.json": {"content": json.dumps(holdings, ensure_ascii=False, indent=2)},
        "fund_mapping.json": {"content": json.dumps(mapping, ensure_ascii=False, indent=2)},
        "processed_uids.json": {"content": json.dumps({"uids": sorted(processed_uids)}, ensure_ascii=False, indent=2)},
    })
    logger.info("已同步 3 個檔案至 Gist")
