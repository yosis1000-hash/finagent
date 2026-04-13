import json

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import OrgConfig

settings = get_settings()


def build_default_config() -> dict:
    return {
        "product_name": "FinAgent",
        "org_name": "האגף הפיננסי",
        "unit_label": "יחידה ארגונית",
        "inbox_email": settings.gmail_address,
        "smtp_from": settings.smtp_from,
        "app_url": settings.app_url,
        "role_labels": {
            "division_head": "ראש אגף",
            "department_head": "ראש מחלקה",
            "section_head": "ראש תחום",
            "office_manager": "מנהלת משרד",
            "economist": "כלכלן",
            "student": "סטודנט",
            "advisor": "יועץ",
            "team_lead": "ראש צוות",
            "external": "חיצוני",
        },
    }


def merge_org_config(stored: dict | None = None, overrides: dict | None = None) -> dict:
    stored = stored or {}
    overrides = overrides or {}
    default_config = build_default_config()

    merged = {**default_config, **stored, **overrides}
    merged["role_labels"] = {
        **default_config["role_labels"],
        **stored.get("role_labels", {}),
        **overrides.get("role_labels", {}),
    }
    return merged


def ensure_org_config(db: Session) -> OrgConfig:
    row = db.query(OrgConfig).first()
    if row and row.config_json:
        return row

    config_json = json.dumps(build_default_config(), ensure_ascii=False)
    if row is None:
        row = OrgConfig(config_json=config_json)
        db.add(row)
    else:
        row.config_json = config_json
    db.commit()
    db.refresh(row)
    return row


def load_org_config(db: Session) -> dict:
    row = ensure_org_config(db)
    try:
        stored = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        stored = {}

    merged = merge_org_config(stored)
    if merged != stored:
        row.config_json = json.dumps(merged, ensure_ascii=False)
        db.commit()
        db.refresh(row)
    return merged


def save_org_config(db: Session, payload: dict) -> dict:
    row = ensure_org_config(db)
    try:
        current = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        current = {}

    merged = merge_org_config(current, payload)
    row.config_json = json.dumps(merged, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return merged
