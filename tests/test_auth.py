"""US-01 acceptance-criteria tests."""
from app.models import User
from tests.conftest import login, register


def test_register_creates_user_and_lands_on_dashboard(client, app):
    resp = register(client)
    assert resp.status_code == 200
    assert b"Your groups" in resp.data          # redirected to dashboard
    with app.app_context():
        assert User.query.filter_by(email="loki@srh.de").count() == 1


def test_password_is_hashed_not_plaintext(client, app):
    register(client)
    with app.app_context():
        u = User.query.filter_by(email="loki@srh.de").first()
        assert u.password_hash != "Str0ng!pw"
        assert u.check_password("Str0ng!pw")


def test_weak_password_rejected(client):
    resp = client.post(
        "/auth/register",
        data={"name": "X", "email": "x@srh.de", "password": "weak", "confirm": "weak"},
        follow_redirects=True,
    )
    assert b"Password needs" in resp.data


def test_invalid_email_rejected(client):
    resp = client.post(
        "/auth/register",
        data={"name": "X", "email": "not-an-email", "password": "Str0ng!pw", "confirm": "Str0ng!pw"},
        follow_redirects=True,
    )
    assert b"valid email" in resp.data


def test_duplicate_email_blocked(client, app):
    register(client)
    client.get("/auth/logout")               # a different, anonymous visitor
    resp = register(client)                  # tries the same email
    assert b"already exists" in resp.data
    with app.app_context():
        assert User.query.filter_by(email="loki@srh.de").count() == 1


def test_email_is_case_insensitive(client, app):
    register(client, email="Loki@SRH.de")
    with app.app_context():
        assert User.query.filter_by(email="loki@srh.de").count() == 1


def test_login_wrong_password_fails(client, make_user):
    make_user(email="a@srh.de")
    resp = client.post(
        "/auth/login", data={"email": "a@srh.de", "password": "wrong"}, follow_redirects=True
    )
    assert b"Incorrect password" in resp.data


def test_login_unregistered_email_suggests_sign_up(client):
    resp = client.post(
        "/auth/login",
        data={"email": "unknown@srh.de", "password": "Str0ng!pw"},
        follow_redirects=True,
    )
    assert b"email is not registered" in resp.data
    assert b"Please sign up" in resp.data


def test_login_success_redirects_to_dashboard(client, make_user):
    make_user(email="a@srh.de")
    resp = login(client, email="a@srh.de")
    assert b"Your groups" in resp.data


def test_password_reset_flow(client, app, make_user):
    from app.services.email import generate_token
    from app.auth.routes import RESET_SALT

    make_user(email="a@srh.de")
    with app.app_context():
        token = generate_token("a@srh.de", salt=RESET_SALT)
    resp = client.post(
        f"/auth/reset/{token}",
        data={"password": "N3w!passw0rd", "confirm": "N3w!passw0rd"},
        follow_redirects=True,
    )
    assert b"Password updated" in resp.data
    assert login(client, email="a@srh.de", password="N3w!passw0rd").status_code == 200


def test_email_confirmation_flow(client, app, make_user):
    from app.auth.routes import CONFIRM_SALT
    from app.services.email import generate_token

    make_user(email="a@srh.de", confirmed=False)
    with app.app_context():
        token = generate_token("a@srh.de", salt=CONFIRM_SALT)

    resp = client.get(f"/auth/confirm/{token}", follow_redirects=True)
    assert b"Email confirmed" in resp.data
    with app.app_context():
        assert User.query.filter_by(email="a@srh.de").first().is_confirmed


def test_forgot_password_writes_reset_email(client, app, make_user):
    make_user(email="a@srh.de")
    resp = client.post(
        "/auth/forgot", data={"email": "a@srh.de"}, follow_redirects=True
    )

    assert b"If that email is registered" in resp.data
    outbox = app.instance_path + "/outbox"
    from pathlib import Path

    messages = list(Path(outbox).glob("*_a_at_srh.de.txt"))
    assert messages
    assert "Reset your WE_OWE password" in messages[-1].read_text(encoding="utf-8")
