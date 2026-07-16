"""US-02: Group Creation & Management.

Covers the Trello checklist for US-02: create group, edit group details,
add members, remove members, assign roles, view members, delete group.

Isolation: a user only ever reaches a group they hold a Membership for; the
_require_membership / _require_admin guards enforce this on every route.
"""
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user, login_required

from .. import db
from ..models import Group, Invitation, Membership, User
from ..services.email import send_email
from .forms import GroupForm, InviteForm

groups_bp = Blueprint("groups", __name__, url_prefix="/groups")


# --- access guards (these are what make group logs isolated) ---
def _get_group_or_404(group_id):
    return db.session.get(Group, group_id) or abort(404)


def _require_membership(group_id):
    group = _get_group_or_404(group_id)
    if not group.has_member(current_user):
        abort(403)
    return group


def _require_admin(group_id):
    group = _get_group_or_404(group_id)
    if not group.is_admin(current_user):
        abort(403)
    return group


def admin_only(view):
    @wraps(view)
    def wrapped(group_id, *args, **kwargs):
        _require_admin(group_id)
        return view(group_id, *args, **kwargs)
    return wrapped


# --- dashboard ---
@groups_bp.route("/")
@login_required
def dashboard():
    groups = current_user.groups  # only groups the user belongs to
    return render_template("groups/dashboard.html", groups=groups, form=GroupForm())


# --- create ---
@groups_bp.route("/create", methods=["POST"])
@login_required
def create_group():
    form = GroupForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        # US-02: a user's group names must be unique
        exists = Group.query.filter_by(owner_id=current_user.id, name=name).first()
        if exists:
            flash(f"You already have a group named '{name}'.", "error")
            return redirect(url_for("groups.dashboard"))

        group = Group(name=name, description=(form.description.data or "").strip(), owner=current_user)
        db.session.add(group)
        db.session.flush()  # get group.id
        # Creator joins as admin
        db.session.add(Membership(user_id=current_user.id, group_id=group.id, role=Membership.ADMIN))
        db.session.commit()
        flash(f"Group '{name}' created.", "success")
        return redirect(url_for("groups.view_group", group_id=group.id))

    for errors in form.errors.values():
        for err in errors:
            flash(err, "error")
    return redirect(url_for("groups.dashboard"))


# --- view / members ---
@groups_bp.route("/<int:group_id>")
@login_required
def view_group(group_id):
    group = _require_membership(group_id)
    memberships = sorted(group.memberships, key=lambda m: (m.role != Membership.ADMIN, m.user.name.lower()))
    pending = [i for i in group.invitations if i.status == Invitation.PENDING]
    return render_template(
        "groups/group_detail.html",
        group=group,
        memberships=memberships,
        pending=pending,
        is_admin=group.is_admin(current_user),
        invite_form=InviteForm(),
        edit_form=GroupForm(obj=group),
        Membership=Membership,
        expenses=sorted(group.expenses, key=lambda expense: expense.expense_date, reverse=True),
    )


# --- edit ---
@groups_bp.route("/<int:group_id>/edit", methods=["POST"])
@login_required
@admin_only
def edit_group(group_id):
    group = _get_group_or_404(group_id)
    form = GroupForm()
    if form.validate_on_submit():
        new_name = form.name.data.strip()
        clash = Group.query.filter(
            Group.owner_id == group.owner_id,
            Group.name == new_name,
            Group.id != group.id,
        ).first()
        if clash:
            flash(f"Another of your groups is already named '{new_name}'.", "error")
        else:
            group.name = new_name
            group.description = (form.description.data or "").strip()
            db.session.commit()
            flash("Group details updated.", "success")
    return redirect(url_for("groups.view_group", group_id=group.id))


# --- delete ---
@groups_bp.route("/<int:group_id>/delete", methods=["POST"])
@login_required
@admin_only
def delete_group(group_id):
    group = _get_group_or_404(group_id)
    name = group.name
    db.session.delete(group)  # cascades memberships + invitations
    db.session.commit()
    flash(f"Group '{name}' deleted.", "info")
    return redirect(url_for("groups.dashboard"))

