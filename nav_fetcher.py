import logging
import re
import warnings

import httpx
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore", message=".*SSL.*", category=UserWarning)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.moneydj.com/funddj/ya/yFundSearch.djhtm"
NAV_URL_T = "https://www.moneydj.com/funddj/ya/yp010000.djhtm?a={code}"


def _get_client() -> httpx.Client:
    return httpx.Client(timeout=15.0, follow_redirects=True, verify=False)


def _search(name: str) -> tuple[str, str] | None:
    params = {"a": name, "B": 1, "C": 1, "D": "T", "ff": 1}
    client = _get_client()
    try:
        resp = client.get(SEARCH_URL, params=params)
        resp.encoding = "big5"
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_="t01")
        if not table:
            return None

        for row in table.find_all("tr")[1:]:
            link = row.find("a")
            if link:
                link_text = link.text.strip()
                href = link.get("href", "")
                m = re.search(r"\?a=([A-Z0-9]+)", href)
                if m:
                    code = m.group(1)
                    if name in link_text or link_text in name:
                        return (link_text, code)

        first_link = table.find("a")
        if first_link:
            m = re.search(r"\?a=([A-Z0-9]+)", first_link.get("href", ""))
            if m:
                return (first_link.text.strip(), m.group(1))
    except Exception as e:
        logger.warning("搜尋失敗 %s: %s", name, e)
        return None
    finally:
        client.close()
    return None


def search_fund_code(fund_name: str) -> str | None:
    candidates = [fund_name]
    stripped = re.sub(r"[-—－][A-Ba-f]?類型.*$", "", fund_name).strip()
    if stripped != fund_name:
        candidates.append(stripped)
    candidates.append(re.sub(r"\s*基金.*$", "", fund_name))

    seen = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        r = _search(c)
        if r:
            return r[1]
    return None


def search_suggestions(query: str, max_results: int = 8) -> list[dict]:
    params = {"a": query, "B": 1, "C": 1, "D": "T", "ff": 1}
    client = _get_client()
    try:
        resp = client.get(SEARCH_URL, params=params)
        resp.encoding = "big5"
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_="t01")
        if not table:
            return []

        results = []
        for row in table.find_all("tr")[1:]:
            link = row.find("a")
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"\?a=([A-Z0-9]+)", href)
            if not m:
                continue
            name = link.text.strip()
            code = m.group(1)
            if query.lower() in name.lower():
                results.append({"name": name, "code": code})
            if len(results) >= max_results:
                break

        if not results:
            link = table.find("a")
            if link:
                m = re.search(r"\?a=([A-Z0-9]+)", link.get("href", ""))
                if m:
                    results.append({"name": link.text.strip(), "code": m.group(1)})

        return results
    except Exception as e:
        logger.warning("搜尋建議失敗 %s: %s", query, e)
        return []
    finally:
        client.close()


def fetch_nav(fund_code: str) -> tuple[str, float] | None:
    url = NAV_URL_T.format(code=fund_code.lower())
    client = _get_client()
    try:
        resp = client.get(url)
        resp.encoding = "big5"
        soup = BeautifulSoup(resp.text, "lxml")

        table = soup.find("table", class_="t01")
        if not table:
            logger.warning("找不到淨值表格 (code=%s)", fund_code)
            return None

        rows = table.find_all("tr")
        if len(rows) < 2:
            return None

        cells = rows[1].find_all("td")
        if len(cells) < 2:
            return None

        date_str = cells[0].text.strip()
        nav_str = cells[1].text.strip()
        nav = float(nav_str)
        return (date_str, nav)

    except Exception as e:
        logger.warning("擷取淨值失敗 (code=%s): %s", fund_code, e)
        return None
    finally:
        client.close()
