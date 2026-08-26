from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import extract
from werkzeug.security import generate_password_hash

from website import db
from website.models import ROLE_ADMIN, ROLE_CLIENT, ROLE_INSTRUCTOR, GymSession, User
from website.utils import booking
from website.utils.datetime_utils import get_days_in_month, string_to_datetime
from website.utils.security import role_required

app = Blueprint("app", __name__)


def _parse_day(year, month, day):
    try:
        return datetime(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def _session_or_404(session_id):
    session = db.session.get(GymSession, session_id)
    if not session:
        abort(404)
    return session


@app.route("/")
def home():
    dashboard = None
    if current_user.is_authenticated:
        now = datetime.now()
        if current_user.is_admin:
            dashboard = {
                "user_count": User.query.count(),
                "instructor_count": User.query.filter_by(role=ROLE_INSTRUCTOR).count(),
                "upcoming": GymSession.query.filter(
                    GymSession.datetime_start >= now,
                    GymSession.status != "cancelled",
                )
                .order_by(GymSession.datetime_start)
                .limit(5)
                .all(),
            }
        elif current_user.is_instructor:
            dashboard = {
                "upcoming": GymSession.query.filter(
                    GymSession.instructor_id == current_user.id,
                    GymSession.datetime_start >= now,
                    GymSession.status != "cancelled",
                )
                .order_by(GymSession.datetime_start)
                .limit(5)
                .all(),
            }
        else:
            dashboard = {
                "upcoming": GymSession.query.filter(
                    GymSession.client_id == current_user.id,
                    GymSession.datetime_start >= now,
                    GymSession.status == "booked",
                )
                .order_by(GymSession.datetime_start)
                .limit(5)
                .all(),
            }
    return render_template("home.html", user=current_user, dashboard=dashboard)


@app.route("/book", methods=["GET", "POST"])
@login_required
def book_calendar():
    current_date = datetime.now()
    if request.method == "POST":
        selected_month = int(request.form.get("month", current_date.month))
        selected_year = int(request.form.get("year", current_date.year))
    else:
        selected_month = int(request.args.get("month", current_date.month))
        selected_year = int(request.args.get("year", current_date.year))

    instructor_id = request.args.get("instructor_id", type=int)
    days = get_days_in_month(selected_year, selected_month)

    query = GymSession.query.filter(
        extract("month", GymSession.datetime_start) == selected_month,
        extract("year", GymSession.datetime_start) == selected_year,
        GymSession.status != "cancelled",
    )
    if current_user.is_instructor:
        query = query.filter(GymSession.instructor_id == current_user.id)
    elif instructor_id:
        query = query.filter(GymSession.instructor_id == instructor_id)

    month_sessions = query.all()
    available_dates = set()
    booked_dates = set()
    for session in month_sessions:
        day_key = session.datetime_start.date()
        if session.status == "booked":
            booked_dates.add(day_key)
        elif session.status == "available":
            available_dates.add(day_key)

    return render_template(
        "trainers-book.html",
        user=current_user,
        selected_month=selected_month,
        selected_year=selected_year,
        current_date=current_date,
        days=days,
        available_dates=available_dates,
        booked_dates=booked_dates,
        now=current_date,
        instructor_id=instructor_id,
        instructors=booking.instructors() if current_user.is_admin else [],
    )


@app.route("/book/<int:year>/<int:month>/<int:day>")
@login_required
def book_day(year, month, day):
    day_date = _parse_day(year, month, day)
    if not day_date:
        flash("That date is not valid.", "error")
        return redirect(url_for("app.book_calendar"))

    instructor_id = request.args.get("instructor_id", type=int)
    sessions = booking.sessions_on_day(year, month, day, current_user, instructor_id)
    return render_template(
        "trainers-book-select-date.html",
        user=current_user,
        year=year,
        month=month,
        day=day,
        day_date=day_date,
        sessions=sessions,
        instructor_id=instructor_id,
        instructors=booking.instructors() if (current_user.is_admin or current_user.is_client) else [],
        is_past=day_date.date() < datetime.now().date(),
    )


@app.route("/book/<int:year>/<int:month>/<int:day>/availability", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN, ROLE_INSTRUCTOR)
def add_availability(year, month, day):
    day_date = _parse_day(year, month, day)
    if not day_date:
        flash("That date is not valid.", "error")
        return redirect(url_for("app.book_calendar"))

    start_time = request.form.get("start_time") or ""
    end_time = request.form.get("end_time") or ""
    try:
        start_hour, start_minute = [int(part) for part in start_time.split(":")]
        end_hour, end_minute = [int(part) for part in end_time.split(":")]
        start = day_date.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end = day_date.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    except ValueError:
        flash("Enter start and end times in HH:MM format.", "error")
        return redirect(url_for("app.book_day", year=year, month=month, day=day))

    if current_user.is_admin:
        instructor = db.session.get(User, request.form.get("instructor_id", type=int))
        if not instructor or not instructor.is_instructor:
            flash("Choose an instructor for this slot.", "error")
            return redirect(url_for("app.book_day", year=year, month=month, day=day))
    else:
        instructor = current_user

    _session, error = booking.create_availability(instructor, start, end)
    flash(error or "Availability published. Clients can now book this slot.", "error" if error else "success")
    return redirect(url_for("app.book_day", year=year, month=month, day=day))


@app.route("/sessions/<int:session_id>/confirm")
@login_required
@role_required(ROLE_CLIENT)
def confirm_booking(session_id):
    session = _session_or_404(session_id)
    if not session.is_available:
        flash("That session is no longer available.", "error")
        return redirect(url_for("app.book_calendar"))
    return render_template("confirm_booking.html", user=current_user, session=session)


@app.route("/sessions/<int:session_id>/book", methods=["POST"])
@login_required
@role_required(ROLE_CLIENT)
def book_session(session_id):
    session = _session_or_404(session_id)
    ok, message = booking.book_session(session, current_user)
    flash(message, "success" if ok else "error")
    if ok:
        return redirect(url_for("app.my_sessions"))
    return redirect(url_for("app.book_calendar"))


@app.route("/sessions/<int:session_id>/cancel", methods=["POST"])
@login_required
def cancel_session(session_id):
    session = _session_or_404(session_id)
    ok, message = booking.cancel_session(session, current_user)
    flash(message, "success" if ok else "error")
    if current_user.is_client:
        return redirect(url_for("app.my_sessions"))
    start = session.datetime_start
    return redirect(url_for("app.book_day", year=start.year, month=start.month, day=start.day))


@app.route("/sessions/<int:session_id>/remove", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN, ROLE_INSTRUCTOR)
def remove_availability(session_id):
    session = _session_or_404(session_id)
    start = session.datetime_start
    ok, message = booking.remove_availability(session, current_user)
    flash(message, "success" if ok else "error")
    return redirect(url_for("app.book_day", year=start.year, month=start.month, day=start.day))


@app.route("/my-sessions")
@login_required
def my_sessions():
    now = datetime.now()
    if current_user.is_client:
        query = GymSession.query.filter(GymSession.client_id == current_user.id)
    elif current_user.is_instructor:
        query = GymSession.query.filter(GymSession.instructor_id == current_user.id)
    else:
        query = GymSession.query

    upcoming = (
        query.filter(GymSession.datetime_start >= now, GymSession.status != "cancelled")
        .order_by(GymSession.datetime_start)
        .all()
    )
    past = (
        query.filter(GymSession.datetime_start < now)
        .order_by(GymSession.datetime_start.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "my_sessions.html",
        user=current_user,
        upcoming=upcoming,
        past=past,
    )


@app.route("/users", methods=["GET", "POST"])
@login_required
@role_required(ROLE_ADMIN)
def users():
    if request.method == "POST":
        return _create_user_from_form()

    users_list = User.query.order_by(User.role, User.name_last, User.name_first).all()
    return render_template("users.html", user=current_user, users_list=users_list)


def _create_user_from_form():
    email = (request.form.get("email") or "").strip()
    name_first = (request.form.get("name_first") or "").strip()
    name_last = (request.form.get("name_last") or "").strip()
    password = request.form.get("password") or ""
    role = request.form.get("role") or ROLE_INSTRUCTOR

    if role not in (ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_CLIENT):
        flash("Choose a valid role.", "error")
    elif User.query.filter_by(email=email).first():
        flash("That email is already in use.", "error")
    elif len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
    elif not email or not name_first or not name_last:
        flash("Email, first name, and last name are required.", "error")
    else:
        db.session.add(
            User(
                email=email,
                name_first=name_first,
                name_last=name_last,
                password=generate_password_hash(password),
                role=role,
            )
        )
        db.session.commit()
        flash(f"{role.capitalize()} account created for {email}.", "success")
    return redirect(url_for("app.users"))


@app.route("/get_user", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def get_user():
    user = db.session.get(User, request.form.get("user_id", type=int))
    if not user:
        return jsonify({"error": "User not found"}), 404
    date_birth = user.date_birth.strftime("%Y-%m-%d") if user.date_birth else None
    return jsonify(
        {
            "id": user.id,
            "name_last": user.name_last,
            "name_first": user.name_first,
            "email": user.email,
            "date_created": user.date_created.isoformat() if user.date_created else None,
            "date_birth": date_birth,
            "address": user.address,
            "role": user.role,
        }
    )


@app.route("/edit_user", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def edit_user():
    user = db.session.get(User, request.form.get("user_id", type=int))
    if not user:
        return jsonify({"error": "User not found"}), 404
    role = request.form.get("role") or user.role
    if role not in (ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_CLIENT):
        return jsonify({"error": "Invalid role"}), 400
    user.name_last = request.form.get("name_last") or user.name_last
    user.name_first = request.form.get("name_first") or user.name_first
    user.email = request.form.get("email") or user.email
    user.date_birth = string_to_datetime(request.form.get("date_birth") or "")
    user.address = request.form.get("address")
    user.role = role
    db.session.commit()
    return jsonify({"success": True})


@app.route("/status_change_user", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def status_change_user():
    user = db.session.get(User, request.form.get("user_id", type=int))
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.id == current_user.id:
        return jsonify({"error": "You cannot disable your own account."}), 400
    user.status = 0 if user.status == 1 else 1
    db.session.commit()
    return jsonify({"success": True, "status": user.status})


@app.route("/reset_password", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def reset_password():
    user = db.session.get(User, request.form.get("user_id", type=int))
    if not user:
        return jsonify({"error": "User not found"}), 404
    new_password = request.form.get("newPassword") or ""
    confirm_password = request.form.get("confirmPassword") or ""
    if new_password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    user.password = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": f"Password reset for {user.email}."})


@app.route("/sw.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
