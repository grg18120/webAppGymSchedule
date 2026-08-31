from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from website.models import User
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


@auth.route("/contact")
def contact():
    return render_template("info.html", user=current_user, page_title="Contact", heading="Contact")


@auth.route("/about")
def about():
    return render_template("info.html", user=current_user, page_title="About", heading="About us")
