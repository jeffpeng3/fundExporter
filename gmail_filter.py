import email
import imaplib
import os
import re
from datetime import datetime


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
        return text_content or "(無內容)"
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload is None:
            return "(無內容)"
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if ct == "text/plain":
            return decoded
        elif ct == "text/html":
            return strip_html(decoded)
        return "(無內容)"


def format_date(date_str):
    if not date_str:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str


def quote_folder(name):
    return f'"{name}"'
