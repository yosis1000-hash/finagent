"""Seed full org structure for FinAgent testing."""
import logging
from app.database import SessionLocal
from app.models.models import User, Team, TeamMember, RoleType, ReportFrequency
from app.auth.auth import hash_password
from app.org_config import ensure_org_config

logger = logging.getLogger(__name__)

# ─── Passwords ────────────────────────────────────────────────────────────────
PW_ADMIN    = "Admin1234!"
PW_MANAGER  = "Manager1234!"
PW_SECTION  = "Section1234!"
PW_ECON     = "Econ1234!"
PW_STUDENT  = "Student1234!"


async def init_db():
    db = SessionLocal()
    try:
        ensure_org_config(db)

        if db.query(User).count() > 0:
            return  # Already seeded

        logger.info("Seeding full org structure...")

        # ── Division Head ──────────────────────────────────────────────────────
        head = User(
            name="יוסי סעדון",
            email="yossef.saadon@gmail.com",
            notification_email="yossef.saadon@gmail.com",
            hashed_password=hash_password(PW_ADMIN),
            role_type=RoleType.division_head,
            report_frequency=ReportFrequency.none,
            is_active=True,
        )
        db.add(head)
        db.flush()

        # ── Office Manager ─────────────────────────────────────────────────────
        office_mgr = User(
            name="דנה אורן",
            email="office.manager@boi.org.il",
            hashed_password=hash_password(PW_MANAGER),
            role_type=RoleType.office_manager,
            parent_id=head.id,
            report_frequency=ReportFrequency.none,
            is_active=True,
        )
        db.add(office_mgr)
        db.flush()

        # ── Section Head A — מדור מחקר ────────────────────────────────────────
        section_a = User(
            name="ד״ר רחל לוי",
            email="rachel.levy@boi.org.il",
            notification_email="yosis1000@gmail.com",
            hashed_password=hash_password(PW_SECTION),
            role_type=RoleType.section_head,
            parent_id=head.id,
            report_frequency=ReportFrequency.weekly,
            is_active=True,
        )
        db.add(section_a)
        db.flush()

        # ── Section Head B — מדור ניתוח ───────────────────────────────────────
        section_b = User(
            name="עמית גולן",
            email="amit.golan@boi.org.il",
            notification_email="newsflow.app@gmail.com",
            hashed_password=hash_password(PW_SECTION),
            role_type=RoleType.section_head,
            parent_id=head.id,
            report_frequency=ReportFrequency.weekly,
            is_active=True,
        )
        db.add(section_b)
        db.flush()

        # ── Economists under Section A ─────────────────────────────────────────
        econ_a1 = User(name="דוד כהן",    email="david.cohen@boi.org.il",
                       notification_email="saadons.family@gmail.com",
                       hashed_password=hash_password(PW_ECON),
                       role_type=RoleType.economist, parent_id=section_a.id,
                       report_frequency=ReportFrequency.weekly, is_active=True)
        econ_a2 = User(name="מיכל אברהם", email="michal.avraham@boi.org.il",
                       hashed_password=hash_password(PW_ECON),
                       role_type=RoleType.economist, parent_id=section_a.id,
                       report_frequency=ReportFrequency.weekly, is_active=True)
        db.add_all([econ_a1, econ_a2])
        db.flush()

        # ── Economists under Section B ─────────────────────────────────────────
        econ_b1 = User(name="שרה מזרחי",    email="sara.mizrahi@boi.org.il",
                       hashed_password=hash_password(PW_ECON),
                       role_type=RoleType.economist, parent_id=section_b.id,
                       report_frequency=ReportFrequency.weekly, is_active=True)
        econ_b2 = User(name="יואב פרידמן", email="yoav.friedman@boi.org.il",
                       hashed_password=hash_password(PW_ECON),
                       role_type=RoleType.economist, parent_id=section_b.id,
                       report_frequency=ReportFrequency.weekly, is_active=True)
        db.add_all([econ_b1, econ_b2])
        db.flush()

        # ── Students under Section A ───────────────────────────────────────────
        stu_a1 = User(name="רון שמיר",    email="ron.shamir@boi.org.il",
                      hashed_password=hash_password(PW_STUDENT),
                      role_type=RoleType.student, parent_id=section_a.id,
                      report_frequency=ReportFrequency.daily, is_active=True)
        stu_a2 = User(name="לי בן-דוד",  email="lee.bendavid@boi.org.il",
                      hashed_password=hash_password(PW_STUDENT),
                      role_type=RoleType.student, parent_id=section_a.id,
                      report_frequency=ReportFrequency.daily, is_active=True)
        db.add_all([stu_a1, stu_a2])
        db.flush()

        # ── Students under Section B ───────────────────────────────────────────
        stu_b1 = User(name="נועה ברקוביץ", email="noa.berkowitz@boi.org.il",
                      hashed_password=hash_password(PW_STUDENT),
                      role_type=RoleType.student, parent_id=section_b.id,
                      report_frequency=ReportFrequency.daily, is_active=True)
        stu_b2 = User(name="אורי שפירא",  email="uri.shapira@boi.org.il",
                      hashed_password=hash_password(PW_STUDENT),
                      role_type=RoleType.student, parent_id=section_b.id,
                      report_frequency=ReportFrequency.daily, is_active=True)
        db.add_all([stu_b1, stu_b2])
        db.flush()

        # ── Cross-functional Team 1 — דוח יציבות 2026 ─────────────────────────
        team1 = Team(
            name="צוות דוח יציבות 2026",
            focus="הכנת דוח היציבות הפיננסית לשנת 2026",
            lead_user_id=section_a.id,
            is_active=True,
        )
        db.add(team1)
        db.flush()
        db.add_all([
            TeamMember(team_id=team1.id, user_id=econ_a1.id),
            TeamMember(team_id=team1.id, user_id=econ_b1.id),
            TeamMember(team_id=team1.id, user_id=econ_b2.id),
        ])

        # ── Cross-functional Team 2 — מדיניות מוניטרית ────────────────────────
        team2 = Team(
            name="צוות מדיניות מוניטרית",
            focus="ניתוח והמלצות בנושא מדיניות ריבית",
            lead_user_id=section_b.id,
            is_active=True,
        )
        db.add(team2)
        db.flush()
        db.add_all([
            TeamMember(team_id=team2.id, user_id=econ_a2.id),
            TeamMember(team_id=team2.id, user_id=econ_a1.id),
            TeamMember(team_id=team2.id, user_id=stu_a1.id),
        ])

        db.commit()
        logger.info(
            "Full seed complete: 1 division_head, 1 office_manager, "
            "2 section_heads, 4 economists, 4 students, 2 cross-functional teams."
        )
        logger.info("Division Head login: yossef.saadon@gmail.com / Admin1234!")

    except Exception as e:
        logger.error(f"Seeding error: {e}")
        db.rollback()
        raise
    finally:
        db.close()
