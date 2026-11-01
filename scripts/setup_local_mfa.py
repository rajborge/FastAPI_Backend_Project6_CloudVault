"""Create a persistent local MFA key without printing it or editing .env."""
import base64
from pathlib import Path
import secrets
import subprocess

root = Path(__file__).resolve().parents[1]
destination = root / ".env.mfa.local"
if subprocess.run(["git", "check-ignore", "-q", str(destination)], cwd=root).returncode:
    raise SystemExit("Refusing to create a key outside Git-ignored storage.")
try:
    with destination.open("x", encoding="utf-8") as output:
        output.write("MFA_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "\n")
    print("Local MFA encryption key created in Git-ignored storage. Keep this file across restarts.")
except FileExistsError:
    print("Local MFA key file already exists; preserved without changes.")
