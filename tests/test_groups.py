"""US-02 acceptance-criteria tests, including group isolation."""
from app import db
from app.models import Group, Invitation, Membership, User
from tests.conftest import login, register


def _make_group(client, name="Flat 4B", description="Summer 2026"):
    return client.post(
        "/groups/create",
        data={"name": name, "description": description},
        follow_redirects=True,
    )


def test_create_group_makes_creator_admin(client, app):
    register(client)
    _make_group(client)
    with app.app_context():
        g = Group.query.filter_by(name="Flat 4B").first()
        assert g is not None
        assert g.member_role(g.owner) == Membership.ADMIN


def test_duplicate_group_name_per_user_blocked(client):
    register(client)
    _make_group(client)
    resp = _make_group(client)  # same name again
    assert b"already have a group named" in resp.data


def test_invite_registered_user_adds_membership(client, app, make_user):
    make_user(name="Ananya", email="ananya@srh.de")
    register(client)  # Loki, logged in
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id
    resp = client.post(
        f"/groups/{gid}/invite",
        data={"email": "ananya@srh.de", "role": "member"},
        follow_redirects=True,
    )
    assert b"added to the group" in resp.data
    with app.app_context():
        g = db.session.get(Group, gid)
        assert any(m.user.email == "ananya@srh.de" for m in g.memberships)


def test_invite_unregistered_email_creates_pending_invitation(client, app):
    register(client)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id
    client.post(f"/groups/{gid}/invite", data={"email": "new@srh.de", "role": "member"},
                follow_redirects=True)
    with app.app_context():
        assert Invitation.query.filter_by(email="new@srh.de", status="pending").count() == 1


def test_duplicate_pending_invitation_is_not_created(client, app):
    register(client)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id

    data = {"email": "new@srh.de", "role": "member"}
    client.post(f"/groups/{gid}/invite", data=data, follow_redirects=True)
    resp = client.post(f"/groups/{gid}/invite", data=data, follow_redirects=True)

    assert resp.status_code == 200
    assert b"already has a pending invite" in resp.data
    with app.app_context():
        assert Invitation.query.filter_by(
            group_id=gid, email="new@srh.de", status=Invitation.PENDING
        ).count() == 1


def test_pending_invite_claimed_on_registration(client, app):
    register(client)                      # Loki (admin)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id
    client.post(f"/groups/{gid}/invite", data={"email": "kavin@srh.de", "role": "member"},
                follow_redirects=True)
    client.get("/auth/logout")
    register(client, name="Kavin", email="kavin@srh.de")  # signs up with invited email
    with app.app_context():
        g = db.session.get(Group, gid)
        assert any(m.user.email == "kavin@srh.de" for m in g.memberships)


def test_change_role_and_remove_member(client, app, make_user):
    make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id
        aid = User.query.filter_by(email="ananya@srh.de").first().id
    client.post(f"/groups/{gid}/invite", data={"email": "ananya@srh.de", "role": "member"},
                follow_redirects=True)
    client.post(f"/groups/{gid}/members/{aid}/role", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Group, gid).member_role(db.session.get(User, aid)) == "admin"
    client.post(f"/groups/{gid}/members/{aid}/remove", follow_redirects=True)
    with app.app_context():
        assert Membership.query.filter_by(group_id=gid, user_id=aid).count() == 0


def test_edit_group_details_and_view_members(client, app, make_user):
    make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id

    client.post(
        f"/groups/{gid}/invite",
        data={"email": "ananya@srh.de", "role": "member"},
        follow_redirects=True,
    )
    resp = client.post(
        f"/groups/{gid}/edit",
        data={"name": "Flat 5B", "description": "Updated description"},
        follow_redirects=True,
    )

    assert b"Flat 5B" in resp.data
    assert b"Updated description" in resp.data
    assert b"Ananya" in resp.data
    with app.app_context():
        group = db.session.get(Group, gid)
        assert group.name == "Flat 5B"
        assert group.description == "Updated description"


def test_non_admin_cannot_manage_group(client, app, make_user):
    owner = make_user(name="Owner", email="owner@srh.de")
    member = make_user(name="Member", email="member@srh.de")
    with app.app_context():
        group = Group(name="Private Group", owner_id=owner.id)
        db.session.add(group)
        db.session.flush()
        db.session.add_all([
            Membership(user_id=owner.id, group_id=group.id, role=Membership.ADMIN),
            Membership(user_id=member.id, group_id=group.id, role=Membership.MEMBER),
        ])
        db.session.commit()
        gid, owner_id = group.id, owner.id

    login(client, email="member@srh.de")
    requests = [
        (f"/groups/{gid}/edit", {"name": "Changed", "description": ""}),
        (f"/groups/{gid}/delete", {}),
        (f"/groups/{gid}/invite", {"email": "new@srh.de", "role": "member"}),
        (f"/groups/{gid}/members/{owner_id}/remove", {}),
        (f"/groups/{gid}/members/{owner_id}/role", {}),
    ]
    for url, data in requests:
        assert client.post(url, data=data).status_code == 403

    with app.app_context():
        assert db.session.get(Group, gid).name == "Private Group"


def test_group_isolation_non_member_forbidden(client, app, make_user):
    # Ananya owns a private group
    ananya = make_user(name="Ananya", email="ananya@srh.de")
    with app.app_context():
        g = Group(name="Ananya's Trip", owner_id=ananya.id)
        db.session.add(g)
        db.session.flush()
        db.session.add(Membership(user_id=ananya.id, group_id=g.id, role="admin"))
        db.session.commit()
        gid = g.id
    # Loki logs in and must NOT be able to see it
    register(client)
    resp = client.get(f"/groups/{gid}")
    assert resp.status_code == 403
    dash = client.get("/groups/")
    assert b"Ananya's Trip" not in dash.data


def test_owner_cannot_be_removed(client, app):
    register(client)
    _make_group(client)
    with app.app_context():
        g = Group.query.filter_by(name="Flat 4B").first()
        gid, oid = g.id, g.owner_id
    resp = client.post(f"/groups/{gid}/members/{oid}/remove", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():  # owner membership must still exist
        assert Membership.query.filter_by(group_id=gid, user_id=oid).count() == 1


def test_delete_group_cascades(client, app):
    register(client)
    _make_group(client)
    with app.app_context():
        gid = Group.query.filter_by(name="Flat 4B").first().id
    client.post(f"/groups/{gid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Group, gid) is None
        assert Membership.query.filter_by(group_id=gid).count() == 0
