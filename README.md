# MichaelMaul Backup

A one-button desktop tool that backs up email from a single sender to a USB
drive **and** to Google Drive — built for Sarah's laptop.

When the USB drive is plugged in, you press one button. The tool:

1. Connects to Gmail and finds new email from the chosen sender.
2. Saves each new email to the USB drive as a **PDF**, a **plain-text** copy,
   and any **attachments**.
3. Uploads each **PDF** to a Google Drive folder named **MichaelMaul**.
4. Remembers what it already did, so pressing the button again only picks up
   new mail.

The button's only job is to say *"my USB is plugged in — go."* Everything else
is automatic.

---

## The whole picture

```
   michael m <2excelon4@gmail.com>
              |
              v
   sarahpepe68@gmail.com  --(Gmail filter: forward)-->  sarahpepe68@yahoo.com
              |                                                |
              |                                         Yahoo filter sorts it
              |                                         into the MichaelMaul
              |                                         folder
              v
   +-------------------------+
   |  MichaelMaul Backup tool |   <- the desktop button, on Sarah's laptop
   |  (reads Gmail)           |
   +-------------------------+
        |                  |
        v                  v
   USB drive          Google Drive
   PDF / text /       "MichaelMaul"
   attachments        folder (PDFs)
```

There are three independent pieces:

- **Email routing** (Gmail -> Yahoo). Set up once by hand in Gmail and Yahoo
  settings. Runs on their servers forever after that. The tool does **not**
  depend on it — it's just an organized second copy of the mail.
- **The backup tool** — runs on the laptop, triggered by the desktop button.
  Reads Gmail, writes to the USB drive, uploads PDFs to Google Drive.
- **The installer** — run once on the laptop. Installs everything, asks a few
  questions, runs the Google sign-in, makes the desktop button.

**The tool reads from Gmail, not Yahoo** — Gmail is where the mail actually
lands, and the originals are cleanest there (forwarded copies get their headers
rewritten). The Yahoo MichaelMaul folder is just a tidy backup copy that
Gmail's forwarding keeps filled on its own.

---

## What one button press does, step by step

1. **Load settings + history.** Reads `config.json`; reads the history file
   `.backup_state.json` from the USB drive (the list of emails already done).
2. **Find the USB drive.** Detects it by a marker file the installer placed on
   it, or by the configured drive path. If it's not plugged in, the tool says
   so and stops — nothing breaks.
3. **Connect to Gmail** over IMAP using the Gmail app password.
4. **Find new mail** from the sender that isn't already in the history file.
5. **For each new email:**
   - render a readable **PDF** -> `USB:\MichaelMaul Backup\Saved as PDF`
   - write a **plain-text** copy with a header block -> `\Saved as Text`
   - save **attachments** -> `\Attachments`
   - **upload the PDF** to the Google Drive **MichaelMaul** folder
   - add it to the history file
6. **Save the history file** back to the USB drive.
7. **Show a summary** in the window — e.g. *"8 new emails -> PDF, 8 uploaded to
   Drive, 3 attachments saved."*

Re-runnable any time. It only ever processes mail it hasn't seen before. If
Google Drive can't be reached for some reason, the USB backup still completes
and the tool tells you Drive was skipped.

> **Videos:** Sarah copies videos onto the USB drive manually, into the
> `Videos` folder the tool creates for her. The tool does not touch Google
> Photos. (Google shut off the API that used to allow that in March 2025.)

---

## The desktop button

The installer puts a **"MichaelMaul Backup"** shortcut on the Desktop.
Double-clicking it opens a small window with:

- a **status line** — *"USB drive detected: E:\MichaelMaul Backup"* or
  *"Plug in the USB drive."*
- one big **Export Now** button
- a live log, and a final summary

No black console window, nothing technical. The window also re-checks for the
USB drive every few seconds, so plugging the drive in updates the status
without reopening anything.

There's also a no-window mode for automation: `python maulbackup.py --cli`
(useful later if you ever want Task Scheduler to run it).

---

## Install

### 1. Get the files
```
git clone https://github.com/Locnar68/MaulBackup.git
cd MaulBackup
```
Or on GitHub: **Code -> Download ZIP**, then extract.

### 2. Install Python
From <https://python.org> if it isn't already installed. On the first installer
screen, check **"Add Python to PATH."**

### 3. Run the installer
Double-click **`install.bat`**. It walks through five steps:

1. Installs the Python libraries.
2. Asks a few questions and writes `config.json`.
3. Runs the Google sign-in (opens a browser, you click **Allow** once) and
   finds/creates the Drive **MichaelMaul** folder.
