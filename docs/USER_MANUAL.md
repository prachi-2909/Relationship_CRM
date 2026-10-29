# Relationship CRM - User manual

How to open, sign in to and use the web CRM and the Android app, step by step.

Who uses what:

| Role | Uses | Works with |
|---|---|---|
| **Relationship Manager (RM)** | Android app + web CRM | Their own CSPs (Kiosk Operators) |
| **District Coordinator (DC)** | Android app | SBI officials in their territory |
| **Admin** | Web CRM (everything) | All data, users, imports, audit log |
| **Approver / Viewer** | Web CRM (read) | Dashboards and reports |

---

## 1. Before you start

1. **Get the link.** The web CRM is at `https://indev.eko.in/sbi-relationship-crm/`.
2. **Get an account.** An admin creates it (web CRM, Users) and gives you the email and password.
3. **Check your network.** Office Wi-Fi works as is. On a Jio hotspot or Jio mobile data the page may not open, because Jio's DNS can return a wrong address for `eko.in`. Fix:
   - Phone: Settings, Network, **Private DNS**, type `dns.google`.
   - Laptop: ask your admin, or switch to the office Wi-Fi.
4. **Android phone** (for calling and recording): Android 8 or newer. You need the APK file (`SBI-Relationship-CRM-server.apk`) from your admin.

---

## 2. Web CRM

### 2.1 Sign in

1. Open `https://indev.eko.in/sbi-relationship-crm/`.
2. Type your **Email** and **Password**, then sign in.
3. To leave, use **Sign out** at the top right of the page.

If the page stays blank or times out, see "Troubleshooting" at the end.

### 2.2 The menu (left side)

| Menu item | What it is for |
|---|---|
| **Dashboard** | Your CSP network at a glance: operators, the RMs who run them, call activity, whose birthday is next. Click any figure or bar to drill in. |
| **Organisation** | The organisation tree (units and levels). Admin and RM. |
| **Officials** | SBI officials: profile, source of each field, timeline. |
| **Relationships** | One relationship per official, with a health score and history. |
| **Birthday Wishes** | Upcoming birthdays. |
| **Interactions** | The log of every call, meeting and email. |
| **Opportunities** | Business opportunities linked to relationships. |
| **Follow-ups** | Tasks, including those created from commitments. |
| **Call Intelligence** | Every call: transcript, AI brief, commitments, review. |
| **Engagement Moments** | Suggested messages (promotion, birthday, anniversary, inactivity). **Drafts only, nothing is sent automatically.** |
| **Autonomous Agent** | Recommendations. Nothing is done until a person approves. |
| **Learning Dashboard** | Admin only. How recommendations and strategies performed. |
| **Intelligence Quality** | Admin only. Quality of the AI output. |
| **Data Ingestion** | Import officials or CSPs from CSV / Excel. |
| **Users** | Admin only. Create users, set roles, reset access. |
| **Audit Log** | Admin only. Who changed what and when. |

DCs only see the items that apply to them.

### 2.3 Ask the Supervisor

At the bottom of the **Dashboard** is the **Ask** box.

1. Type a question, for example: `What did we discuss with Deepak Dhawan last time?`
2. Read the answer. It is built from the recorded call history. An RM only gets answers about their own CSPs.
3. Ask a follow-up in the same box. It remembers what you just discussed.

Without an AI service connected, the Supervisor answers from a fixed template, which is shorter and less fluent.

### 2.4 Review a call

1. Open **Call Intelligence**.
2. Choose a call from **Pending** (waiting for review) or **History**.
3. Check the **Transcript** and the **AI Call Brief**.
4. Fix anything that is wrong, then confirm. This logs the call as an **Interaction** on the relationship.
5. Commitments found in the call appear for review. Accept the real ones. Duplicates of an open commitment are flagged.

---

## 3. Android app

### 3.1 Install

1. Copy `SBI-Relationship-CRM-server.apk` to the phone (USB, WhatsApp, Drive).
2. Open the file. If Android asks, allow "Install unknown apps" for the app you opened it from.
3. Install. To update, install the new APK over the old one.

### 3.2 First sign-in

1. Open the app. The screen says **Welcome back**.
2. Enter your **Email** and **Password**, then sign in.
3. Allow the permissions it asks for: **Phone** (to place calls), **Notifications**, and **Call log** if asked. Without **Phone**, the Call button cannot dial.
4. If asked "**Record your calls?**" (DC) or "**Record your CSP calls?**" (RM), read it and choose. RM recording applies only to calls with a CSP's number.

### 3.3 Home screen

The home screen shows counts such as **Pending calls**, **Calls awaiting review** and **Logged interactions**, then **Quick actions**:

- **My CSPs** (RM) or **All officials** (DC): your list to call from.
- **Dial a number**: call a number that is not in your list.
- **Recording capability**: set up two-way recording (section 3.4).

### 3.4 One-time setup for two-way recording

Without this the app records only your side of the call (or nothing). Do it once per phone.

