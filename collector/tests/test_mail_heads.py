from datetime import UTC, datetime

import pytest

import mail_heads
from mail_heads import compose, send, settings

NOW = datetime(2026, 9, 14, 21, 20, tzinfo=UTC)
CONFIG = {"HEAD_HASH_SMTP_HOST": "smtp.example.org", "HEAD_HASH_SMTP_PORT": "587",
          "HEAD_HASH_SMTP_USERNAME": "witness", "HEAD_HASH_SMTP_PASSWORD": "not-a-real-password",
          "HEAD_HASH_MAIL_FROM": "ledger@example.org", "HEAD_HASH_MAIL_TO": "witness@example.net"}


def walk(table, ok=True, verified_at="2026-09-14T21:17:05.123456+00:00", rows=10):
    return {"table_name": table, "verified_at": verified_at, "rows_checked": rows,
            "first_seq": 1 if rows else None, "head_seq": rows or None,
            "head_row_hash": ("ab" * 32) if rows else None, "breaks": 0 if ok else 1,
            "first_break_seq": None if ok else 4,
            "first_break_problem": None if ok else "row_hash does not match row contents",
            "ok": ok}


def test_every_setting_is_required_and_only_names_are_reported():
    with pytest.raises(RuntimeError) as missing:
        settings({**CONFIG, "HEAD_HASH_SMTP_PASSWORD": "", "HEAD_HASH_MAIL_TO": ""})
    assert "HEAD_HASH_SMTP_PASSWORD, HEAD_HASH_MAIL_TO" in str(missing.value)
    assert "witness@example.net" not in str(missing.value)
    assert settings(CONFIG) == CONFIG


def test_message_carries_both_heads():
    message = compose([walk("samples"), walk("failed_samples", rows=0)], NOW,
                      "ledger@example.org", "witness@example.net", "smatt92/ledger")
    body = message.get_content()
    assert message["Subject"] == "[corridor ledger] chain heads 2026-09-14: intact"
    assert "head row_hash  " + "ab" * 32 in body and "seq            1..10" in body
    assert "head row_hash  (empty chain)" in body and "seq            empty" in body
    assert "Repository: smatt92/ledger" in body


def test_a_broken_chain_is_mailed_as_broken():
    message = compose([walk("samples", ok=False), walk("failed_samples")], NOW, "a@b", "c@d", "")
    assert message["Subject"].endswith("BROKEN")
    assert "first at seq 4: row_hash does not match row contents" in message.get_content()


def test_a_stale_walk_is_refused():
    with pytest.raises(RuntimeError, match="not recorded"):
        compose([walk("samples", verified_at="2026-09-13T21:17:05+00:00"),
                 walk("failed_samples")], NOW, "a@b", "c@d", "")


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, **kwargs):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, message):
        self.calls.append(("send", message["Subject"]))


def test_send_uses_tls_on_either_port(monkeypatch):
    monkeypatch.setattr(mail_heads.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail_heads.smtplib, "SMTP_SSL", FakeSMTP)
    message = compose([walk("samples"), walk("failed_samples")], NOW, "a@b", "c@d", "")
    FakeSMTP.instances = []
    send(message, CONFIG)
    send(message, {**CONFIG, "HEAD_HASH_SMTP_PORT": "465"})
    starttls, implicit = FakeSMTP.instances
    assert starttls.calls == ["starttls", ("login", "witness"), ("send", message["Subject"])]
    assert implicit.port == 465 and implicit.calls[0] == ("login", "witness")
