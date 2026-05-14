# Setup Checklist — one-time manual steps

These are the things Google and Yahoo require a *human* to do — a script can't
do them, by design. Total time: about 15 minutes, done once.

Do these in order. After this, `install.bat` handles the rest, and the daily
use is just: plug in USB -> press the button.

---

## Part 1 — Gmail app password (~3 min)

Gmail won't let a program log in with the normal password. You generate a
separate, revocable "app password."

1. Sign in to **sarahpepe68@gmail.com** in a browser.
2. Go to **<https://myaccount.google.com/security>**.
3. Make sure **2-Step Verification** is **On**. (App passwords don't exist
   until it is. If it's off, turn it on first — it'll ask for a phone number.)
4. In the search bar at the top of that page, type **App passwords** and open
   it. (Or go directly to <https://myaccount.google.com/apppasswords>.)
5. Give it a name like **MichaelMaul Backup** and click **Create**.
6. Google shows a **16-character password**. Copy it — you'll paste it into the
   installer in step 2 of `install.bat`.
7. Also confirm IMAP is on: Gmail -> **Settings (gear) -> See all settings ->
   Forwarding and POP/IMAP -> Enable IMAP -> Save**.

> This password works only for mail apps and can be revoked any time from the
> same App passwords page. It is not the account's real password.

---

## Part 2 — Google Cloud credentials.json (~7 min)

This is what lets the tool upload PDFs to Google Drive. You create an OAuth
"client" once and download a small file.

1. Go to **<https://console.cloud.google.com/>** and sign in as
   **sarahpepe68@gmail.com**.
2. At the top, click the project dropdown -> **New Project**. Name it
   **MichaelMaul Backup** -> **Create**. Wait a few seconds, then make sure that
   project is selected in the dropdown.
3. **Enable the Drive API:**
   - In the search bar type **Google Drive API** -> open it -> **Enable**.
4. **Configure the consent screen:**
   - Left menu -> **APIs & Services -> OAuth consent screen**.
   - User type: **External** -> **Create**.
   - App name: **MichaelMaul Backup**. User support email: Sarah's address.
     Developer contact email: Sarah's address. -> **Save and Continue**.
   - Scopes page: just **Save and Continue** (the tool requests its scope at
     sign-in time).
   - Test users page: click **Add Users**, add **sarahpepe68@gmail.com** ->
     **Save and Continue**.
   - (Leaving the app in "testing" mode is fine — it just means only the test
     users you listed can use it, which is exactly what you want.)
5. **Create the credentials:**
   - Left menu -> **APIs & Services -> Credentials**.
   - **Create Credentials -> OAuth client ID**.
   - Application type: **Desktop app**. Name: **MichaelMaul Backup**. ->
     **Create**.
   - A box pops up — click **Download JSON**.
6. **Rename and place the file:**
   - Rename the downloaded file to exactly **`credentials.json`**.
   - Put it in the **MaulBackup folder** (next to `maulbackup.py`).

> `credentials.json` is gitignored — it never goes to GitHub. After this,
> re-run `install.bat`; step 3 will open a browser once for you to click
> **Allow**, and that's the Google side done.

---

## Part 3 — Gmail -> Yahoo forwarding (~3 min)

This keeps a copy of the sender's mail flowing into Yahoo. It's separate from
the backup tool — the tool reads Gmail directly — but it's part of your overall
goal, so set it up here.

1. In **Gmail (sarahpepe68@gmail.com)**: **Settings (gear) -> See all settings ->
   Forwarding and POP/IMAP**.
2. Click **Add a forwarding address** -> enter **sarahpepe68@yahoo.com** ->
   **Next -> Proceed -> OK**.
3. Gmail sends a **confirmation code** to the Yahoo inbox. Open
   **sarahpepe68@yahoo.com**, find that email, and either click its link or
   copy the code back into Gmail's forwarding settings to confirm.
   *(This verification step is why a script can't do this part.)*
4. Back in Gmail, **don't** set "forward all mail." Instead make a filter so
   only the sender's mail forwards:
   - **Settings -> Filters and Blocked Addresses -> Create a new filter**.
   - **From:** `2excelon4@gmail.com` -> **Create filter**.
   - Tick **Forward it to:** and choose **sarahpepe68@yahoo.com**.
   - Click **Create filter**.

---

## Part 4 — Yahoo MichaelMaul folder + filter (~2 min)

So the forwarded mail lands tidily in Yahoo instead of the inbox.

1. Sign in to **sarahpepe68@yahoo.com**.
2. In the left folder list, click the **+** (or **New Folder**) and name it
   exactly **MichaelMaul**.
3. **Settings (gear) -> More Settings -> Filters -> Add new filters**.
4. Name it **MichaelMaul**. Set a **From contains** rule — the safest match is
   `2excelon4@gmail.com` (the original sender shows through on the forwarded
   mail). If you find forwarded mail doesn't match on the sender, change the
   rule to **To contains** `sarahpepe68@yahoo.com` instead.
5. Set the destination folder to **MichaelMaul** -> **Save**.

---

## Done

Now run **`install.bat`** (or run it again if you ran it before `credentials.json`
existed). After it finishes:

- The **MichaelMaul Backup** button is on the Desktop.
- Plug in the USB drive, press the button — new mail gets backed up to the USB
  drive and the PDFs upload to the Google Drive **MichaelMaul** folder.

Quick check that it's all working:
```
python maulbackup.py --dry-run
```
This connects and lists what it *would* back up, without writing or uploading
anything.