1. Home, **Recording capability**.
2. Pick **Built-in (no 2nd app)**, or **Shizuku** if you use that app.
3. For **Built-in**, follow the steps on the screen, in this order:
   1. Tap **Start pairing**.
   2. Open **Developer options** and turn on **Wireless debugging**. (To get Developer options: Settings, About phone, tap **Build number** 7 times.)
   3. Tap **Pair device with pairing code**. A 6-digit code appears. Keep it open.
   4. Pull down the notification shade. Type the 6-digit code **into the notification**, not into the app.
   5. Go back to the app. The screen shows **Ready**.
4. If the connection is lost later (for example after turning Developer options off), the screen goes back to the pairing steps. Repeat them, or tap **Pair again with code**.

### 3.5 Call a CSP (RM)

1. Home, **My CSPs**. Use the search box (name, code, number or branch).
2. Open a CSP. The **Before you call** page shows:
   - **Talking points**
   - **They committed** and **You committed** (open commitments)
   - **Last call** and **Current slab status**
   - **Suggested from your calls**: rate a suggestion to say whether it was useful.
3. Tap the **Call** button next to the number. The phone's dialer opens and the call is placed.
4. Talk. A notification says **Call in progress**. If recording is allowed it says **Recording is ON**: tell the other person the call is recorded.
5. End the call as usual. The app reports the call and uploads the recording.

Calls shorter than **5 seconds** are not recorded.

### 3.6 Call an official (DC)

1. Home, **All officials**, search and open an official.
2. Review the briefing, then tap **Call**. The rest is the same as in 3.5.

### 3.7 After the call: Call Review

1. Home, **Calls awaiting review**, or the **Calls** screen (tabs **Pending** and **History**).
2. Open the call. **Call Review** shows the **Call recording**, **Transcript** and **AI Call Brief**. Transcription takes a few minutes for a long call.
3. If the box **Identity resolution needed** appears, the number is not linked to anyone yet. Choose:
   - **Search existing officials**, then **Link**, or
   - **Create a new official**, or
   - **Dismiss / keep unidentified**.
4. If there is no recording, add the call yourself with **Record voice note** or **Type manual notes**.
5. Confirm the call. It becomes an **Interaction** in the CRM.

### 3.8 Dial a number that is not in your list

Home, **Dial a number**, **Enter phone number**, then call. Recording follows the same rules: an RM's call is stored only if the number is a CSP's.

### 3.9 Profile

Open **My Profile** for your details, your territory (**My Territory**) and the recording setting (**Record my calls**). To sign out, use the **Log out** icon at the top of the home screen.

---

## 4. What the system keeps, and for how long

| | DC - SBI official | RM - CSP |
|---|---|---|
| Audio | Deleted when the call is logged as an Interaction. If never logged, deleted after 7 days. | Deleted 60 days after it was stored |
| Transcript, AI brief, summary | Kept | Kept |
| Calls under 5 seconds | Not recorded | Not recorded |

An RM's recording is stored only for a CSP's number. Details: `docs/data-retention.md`.

---

## 5. Troubleshooting

| Problem | What to do |
|---|---|
| The web page does not open, or times out | Try the office Wi-Fi. On Jio, set Private DNS to `dns.google` (phone). Try an Incognito window. |
| Sign-in says "Invalid email or password" | Check the email. Ask an admin to reset the password. |
| **Call button does nothing, dialer does not open** | Settings, Apps, this app, Permissions: allow **Phone**. Make sure the installed APK is the server one (`SBI-Relationship-CRM-server.apk`), not an older test build. If it still fails, tell your admin the exact time you tapped Call. |
| A call shows in Pending but you never called | The call was registered but never placed. It is cancelled automatically within a few hours. |
| **Recording capability** does not say Ready | Repeat the pairing steps in 3.4. Wireless debugging must be on while pairing. |
| Only your own voice is recorded | Two-way recording is not set up. See 3.4. |
| Transcript is empty or late | A long call takes several minutes. Check again later. |
| "A call is already in progress" | Finish or hang up the current call. A stuck one clears itself after a while. |

---

## 6. For admins

### First start of a new server

1. Create the first admin (on the server, in the project folder):
   ```bash
   sudo docker compose exec backend python -m app.scripts.create_admin --email you@eko.co.in --name "Your Name" --password "choose-a-strong-one"
   ```
2. Sign in on the web, open **Users** and create the RMs and DCs.
3. Load CSPs and officials with **Data Ingestion** (CSV or Excel). Check the preview, then commit.

### Update the server after a new version

```bash
sudo -u prachi git -C /home/prachi/SBI_Relationship_CRM pull origin main
cd /home/prachi/SBI_Relationship_CRM && sudo docker compose up -d --build backend frontend
sudo docker compose ps
```
All containers should show `healthy`. Your data (database and recordings) is kept.

### Where to read more

- `docs/RUNBOOK.md`: server deployment, backups, rollback.
- `docs/data-retention.md`: what is deleted, when, and how that is proved.
- `README.md`: overview of the project.
