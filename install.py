#!/usr/bin/env python3
r"""
MichaelMaul Backup - Installer
==============================
Run this once on Sarah's laptop (double-click install.bat, which calls this).

It does everything that CAN be automated:
  1. Installs the required Python libraries.
  2. Asks a few questions and writes config.json.
  3. Runs the Google sign-in (one browser click) -> saves token.json,
     then finds or creates the Google Drive "MichaelMaul" folder.
  4. Drops a ".maulbackup_usb" marker on the USB drive so the tool can
     auto-detect it.
  5. Creates the "MichaelMaul Backup" shortcut on the Desktop.

What it CANNOT do (these are one-time manual steps - see SETUP-CHECKLIST.md):
  - Generate the Gmail app password (Google requires a human).
  - Create the Google Cloud OAuth credentials.json (Google requires a human).
  - Set up Gmail -> Yahoo forwarding and the Yahoo MichaelMaul folder.

This script is safe to re-run; it updates rather than duplicates.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
EXAMPLE_PATH = SCRIPT_DIR / "config.example.json"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"
REQUIREMENTS_PATH = SCRIPT_DIR / "requirements.txt"
MAIN_SCRIPT = SCRIPT_DIR / "maulbackup.py"
USB_MARKER_FILENAME = ".maulbackup_usb"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def hr():
    print("-" * 64)


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    answer = input(f"{prompt} ({d}): ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


# ---------------------------------------------------------------------------
# Step 1 - install Python libraries
# ---------------------------------------------------------------------------
def install_dependencies():
    hr()
    print("STEP 1 of 5 - Installing Python libraries")
    hr()
    if not REQUIREMENTS_PATH.exists():
        print(f"  requirements.txt not found at {REQUIREMENTS_PATH}")
        print("  Make sure you're running this from inside the MaulBackup "
              "folder.")
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade",
                        "pip"], check=False)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r",
             str(REQUIREMENTS_PATH)],
            check=False)
        if result.returncode != 0:
            print("\n  pip reported a problem installing the libraries.")
            print("  Make sure Python was installed from python.org with")
            print("  'Add Python to PATH' checked, then run install.bat again.")
            return False
    except Exception as e:
        print(f"  Could not run pip: {e}")
        return False
    print("\n  Libraries installed.")
    return True


# ---------------------------------------------------------------------------
# Step 2 - build config.json
# ---------------------------------------------------------------------------
def build_config():
    hr()
    print("STEP 2 of 5 - Settings (writes config.json)")
    hr()

    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            print("  Found an existing config.json - press Enter to keep "
                  "each value.\n")
        except json.JSONDecodeError:
            cfg = {}
    elif EXAMPLE_PATH.exists():
        try:
            cfg = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        except json.JSONDecodeError:
            cfg = {}

    print("  Gmail is the account the mail arrives in.")
    cfg["gmail_address"] = ask("  Gmail address",
                               cfg.get("gmail_address", "sarahpepe68@gmail.com"))
    print()
    print("  The Gmail APP PASSWORD is the 16-character code from")
    print("  myaccount.google.com -> Security -> App passwords.")
    print("  (This is NOT the normal Gmail password. See SETUP-CHECKLIST.md.)")
    existing_pw = cfg.get("gmail_app_password", "")
    placeholder = "PASTE 16-CHARACTER GMAIL APP PASSWORD HERE"
    if existing_pw and existing_pw != placeholder:
        if not yes_no("  Keep the app password already saved?", True):
            cfg["gmail_app_password"] = ask("  Gmail app password")
    else:
        cfg["gmail_app_password"] = ask("  Gmail app password")
    print()

    cfg["sender_filter"] = ask("  Back up email FROM this sender",
                               cfg.get("sender_filter", "2excelon4@gmail.com"))
    print()

    cfg["usb_label"] = ask("  Folder name to use on the USB drive",
                           cfg.get("usb_label", "MichaelMaul Backup"))
    print("  USB path can be left blank - the tool auto-detects the drive")
    print("  using the marker file this installer drops on it in step 4.")
    cfg["usb_path"] = ask("  USB drive path (optional, e.g. E:\\)",
                          cfg.get("usb_path", ""))
    print()

    cfg["drive_folder_name"] = ask("  Google Drive folder name",
                                   cfg.get("drive_folder_name", "MichaelMaul"))
    cfg.setdefault("drive_folder_id", "")
    cfg["upload_to_drive"] = yes_no("  Upload PDFs to Google Drive?",
                                    cfg.get("upload_to_drive", True))
    cfg.setdefault("source_mailbox", "INBOX")

    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"\n  Saved {CONFIG_PATH}")
    return cfg


# ---------------------------------------------------------------------------
# Step 3 - Google sign-in + Drive folder
# ---------------------------------------------------------------------------
def setup_google(cfg):
    hr()
    print("STEP 3 of 5 - Google sign-in and Drive folder")
    hr()

    if not cfg.get("upload_to_drive", True):
        print("  Drive upload is turned off in the settings - skipping.")
        return

    if not CREDENTIALS_PATH.exists():
        print("  credentials.json is not in this folder yet.")
        print()
        print("  This is the one-time Google Cloud step from SETUP-CHECKLIST.md:")
        print("   - create a Google Cloud project")
        print("   - enable the Google Drive API")
        print("   - create an OAuth client ID (Desktop app)")
        print("   - download it and save it here as:")
        print(f"       {CREDENTIALS_PATH}")
        print()
        print("  Once credentials.json is in place, run install.bat again and")
        print("  this step will finish automatically. Skipping for now.")
        return

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("  Google libraries are not available - did step 1 succeed?")
        return

    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH),
                                                          DRIVE_SCOPES)
        except (ValueError, OSError):
            creds = None

    if creds and creds.valid:
        print("  Already signed in to Google (token.json found).")
    elif creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            print("  Refreshed the existing Google sign-in.")
        except Exception:
            creds = None

    if not creds or not creds.valid:
        print("  A browser window will open - sign in as")
        print(f"    {cfg.get('gmail_address', 'the Gmail account')}")
        print("  and click Allow. Just once; it is remembered after that.")
        input("  Press Enter to open the browser ...")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            print("  Signed in. Saved token.json.")
        except Exception as e:
            print(f"  Google sign-in did not complete: {e}")
            print("  You can run install.bat again to retry.")
            return

    try:
        service = build("drive", "v3", credentials=creds,
                        cache_discovery=False)
        name = cfg.get("drive_folder_name", "MichaelMaul")
        safe_name = name.replace("'", "\\'")
        query = ("mimeType='application/vnd.google-apps.folder' "
                 f"and trashed=false and name='{safe_name}'")
        resp = service.files().list(q=query, spaces="drive",
                                    fields="files(id,name)").execute()
        files = resp.get("files", [])
        if files:
            folder_id = files[0]["id"]
            print(f"  Found the Drive folder '{name}'.")
        else:
            meta = {"name": name,
                    "mimeType": "application/vnd.google-apps.folder"}
            folder = service.files().create(body=meta, fields="id").execute()
            folder_id = folder["id"]
            print(f"  Created the Drive folder '{name}'.")

        cfg["drive_folder_id"] = folder_id
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print(f"  Drive folder link: "
              f"https://drive.google.com/drive/folders/{folder_id}")
        print("  (If you want to share this folder, do that yourself in "
              "Google Drive.)")
    except Exception as e:
        print(f"  Could not set up the Drive folder: {e}")
        print("  The tool will try again on its first run.")


# ---------------------------------------------------------------------------
# Step 4 - mark the USB drive
# ---------------------------------------------------------------------------
def mark_usb_drive(cfg):
    hr()
    print("STEP 4 of 5 - Mark the USB drive for auto-detect")
    hr()
    print("  Plug in the USB drive now if it isn't already.")
    if not yes_no("  Is the USB drive plugged in?", True):
        print("  Skipping - you can re-run install.bat later to do this,")
        print("  or just set 'usb_path' in config.json by hand.")
        return

    drive = ask("  USB drive letter or path (e.g. E:\\)",
                cfg.get("usb_path", ""))
    if not drive:
        print("  No path given - skipping the marker.")
        return
    root = Path(drive)
    if not root.exists():
        print(f"  {root} does not exist right now - skipping the marker.")
        return
    try:
        marker = root / USB_MARKER_FILENAME
        marker.write_text(
            "This file lets MichaelMaul Backup auto-detect this USB drive.\n",
            encoding="utf-8")
        (root / cfg.get("usb_label", "MichaelMaul Backup")).mkdir(
            exist_ok=True)
        print(f"  Marked {root} - the tool will now find this drive "
              f"automatically.")
    except OSError as e:
        print(f"  Could not write to {root}: {e}")


# ---------------------------------------------------------------------------
# Step 5 - desktop shortcut
# ---------------------------------------------------------------------------
def create_desktop_shortcut():
    hr()
    print("STEP 5 of 5 - Desktop button")
    hr()

    if os.name != "nt":
        print("  Desktop shortcut creation is Windows-only - skipping.")
        print(f"  On this OS, run the tool with:  python {MAIN_SCRIPT}")
        return

    desktop = Path(os.path.join(os.path.expanduser("~"), "Desktop"))
    if not desktop.exists():
        alt = Path(os.path.join(os.path.expanduser("~"), "OneDrive",
                                "Desktop"))
        desktop = alt if alt.exists() else desktop

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    shortcut_path = desktop / "MichaelMaul Backup.lnk"

    try:
        vbs = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
Set oLink = oWS.CreateShortcut("{shortcut_path}")
oLink.TargetPath = "{runner}"
oLink.Arguments = """{MAIN_SCRIPT}"""
oLink.WorkingDirectory = "{SCRIPT_DIR}"
oLink.WindowStyle = 1
oLink.Description = "MichaelMaul Backup - export new email to USB and Drive"
oLink.Save
'''
        tmp_vbs = SCRIPT_DIR / "_mk_shortcut.vbs"
        tmp_vbs.write_text(vbs, encoding="utf-8")
        subprocess.run(["cscript", "//nologo", str(tmp_vbs)], check=False)
        tmp_vbs.unlink(missing_ok=True)
        if shortcut_path.exists():
            print(f"  Created the Desktop button: {shortcut_path.name}")
            return
    except Exception:
        pass

    try:
        bat = desktop / "MichaelMaul Backup.bat"
        bat.write_text(
            "@echo off\n"
            f'cd /d "{SCRIPT_DIR}"\n'
            f'"{runner}" "{MAIN_SCRIPT}"\n',
            encoding="utf-8")
        print(f"  Created the Desktop button: {bat.name}")
        print("  (A .bat launcher - works the same; double-click to run.)")
    except OSError as e:
        print(f"  Could not create a Desktop shortcut: {e}")
        print(f"  You can still run the tool with:  python {MAIN_SCRIPT}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 64)
    print("  MichaelMaul Backup - Installer")
    print("=" * 64)
    print("  This sets up the backup tool on this computer.")
    print("  You can re-run it any time; it updates rather than duplicates.")
    print()

    if not install_dependencies():
        print("\nSetup stopped at step 1. Fix the issue above and re-run.")
        input("Press Enter to close.")
        return

    cfg = build_config()
    setup_google(cfg)
    mark_usb_drive(cfg)
    create_desktop_shortcut()

    hr()
    print("Setup finished.")
    hr()
    print("What happens now:")
    print("  - Double-click the 'MichaelMaul Backup' button on the Desktop")
    print("    whenever the USB drive is plugged in.")
    print("  - It backs up new email from the sender to the USB drive and")
    print("    uploads the PDFs to the Google Drive MichaelMaul folder.")
    print()
    if not CREDENTIALS_PATH.exists():
        print("REMINDER: Google Drive upload needs credentials.json.")
        print("  Follow SETUP-CHECKLIST.md, drop the file in this folder,")
        print("  and run install.bat once more to finish the Google step.")
        print()
    print("One-time manual items (if not done yet) - see SETUP-CHECKLIST.md:")
    print("  - Gmail app password")
    print("  - Gmail -> Yahoo forwarding + the Yahoo MichaelMaul folder")
    print("  - Google Cloud credentials.json")
    print()
    input("Press Enter to close.")


if __name__ == "__main__":
    main()
