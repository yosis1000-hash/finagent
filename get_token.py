"""
Gmail OAuth2 - Get Refresh Token
Run this once to authorize the app and receive a refresh token.
The token is saved to .env automatically.
"""
import json
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
ENV_FILE = Path(__file__).parent / ".env"
ENV_EXAMPLE_FILE = Path(__file__).parent / ".env.example"


def update_env(key: str, value: str):
    """Insert or update a key=value line in .env."""
    if not ENV_FILE.exists():
        if ENV_EXAMPLE_FILE.exists():
            ENV_FILE.write_text(ENV_EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_FILE.write_text("", encoding="utf-8")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: credentials.json not found at {CREDENTIALS_FILE}")
        return

    print("Starting Gmail OAuth2 flow...")
    print("A browser window will open. Log in with the FinAgent Gmail account and approve permissions.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    refresh_token = creds.refresh_token
    client_id = creds.client_id
    client_secret = creds.client_secret

    print("\n" + "=" * 60)
    print("SUCCESS! Tokens received:")
    print(f"  GMAIL_CLIENT_ID     = {client_id}")
    print(f"  GMAIL_CLIENT_SECRET = {client_secret}")
    print(f"  GMAIL_REFRESH_TOKEN = {refresh_token}")
    print("=" * 60)

    update_env("GMAIL_CLIENT_ID", client_id)
    update_env("GMAIL_CLIENT_SECRET", client_secret)
    update_env("GMAIL_REFRESH_TOKEN", refresh_token)

    print(f"\nValues saved to {ENV_FILE}")
    print("Done. You can now run the app.")


if __name__ == "__main__":
    main()
