from collections.abc import Iterable

from app.config import get_settings

settings = get_settings()
LEGACY_MAILBOX_ALIASES = {"finagent@gmail.com", "finagent"}


def build_mailbox_aliases(primary_email: str | None = None) -> set[str]:
    email = (primary_email or settings.gmail_address or "").strip().lower()
    aliases = set(LEGACY_MAILBOX_ALIASES)

    if email:
        aliases.add(email)
        local_part = email.split("@", 1)[0]
        aliases.add(local_part)

        local_part_dotless = local_part.replace(".", "")
        aliases.add(local_part_dotless)

        if email.endswith("@gmail.com"):
            aliases.add(f"{local_part_dotless}@gmail.com")

    return {alias for alias in aliases if alias}


def is_addressed_to_agent(
    recipients: Iterable[str],
    primary_email: str | None = None,
) -> bool:
    normalized_recipients = {recipient.strip().lower() for recipient in recipients}
    return bool(normalized_recipients & build_mailbox_aliases(primary_email))


def body_mentions_agent(body: str, primary_email: str | None = None) -> bool:
    lowered_body = (body or "").lower()
    return any(f"@{alias}" in lowered_body for alias in build_mailbox_aliases(primary_email))