@groups_bp.route(
    "/<int:group_id>/invitations/<int:invitation_id>/cancel",
    methods=["POST"],
)
@login_required
@admin_only
def cancel_invitation(group_id, invitation_id):
    group = _get_group_or_404(group_id)

    invitation = Invitation.query.filter_by(
        id=invitation_id,
        group_id=group.id,
        status=Invitation.PENDING,
    ).first_or_404()

    db.session.delete(invitation)
    db.session.commit()

    flash("Pending invitation removed.", "info")
    return redirect(
        url_for("groups.view_group", group_id=group.id)
    )

# --- invite / add member ---
@groups_bp.route("/<int:group_id>/invite", methods=["POST"])
@login_required
@admin_only
def invite_member(group_id):
    group = _get_group_or_404(group_id)
    form = InviteForm()
    if not form.validate_on_submit():
        flash("Enter a valid email address.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id))

    email = User.normalize_email(form.email.data)
    role = form.role.data if form.role.data in Membership.ROLES else Membership.MEMBER
    user = User.query.filter_by(email=email).first()

    if user:
        if group.has_member(user):
            flash(f"{user.name} is already in this group.", "info")
        else:
            db.session.add(Membership(user_id=user.id, group_id=group.id, role=role))
            db.session.commit()
            send_email(
                email,
                f"You've been added to '{group.name}' on WE_OWE",
                f"{current_user.name} added you to the group '{group.name}'.",
            )
            flash(f"{user.name} added to the group.", "success")
    else:
        # Not registered yet -> pending invitation, claimed on sign-up
        existing = Invitation.query.filter_by(
            group_id=group.id, email=email, status=Invitation.PENDING
        ).first()
        if existing:
            flash("That email already has a pending invite.", "info")
            return redirect(url_for("groups.view_group", group_id=group.id))

        invitation = Invitation(
            group_id=group.id,
            email=email,
            role=role,
            invited_by_id=current_user.id,
        )

        db.session.add(invitation)
        db.session.commit()

        link = url_for("auth.register", _external=True)

        try:
            delivered = send_email(
                email,
                f"You're invited to '{group.name}' on WE_OWE",
                f"{current_user.name} invited you to '{group.name}'. "
                f"Create an account with this email to join:\n{link}",
            )

            if delivered:
                flash("Invitation email sent successfully.", "success")
            else:
                flash(
                    "Invitation created, but email delivery is disabled. "
                    "Check the local outbox or configure SMTP.",
                    "info",
                )

        except RuntimeError as error:
            db.session.delete(invitation)
            db.session.commit()
            flash(str(error), "error")

    return redirect(url_for("groups.view_group", group_id=group.id))


# --- remove member ---
@groups_bp.route("/<int:group_id>/members/<int:user_id>/remove", methods=["POST"])
@login_required
@admin_only
def remove_member(group_id, user_id):
    group = _get_group_or_404(group_id)
    if user_id == group.owner_id:
        flash("The group owner can't be removed.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id))

    membership = Membership.query.filter_by(group_id=group.id, user_id=user_id).first_or_404()
    name = membership.user.name
    db.session.delete(membership)
    db.session.commit()
    flash(f"{name} removed from the group.", "info")
    return redirect(url_for("groups.view_group", group_id=group.id))


# --- assign role ---
@groups_bp.route("/<int:group_id>/members/<int:user_id>/role", methods=["POST"])
@login_required
@admin_only
def change_role(group_id, user_id):
    group = _get_group_or_404(group_id)
    if user_id == group.owner_id:
        flash("The owner is always an admin.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id))

    membership = Membership.query.filter_by(group_id=group.id, user_id=user_id).first_or_404()
    membership.role = Membership.MEMBER if membership.role == Membership.ADMIN else Membership.ADMIN
    db.session.commit()
    flash(f"{membership.user.name} is now a{'n admin' if membership.role == Membership.ADMIN else ' member'}.", "success")
    return redirect(url_for("groups.view_group", group_id=group.id))
