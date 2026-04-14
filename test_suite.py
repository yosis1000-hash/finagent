"""
FinAgent API Test Suite
Runs against live Railway URL after deploy.
"""
import asyncio
import httpx
import json
from datetime import date, timedelta

BASE = "https://web-production-21d65.up.railway.app"
RESULTS = []


def log(test, passed, detail=""):
    icon = "✅" if passed else "❌"
    RESULTS.append((test, passed, detail))
    print(f"{icon} {test}" + (f" — {detail}" if detail else ""))


async def login(client, email, password):
    r = await client.post(f"{BASE}/api/auth/login",
        json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()["access_token"]
    return None


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Phase 0: Health & Login ──────────────────────────────────────────────────

async def test_health(client):
    r = await client.get(f"{BASE}/health")
    log("Health endpoint", r.status_code == 200 and r.json() == {"status": "ok"})


async def test_logins(client):
    users = [
        ("yosis@boi.org.il",           "Admin1234!",    "division_head"),
        ("office.manager@boi.org.il",  "Manager1234!",  "office_manager"),
        ("rachel.levy@boi.org.il",     "Section1234!",  "section_head"),
        ("amit.golan@boi.org.il",      "Section1234!",  "section_head"),
        ("david.cohen@boi.org.il",     "Econ1234!",     "economist"),
        ("sara.mizrahi@boi.org.il",    "Econ1234!",     "economist"),
        ("ron.shamir@boi.org.il",      "Student1234!",  "student"),
        ("noa.berkowitz@boi.org.il",   "Student1234!",  "student"),
    ]
    tokens = {}
    for email, pw, role in users:
        token = await login(client, email, pw)
        ok = token is not None
        log(f"Login {role} ({email.split('@')[0]})", ok)
        if ok:
            tokens[email] = token
    return tokens


# ─── Phase 1: Org Tree & Seed Verification ────────────────────────────────────

async def test_org_tree(client, token):
    r = await client.get(f"{BASE}/api/users/org-tree", headers=auth(token))
    ok = r.status_code == 200
    if ok:
        tree = r.json()
        total = count_users(tree)
        log("Org tree returned", ok, f"{total} users total")
        log("Org tree has 12 users", total == 12, f"got {total}")
    else:
        log("Org tree returned", False, r.text[:100])


def count_users(nodes):
    count = 0
    for n in nodes:
        count += 1
        count += count_users(n.get("children", []))
    return count


# ─── Phase 2: RBAC — create tasks, check visibility ──────────────────────────

async def get_user_id(client, token, email):
    """Lookup user_id by email from org-tree."""
    r = await client.get(f"{BASE}/api/users/", headers=auth(token))
    if r.status_code == 200:
        for u in r.json():
            if u.get("email") == email:
                return u["id"]
    return None


async def test_create_task(client, token, title, assignee_email, deadline_days=7):
    deadline = (date.today() + timedelta(days=deadline_days)).isoformat()
    assignee_id = await get_user_id(client, token, assignee_email)
    r = await client.post(f"{BASE}/api/items/", headers=auth(token),
        json={"title": title, "type": "task", "status": "open",
              "priority": "high", "deadline": deadline,
              "assignee_user_id": assignee_id})
    ok = r.status_code in (200, 201)
    item_id = r.json().get("id") if ok else None
    return ok, item_id


async def test_rbac(client, tokens):
    # Division head creates tasks for everyone
    head_token = tokens.get("yosis@boi.org.il")
    if not head_token:
        log("RBAC tests", False, "No division_head token")
        return {}

    item_ids = {}

    ok, id1 = await test_create_task(client, head_token,
        "הכנת נתוני אשראי לדוח היציבות", "david.cohen@boi.org.il", 16)
    log("Division head creates task for economist", ok, f"id={id1}")
    if id1: item_ids["task_econ_a1"] = id1

    ok, id2 = await test_create_task(client, head_token,
        "ניתוח נתוני אינפלציה רבעון 1", "sara.mizrahi@boi.org.il", 10)
    log("Division head creates task for economist B", ok, f"id={id2}")
    if id2: item_ids["task_econ_b1"] = id2

    ok, id3 = await test_create_task(client, head_token,
        "עדכון מודל חיזוי צמיחה", "michal.avraham@boi.org.il", 5)
    log("Division head creates urgent task", ok, f"id={id3}")
    if id3: item_ids["task_econ_a2"] = id3

    ok, id4 = await test_create_task(client, head_token,
        "סקירת מצב שוק ההון השבועית", "ron.shamir@boi.org.il", 3)
    log("Division head creates task for student", ok, f"id={id4}")
    if id4: item_ids["task_student"] = id4

    def get_assignee_email(item):
        """Extract assignee email from nested assignee object."""
        assignee = item.get("assignee") or {}
        return assignee.get("email")

    # Section head can see their section's tasks
    sec_a_token = tokens.get("rachel.levy@boi.org.il")
    if sec_a_token:
        r = await client.get(f"{BASE}/api/items/", headers=auth(sec_a_token))
        if r.status_code == 200:
            items = r.json()
            emails_visible = {get_assignee_email(i) for i in items}
            sec_b_visible = "sara.mizrahi@boi.org.il" in emails_visible
            log("Section head A sees own section tasks", r.status_code == 200,
                f"{len(items)} items")
            log("Section head A does NOT see section B tasks", not sec_b_visible,
                "sara.mizrahi visible=" + str(sec_b_visible))

    # Economist sees only own tasks (plus team tasks and tasks they reported)
    econ_token = tokens.get("david.cohen@boi.org.il")
    if econ_token:
        r = await client.get(f"{BASE}/api/items/", headers=auth(econ_token))
        if r.status_code == 200:
            items = r.json()
            assigned_to_me = [i for i in items if i.get("assignee_user_id") is not None
                              and get_assignee_email(i) == "david.cohen@boi.org.il"]
            log("Economist sees own tasks", len(assigned_to_me) >= 1,
                f"{len(items)} total, {len(assigned_to_me)} assigned to me")

    # Student sees only own tasks
    stu_token = tokens.get("ron.shamir@boi.org.il")
    if stu_token:
        r = await client.get(f"{BASE}/api/items/", headers=auth(stu_token))
        if r.status_code == 200:
            items = r.json()
            assigned_to_me = [i for i in items if get_assignee_email(i) == "ron.shamir@boi.org.il"]
            log("Student sees own tasks", len(assigned_to_me) >= 1,
                f"{len(items)} total, {len(assigned_to_me)} assigned to me")

    return item_ids


# ─── Phase 3: Projects with sub-tasks ─────────────────────────────────────────

async def test_projects(client, tokens):
    head_token = tokens.get("yosis@boi.org.il")
    if not head_token:
        return

    # Create project
    r = await client.post(f"{BASE}/api/items/", headers=auth(head_token),
        json={"title": "דוח היציבות 2026", "type": "project",
              "status": "active", "priority": "critical"})
    ok = r.status_code in (200, 201)
    proj_id = r.json().get("id") if ok else None
    log("Create project 'דוח היציבות 2026'", ok, f"id={proj_id}")

    if not proj_id:
        return

    # Create 4 sub-tasks under project
    subtasks = [
        ("פרק אשראי — נתונים גולמיים",      "david.cohen@boi.org.il"),
        ("פרק אשראי — ניתוח מגמות",         "michal.avraham@boi.org.il"),
        ("פרק ריבית — השוואה בינלאומית",    "sara.mizrahi@boi.org.il"),
        ("פרק ריבית — המלצות מדיניות",      "yoav.friedman@boi.org.il"),
    ]
    sub_ids = []
    for title, assignee_email in subtasks:
        assignee_id = await get_user_id(client, head_token, assignee_email)
        r2 = await client.post(f"{BASE}/api/items/", headers=auth(head_token),
            json={"title": title, "type": "task", "status": "open",
                  "priority": "high", "parent_item_id": proj_id,
                  "assignee_user_id": assignee_id,
                  "deadline": (date.today() + timedelta(days=30)).isoformat()})
        ok2 = r2.status_code in (200, 201)
        if ok2: sub_ids.append(r2.json()["id"])

    log("Created 4 sub-tasks under project", len(sub_ids) == 4, f"ids={sub_ids}")

    # Verify project has children
    r3 = await client.get(f"{BASE}/api/items/{proj_id}", headers=auth(head_token))
    if r3.status_code == 200:
        proj = r3.json()
        log("Project detail accessible", True, f"title={proj.get('title','?')[:20]}")


# ─── Phase 4: Task lifecycle — update, complete ───────────────────────────────

async def test_lifecycle(client, tokens, item_ids):
    head_token = tokens.get("yosis@boi.org.il")
    econ_token = tokens.get("david.cohen@boi.org.il")
    task_id = item_ids.get("task_econ_a1")
    if not task_id or not econ_token:
        return

    # Economist updates own task to in_progress
    r = await client.put(f"{BASE}/api/items/{task_id}", headers=auth(econ_token),
        json={"status": "in_progress"})
    log("Economist updates task to in_progress", r.status_code == 200)

    # Economist marks task as completed
    r2 = await client.put(f"{BASE}/api/items/{task_id}", headers=auth(econ_token),
        json={"status": "completed"})
    log("Economist marks task completed", r2.status_code == 200)

    # Verify completed appears in dashboard
    r3 = await client.get(f"{BASE}/api/dashboard/stats", headers=auth(head_token))
    if r3.status_code == 200:
        stats = r3.json()
        log("Dashboard reflects completion", stats.get("completed_this_month", 0) >= 1,
            str(stats))


# ─── Phase 5: Report submission & scoring ────────────────────────────────────

async def test_reports(client, tokens):
    econ_token = tokens.get("david.cohen@boi.org.il")
    head_token = tokens.get("yosis@boi.org.il")
    if not econ_token:
        return

    # Submit detailed report (should score high)
    r = await client.post(f"{BASE}/api/reports/submit", headers=auth(econ_token),
        json={"report_text": (
            "עדכון שבועי מפורט:\n"
            "1. משימת נתוני אשראי — הושלמה. עיבדתי 3 מקורות נתונים, בניתי טבלה השוואתית.\n"
            "2. ניתוח מגמות — בתהליך. זיהיתי עלייה של 4% באשראי הצרכני. צפי סיום: יום ד'.\n"
            "3. תיאום עם ד\"ר לוי לגבי פרק הריבית — נקבעה פגישה ליום ג'.\n"
            "חסמים: אין. הכל במסלול."
        )})
    ok = r.status_code in (200, 201)
    score_hi = r.json().get("ai_score") if ok else None
    log("Submit detailed report", ok, f"score={score_hi}")
    log("Detailed report scored ≥ 2", ok and score_hi and score_hi >= 2,
        f"got {score_hi}")

    # Submit minimal report (should score low)
    r2 = await client.post(f"{BASE}/api/reports/submit", headers=auth(econ_token),
        json={"report_text": "הכל בסדר."})
    ok2 = r2.status_code in (200, 201)
    score_lo = r2.json().get("ai_score") if ok2 else None
    log("Submit minimal report", ok2, f"score={score_lo}")
    log("Minimal report scored ≤ 2", ok2 and score_lo and score_lo <= 2,
        f"got {score_lo}")
    log("Detailed report scored higher than minimal",
        ok and ok2 and score_hi is not None and score_lo is not None and score_hi > score_lo,
        f"detailed={score_hi} > minimal={score_lo}")

    # Division head sees all reports
    r3 = await client.get(f"{BASE}/api/reports/", headers=auth(head_token))
    ok3 = r3.status_code == 200
    count = len(r3.json()) if ok3 else 0
    log("Division head sees all reports", ok3 and count >= 2, f"{count} reports")


# ─── Phase 6: Dashboard ───────────────────────────────────────────────────────

async def test_dashboard(client, tokens):
    head_token = tokens.get("yosis@boi.org.il")
    if not head_token:
        return

    r = await client.get(f"{BASE}/api/dashboard/stats", headers=auth(head_token))
    ok = r.status_code == 200
    stats = r.json() if ok else {}
    log("Dashboard stats", ok, str(stats))
    log("Dashboard shows open tasks", ok and stats.get("total_open", 0) > 0,
        f"total_open={stats.get('total_open')}")

    r2 = await client.get(f"{BASE}/api/dashboard/activity", headers=auth(head_token))
    log("Dashboard activity", r2.status_code == 200, f"{len(r2.json())} items" if r2.status_code == 200 else r2.text[:50])

    r3 = await client.get(f"{BASE}/api/dashboard/followups", headers=auth(head_token))
    log("Dashboard followups", r3.status_code == 200)


# ─── Phase 7: Error handling ──────────────────────────────────────────────────

async def test_error_handling(client, tokens):
    head_token = tokens.get("yosis@boi.org.il")

    # Non-existent item
    r = await client.get(f"{BASE}/api/items/99999", headers=auth(head_token))
    log("Non-existent item returns 404", r.status_code == 404)

    # Invalid login
    r2 = await client.post(f"{BASE}/api/auth/login",
        json={"email": "unknown@boi.org.il", "password": "wrong"})
    log("Unknown user login rejected", r2.status_code == 401)

    # Unauthorized access (no token)
    r3 = await client.get(f"{BASE}/api/items/")
    log("Unauthenticated request rejected", r3.status_code == 401)

    # Economist can create tasks (no cross-section restriction enforced)
    econ_token = tokens.get("david.cohen@boi.org.il")
    if econ_token:
        sara_id = await get_user_id(client, econ_token, "sara.mizrahi@boi.org.il")
        r4 = await client.post(f"{BASE}/api/items/", headers=auth(econ_token),
            json={"title": "test cross-section", "type": "task", "status": "open",
                  "assignee_user_id": sara_id})
        log("Economist can create task (cross-section allowed)", r4.status_code in (200, 201),
            f"status={r4.status_code}")


# ─── Phase 8: Email processing simulation ────────────────────────────────────

async def test_email_simulation(client, tokens):
    """Simulate email processing via the processor directly (no real send needed)."""
    import sys, os
    sys.path.insert(0, 'c:/yossi/laptop-boi/my_apps/office_manager/for_office_manager')
    os.chdir('c:/yossi/laptop-boi/my_apps/office_manager/for_office_manager')
    try:
        from dotenv import load_dotenv; load_dotenv()
        from app.ai.claude import extract_tasks_from_email, parse_finagent_command

        known_users = [
            {"name": "יוסי סעדון", "email": "yosis@boi.org.il", "role_type": "division_head"},
            {"name": "דוד כהן", "email": "david.cohen@boi.org.il", "role_type": "economist"},
            {"name": "שרה מזרחי", "email": "sara.mizrahi@boi.org.il", "role_type": "economist"},
        ]

        # Test 1: @FinAgent command parsing
        cmd_body = "@FinAgent צור משימה: הכנת נתוני אשראי לדוח היציבות דד-ליין: 30/04/2026 מוקצה ל: דוד כהן"
        cmd = await parse_finagent_command(cmd_body, known_users)
        ok = cmd and cmd.get("command") in ("create_task", None)
        log("@FinAgent command parsed", cmd is not None, f"command={cmd.get('command') if cmd else 'None'}")

        # Test 2: Task extraction from email body
        result = await extract_tasks_from_email(
            subject="מעקב: נתוני אשראי",
            body="שלום דוד, אנא הכן את נתוני האשראי לדוח היציבות עד 30 באפריל. חשוב שיכלול ניתוח מגמות.",
            sender="yosis@boi.org.il",
            recipients=["david.cohen@boi.org.il", "boi.finagent@gmail.com"],
            known_users=known_users
        )
        has_tasks = len(result.get("tasks", [])) > 0
        log("AI extracts tasks from email", has_tasks,
            f"{len(result.get('tasks', []))} tasks found")

        # Test 3: @FinAgent followup command
        followup_body = "@FinAgent למעקב: דוד כהן — נתוני אשראי — דד-ליין 25/04"
        cmd2 = await parse_finagent_command(followup_body, known_users)
        log("@FinAgent followup parsed", cmd2 is not None,
            f"command={cmd2.get('command') if cmd2 else 'None'}")

        # Test 4: Unknown command — graceful
        unknown_body = "@FinAgent בלבול מוחלט ללא הגיון"
        cmd3 = await parse_finagent_command(unknown_body, known_users)
        log("Unknown @FinAgent command — no crash", True,
            f"returned: {cmd3.get('command') if cmd3 else 'None'}")

    except Exception as e:
        log("Email simulation", False, str(e)[:100])


# ─── Main runner ──────────────────────────────────────────────────────────────

async def run_all():
    async with httpx.AsyncClient(timeout=90) as client:
        print("\n" + "="*60)
        print("FinAgent Test Suite — " + BASE)
        print("="*60 + "\n")

        print("── Phase 0: Health & Logins ──")
        await test_health(client)
        tokens = await test_logins(client)
        head_token = tokens.get("yosis@boi.org.il")
        if not head_token:
            print("\n❌ FATAL: Division head login failed — aborting tests")
            return

        print("\n── Phase 1: Org Tree & Seed ──")
        await test_org_tree(client, head_token)

        print("\n── Phase 2: RBAC & Task Creation ──")
        item_ids = await test_rbac(client, tokens)

        print("\n── Phase 3: Projects & Sub-tasks ──")
        await test_projects(client, tokens)

        print("\n── Phase 4: Task Lifecycle ──")
        await test_lifecycle(client, tokens, item_ids)

        print("\n── Phase 5: Reports & AI Scoring ──")
        await test_reports(client, tokens)

        print("\n── Phase 6: Dashboard ──")
        await test_dashboard(client, tokens)

        print("\n── Phase 7: Error Handling ──")
        await test_error_handling(client, tokens)

        print("\n── Phase 8: Email Simulation (Gemini AI) ──")
        await test_email_simulation(client, tokens)

        # Summary
        passed = sum(1 for _, p, _ in RESULTS if p)
        total = len(RESULTS)
        failed = [(t, d) for t, p, d in RESULTS if not p]
        print(f"\n{'='*60}")
        print(f"RESULTS: {passed}/{total} passed")
        if failed:
            print(f"\nFailed tests:")
            for name, detail in failed:
                print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
        print("="*60)


if __name__ == "__main__":
    asyncio.run(run_all())