4. Marks the USB drive so the tool auto-detects it.
5. Creates the **MichaelMaul Backup** button on the Desktop.

The installer is safe to re-run — it updates instead of duplicating.

### 4. One-time manual setup
A few things Google and Yahoo require a human for — see **`SETUP-CHECKLIST.md`**
for the exact click-by-click steps:

- Generate the **Gmail app password** (the installer asks you to paste it in).
- Create the **Google Cloud `credentials.json`** (drop it in the folder, then
  re-run `install.bat` so step 3 can finish).
- Set up **Gmail -> Yahoo forwarding** and the **Yahoo MichaelMaul folder**.

This is about 15 minutes, done once.

---

## Running it

Plug in the USB drive, double-click **MichaelMaul Backup** on the Desktop, click
**Export Now**. That's it.

### Test safely first
```
python maulbackup.py --dry-run
```
Connects and lists what *would* be backed up — writes nothing, uploads nothing.

---

## Files

| File | Purpose |
|---|---|
| `maulbackup.py` | The tool — desktop button (GUI) plus a `--cli` mode |
| `install.py` | The installer logic |
| `install.bat` | Double-click wrapper that runs the installer |
| `config.example.json` | Settings template — the installer copies it to `config.json` |
| `config.json` | Your real settings, incl. the Gmail app password *(gitignored — you create it)* |
| `credentials.json` | Google OAuth client *(gitignored — you download it once)* |
| `token.json` | Saved Google sign-in *(gitignored — the installer creates it)* |
| `requirements.txt` | Python libraries the installer installs |
| `README.md` | This file |
| `SETUP-CHECKLIST.md` | The ~15-minute one-time manual steps |
| `.gitignore` | Keeps the secret/local files out of the public repo |

On the USB drive the tool creates:
```
USB:\MichaelMaul Backup\
    Saved as PDF\
    Saved as Text\
    Attachments\
    Videos\               <- Sarah's manual video copies go here
    .backup_state.json    <- history; don't delete it
```

If `.backup_state.json` is ever deleted, the next run just re-saves everything
(harmless — only slower, and duplicates in Drive).

---

## Settings (`config.json`)

| Field | What it is |
|---|---|
| `gmail_address` | The Gmail account the mail arrives in (`sarahpepe68@gmail.com`) |
| `gmail_app_password` | 16-char Gmail **app password** (not the normal password) |
| `sender_filter` | The sender to back up (`2excelon4@gmail.com`) |
| `source_mailbox` | Which Gmail mailbox to read — leave as `INBOX` |
| `usb_label` | Folder name to use on the USB drive |
| `usb_path` | Drive path like `E:\` — leave blank to auto-detect |
| `upload_to_drive` | `true` to upload PDFs to Google Drive |
| `drive_folder_name` | Google Drive folder name (`MichaelMaul`) |
| `drive_folder_id` | Filled in automatically the first time — leave blank |

---

## Security & privacy

- `config.json`, `credentials.json`, and `token.json` are all **gitignored** —
  no passwords or tokens reach GitHub. Only `config.example.json` (placeholders)
  is committed.
- The Google permission is the **minimum possible** — `drive.file`, which lets
  the tool see only files it creates itself. It cannot read the rest of Drive.
- The Gmail app password and the Google sign-in token are both **revocable**
  any time from the Google account's security page.
- The tool only **reads** mail and **uploads** PDFs. It never deletes anything
  from Gmail, Yahoo, Drive, or the USB drive.
- The tool does not change Google Drive sharing. If you want to share the
  MichaelMaul folder, do that yourself in Drive — the installer prints the
  folder link to make that easy.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not find the USB drive" | Plug it in. If it still isn't found, re-run `install.bat` (step 4 marks the drive), or set `usb_path` in `config.json`. |
| "Gmail login failed" | The `gmail_app_password` is wrong, or the normal password was used. Generate an app password — see `SETUP-CHECKLIST.md`. |
| "credentials.json is missing" | Do the Google Cloud step in `SETUP-CHECKLIST.md`, put the file in the folder, re-run `install.bat`. |
| Drive upload skipped, USB backup worked | Expected fallback when Google can't be reached. The log says why; the next run retries. |
| `python` not recognized | Python wasn't added to PATH — reinstall from python.org and check that box. |
| Nothing gets backed up | No new mail from that sender, or it's all been done. Try `--dry-run`; check `sender_filter` is exact. |
| Want to re-back-up everything | Delete `.backup_state.json` from the USB drive. |
| Mail isn't reaching the Yahoo folder | That's the Gmail/Yahoo forwarding, separate from this tool — recheck the filter steps in `SETUP-CHECKLIST.md`. |
