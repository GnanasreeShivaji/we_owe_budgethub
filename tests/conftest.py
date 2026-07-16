import pytest

from app import create_app, db
from app.models import User


@pytest.fixture
def app():
    app = create_app("app.config.TestConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    def _make(name="Test User", email="test@srh.de", password="Str0ng!pw", confirmed=True):
        u = User(name=name, email=User.normalize_email(email), is_confirmed=confirmed)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u
    return _make


def register(client, name="Loki", email="loki@srh.de", password="Str0ng!pw"):
    return client.post(
        "/auth/register",
        data={"name": name, "email": email, "password": password, "confirm": password},
        follow_redirects=True,
    )


def login(client, email="loki@srh.de", password="Str0ng!pw"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
