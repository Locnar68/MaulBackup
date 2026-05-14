#!/usr/bin/env python3
r"""
MichaelMaul Backup
==================
One button: "my USB is plugged in - go".

When you run it (via the desktop button or `python maulbackup.py --cli`) it:
  1. Connects to Gmail (sarahpepe68@gmail.com) over IMAP.
  2. Finds every email from michael m <2excelon4@gmail.com> that hasn't been
     backed up yet.
  3. For each new email, writes to the USB drive:
        - a readable PDF                 (USB\MichaelMaul Backup\Saved as PDF)
        - a plain-text copy with header  (\Saved as Text)
        - any attachments                (\Attachments)
  4. Uploads each PDF to the Google Drive folder "MichaelMaul".
  5. Records what it did so re-runs only pick up new mail.

Email -> [button] -> USB (PDF / text / attachments) + Google Drive (PDFs)

Videos are NOT handled here - Sarah copies those onto the USB manually.
The Gmail -> Yahoo -> MichaelMaul forwarding is set up once on the provider
side (see SETUP-CHECKLIST.md); this tool does not depend on it.

Configuration lives in config.json next to this file.
Google auth lives in credentials.json + token.json next to this file.
"""

import argparse
import email
import email.utils
import html
import imaplib
import json
import os
import re
import sys
import string
from datetime import datetime
from email.header import decode_header
from pathlib import Path

# --- third-party deps, with friendly messages if missing --------------------
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependency 'beautifulsoup4'. Run install.bat first.")
    sys.exit(1)

try:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
except ImportError:
    print("Missing dependency 'reportlab'. Run install.bat first.")
    sys.exit(1)

# Google libs are needed only when Drive upload is enabled; imported lazily in
# the Drive section so the email/USB half still works without them.

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
STATE_FILENAME = ".backup_state.json"
USB_MARKER_FILENAME = ".maulbackup_usb"   # optional marker for auto-detect

SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_PATH = SCRIPT_DIR / "token.json"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
# Minimal scope: the app can only touch files it creates itself.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ===========================================================================
# Logging helper - prints to console AND to an optional GUI callback
# ===========================================================================
class Log:
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback

    def __call__(self, msg=""):
        print(msg)
        if self.gui_callback:
            self.gui_callback(msg)


# ===========================================================================
# Configuration
# ===========================================================================
def load_config(path, log):
    if not os.path.exists(path):
        log(f"Could not find config file: {path}")
        log("Copy config.example.json to config.json, fill it in, and retry.")
        log("(install.bat does this for you.)")
        raise SystemExit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # source_mailboxes is the new (list) form. Accept the old single
    # "source_mailbox" string too, so existing configs keep working.
    if "source_mailboxes" not in cfg:
        legacy = cfg.get("source_mailbox")
        if isinstance(legacy, str) and legacy.strip():
            cfg["source_mailboxes"] = [legacy.strip()]
        else:
            cfg["source_mailboxes"] = ["INBOX", "Michael Maul",
                                       "Michael Maul After 4/26"]
    if isinstance(cfg["source_mailboxes"], str):
        cfg["source_mailboxes"] = [cfg["source_mailboxes"]]
    cfg.setdefault("usb_label", "MichaelMaul Backup")
    cfg.setdefault("usb_path", "")
    cfg.setdefault("drive_folder_name", "MichaelMaul")
    cfg.setdefault("drive_folder_id", "")
    cfg.setdefault("upload_to_drive", True)

    required = ["gmail_address", "gmail_app_password", "sender_filter"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        log(f"config.json is missing values for: {', '.join(missing)}")
        raise SystemExit(1)
    return cfg


# ===========================================================================
# Small helpers
# ===========================================================================
def sanitize_filename(text, max_len=120):
    """Make a string safe for a Windows/Mac filename."""
    text = text or "no-subject"
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".")
    return (text or "no-subject")[:max_len]


def decode_mime(value):
    """Decode an RFC2047-encoded header (subjects, names) into plain text."""
    if not value:
        return ""
    parts = []
    for chunk, enc in decode_header(value):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def get_email_date(msg):
    """Return a datetime for the message, falling back to 'now'."""
    raw = msg.get("Date")
    if raw:
        try:
            dt = email.utils.parsedate_to_datetime(raw)
            if dt is not None:
                return dt
        except (TypeError, ValueError):
            pass
    return datetime.now()


