from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

DB_NAME = "database.db"

db = SQLAlchemy()


def create_app(test_config=None):
    app_flask = Flask(__name__)
    app_flask.config.from_mapping(
        SECRET_KEY="si0fdmewmfic.k405964305c.fem[serWDO>$K#$%()]",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{DB_NAME}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GYM_TIMEZONE="Europe/Athens",
    )
    if test_config:
        app_flask.config.update(test_config)

    db.init_app(app_flask)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "error"
    login_manager.init_app(app_flask)

    from .auth import auth
    from .app import app
    from .views import views

    app_flask.register_blueprint(views, url_prefix="/")
    app_flask.register_blueprint(auth, url_prefix="/")
    app_flask.register_blueprint(app, url_prefix="/")

    create_database(app_flask)

    from .models import (
        ROLE_ADMIN,
        ROLE_CLIENT,
        ROLE_INSTRUCTOR,
        SESSION_AVAILABLE,
        SESSION_BOOKED,
        SESSION_CANCELLED,
        User,
    )

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app_flask.context_processor
    def inject_globals():
        return {
            "ROLE_ADMIN": ROLE_ADMIN,
            "ROLE_INSTRUCTOR": ROLE_INSTRUCTOR,
            "ROLE_CLIENT": ROLE_CLIENT,
            "SESSION_AVAILABLE": SESSION_AVAILABLE,
            "SESSION_BOOKED": SESSION_BOOKED,
            "SESSION_CANCELLED": SESSION_CANCELLED,
        }

    @app_flask.errorhandler(403)
    def forbidden(_error):
        user = current_user if current_user.is_authenticated else None
        return render_template("403.html", user=user), 403

    @app_flask.errorhandler(404)
    def not_found(_error):
        user = current_user if current_user.is_authenticated else None
        return render_template("404.html", user=user), 404

    return app_flask


def create_database(app):
    from website.models_utils.init_models import init_database

    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        need_reset = False
        if "user" in tables:
            columns = [column["name"] for column in inspector.get_columns("user")]
            if "role" not in columns:
                need_reset = True
        if "gym_session" not in tables and "schedule_trainning" in tables:
            need_reset = True
        if need_reset:
            db.drop_all()
        if "gym_session" in inspect(db.engine).get_table_names():
            _collapse_duplicate_active_slots()
        db.create_all()
        _ensure_active_slot_index()
        init_database(db)


def _collapse_duplicate_active_slots():
    rows = db.session.execute(
        text(
            """
            SELECT instructor_id, datetime_start, id
            FROM gym_session
            WHERE status != 'cancelled'
            ORDER BY instructor_id, datetime_start, id
            """
        )
    ).fetchall()
    seen = set()
    cancelled = 0
    for instructor_id, start, session_id in rows:
        key = (instructor_id, start)
        if key in seen:
            db.session.execute(
                text("UPDATE gym_session SET status = 'cancelled', client_id = NULL WHERE id = :id"),
                {"id": session_id},
            )
            cancelled += 1
        else:
            seen.add(key)
    if cancelled:
        db.session.commit()


def _ensure_active_slot_index():
    db.session.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_gym_session_instructor_start_active
            ON gym_session (instructor_id, datetime_start)
            WHERE status != 'cancelled'
            """
        )
    )
    db.session.commit()
