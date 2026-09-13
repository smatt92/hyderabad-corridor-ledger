"""Nightly head-hash mail-out: python collector/mail_heads.py

After chain.py records a walk of both chains, this mails the head of each to
a mailbox outside the systems the chains audit. A head hash stored only in the
database it describes proves nothing: whoever can rewrite the chain can
rewrite the record of its head too. A copy in a separate mailbox, which no one
with database or repository access can edit, lets anyone check later that the
chain in the database still extends the head mailed on an earlier night.

Settings come from GitHub Actions secrets, never from files:
  HEAD_HASH_SMTP_HOST, HEAD_HASH_SMTP_PORT, HEAD_HASH_SMTP_USERNAME,
  HEAD_HASH_SMTP_PASSWORD, HEAD_HASH_MAIL_FROM, HEAD_HASH_MAIL_TO
Port 465 uses implicit TLS; any other port must offer STARTTLS. The step fails
loudly when a setting is missing, tonight's walk is not recorded, or the send
fails. It never prints the password or the addresses.
"""

import os
import smtplib
import ssl
import sys
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

SETTINGS = (
    "HEAD_HASH_SMTP_HOST", "HEAD_HASH_SMTP_PORT", "HEAD_HASH_SMTP_USERNAME",
    "HEAD_HASH_SMTP_PASSWORD", "HEAD_HASH_MAIL_FROM", "HEAD_HASH_MAIL_TO",
)
CHAINS = ("samples", "failed_samples")
MAX_AGE = timedelta(hours=2)  # the walk this step mails must be tonight's


def settings(env) -> dict[str, str]:
    missing = [name for name in SETTINGS if not env.get(name)]
    if missing:
        raise RuntimeError("head-hash mail-out is not configured; missing secrets: "
                           + ", ".join(missing))
    return {name: env[name] for name in SETTINGS}


def latest_walks(db) -> list[dict]:
    walks = []
    for table in CHAINS:
        _, found = db.request("GET", "chain_verifications", [
            ("select", "*"), ("table_name", f"eq.{table}"), ("order", "id.desc"), ("limit", "1"),
        ])
        if not found:
            raise RuntimeError(f"no recorded walk of the {table} chain")
        walks.append(found[0])
    return walks


def compose(walks: list[dict], now: datetime, sender: str, recipient: str,
            repository: str) -> EmailMessage:
    stale = [w["table_name"] for w in walks
             if now - datetime.fromisoformat(w["verified_at"]) > MAX_AGE]
    if stale:
        raise RuntimeError(f"the latest walk of {', '.join(stale)} is older than {MAX_AGE}: "
                           "tonight's walk was not recorded, so there is no head to mail")
    intact = all(w["ok"] for w in walks)
    message = EmailMessage()
    message["Subject"] = (f"[corridor ledger] chain heads {now:%Y-%m-%d}: "
                          f"{'intact' if intact else 'BROKEN'}")
    message["From"] = sender
    message["To"] = recipient
    lines = [f"Hash chain heads recorded {now:%Y-%m-%d %H:%M} UTC.", ""]
    for w in walks:
        breaks = f"{w['breaks']}"
        if w["breaks"]:
            breaks += f", first at seq {w['first_break_seq']}: {w['first_break_problem']}"
        span = f"{w['first_seq']}..{w['head_seq']}" if w["rows_checked"] else "empty"
        lines += [
            w["table_name"],
            f"  walked at      {w['verified_at']}",
            f"  rows checked   {w['rows_checked']}",
            f"  seq            {span}",
            f"  head row_hash  {w['head_row_hash'] or '(empty chain)'}",
            f"  breaks         {breaks}",
            "",
        ]
    lines += [
        "Keep this message. It is a copy of each chain's head held outside the database.",
        "If the database's chain ever fails to extend a head mailed here, the chain",
        "was rewritten after that night.",
        "",
        f"Repository: {repository}" if repository else "",
    ]
    message.set_content("\n".join(lines).rstrip() + "\n")
    return message


def send(message: EmailMessage, config: dict[str, str]) -> None:
    host, port = config["HEAD_HASH_SMTP_HOST"], int(config["HEAD_HASH_SMTP_PORT"])
    context = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
    with smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(config["HEAD_HASH_SMTP_USERNAME"], config["HEAD_HASH_SMTP_PASSWORD"])
        smtp.send_message(message)


def main() -> int:
    from store import Database

    try:
        config = settings(os.environ)
        message = compose(latest_walks(Database.from_env()), datetime.now(UTC),
                          config["HEAD_HASH_MAIL_FROM"], config["HEAD_HASH_MAIL_TO"],
                          os.environ.get("GITHUB_REPOSITORY", ""))
        send(message, config)
    except (RuntimeError, ValueError, OSError, smtplib.SMTPException) as exc:
        print(f"::error::head-hash mail-out failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"mailed the chain heads: {message['Subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