def get_body_text(msg):
    """Extract a readable plain-text body, converting HTML if needed."""
    plain, html_body = [], []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain":
                plain.append(_decode_part(part))
            elif ctype == "text/html":
                html_body.append(_decode_part(part))
    else:
        if msg.get_content_type() == "text/html":
            html_body.append(_decode_part(msg))
        else:
            plain.append(_decode_part(msg))

    if any(p.strip() for p in plain):
        return "\n".join(plain).strip()
    if html_body:
        soup = BeautifulSoup("\n".join(html_body), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n").strip()
    return "(This email had no readable text body.)"


def _decode_part(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def list_attachments(msg):
    """Return a list of (filename, bytes) for real attachments."""
    out = []
    if not msg.is_multipart():
        return out
    seen = 0
    for part in msg.walk():
        disp = part.get_content_disposition()
        filename = part.get_filename()
        if disp == "attachment" or (filename and disp != "inline"):
            seen += 1
            name = decode_mime(filename) if filename else f"attachment-{seen}"
            data = part.get_payload(decode=True)
            if data:
                out.append((sanitize_filename(name), data))
    return out


# ===========================================================================
# USB drive detection
# ===========================================================================
def find_usb_path(cfg, log):
    """Work out where to write the backup.

    Priority:
      1. cfg['usb_path'] if set and the drive exists.
      2. Any drive whose root contains a USB_MARKER_FILENAME file.
      3. Any drive that already has the backup folder on it.
      4. None -> caller reports "plug in the USB drive".
    """
    label = cfg["usb_label"]

    # 1. Explicit path from config.
    configured = cfg.get("usb_path", "").strip()
    if configured:
        root = Path(configured)
        if root.exists():
            return root / label
        log(f"Configured USB path '{configured}' is not available right now.")

    # 2 + 3. Scan drive letters (Windows) / mount points (mac/Linux).
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:\\")
            try:
                if root.exists() and (root / USB_MARKER_FILENAME).exists():
                    return root / label
            except OSError:
                continue
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:\\")
            try:
                if root.exists() and (root / label).exists():
                    return root / label
            except OSError:
                continue
    else:
        bases = ["/Volumes", "/media", f"/media/{os.getenv('USER', '')}",
                 "/run/media"]
        for base in bases:
            b = Path(base)
            if not b.exists():
                continue
            try:
                for mount in b.iterdir():
                    if (mount / USB_MARKER_FILENAME).exists():
                        return mount / label
                    if (mount / label).exists():
                        return mount / label
            except OSError:
                continue

    return None


def ensure_usb_folders(base_path):
    base = Path(base_path)
    subfolders = {
        "pdf": base / "Saved as PDF",
        "text": base / "Saved as Text",
        "attachments": base / "Attachments",
        "videos": base / "Videos",   # created for Sarah's manual video copies
    }
    for folder in [base, *subfolders.values()]:
        folder.mkdir(parents=True, exist_ok=True)
    return subfolders


# ===========================================================================
# Saving to disk
# ===========================================================================
def build_header_block(msg, to_addr, has_attachments):
    return (
        f"From: {decode_mime(msg.get('From'))}\n"
        f"To: {to_addr}\n"
        f"Date: {decode_mime(msg.get('Date'))}\n"
        f"Subject: {decode_mime(msg.get('Subject'))}\n"
        f"Attachments saved separately: {'Yes' if has_attachments else 'No'}\n"
        f"Notes: \n"
        f"{'-' * 60}\n"
    )


def save_as_text(folder, filename, header_block, body):
    path = Path(folder) / f"{filename}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header_block)
        f.write("\n")
        f.write(body)
        f.write("\n")
    return path


def save_as_pdf(folder, filename, header_lines, body):
    path = Path(folder) / f"{filename}.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    )
    styles = getSampleStyleSheet()
    head_style = ParagraphStyle(
        "Head", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=13, textColor="#222222",
    )
    label_style = ParagraphStyle(
        "Label", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=13, textColor="#444444",
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, alignment=TA_LEFT,
    )

    story = [Paragraph("MichaelMaul Backup", head_style), Spacer(1, 6)]
    for line in header_lines:
        story.append(Paragraph(html.escape(line), label_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("_" * 80, label_style))
    story.append(Spacer(1, 10))

    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        while len(block) > 3000:
            chunk, block = block[:3000], block[3000:]
            story.append(Paragraph(_pdf_escape(chunk), body_style))
        story.append(Paragraph(_pdf_escape(block), body_style))
        story.append(Spacer(1, 8))

    doc.build(story)
    return path


def _pdf_escape(text):
    return html.escape(text).replace("\n", "<br/>")


def save_attachments(folder, base_filename, attachments):
    saved = []
    for idx, (name, data) in enumerate(attachments, start=1):
        target = Path(folder) / f"{base_filename} - {name}"
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = Path(folder) / f"{stem} ({idx}){suffix}"
        with open(target, "wb") as f:
            f.write(data)
        saved.append(target)
    return saved


# ===========================================================================
# State tracking (so re-runs only fetch new mail) - stored on the USB drive
# ===========================================================================
def load_state(base_path):
    path = Path(base_path) / STATE_FILENAME
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f).get("processed_message_ids", []))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_state(base_path, processed_ids):
    path = Path(base_path) / STATE_FILENAME
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"processed_message_ids": sorted(processed_ids),
             "last_run": datetime.now().isoformat(timespec="seconds")},
            f, indent=2,
        )


