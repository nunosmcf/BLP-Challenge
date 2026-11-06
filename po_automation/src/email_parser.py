"""Parse .eml files into structured data.

Handles:
  - Plain text emails
  - multipart/mixed emails with real base64-encoded PDF attachments
  - Text references like "[Attachment: filename.pdf]" that point to quotes/
"""
import base64
import email
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass
class ParsedEmail:
    subject: str
    sender: str
    sender_email: str
    body: str
    attachments: list[tuple[str, bytes]] = field(default_factory=list)
    # (filename, raw_bytes)


def parse_eml(path: str | Path) -> ParsedEmail:
    path = Path(path)
    with open(path, "rb") as fh:
        msg = email.message_from_bytes(fh.read())

    subject = msg.get("Subject", "")
    from_header = msg.get("From", "")
    sender_email = _extract_email(from_header)
    sender_name = _extract_name(from_header)

    body_parts: list[str] = []
    attachments: list[tuple[str, bytes]] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")

            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_parts.append(part.get_payload(decode=True).decode(charset, errors="replace"))
                except Exception:
                    pass
            elif ct == "application/pdf" or "attachment" in disp:
                fname = part.get_filename() or "attachment.pdf"
                data = part.get_payload(decode=True)
                if data:
                    attachments.append((fname, data))
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            body_parts.append(payload.decode(charset, errors="replace"))

    body = "\n".join(body_parts).strip()

    # Resolve text-style references: [Attachment: filename.pdf]
    for ref_name in re.findall(r"\[Attachment:\s*([^\]]+)\]", body, re.IGNORECASE):
        ref_name = ref_name.strip()
        already = {fname for fname, _ in attachments}
        if ref_name not in already:
            resolved = _find_quote(ref_name)
            if resolved:
                attachments.append((ref_name, resolved.read_bytes()))

    return ParsedEmail(
        subject=subject,
        sender=sender_name,
        sender_email=sender_email,
        body=body,
        attachments=attachments,
    )


def _extract_email(header: str) -> str:
    m = re.search(r"<([^>]+)>", header)
    if m:
        return m.group(1).strip().lower()
    return header.strip().lower()


def _extract_name(header: str) -> str:
    m = re.match(r"^(.+?)\s*<", header)
    if m:
        return m.group(1).strip().strip('"')
    return _extract_email(header)


def _find_quote(filename: str) -> Path | None:
    target = config.QUOTES_DIR / filename
    if target.exists():
        return target
    # Case-insensitive search
    for p in config.QUOTES_DIR.iterdir():
        if p.name.lower() == filename.lower():
            return p
    return None
