from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from website import db
from website.models import ROLE_CLIENT, User
from website.utils.datetime_utils import string_to_datetime
from website.utils.security import sanitize_str_input

auth = Blueprint("auth", __name__)


def _home_endpoint_for(user):
    return "app.home"


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(_home_endpoint_for(current_user)))

    if request.method == "POST":
        email = sanitize_str_input(request.form.get("email", "")).strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("No account exists for that email.", "error")
        elif user.status != 1:
            flash("This account is disabled. Contact an admin.", "error")
        elif not check_password_hash(user.password, password):
            flash("Incorrect password. Try again.", "error")
        else:
            login_user(user, remember=True)
            flash(f"Welcome back, {user.display_name}.", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for(_home_endpoint_for(user)))

    return render_template("login.html", user=current_user)


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


@auth.route("/sign-up", methods=["GET", "POST"])
def sign_up():
    if current_user.is_authenticated:
        return redirect(url_for("app.home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        name_first = (request.form.get("name_first") or "").strip()
        name_last = (request.form.get("name_last") or "").strip()
        passwd = request.form.get("passwd") or ""
        passwd_conf = request.form.get("passwd_conf") or ""
        date_birth = string_to_datetime(request.form.get("date_birth") or "")
        address = (request.form.get("address") or "").strip()

        if len(email) < 5 or "@" not in email:
            flash("Enter a valid email address.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered. Log in instead.", "error")
        elif len(name_first) < 1 or len(name_last) < 1:
            flash("First and last name are required.", "error")
        elif len(passwd) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif passwd != passwd_conf:
            flash("Passwords do not match.", "error")
        else:
            new_user = User(
                email=email,
                name_first=name_first,
                name_last=name_last,
                password=generate_password_hash(passwd),
                date_birth=date_birth,
                address=address,
                role=ROLE_CLIENT,
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user, remember=True)
            flash("Account created. You can book a session now.", "success")
            return redirect(url_for("app.home"))

    return render_template("sign_up.html", user=current_user)


@auth.route("/contact")
def contact():
    return render_template("info.html", user=current_user, page_title="Contact", heading="Contact")


@auth.route("/about")
def about():
    return render_template("info.html", user=current_user, page_title="About", heading="About us")