# ===========================================================================
# Gmail (IMAP)
# ===========================================================================
def connect_gmail(cfg, log):
    log(f"Connecting to Gmail as {cfg['gmail_address']} ...")
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        conn.login(cfg["gmail_address"], cfg["gmail_app_password"])
    except imaplib.IMAP4.error as e:
        log("")
        log("Gmail login failed. The usual cause is the password field:")
        log("  Gmail needs an APP PASSWORD here, not the normal password.")
        log("  Generate one at myaccount.google.com -> Security -> App passwords,")
        log("  and make sure IMAP is enabled in Gmail settings.")
        log(f"  (technical detail: {e})")
        raise SystemExit(1)
    except OSError as e:
        log(f"\nCould not reach Gmail. Check the internet connection.\n({e})")
        raise SystemExit(1)
    log("Connected to Gmail.")
    return conn


def _selectable_mailboxes(conn):
    """Return the set of mailbox names the server says we CAN select.

    Gmail marks phantom parent folders (created by a '/' in a label name)
    with \\Noselect - trying to open those fails. This lets us skip them.
    """
    selectable = set()
    try:
        typ, boxes = conn.list()
        if typ == "OK" and boxes:
            for entry in boxes:
                line = entry.decode(errors="replace") \
                    if isinstance(entry, bytes) else entry
                m = re.search(r'"([^"]*)"\s*$', line)
                if not m:
                    continue
                name = m.group(1)
                if "\\Noselect" in line:
                    continue
                selectable.add(name)
    except Exception:
        pass
    return selectable


def _select_mailbox(conn, mailbox):
    """Try to select one mailbox. Returns True on success, False otherwise.

    Names with spaces must be sent quoted; an unquoted name makes Gmail
    return BAD, which imaplib raises - so each attempt is wrapped.
    """
    raw = mailbox.strip().strip('"')
    for name in (f'"{raw}"', raw):
        try:
            typ, _ = conn.select(name, readonly=True)
            if typ == "OK":
                return True
        except imaplib.IMAP4.error:
            continue
    return False


