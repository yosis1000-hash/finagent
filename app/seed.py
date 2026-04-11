"""Seed initial data: Division Head user and default org structure."""
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import User, RoleType, ReportFrequency
from app.auth.auth import hash_password

logger = logging.getLogger(__name__)


async def init_db():
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return  # Already seeded

        logger.info("Seeding initial database...")

        # Division Head
        division_head = User(
            name="יוסי סעדון",
            email="yossef.saadon@gmail.com",
            hashed_password=hash_password("Admin1234!"),
            role_type=RoleType.division_head,
            report_frequency=ReportFrequency.none,
            is_active=True,
        )
        db.add(division_head)
        db.flush()

        # Office Manager
        office_manager = User(
            name="מנהלת משרד",
            email="office.manager@boi.org.il",
            hashed_password=hash_password("OfficeManager1!"),
            role_type=RoleType.office_manager,
            parent_id=division_head.id,
            report_frequency=ReportFrequency.none,
            is_active=True,
        )
        db.add(office_manager)
        db.flush()

        # Section Head A
        section_head_a = User(
            name="ראש מדור א'",
            email="section.head.a@boi.org.il",
            hashed_password=hash_password("SectionA1!"),
            role_type=RoleType.section_head,
            parent_id=division_head.id,
            report_frequency=ReportFrequency.weekly,
            is_active=True,
        )
        db.add(section_head_a)
        db.flush()

        # Section Head B
        section_head_b = User(
            name="ראש מדור ב'",
            email="section.head.b@boi.org.il",
            hashed_password=hash_password("SectionB1!"),
            role_type=RoleType.section_head,
            parent_id=division_head.id,
            report_frequency=ReportFrequency.weekly,
            is_active=True,
        )
        db.add(section_head_b)
        db.flush()

        # Economists under Section A
        economists_a = [
            ("כלכלן א.1", "econ.a1@boi.org.il"),
            ("כלכלן א.2", "econ.a2@boi.org.il"),
            ("כלכלן א.3", "econ.a3@boi.org.il"),
        ]
        for name, email in economists_a:
            db.add(User(
                name=name, email=email,
                hashed_password=hash_password("Econ1234!"),
                role_type=RoleType.economist,
                parent_id=section_head_a.id,
                report_frequency=ReportFrequency.weekly,
                is_active=True,
            ))

        # Economists under Section B
        economists_b = [
            ("כלכלן ב.1", "econ.b1@boi.org.il"),
            ("כלכלן ב.2", "econ.b2@boi.org.il"),
        ]
        for name, email in economists_b:
            db.add(User(
                name=name, email=email,
                hashed_password=hash_password("Econ1234!"),
                role_type=RoleType.economist,
                parent_id=section_head_b.id,
                report_frequency=ReportFrequency.weekly,
                is_active=True,
            ))

        # Students under Division Head
        students = [
            ("סטודנט 1", "student1@boi.org.il"),
            ("סטודנט 2", "student2@boi.org.il"),
        ]
        for name, email in students:
            db.add(User(
                name=name, email=email,
                hashed_password=hash_password("Student1234!"),
                role_type=RoleType.student,
                parent_id=division_head.id,
                report_frequency=ReportFrequency.daily,
                is_active=True,
            ))

        db.commit()
        logger.info("Database seeded successfully. Division Head: yossi.saadon@boi.org.il / Admin1234!")
    except Exception as e:
        logger.error(f"Seeding error: {e}")
        db.rollback()
    finally:
        db.close()