def search_senders(conn, mailboxes, sender, log):
    """Search every configured mailbox for mail from `sender`.

    Returns a list of (mailbox, uid) pairs. Mailboxes that can't be opened
    are reported and skipped rather than aborting the whole run.
    """
    selectable = _selectable_mailboxes(conn)
    results = []
    opened_any = False

    for mailbox in mailboxes:
        target = mailbox.strip().strip('"')
        # Warn (but still try) if the server's list didn't show it as selectable.
        if selectable and target not in selectable:
            log(f"Note: '{target}' is not in the selectable folder list - "
                f"trying anyway.")
        if not _select_mailbox(conn, target):
            log(f"Could not open mailbox '{target}' - skipping it.")
            continue
        opened_any = True
        typ, data = conn.uid("search", None, f'(FROM "{sender}")')
        if typ != "OK" or not data or not data[0]:
            log(f"  '{target}': 0 message(s) from {sender}.")
            continue
        uids = data[0].split()
        log(f"  '{target}': {len(uids)} message(s) from {sender}.")
        for uid in uids:
            results.append((target, uid))

    if not opened_any:
        log("None of the configured mailboxes could be opened.")
        log("Check 'source_mailboxes' in config.json against the label names")
        log("shown in Gmail. Run this to list them:")
        log('  python -c "import imaplib,json; '
            "c=json.load(open('config.json')); "
            "m=imaplib.IMAP4_SSL('imap.gmail.com',993); "
            "m.login(c['gmail_address'],c['gmail_app_password']); "
            '[print(x) for x in m.list()[1]]; m.logout()"')
        raise SystemExit(1)

    return results


# ===========================================================================
# Google Drive
# ===========================================================================
def get_drive_service(log):
    """Build an authenticated Drive service from token.json / credentials.json.

    install.py is expected to have already produced token.json. If it hasn't,
    this attempts the browser sign-in as a fallback. Any failure here is
    non-fatal - the caller continues with the USB backup only.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        log("Google libraries are not installed - run install.bat.")
        log("Skipping the Google Drive upload for this run.")
        return None

    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH),
                                                          DRIVE_SCOPES)
        except (ValueError, OSError):
            creds = None

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            log(f"Could not refresh the Google sign-in: {e}")
            creds = None

    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            log("Google Drive upload is enabled but credentials.json is missing.")
            log("See SETUP-CHECKLIST.md to create it, or re-run install.bat.")
            log("Skipping the Drive upload for this run (USB backup still ran).")
            return None
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            log(f"Google sign-in failed: {e}")
            log("Skipping the Drive upload for this run.")
            return None

    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"Could not start the Google Drive service: {e}")
        return None


def ensure_drive_folder(service, cfg, log):
    """Return the Drive folder ID for the MichaelMaul folder.

    Uses cfg['drive_folder_id'] if present; otherwise searches by name; finally
    creates it. The resolved id is written back into config.json so the next
    run is instant.
    """
    folder_id = cfg.get("drive_folder_id", "").strip()
    if folder_id:
        return folder_id

    name = cfg["drive_folder_name"]
    safe_name = name.replace("'", "\\'")
    query = ("mimeType='application/vnd.google-apps.folder' and trashed=false "
             f"and name='{safe_name}'")
    try:
        resp = service.files().list(q=query, spaces="drive",
                                    fields="files(id,name)").execute()
        files = resp.get("files", [])
        if files:
            folder_id = files[0]["id"]
            log(f"Found Google Drive folder '{name}'.")
        else:
            meta = {"name": name,
                    "mimeType": "application/vnd.google-apps.folder"}
            folder = service.files().create(body=meta, fields="id").execute()
            folder_id = folder["id"]
            log(f"Created Google Drive folder '{name}'.")
    except Exception as e:
        log(f"Could not find or create the Drive folder: {e}")
        return None

    # Persist the id back to config.json so we don't search again next time.
    try:
        cfg["drive_folder_id"] = folder_id
        cfg_path = SCRIPT_DIR / "config.json"
        if cfg_path.exists():
            disk = json.loads(cfg_path.read_text(encoding="utf-8"))
            disk["drive_folder_id"] = folder_id
            cfg_path.write_text(json.dumps(disk, indent=2), encoding="utf-8")
    except Exception:
        pass  # not fatal - we still have the id for this run
    return folder_id


def upload_pdf_to_drive(service, folder_id, pdf_path, log):
    """Upload one PDF into the Drive folder. Returns True on success."""
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return False
    try:
        meta = {"name": Path(pdf_path).name, "parents": [folder_id]}
        media = MediaFileUpload(str(pdf_path), mimetype="application/pdf",
                                resumable=False)
        service.files().create(body=meta, media_body=media,
                               fields="id").execute()
        return True
    except Exception as e:
        log(f"  ! Drive upload failed for {Path(pdf_path).name}: {e}")
        return False


# ===========================================================================
# The actual backup run
# ===========================================================================
def run_backup(config_path=None, gui_callback=None, dry_run=False):
    """Run one full backup. Returns a summary dict. Safe to call from a GUI."""
    log = Log(gui_callback)
    config_path = config_path or str(SCRIPT_DIR / "config.json")
    cfg = load_config(config_path, log)

    log("=" * 60)
    log("  MichaelMaul Backup")
    if dry_run:
        log("  *** DRY RUN - nothing will be saved or uploaded ***")
    log("=" * 60)

    # --- locate the USB drive ----------------------------------------------
    usb_path = find_usb_path(cfg, log)
    if usb_path is None:
        log("")
        log("Could not find the USB drive.")
        log("Plug it in and press the button again.")
        log("(Tip: a file named '.maulbackup_usb' on the drive root makes it")
        log(" auto-detect; install.py can place this for you.)")
        return {"ok": False, "reason": "no_usb"}

    folders = ensure_usb_folders(usb_path)
    processed = load_state(usb_path)
    log(f"USB backup folder: {usb_path}")
    log(f"Already backed up previously: {len(processed)} message(s)")

    # --- connect to Gmail ---------------------------------------------------
    conn = connect_gmail(cfg, log)

    # --- set up Google Drive (optional; failure is non-fatal) --------------
    drive_service = None
    drive_folder_id = None
    if cfg["upload_to_drive"] and not dry_run:
        drive_service = get_drive_service(log)
        if drive_service:
            drive_folder_id = ensure_drive_folder(drive_service, cfg, log)
        if not drive_folder_id:
            log("Continuing without Drive upload - the USB backup still runs.")
            drive_service = None

    new_count = saved_pdf = saved_txt = saved_att = uploaded = 0

    try:
        log(f"\nSearching mailboxes: "
            f"{', '.join(cfg['source_mailboxes'])}")
        hits = search_senders(conn, cfg["source_mailboxes"],
                              cfg["sender_filter"], log)
        log(f"Total: {len(hits)} message(s) from {cfg['sender_filter']} "
            f"across all mailboxes.")

        current_mailbox = None
        seen_keys = set()  # de-dupe within this run (same mail under 2 labels)

        for mailbox, uid in hits:
            # Re-select the mailbox when it changes - UIDs are per-mailbox.
            if mailbox != current_mailbox:
                if not _select_mailbox(conn, mailbox):
                    log(f"Could not re-open '{mailbox}' - skipping its mail.")
                    current_mailbox = None
                    continue
                current_mailbox = mailbox

            typ, msg_data = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            message_id = (msg.get("Message-ID") or "").strip()
            key = message_id or f"{mailbox}:uid:{uid.decode()}"
            if key in processed or key in seen_keys:
                continue
            seen_keys.add(key)
            new_count += 1

            subject = decode_mime(msg.get("Subject")) or "no-subject"
            date = get_email_date(msg)
            date_str = date.strftime("%Y-%m-%d")
            sender_tag = cfg["sender_filter"].split("@")[0]
            base_name = sanitize_filename(
                f"{date_str} - {sender_tag} - {subject}")

            attachments = list_attachments(msg)
            body = get_body_text(msg)
            header_lines = [
                f"From: {decode_mime(msg.get('From'))}",
                f"To: {cfg['gmail_address']}",
                f"Date: {decode_mime(msg.get('Date'))}",
                f"Subject: {subject}",
                f"Attachments saved separately: "
                f"{'Yes' if attachments else 'No'}",
            ]

            log(f"  + {base_name}")
            if dry_run:
                if attachments:
                    log(f"      ({len(attachments)} attachment(s) "
                        f"would be saved)")
                continue

            pdf_path = save_as_pdf(folders["pdf"], base_name,
                                   header_lines, body)
            saved_pdf += 1
            save_as_text(folders["text"], base_name,
                         build_header_block(msg, cfg["gmail_address"],
                                            bool(attachments)),
                         body)
            saved_txt += 1
            if attachments:
                files = save_attachments(folders["attachments"],
                                         base_name, attachments)
                saved_att += len(files)

            if drive_service and drive_folder_id:
                if upload_pdf_to_drive(drive_service, drive_folder_id,
                                       pdf_path, log):
                    uploaded += 1

            processed.add(key)

        if not dry_run:
            save_state(usb_path, processed)

    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # --- summary ------------------------------------------------------------
    log("\n" + "-" * 60)
    if dry_run:
        log(f"Dry run complete. {new_count} new message(s) would be "
            f"backed up.")
    else:
        log("Backup complete.")
        log(f"  New messages backed up   : {new_count}")
        log(f"  PDFs saved to USB        : {saved_pdf}")
        log(f"  Text files saved to USB  : {saved_txt}")
        log(f"  Attachments saved to USB : {saved_att}")
        log(f"  PDFs uploaded to Drive   : {uploaded}")
        log(f"  USB location             : {usb_path}")
        if cfg["upload_to_drive"] and not drive_service:
            log("  (Google Drive upload was skipped - see messages above.)")
    log("-" * 60)

    return {
        "ok": True, "new": new_count, "pdf": saved_pdf, "text": saved_txt,
        "attachments": saved_att, "uploaded": uploaded, "usb": str(usb_path),
        "drive_ok": bool(drive_service),
    }


# ===========================================================================
# GUI - the desktop button
# ===========================================================================
def run_gui():
    """Small tkinter window: status line, one big Export button, a log area."""
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        print("tkinter is not available; running in CLI mode instead.")
        run_backup()
        return

    import threading

    root = tk.Tk()
    root.title("MichaelMaul Backup")
    root.geometry("620x460")
    root.minsize(520, 380)

    header = tk.Label(root, text="MichaelMaul Backup",
                      font=("Segoe UI", 16, "bold"))
    header.pack(pady=(14, 2))

    status = tk.Label(root, text="Checking for the USB drive ...",
                      font=("Segoe UI", 10))
    status.pack(pady=(0, 8))

    btn = tk.Button(root, text="Export Now", font=("Segoe UI", 13, "bold"),
                    width=20, height=2, state="disabled")
    btn.pack(pady=(0, 10))

    log_box = scrolledtext.ScrolledText(root, height=14, width=72,
                                        font=("Consolas", 9), state="disabled")
    log_box.pack(padx=12, pady=(0, 12), fill="both", expand=True)

    def gui_log(msg):
        log_box.configure(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")
        root.update_idletasks()

    def refresh_status():
        """Check for the USB drive and update the status line."""
        try:
            cfg = load_config(str(SCRIPT_DIR / "config.json"), Log(None))
            usb = find_usb_path(cfg, Log(None))
        except SystemExit:
            status.config(text="config.json problem - re-run install.bat",
                          fg="#a32d2d")
            btn.config(state="disabled")
            return
        if usb is not None:
            status.config(text=f"USB drive detected: {usb}", fg="#0f6e56")
        else:
            status.config(text="Plug in the USB drive, then click below.",
                          fg="#854f0b")
        btn.config(state="normal")

    def do_backup():
        btn.config(state="disabled", text="Working ...")
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        log_box.configure(state="disabled")

        def worker():
            try:
                result = run_backup(gui_callback=gui_log)
            except SystemExit:
                result = {"ok": False, "reason": "config"}
            except Exception as e:
                gui_log(f"\nUnexpected error: {e}")
                result = {"ok": False, "reason": "error"}

            def finish():
                if result.get("ok"):
                    status.config(
                        text=f"Done - {result.get('new', 0)} new email(s) "
                             f"backed up.", fg="#0f6e56")
                elif result.get("reason") == "no_usb":
                    status.config(text="No USB drive found - plug it in.",
                                  fg="#854f0b")
                else:
                    status.config(text="Finished with problems - see log.",
                                  fg="#a32d2d")
                btn.config(state="normal", text="Export Now")
                refresh_status()

            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    btn.config(command=do_backup)
    refresh_status()

    # Re-check for the USB drive every few seconds while idle.
    def poll():
        if btn["text"] == "Export Now":
            refresh_status()
        root.after(4000, poll)
    root.after(4000, poll)

    root.mainloop()


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(
        description="MichaelMaul Backup - Gmail to USB + Google Drive")
    parser.add_argument("--cli", action="store_true",
                        help="Run in the terminal with no window")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen; write/upload nothing")
    args = parser.parse_args()

    if args.cli or args.dry_run:
        try:
            run_backup(config_path=args.config, dry_run=args.dry_run)
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 1)
    else:
        run_gui()


if __name__ == "__main__":
    main()
