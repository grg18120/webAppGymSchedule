import os
import tempfile
import unittest

from website import create_app, db
from website.models import (
    GymSession,
    ROLE_CLIENT,
    SESSION_AVAILABLE,
    SESSION_BOOKED,
    SESSION_CANCELLED,
    User,
)
from website.utils.timeutils import now_gym
from werkzeug.security import generate_password_hash


class BookingRolesTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + self.db_path,
            }
        )
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        os.unlink(self.db_path)

    def login(self, email, password):
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def static_bytes(self, path):
        response = self.client.get(path)
        try:
            return response.status_code, response.get_data()
        finally:
            response.close()

    def cancel_active_start(self, instructor_id, start):
        slots = GymSession.query.filter_by(
            instructor_id=instructor_id,
            datetime_start=start,
        ).all()
        for slot in slots:
            if slot.status != SESSION_CANCELLED:
                slot.status = SESSION_CANCELLED
                slot.client_id = None
        db.session.flush()

    def test_client_cannot_open_users(self):
        self.login("client@gym.com", "client123")
        response = self.client.get("/users")
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"You do not have access", response.data)

    def test_book_then_slot_unavailable(self):
        session = GymSession.query.filter_by(status=SESSION_AVAILABLE).first()
        self.assertIsNotNone(session)
        session_id = session.id

        self.login("client@gym.com", "client123")
        confirm = self.client.get(f"/sessions/{session_id}/confirm")
        self.assertEqual(confirm.status_code, 200)
        booked = self.client.post(f"/sessions/{session_id}/book", follow_redirects=True)
        self.assertEqual(booked.status_code, 200)
        self.assertIn(b"Session booked", booked.data)

        refreshed = db.session.get(GymSession, session_id)
        self.assertEqual(refreshed.status, SESSION_BOOKED)

        extra = User(
            email="second@gym.com",
            password=generate_password_hash("client123"),
            name_first="Second",
            name_last="Client",
            role=ROLE_CLIENT,
        )
        db.session.add(extra)
        db.session.commit()
        self.client.get("/logout")
        self.login("second@gym.com", "client123")
        again = self.client.post(f"/sessions/{session_id}/book", follow_redirects=True)
        self.assertIn(b"no longer available", again.data)

    def test_atomic_book_keeps_a_single_client(self):
        from datetime import timedelta

        from website.utils import booking

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        casey = User.query.filter_by(email="client@gym.com").first()
        jordan = User.query.filter_by(email="jordan@gym.com").first()
        start = now_gym().replace(minute=0, second=0, microsecond=0) + timedelta(days=20)
        slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=start,
            datetime_end=start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        db.session.add(slot)
        db.session.commit()
        ok_first, _ = booking.book_session(slot, casey)
        ok_second, message = booking.book_session(slot, jordan)
        self.assertTrue(ok_first)
        self.assertFalse(ok_second)
        self.assertIn("no longer available", message)
        refreshed = db.session.get(GymSession, slot.id)
        self.assertEqual(refreshed.status, SESSION_BOOKED)
        self.assertEqual(refreshed.client_id, casey.id)

    def test_duplicate_active_slot_start_is_rejected(self):
        from datetime import datetime, timedelta

        from sqlalchemy.exc import IntegrityError

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        start = datetime(2099, 12, 1, 9, 0)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=start,
                datetime_end=start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.commit()
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=start,
                datetime_end=start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_create_availability_rejects_duplicate_start(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch

        from website.utils import booking

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        start = datetime(2099, 12, 15, 6, 0)
        end = start + timedelta(hours=1)
        first, error = booking.create_availability(instructor, start, end)
        self.assertIsNotNone(first)
        self.assertIsNone(error)

        second, overlap = booking.create_availability(instructor, start, end)
        self.assertIsNone(second)
        self.assertIn("overlaps an existing session", overlap)

        with patch("website.utils.booking.overlapping_sessions", return_value=[]):
            raced, raced_error = booking.create_availability(instructor, start, end)
        self.assertIsNone(raced)
        self.assertIn("overlaps an existing session", raced_error)

    def test_extra_client_bookings_skip_occupied_starts(self):
        from website.models_utils.init_models import _ensure_extra_client_bookings

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        before = GymSession.query.filter_by(instructor_id=instructor.id).count()
        _ensure_extra_client_bookings(db)
        _ensure_extra_client_bookings(db)
        after = GymSession.query.filter_by(instructor_id=instructor.id).count()
        self.assertGreaterEqual(after, before)

    def test_seed_skips_overlapping_instructor_range(self):
        from datetime import datetime, timedelta

        from website.models_utils.init_models import _add_session_if_missing

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        existing_start = datetime(2099, 9, 25, 10, 15)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=existing_start,
                datetime_end=existing_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.commit()
        added = _add_session_if_missing(
            db,
            instructor,
            datetime(2099, 9, 25, 10, 0),
            datetime(2099, 9, 25, 11, 0),
            None,
        )
        self.assertFalse(added)
        day_slots = (
            GymSession.query.filter_by(instructor_id=instructor.id)
            .filter(GymSession.status != SESSION_CANCELLED)
            .filter(GymSession.datetime_start >= datetime(2099, 9, 25))
            .filter(GymSession.datetime_start < datetime(2099, 9, 26))
            .all()
        )
        self.assertEqual(len(day_slots), 1)
        self.assertEqual(day_slots[0].datetime_start, existing_start)

    def test_reconcile_cancels_overlapping_available_keeps_booked(self):
        from datetime import datetime, timedelta

        from website.utils.booking import reconcile_overlapping_sessions

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        first_start = datetime(2099, 9, 22, 15, 15)
        overlap_start = datetime(2099, 9, 22, 16, 0)
        adjacent_start = datetime(2099, 9, 22, 16, 15)
        booked_start = datetime(2099, 9, 22, 18, 0)
        later_open = datetime(2099, 9, 22, 18, 15)
        db.session.add_all(
            [
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=first_start,
                    datetime_end=first_start + timedelta(hours=1),
                    status=SESSION_AVAILABLE,
                ),
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=overlap_start,
                    datetime_end=overlap_start + timedelta(hours=1),
                    status=SESSION_AVAILABLE,
                ),
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=adjacent_start,
                    datetime_end=adjacent_start + timedelta(hours=1),
                    status=SESSION_AVAILABLE,
                ),
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=booked_start,
                    datetime_end=booked_start + timedelta(hours=1),
                    status=SESSION_BOOKED,
                    client_id=client.id,
                ),
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=later_open,
                    datetime_end=later_open + timedelta(hours=1),
                    status=SESSION_AVAILABLE,
                ),
            ]
        )
        db.session.commit()
        cancelled = reconcile_overlapping_sessions()
        self.assertGreaterEqual(cancelled, 2)

        def active_at(start):
            return GymSession.query.filter_by(
                instructor_id=instructor.id,
                datetime_start=start,
            ).filter(GymSession.status != SESSION_CANCELLED).first()

        self.assertIsNotNone(active_at(first_start))
        self.assertIsNone(active_at(overlap_start))
        self.assertIsNotNone(active_at(adjacent_start))
        booked = active_at(booked_start)
        self.assertIsNotNone(booked)
        self.assertEqual(booked.status, SESSION_BOOKED)
        self.assertIsNone(active_at(later_open))

        remaining = (
            GymSession.query.filter_by(instructor_id=instructor.id)
            .filter(GymSession.status != SESSION_CANCELLED)
            .filter(GymSession.datetime_start >= datetime(2099, 9, 22))
            .filter(GymSession.datetime_start < datetime(2099, 9, 23))
            .order_by(GymSession.datetime_start)
            .all()
        )
        for index, slot in enumerate(remaining):
            for other in remaining[index + 1 :]:
                overlaps = (
                    slot.datetime_start < other.datetime_end
                    and slot.datetime_end > other.datetime_start
                )
                self.assertFalse(overlaps)

    def test_nav_label_depends_on_role(self):
        self.login("client@gym.com", "client123")
        client_cal = self.client.get("/book")
        self.assertIn(b"Book session monthly", client_cal.data)
        self.assertNotIn(b"My availability", client_cal.data)

        self.client.get("/logout")
        self.login("instructor@gym.com", "instructor123")
        instructor_cal = self.client.get("/book")
        self.assertRegex(
            instructor_cal.data.decode(),
            r'id="mainNav"[\s\S]*href="/book">\s*Calendar\s*</a>',
        )
        self.assertNotIn(b"Book a session", instructor_cal.data)
        self.assertNotIn(b"Book session monthly", instructor_cal.data)
        self.assertNotIn(b"My availability", instructor_cal.data)
        self.assertIn(b"Book session weekly", instructor_cal.data)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_cal = self.client.get("/book")
        self.assertIn(b"Calendar", admin_cal.data)
        self.assertNotIn(b"Book a session", admin_cal.data)
        self.assertNotIn(b"Book session monthly", admin_cal.data)
        self.assertNotIn(b"My availability", admin_cal.data)

    def test_instructor_cannot_book_as_client(self):
        session = GymSession.query.filter_by(status=SESSION_AVAILABLE).first()
        self.assertIsNotNone(session)
        self.login("instructor@gym.com", "instructor123")
        response = self.client.post(f"/sessions/{session.id}/book")
        self.assertEqual(response.status_code, 403)
        refreshed = db.session.get(GymSession, session.id)
        self.assertEqual(refreshed.status, SESSION_AVAILABLE)
        self.assertIsNone(refreshed.client_id)

    def test_seeded_clients_can_be_compared_by_role(self):
        emails = ["client@gym.com", "jordan@gym.com", "riley@gym.com", "morgan@gym.com"]
        clients = User.query.filter(User.email.in_(emails)).all()
        self.assertEqual(len(clients), 4)
        self.assertTrue(all(user.role == ROLE_CLIENT for user in clients))
        self.assertEqual(User.query.filter_by(role="instructor").count(), 1)
        self.assertEqual(User.query.filter_by(role="admin").count(), 1)
        self.assertIsNotNone(User.query.filter_by(email="instructor@gym.com").first())
        self.assertIsNone(User.query.filter_by(email="sam@gym.com").first())

        self.login("jordan@gym.com", "client123")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Client", home.data)
        self.assertEqual(self.client.get("/users").status_code, 403)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        users_page = self.client.get("/users")
        self.assertEqual(users_page.status_code, 200)
        users_html = users_page.get_data(as_text=True)
        for email in emails + ["instructor@gym.com"]:
            self.assertIn(email, users_html)
        self.assertNotIn("sam@gym.com", users_html)
        self.assertIn('id="filterRole"', users_html)
        self.assertIn("user-card", users_html)
        self.assertIn("Create account", users_html)
        self.assertNotIn("users-table", users_html)
        self.assertIn("Admins", users_html)
        self.assertIn("Instructors", users_html)
        self.assertIn("Clients", users_html)
        status, users_css = self.static_bytes("/static/css/users.css")
        self.assertEqual(status, 200)
        self.assertIn(b".user-card", users_css)
        login_page = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"instructor@gym.com", login_page.data)
        self.assertNotIn(b"sam@gym.com", login_page.data)

    def test_extra_instructor_is_collapsed_onto_alex(self):
        from datetime import datetime, timedelta

        from website.models import ROLE_INSTRUCTOR
        from website.models_utils.init_models import _ensure_single_instructor

        alex = User.query.filter_by(email="instructor@gym.com").first()
        extra = User(
            email="sam@gym.com",
            password=generate_password_hash("instructor123"),
            name_first="Sam",
            name_last="Rivera",
            role=ROLE_INSTRUCTOR,
        )
        db.session.add(extra)
        db.session.commit()
        unique_start = datetime(2099, 10, 1, 9, 0)
        clash_start = datetime(2099, 10, 1, 11, 0)
        db.session.add(
            GymSession(
                instructor_id=extra.id,
                datetime_start=unique_start,
                datetime_end=unique_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=alex.id,
                datetime_start=clash_start,
                datetime_end=clash_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=extra.id,
                datetime_start=clash_start,
                datetime_end=clash_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.commit()
        extra_session_count = GymSession.query.filter_by(instructor_id=extra.id).count()
        self.assertEqual(extra_session_count, 2)
        _ensure_single_instructor(db)
        self.assertIsNone(User.query.filter_by(email="sam@gym.com").first())
        self.assertEqual(User.query.filter_by(role=ROLE_INSTRUCTOR).count(), 1)
        moved = GymSession.query.filter_by(instructor_id=alex.id, datetime_start=unique_start).first()
        self.assertIsNotNone(moved)
        self.assertEqual(
            GymSession.query.filter_by(instructor_id=alex.id, datetime_start=clash_start).count(),
            1,
        )
        self.assertEqual(GymSession.query.filter(GymSession.instructor_id.is_(None)).count(), 0)

    def test_calendar_labels_open_slots_and_past_bookings(self):
        from datetime import datetime, timedelta

        from website.models import SESSION_BOOKED

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        past_start = now_gym().replace(minute=0, second=0, microsecond=0) - timedelta(days=2)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=past_start,
                datetime_end=past_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("client@gym.com", "client123")
        page = self.client.get("/book")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Open slots", page.data)
        self.assertIn(b"Open &amp; Booked", page.data)
        self.assertIn(b'data-short="Op&amp;B"', page.data)
        self.assertIn(b'data-short="Op"', page.data)
        self.assertIn(b'data-short="B"', page.data)
        self.assertIn(b'data-full="Open &amp; Booked"', page.data)
        self.assertNotIn(b"Open + booked", page.data)
        self.assertNotIn(b"day-status--short", page.data)
        self.assertNotIn(b"day-status--full", page.data)
        self.assertEqual(
            page.data.count(b'class="day-status"'),
            page.data.count(b'class="day-number"'),
        )
        self.assertIn(b"No slots", page.data)
        self.assertIn(b"No bookings", page.data)
        self.assertIn(b"past-booked", page.data)
        self.assertIn(b"has-booked", page.data)
        self.assertNotIn(b">None<", page.data)

        self.assertIn(b"Previous month", page.data)
        self.assertIn(b"Next month", page.data)
        self.assertNotIn(b"month-select", page.data)
        self.assertIn(b"day-disabled", page.data)

        blocked = self.client.get("/book/2099/1/1", follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        past_empty = self.client.get("/book/2026/7/1", follow_redirects=False)
        self.assertEqual(past_empty.status_code, 302)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_cal = self.client.get("/book")
        self.assertIn(b"month-select", admin_cal.data)
        open_empty = self.client.get("/book/2099/1/1")
        self.assertEqual(open_empty.status_code, 200)
        admin_past_empty = self.client.get("/book/2026/7/1", follow_redirects=False)
        self.assertEqual(admin_past_empty.status_code, 302)

    def test_calendar_booked_is_blue_and_hover_keeps_letter_colors(self):
        status, css = self.static_bytes("/static/css/trainers_book.css")
        self.assertEqual(status, 200)
        self.assertIn(b"#1565c0", css)
        self.assertIn(b"rgba(21, 101, 192", css)
        self.assertNotIn(b"#8e24aa", css)
        self.assertNotIn(b"#ce93d8", css)
        self.assertIn(b"a.day.no-slots:hover", css)
        self.assertIn(b"color: #ffffff", css)
        self.assertIn(b"color: #000000", css)
        self.assertIn(b".day.has-open.has-booked:not(.passed)", css)
        self.assertIn(b"linear-gradient(135deg, #2e7d32 50%, #1565c0 50%)", css)
        self.assertIn(b"background-clip: padding-box", css)
        self.assertIn(b".day.today.has-open.has-booked:not(.passed)", css)
        self.assertIn(b".legend-swatch.mixed", css)
        self.assertIn(b"attr(data-full)", css)
        self.assertIn(b"attr(data-short)", css)
        self.assertNotIn(b".day-status--short", css)

    def test_client_calendar_shows_only_own_bookings(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        casey = User.query.filter_by(email="client@gym.com").first()
        jordan = User.query.filter_by(email="jordan@gym.com").first()
        jordan_only = datetime(2099, 11, 5, 10, 0)
        casey_only = datetime(2099, 11, 6, 10, 0)
        casey_mixed_booked = datetime(2099, 11, 7, 10, 0)
        casey_mixed_open = datetime(2099, 11, 7, 14, 0)
        open_only = datetime(2099, 11, 8, 10, 0)
        jordan_past = now_gym().replace(minute=0, second=0, microsecond=0) - timedelta(days=4)
        casey_past = now_gym().replace(minute=0, second=0, microsecond=0) - timedelta(days=5)
        for start, client in (
            (jordan_only, jordan),
            (casey_only, casey),
            (casey_mixed_booked, casey),
            (jordan_past, jordan),
            (casey_past, casey),
        ):
            db.session.add(
                GymSession(
                    instructor_id=instructor.id,
                    client_id=client.id,
                    datetime_start=start,
                    datetime_end=start + timedelta(hours=1),
                    status=SESSION_BOOKED,
                )
            )
        for start in (casey_mixed_open, open_only):
            db.session.add(
                GymSession(
                    instructor_id=instructor.id,
                    datetime_start=start,
                    datetime_end=start + timedelta(hours=1),
                    status=SESSION_AVAILABLE,
                )
            )
        db.session.commit()

        def cell_for(html, year, month, day):
            marker = f"/book/{year}/{month}/{day}"
            idx = html.find(marker)
            self.assertNotEqual(idx, -1, f"missing link {marker}")
            start = html.rfind("<a", 0, idx)
            end = html.find("</a>", idx)
            return html[start:end]

        self.login("client@gym.com", "client123")
        casey_page = self.client.get("/book?month=11&year=2099").get_data(as_text=True)
        casey_day = cell_for(casey_page, 2099, 11, 6)
        mixed_day = cell_for(casey_page, 2099, 11, 7)
        open_day = cell_for(casey_page, 2099, 11, 8)
        self.assertNotIn("/book/2099/11/5", casey_page)
        self.assertIn("has-booked", casey_day)
        self.assertNotIn("has-open", casey_day)
        self.assertIn("has-open has-booked", mixed_day)
        self.assertIn("Open & Booked", mixed_day)
        self.assertIn("has-open", open_day)
        self.assertNotIn("has-booked", open_day)

        current = self.client.get("/book").get_data(as_text=True)
        self.assertIn(f"/book/{casey_past.year}/{casey_past.month}/{casey_past.day}", current)
        self.assertNotIn(f"/book/{jordan_past.year}/{jordan_past.month}/{jordan_past.day}", current)

        self.client.get("/logout")
        self.login("jordan@gym.com", "client123")
        jordan_page = self.client.get("/book?month=11&year=2099").get_data(as_text=True)
        self.assertIn("has-booked", cell_for(jordan_page, 2099, 11, 5))
        self.assertNotIn("/book/2099/11/6", jordan_page)
        self.assertNotIn("has-booked", cell_for(jordan_page, 2099, 11, 7))
        self.assertIn("has-open", cell_for(jordan_page, 2099, 11, 7))

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_page = self.client.get("/book?month=11&year=2099").get_data(as_text=True)
        self.assertIn("has-booked", cell_for(admin_page, 2099, 11, 5))
        self.assertIn("has-booked", cell_for(admin_page, 2099, 11, 6))

    def test_today_mixed_cell_keeps_today_outline_classes(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        today = now_gym().replace(minute=0, second=0, microsecond=0)
        open_start = today.replace(hour=8)
        booked_start = today.replace(hour=10)
        self.cancel_active_start(instructor.id, open_start)
        self.cancel_active_start(instructor.id, booked_start)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=open_start,
                datetime_end=open_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=booked_start,
                datetime_end=booked_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("client@gym.com", "client123")
        html = self.client.get("/book").get_data(as_text=True)
        self.assertIn('class="day today has-open has-booked"', html)

    def test_calendar_mixed_day_shows_open_plus_booked(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        open_start = datetime(2099, 10, 15, 9, 0)
        booked_start = datetime(2099, 10, 15, 11, 0)
        past_open = now_gym().replace(minute=0, second=0, microsecond=0) - timedelta(days=2, hours=2)
        past_booked = past_open + timedelta(hours=2)
        self.cancel_active_start(instructor.id, past_open)
        self.cancel_active_start(instructor.id, past_booked)
        db.session.commit()
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=open_start,
                datetime_end=open_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=booked_start,
                datetime_end=booked_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=past_open,
                datetime_end=past_open + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=past_booked,
                datetime_end=past_booked + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("client@gym.com", "client123")
        future_page = self.client.get("/book?month=10&year=2099")
        self.assertEqual(future_page.status_code, 200)
        future_html = future_page.get_data(as_text=True)
        self.assertIn("Open & Booked", future_html)
        self.assertIn("legend-swatch mixed", future_html)
        self.assertIn("/book/2099/10/15", future_html)
        self.assertIn("has-open has-booked", future_html)
        self.assertNotIn('class="day passed has-open has-booked"', future_html)

        current_page = self.client.get("/book")
        current_html = current_page.get_data(as_text=True)
        self.assertIn("legend-swatch mixed", current_html)
        past_cell = None
        for chunk in current_html.split("<"):
            if "day passed" in chunk and "has-open" in chunk and "has-booked" in chunk:
                past_cell = chunk
                break
        self.assertIsNotNone(past_cell)
        past_block_start = current_html.find(past_cell)
        past_block = current_html[past_block_start : past_block_start + 800]
        self.assertIn("Booked", past_block)
        self.assertNotIn("Open & Booked", past_block)
        self.assertNotIn("Open &amp; Booked", past_block)
        self.assertNotIn("Open + booked", past_block)

    def test_instructor_publish_uses_24h_dropdowns_not_ampm(self):
        self.login("instructor@gym.com", "instructor123")
        page = self.client.get("/book/2099/6/15")
        self.assertEqual(page.status_code, 200)
        html = page.data
        self.assertIn(b'name="start_hour"', html)
        self.assertIn(b'name="start_minute"', html)
        self.assertIn(b'name="end_hour"', html)
        self.assertIn(b'name="end_minute"', html)
        self.assertNotIn(b'type="time"', html)
        self.assertIn(b">00</option>", html)
        self.assertIn(b">05</option>", html)
        self.assertIn(b">55</option>", html)
        self.assertIn(b'value="24"', html)
        self.assertIn(b"Publish all day", html)
        self.assertIn(b"Publish a custom slot", html)
        self.assertIn(b"Publish a range of slots", html)
        self.assertIn(b"Publish range", html)
        self.assertNotIn(b'name="slot_hours"', html)
        self.assertIn(b'name="slot_minutes"', html)
        self.assertIn(b'name="break_minutes"', html)
        self.assertIn(b'value="60" selected', html)
        self.assertIn(b">60 min</option>", html)
        self.assertIn(b">0 min</option>", html)
        self.assertIn(b"Break between slots", html)
        self.assertIn(b"Slot length", html)
        self.assertIn(b"Delete all Available slots", html)
        self.assertIn(b"btn-delete-available", html)
        self.assertIn(b"publish-card--custom", html)
        self.assertIn(b"publish-card--range", html)
        self.assertIn(b"publish-card__summary", html)
        self.assertIn(b'<details class="publish-card publish-card--custom">', html)
        self.assertIn(b'<details class="publish-card publish-card--range">', html)
        self.assertNotIn(b'publish-card--custom" open', html)
        self.assertNotIn(b'publish-card--range" open', html)
        _status, app_css = self.static_bytes("/static/css/app.css")
        self.assertIn(b".publish-card__summary", app_css)
        self.assertIn(b'content: "Show"', app_css)
        self.assertIn(b"Cancel all booked slots", html)
        self.assertIn(
            b"Cancel ALL booked slots on this day? Clients will lose those sessions.",
            html,
        )

    def test_instructor_cannot_publish_overlapping_slot(self):
        from datetime import datetime

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        start = datetime(2099, 6, 15, 10, 0)
        end = datetime(2099, 6, 15, 11, 0)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=start,
                datetime_end=end,
                status=SESSION_AVAILABLE,
            )
        )
        db.session.commit()

        self.login("instructor@gym.com", "instructor123")
        overlap = self.client.post(
            "/book/2099/6/15/availability",
            data={
                "start_hour": "10",
                "start_minute": "5",
                "end_hour": "11",
                "end_minute": "0",
            },
            follow_redirects=True,
        )
        self.assertEqual(overlap.status_code, 200)
        self.assertIn(b"overlaps an existing session", overlap.data)
        same_day = GymSession.query.filter(
            GymSession.instructor_id == instructor.id,
            GymSession.datetime_start >= datetime(2099, 6, 15),
            GymSession.datetime_start < datetime(2099, 6, 16),
        ).count()
        self.assertEqual(same_day, 1)

    def test_publish_all_day_creates_hourly_slots_and_skips_overlap(self):
        from datetime import datetime

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        self.login("instructor@gym.com", "instructor123")
        first = self.client.post("/book/2099/6/16/availability/all-day", follow_redirects=True)
        self.assertEqual(first.status_code, 200)
        self.assertIn(b"Published 13 hourly slots from 09:00 to 22:00", first.data)
        slots = (
            GymSession.query.filter_by(instructor_id=instructor.id, status=SESSION_AVAILABLE)
            .filter(GymSession.datetime_start >= datetime(2099, 6, 16))
            .filter(GymSession.datetime_start < datetime(2099, 6, 17))
            .order_by(GymSession.datetime_start)
            .all()
        )
        self.assertEqual(len(slots), 13)
        self.assertEqual(slots[0].datetime_start.hour, 9)
        self.assertEqual(slots[-1].datetime_end.hour, 22)

        again = self.client.post("/book/2099/6/16/availability/all-day", follow_redirects=True)
        self.assertIn(b"No new slots were published", again.data)
        self.assertEqual(
            GymSession.query.filter_by(instructor_id=instructor.id, status=SESSION_AVAILABLE)
            .filter(GymSession.datetime_start >= datetime(2099, 6, 16))
            .filter(GymSession.datetime_start < datetime(2099, 6, 17))
            .count(),
            13,
        )

    def test_delete_all_available_and_booked_slots(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        day_start = datetime(2099, 6, 17, 9, 0)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=day_start,
                datetime_end=day_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=day_start + timedelta(hours=2),
                datetime_end=day_start + timedelta(hours=3),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("instructor@gym.com", "instructor123")
        deleted_available = self.client.post(
            "/book/2099/6/17/availability/delete-available",
            follow_redirects=True,
        )
        self.assertIn(b"Deleted 1 available slot", deleted_available.data)
        remaining = GymSession.query.filter(
            GymSession.instructor_id == instructor.id,
            GymSession.datetime_start >= datetime(2099, 6, 17),
            GymSession.datetime_start < datetime(2099, 6, 18),
        ).all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].status, SESSION_BOOKED)

        cancelled_booked = self.client.post(
            "/book/2099/6/17/bookings/cancel-booked",
            follow_redirects=True,
        )
        self.assertIn(b"Cancelled 1 booked slot", cancelled_booked.data)
        remaining_after = GymSession.query.filter(
            GymSession.instructor_id == instructor.id,
            GymSession.datetime_start >= datetime(2099, 6, 17),
            GymSession.datetime_start < datetime(2099, 6, 18),
        ).all()
        self.assertEqual(len(remaining_after), 1)
        self.assertEqual(remaining_after[0].status, SESSION_CANCELLED)

    def test_instructor_can_delete_future_available_slot(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        start = datetime(2099, 6, 18, 10, 0)
        session = GymSession(
            instructor_id=instructor.id,
            datetime_start=start,
            datetime_end=start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id

        self.login("instructor@gym.com", "instructor123")
        page = self.client.get("/book/2099/6/18")
        self.assertIn(b"Delete slot", page.data)
        self.assertIn(b"btn-delete-slot", page.data)
        self.assertIn(b"btn-delete-available", page.data)

        deleted = self.client.post(f"/sessions/{session_id}/remove", follow_redirects=True)
        self.assertIn(b"Availability removed", deleted.data)
        self.assertIsNone(db.session.get(GymSession, session_id))

    def test_admin_can_cancel_and_delete_sessions_including_past(self):
        from datetime import datetime, timedelta

        from website.utils.timeline import monday_of

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        future_open = now_gym().replace(minute=0, second=0, microsecond=0) + timedelta(days=21)
        future_open = future_open.replace(hour=10)
        future_booked = future_open + timedelta(hours=2)
        past_open = datetime(2020, 3, 10, 16, 25)
        past_booked = datetime(2020, 3, 10, 18, 25)
        for start in (future_open, future_booked, past_open, past_booked):
            self.cancel_active_start(instructor.id, start)

        future_open_slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=future_open,
            datetime_end=future_open + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        future_booked_slot = GymSession(
            instructor_id=instructor.id,
            client_id=client.id,
            datetime_start=future_booked,
            datetime_end=future_booked + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        past_open_slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=past_open,
            datetime_end=past_open + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        past_booked_slot = GymSession(
            instructor_id=instructor.id,
            client_id=client.id,
            datetime_start=past_booked,
            datetime_end=past_booked + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        db.session.add_all(
            [future_open_slot, future_booked_slot, past_open_slot, past_booked_slot]
        )
        db.session.commit()
        future_open_id = future_open_slot.id
        future_booked_id = future_booked_slot.id
        past_open_id = past_open_slot.id
        past_booked_id = past_booked_slot.id
        past_week = monday_of(past_open.date()).isoformat()
        future_week = monday_of(future_open.date()).isoformat()
        remove_future = f"/sessions/{future_open_id}/remove".encode()
        cancel_future = f"/sessions/{future_booked_id}/cancel".encode()
        remove_past = f"/sessions/{past_open_id}/remove".encode()
        delete_past = f"/sessions/{past_booked_id}/delete".encode()

        self.login("instructor@gym.com", "instructor123")
        instructor_past = self.client.get(f"/timeline?start={past_week}")
        self.assertEqual(instructor_past.status_code, 200)
        self.assertNotIn(remove_past, instructor_past.data)
        self.assertNotIn(delete_past, instructor_past.data)
        self.assertNotIn(b"Delete this past booked session?", instructor_past.data)
        instructor_future = self.client.get(f"/timeline?start={future_week}")
        self.assertIn(remove_future, instructor_future.data)
        self.assertIn(cancel_future, instructor_future.data)
        self.assertEqual(
            self.client.post(f"/sessions/{past_booked_id}/delete").status_code,
            403,
        )
        blocked_past_cancel = self.client.post(
            f"/sessions/{past_booked_id}/cancel",
            follow_redirects=True,
        )
        self.assertIn(b"Past sessions cannot be cancelled", blocked_past_cancel.data)
        self.assertEqual(
            db.session.get(GymSession, past_booked_id).status,
            SESSION_BOOKED,
        )

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_future = self.client.get(f"/timeline?start={future_week}")
        self.assertEqual(admin_future.status_code, 200)
        self.assertIn(remove_future, admin_future.data)
        self.assertIn(cancel_future, admin_future.data)
        self.assertIn(b"Delete this available slot?", admin_future.data)
        self.assertIn(b"Cancel this booked session? The client will lose the booking.", admin_future.data)

        admin_past = self.client.get(f"/timeline?start={past_week}")
        self.assertEqual(admin_past.status_code, 200)
        self.assertIn(remove_past, admin_past.data)
        self.assertIn(delete_past, admin_past.data)
        self.assertIn(b"Delete this available slot?", admin_past.data)
        self.assertIn(b"Delete this past booked session? This cannot be undone.", admin_past.data)
        self.assertNotIn(b"/sessions/%d/cancel" % past_booked_id, admin_past.data)

        day_path = f"/book/{past_open.year}/{past_open.month}/{past_open.day}"
        day_page = self.client.get(f"{day_path}?instructor_id={instructor.id}")
        self.assertEqual(day_page.status_code, 200)
        self.assertIn(b"Delete slot", day_page.data)
        self.assertIn(b"Delete session", day_page.data)
        self.assertIn(delete_past, day_page.data)
        self.assertIn(b"Delete all booked slots", day_page.data)
        self.assertIn(b"/bookings/delete-booked", day_page.data)

        cancelled = self.client.post(
            f"/sessions/{future_booked_id}/cancel",
            data={"next": f"/timeline?start={future_week}"},
            follow_redirects=True,
        )
        self.assertIn(b"Session cancelled", cancelled.data)
        self.assertEqual(
            db.session.get(GymSession, future_booked_id).status,
            SESSION_CANCELLED,
        )

        removed_future = self.client.post(
            f"/sessions/{future_open_id}/remove",
            follow_redirects=True,
        )
        self.assertIn(b"Availability removed", removed_future.data)
        self.assertIsNone(db.session.get(GymSession, future_open_id))

        removed_past = self.client.post(
            f"/sessions/{past_open_id}/remove",
            data={"next": f"/timeline?start={past_week}"},
            follow_redirects=True,
        )
        self.assertIn(b"Availability removed", removed_past.data)
        self.assertIn(b"Session timeline", removed_past.data)
        self.assertIsNone(db.session.get(GymSession, past_open_id))

        deleted_past = self.client.post(
            f"/sessions/{past_booked_id}/delete",
            data={"next": f"/timeline?start={past_week}"},
            follow_redirects=True,
        )
        self.assertIn(b"Booked session deleted", deleted_past.data)
        self.assertIn(b"Session timeline", deleted_past.data)
        self.assertIsNone(db.session.get(GymSession, past_booked_id))

    def test_admin_can_bulk_delete_past_booked_slots(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        past_start = datetime(2020, 3, 11, 11, 10)
        self.cancel_active_start(instructor.id, past_start)
        slot = GymSession(
            instructor_id=instructor.id,
            client_id=client.id,
            datetime_start=past_start,
            datetime_end=past_start + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        db.session.add(slot)
        db.session.commit()
        slot_id = slot.id
        day_path = (
            f"/book/{past_start.year}/{past_start.month}/{past_start.day}"
            "/bookings/delete-booked"
        )

        self.login("instructor@gym.com", "instructor123")
        self.assertEqual(
            self.client.post(
                day_path,
                data={"instructor_id": instructor.id},
            ).status_code,
            403,
        )
        self.assertIsNotNone(db.session.get(GymSession, slot_id))

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        deleted = self.client.post(
            day_path,
            data={"instructor_id": instructor.id},
            follow_redirects=True,
        )
        self.assertIn(b"Deleted 1 booked slot", deleted.data)
        self.assertIsNone(db.session.get(GymSession, slot_id))

    def test_day_session_cards_separate_instructor_and_client(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        open_start = datetime(2099, 6, 21, 9, 0)
        booked_start = datetime(2099, 6, 21, 11, 0)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=open_start,
                datetime_end=open_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=booked_start,
                datetime_end=booked_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("instructor@gym.com", "instructor123")
        page = self.client.get("/book/2099/6/21")
        self.assertEqual(page.status_code, 200)
        html = page.data
        self.assertIn(b"session-card--day", html)
        self.assertIn(b"session-person--instructor", html)
        self.assertIn(b"session-person--client", html)
        self.assertIn(b"session-person--open", html)
        self.assertIn(b"Alex Instructor", html)
        self.assertIn(b"Casey Client", html)
        self.assertIn(b"No client yet", html)
        self.assertNotIn(b"No client has made a reservation", html)
        self.assertIn(b"session-status--badge", html)
        self.assertNotIn(b"Instructor: Alex Instructor", html)
        self.assertNotIn(" · Client:".encode(), html)

        _status, css = self.static_bytes("/static/css/app.css")
        self.assertIn(b".session-people", css)
        self.assertIn(b".session-person--open", css)
        self.assertNotIn(b"#d6f3f7", css)
        self.assertNotIn(b"#f1f8e9", css)
        self.assertIn(b"#607d8b", css)

    def test_past_open_slot_says_no_client_made_a_reservation(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        past_start = datetime(2020, 4, 8, 10, 15)
        self.cancel_active_start(instructor.id, past_start)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=past_start,
                datetime_end=past_start + timedelta(hours=1),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.commit()

        self.login("instructor@gym.com", "instructor123")
        page = self.client.get("/book/2020/4/8")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"<dt>Client:</dt>", page.data)
        self.assertIn(b"No client has made a reservation", page.data)
        self.assertNotIn(b"No client yet", page.data)

        timeline = self.client.get("/timeline?start=2020-04-06")
        self.assertEqual(timeline.status_code, 200)
        self.assertIn(b"no client has made a reservation", timeline.data)
        self.assertNotIn(b"no client yet", timeline.data)

    def test_publish_range_with_thirty_minute_slots(self):
        from datetime import datetime

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        self.login("instructor@gym.com", "instructor123")
        response = self.client.post(
            "/book/2099/6/19/availability/range",
            data={
                "range_start_hour": "9",
                "range_start_minute": "0",
                "range_end_hour": "11",
                "range_end_minute": "0",
                "slot_minutes": "30",
                "break_minutes": "0",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Published 4 slot", response.data)
        slots = (
            GymSession.query.filter_by(instructor_id=instructor.id, status=SESSION_AVAILABLE)
            .filter(GymSession.datetime_start >= datetime(2099, 6, 19))
            .filter(GymSession.datetime_start < datetime(2099, 6, 20))
            .order_by(GymSession.datetime_start)
            .all()
        )
        self.assertEqual(len(slots), 4)
        times = [(s.datetime_start.strftime("%H:%M"), s.datetime_end.strftime("%H:%M")) for s in slots]
        self.assertEqual(
            times,
            [("09:00", "09:30"), ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00")],
        )

    def test_publish_range_with_break_between_slots(self):
        from datetime import datetime

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        self.login("instructor@gym.com", "instructor123")
        response = self.client.post(
            "/book/2099/6/20/availability/range",
            data={
                "range_start_hour": "9",
                "range_start_minute": "0",
                "range_end_hour": "12",
                "range_end_minute": "0",
                "slot_minutes": "60",
                "break_minutes": "15",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Published 2 slot", response.data)
        slots = (
            GymSession.query.filter_by(instructor_id=instructor.id, status=SESSION_AVAILABLE)
            .filter(GymSession.datetime_start >= datetime(2099, 6, 20))
            .filter(GymSession.datetime_start < datetime(2099, 6, 21))
            .order_by(GymSession.datetime_start)
            .all()
        )
        times = [(s.datetime_start.strftime("%H:%M"), s.datetime_end.strftime("%H:%M")) for s in slots]
        self.assertEqual(times, [("09:00", "10:00"), ("10:15", "11:15")])

    def test_my_sessions_lists_future_dates_before_past_dates(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        far_future = datetime(2099, 8, 1, 10, 0)
        near_future = datetime(2099, 7, 1, 10, 0)
        past = now_gym().replace(minute=0, second=0, microsecond=0) - timedelta(days=5)
        for start in (far_future, near_future, past):
            db.session.add(
                GymSession(
                    instructor_id=instructor.id,
                    client_id=client.id,
                    datetime_start=start,
                    datetime_end=start + timedelta(hours=1),
                    status=SESSION_BOOKED,
                )
            )
        db.session.commit()

        for email, password in (
            ("instructor@gym.com", "instructor123"),
            ("client@gym.com", "client123"),
            ("admin@gym.com", "admin123"),
        ):
            self.client.get("/logout")
            self.login(email, password)
            page = self.client.get("/my-sessions?upcoming_page=999")
            self.assertEqual(page.status_code, 200)
            html = page.data.decode()
            far_pos = html.find("01 Aug 2099")
            near_pos = html.find("01 Jul 2099")
            past_pos = html.find(past.strftime("%d %b %Y"))
            self.assertGreater(far_pos, 0, email)
            self.assertGreater(near_pos, 0, email)
            self.assertGreater(past_pos, 0, email)
            self.assertLess(near_pos, far_pos, email)
            self.assertLess(far_pos, past_pos, email)

    def test_my_sessions_limits_each_section_to_ten(self):
        from datetime import timedelta

        from website.app import MY_SESSIONS_PER_PAGE

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        base = now_gym().replace(minute=0, second=0, microsecond=0)
        extra_upcoming = []
        extra_past = []
        for index in range(12):
            future_start = base.replace(hour=7, minute=5) + timedelta(days=100 + index)
            past_start = base.replace(hour=7, minute=5) - timedelta(days=100 + index)
            extra_upcoming.append(future_start)
            extra_past.append(past_start)
            db.session.add(
                GymSession(
                    instructor_id=instructor.id,
                    client_id=client.id,
                    datetime_start=future_start,
                    datetime_end=future_start + timedelta(hours=1),
                    status=SESSION_BOOKED,
                )
            )
            db.session.add(
                GymSession(
                    instructor_id=instructor.id,
                    client_id=client.id,
                    datetime_start=past_start,
                    datetime_end=past_start + timedelta(hours=1),
                    status=SESSION_BOOKED,
                )
            )
        db.session.commit()

        self.login("instructor@gym.com", "instructor123")
        first = self.client.get("/my-sessions")
        self.assertEqual(first.status_code, 200)
        html = first.data.decode()
        self.assertIn("Showing 1–10 of", html)
        self.assertIn("Page 1 of", html)
        self.assertIn("upcoming_page=2", html)
        self.assertIn("past_page=2", html)
        last_future = extra_upcoming[-1].strftime("%d %b %Y, %H:%M")
        oldest_past = extra_past[-1].strftime("%d %b %Y, %H:%M")
        newest_past = extra_past[0].strftime("%d %b %Y, %H:%M")
        self.assertNotIn(last_future, html)
        self.assertNotIn(oldest_past, html)
        self.assertEqual(html.count('class="session-card'), MY_SESSIONS_PER_PAGE * 2)
        self.assertEqual(html.count("Showing 1–10 of"), 2)

        upcoming_html = self.client.get("/my-sessions?upcoming_page=999").data.decode()
        self.assertIn(last_future, upcoming_html)
        self.assertIn("upcoming_page=", upcoming_html)

        past_html = self.client.get("/my-sessions?past_page=999").data.decode()
        self.assertIn(oldest_past, past_html)
        self.assertNotIn(newest_past, past_html)
        self.assertEqual(MY_SESSIONS_PER_PAGE, 10)

    def test_client_cannot_publish_or_bulk_delete_slots(self):
        self.login("client@gym.com", "client123")
        self.assertEqual(
            self.client.post("/book/2099/6/15/availability").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/book/2099/6/15/availability/all-day").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/book/2099/6/15/availability/delete-available").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/book/2099/6/15/bookings/cancel-booked").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/book/2099/6/15/bookings/delete-booked").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/sessions/1/delete").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/book/2099/6/15/availability/range").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/timeline/availability").status_code,
            403,
        )

    def test_timeline_is_available_to_every_role(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        casey = User.query.filter_by(email="client@gym.com").first()
        open_start = datetime(2099, 6, 16, 10, 0)
        casey_start = datetime(2099, 6, 16, 14, 0)
        open_slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=open_start,
            datetime_end=open_start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        booked_slot = GymSession(
            instructor_id=instructor.id,
            client_id=casey.id,
            datetime_start=casey_start,
            datetime_end=casey_start + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        db.session.add_all([open_slot, booked_slot])
        db.session.commit()
        open_id = open_slot.id
        booked_id = booked_slot.id
        remove_path = f"/sessions/{open_id}/remove".encode()
        book_path = f"/sessions/{open_id}/book".encode()
        cancel_path = f"/sessions/{booked_id}/cancel".encode()

        guest = self.client.get("/timeline")
        self.assertEqual(guest.status_code, 302)

        self.login("instructor@gym.com", "instructor123")
        page = self.client.get("/timeline?start=2099-06-16")
        self.assertEqual(page.status_code, 200)
        html = page.data
        self.assertIn(b"Session timeline", html)
        self.assertIn(b"timeline__block", html)
        self.assertNotIn(b"Available Slot", html)
        self.assertNotIn(b"Booked Slot", html)
        self.assertIn(b'timeline__block-person">Casey Client', html)
        self.assertNotIn(b'timeline__block-person">Alex Instructor', html)
        self.assertNotIn(b"timeline__block-time", html)
        self.assertIn(b'timeline__block--booked', html)
        self.assertIn(b">06:00<", html)
        self.assertIn(b">23:00<", html)
        self.assertIn(b"Tue", html)
        self.assertIn(b"16 Jun", html)
        self.assertNotIn(b"/book/2099/6/16", html)
        self.assertNotIn(b"timeline__block-link", html)
        self.assertIn(b"Previous week", html)
        self.assertIn(b"Next week", html)
        self.assertIn(b"timeline__block-action", html)
        self.assertIn(remove_path, html)
        self.assertIn(cancel_path, html)
        self.assertNotIn(book_path, html)
        self.assertIn(b"Delete this available slot?", html)
        self.assertIn(b"Cancel this booked session? The client will lose the booking.", html)
        self.assertIn(b'name="next"', html)
        self.assertIn(b"/timeline?start=2099-06-16", html)
        self.assertIn(b"Publish this week", html)
        self.assertIn(b'<details class="publish-card publish-card--range timeline-publish">', html)
        self.assertIn(b"publish-card__summary", html)
        self.assertNotIn(b'timeline-publish" open', html)
        self.assertIn(b"/timeline/availability", html)
        self.assertIn(b'timeline-day-chip', html)
        self.assertIn(b'value="2099-06-15"', html)
        self.assertIn(b'value="2099-06-19"', html)

        self.client.get("/logout")
        self.login("client@gym.com", "client123")
        casey_page = self.client.get("/timeline?start=2099-06-16")
        self.assertEqual(casey_page.status_code, 200)
        self.assertNotIn(b"Available Slot", casey_page.data)
        self.assertNotIn(b"Booked Slot", casey_page.data)
        self.assertIn(b'timeline__block-person">Alex Instructor', casey_page.data)
        self.assertNotIn(b'timeline__block-person">Casey Client', casey_page.data)
        self.assertIn(cancel_path, casey_page.data)
        self.assertIn(book_path, casey_page.data)
        self.assertIn(b"timeline__block-action", casey_page.data)
        self.assertIn(b"Book this session?", casey_page.data)
        self.assertIn(b"Cancel this booking? The slot will become available again.", casey_page.data)
        self.assertNotIn(remove_path, casey_page.data)
        self.assertNotIn(b"/remove", casey_page.data)
        self.assertNotIn(b"Delete this available slot?", casey_page.data)
        self.assertNotIn(b"Cancel this booked session? The client will lose the booking.", casey_page.data)
        self.assertNotIn(b"Publish this week", casey_page.data)
        self.assertNotIn(b"/timeline/availability", casey_page.data)

        self.client.get("/logout")
        self.login("jordan@gym.com", "client123")
        jordan_page = self.client.get("/timeline?start=2099-06-16")
        self.assertEqual(jordan_page.status_code, 200)
        self.assertNotIn(b"Available Slot", jordan_page.data)
        self.assertIn(b'timeline__block-person">Alex Instructor', jordan_page.data)
        self.assertNotIn(b"Booked Slot", jordan_page.data)
        self.assertNotIn(b"timeline__block--booked", jordan_page.data)
        self.assertIn(book_path, jordan_page.data)
        self.assertIn(b"Book this session?", jordan_page.data)
        self.assertIn(b"timeline__block-action", jordan_page.data)
        self.assertNotIn(cancel_path, jordan_page.data)
        self.assertNotIn(b"/remove", jordan_page.data)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_page = self.client.get("/timeline?start=2099-06-16")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn(b"Timeline", admin_page.data)
        self.assertIn(b'timeline__block-person">Alex Instructor', admin_page.data)
        self.assertIn(b'timeline__block-person">Casey Client', admin_page.data)
        self.assertIn(b"14:00", admin_page.data)
        self.assertIn(b"timeline__block-action", admin_page.data)
        self.assertIn(remove_path, admin_page.data)
        self.assertIn(cancel_path, admin_page.data)
        self.assertNotIn(book_path, admin_page.data)
        self.assertIn(b"Delete this available slot?", admin_page.data)
        self.assertIn(b"Cancel this booked session? The client will lose the booking.", admin_page.data)
        self.assertIn(b"Publish this week", admin_page.data)
        self.assertIn(b"week-instructor", admin_page.data)

        current_week = self.client.get("/timeline")
        self.assertEqual(current_week.status_code, 200)
        self.assertIn(b"timeline__today-badge", current_week.data)
        self.assertIn(b">Today<", current_week.data)
        self.assertIn(b"timeline__lane--today", current_week.data)
        self.assertIn(b"timeline__day-head--today", current_week.data)

        status, css = self.static_bytes("/static/css/timeline.css")
        self.assertEqual(status, 200)
        self.assertIn(b".timeline__block--available", css)
        self.assertIn(b".timeline__block--booked", css)
        self.assertIn(b".timeline__block-action", css)
        self.assertIn(b".timeline__block-action--book", css)
        self.assertIn(b".timeline__block--available {\n  background: #2e7d32;", css)
        self.assertIn(b".timeline__block-action--book button {\n  background: #ffffff;", css)
        self.assertIn(b".timeline__block-action button {\n  font-size: 0.52rem;", css)
        self.assertIn(b"color: #c62828;", css)
        self.assertIn(b".timeline__block:hover .timeline__block-action", css)
        self.assertIn(b".timeline__block:focus-within .timeline__block-action", css)
        self.assertIn(b".timeline__block--available.timeline__block--past", css)
        self.assertIn(b"rgba(46, 125, 50, 0.22)", css)
        self.assertIn(b".timeline__block--booked.timeline__block--past", css)
        self.assertIn(b"rgba(21, 101, 192, 0.22)", css)
        self.assertIn(b".timeline__today-badge", css)
        self.assertIn(b"3px solid #ffffff", css)
        self.assertIn(b"0 0 0 2px #fff, 0 0 0 5px #102a3a", css)
        self.assertIn(b"0 0 0 3px #fff, 0 0 0 8px #a5d6a7", css)
        self.assertIn(b"rgba(16, 42, 58, 0.75)", css)
        self.assertNotIn(b"#ffca28", css)
        self.assertNotIn(b"rgba(255, 193, 7", css)
        self.assertIn(b".timeline-swatch--past-available", css)
        self.assertIn(b".timeline-swatch--past-booked", css)
        self.assertIn(b".timeline__block-people", css)
        self.assertIn(b".timeline__block-person", css)
        self.assertNotIn(b".timeline__block-link", css)
        self.assertIn(b".timeline-publish", css)
        self.assertIn(b".timeline-day-chip", css)

    def test_instructor_can_publish_week_from_timeline(self):
        from datetime import datetime

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        self.login("instructor@gym.com", "instructor123")
        published = self.client.post(
            "/timeline/availability",
            data={
                "week_start": "2099-06-16",
                "days": ["2099-06-15", "2099-06-17"],
                "range_start_hour": "9",
                "range_start_minute": "0",
                "range_end_hour": "11",
                "range_end_minute": "0",
                "slot_minutes": "60",
                "break_minutes": "0",
            },
            follow_redirects=True,
        )
        self.assertEqual(published.status_code, 200)
        self.assertIn(b"Session timeline", published.data)
        self.assertIn(b"Published 4 slot", published.data)
        slots = (
            GymSession.query.filter_by(instructor_id=instructor.id, status=SESSION_AVAILABLE)
            .filter(GymSession.datetime_start >= datetime(2099, 6, 15))
            .filter(GymSession.datetime_start < datetime(2099, 6, 18))
            .order_by(GymSession.datetime_start)
            .all()
        )
        times = [(s.datetime_start.strftime("%Y-%m-%d %H:%M"), s.datetime_end.strftime("%H:%M")) for s in slots]
        self.assertEqual(
            times,
            [
                ("2099-06-15 09:00", "10:00"),
                ("2099-06-15 10:00", "11:00"),
                ("2099-06-17 09:00", "10:00"),
                ("2099-06-17 10:00", "11:00"),
            ],
        )

        again = self.client.post(
            "/timeline/availability",
            data={
                "week_start": "2099-06-15",
                "days": ["2099-06-15"],
                "range_start_hour": "9",
                "range_start_minute": "0",
                "range_end_hour": "11",
                "range_end_minute": "0",
                "slot_minutes": "60",
                "break_minutes": "0",
            },
            follow_redirects=True,
        )
        self.assertIn(b"No new slots were published", again.data)

        skipped_day = self.client.post(
            "/timeline/availability",
            data={
                "week_start": "2099-06-15",
                "days": ["2099-06-22"],
                "range_start_hour": "9",
                "range_start_minute": "0",
                "range_end_hour": "11",
                "range_end_minute": "0",
                "slot_minutes": "60",
                "break_minutes": "0",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Choose at least one remaining day in this week.", skipped_day.data)

    def test_timeline_hover_actions_post_back_to_week(self):
        from datetime import datetime, timedelta

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        casey = User.query.filter_by(email="client@gym.com").first()
        next_week = "/timeline?start=2099-06-16"

        open_start = datetime(2099, 6, 16, 9, 0)
        instructor_booked_start = datetime(2099, 6, 16, 11, 0)
        client_booked_start = datetime(2099, 6, 16, 15, 0)
        trap_start = datetime(2099, 6, 16, 16, 0)
        open_slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=open_start,
            datetime_end=open_start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        instructor_booked = GymSession(
            instructor_id=instructor.id,
            client_id=casey.id,
            datetime_start=instructor_booked_start,
            datetime_end=instructor_booked_start + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        client_booked = GymSession(
            instructor_id=instructor.id,
            client_id=casey.id,
            datetime_start=client_booked_start,
            datetime_end=client_booked_start + timedelta(hours=1),
            status=SESSION_BOOKED,
        )
        trap_slot = GymSession(
            instructor_id=instructor.id,
            datetime_start=trap_start,
            datetime_end=trap_start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        client_open_start = datetime(2099, 6, 16, 17, 0)
        client_open = GymSession(
            instructor_id=instructor.id,
            datetime_start=client_open_start,
            datetime_end=client_open_start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        db.session.add_all([open_slot, instructor_booked, client_booked, trap_slot, client_open])
        db.session.commit()
        open_id = open_slot.id
        instructor_booked_id = instructor_booked.id
        client_booked_id = client_booked.id
        trap_id = trap_slot.id
        client_open_id = client_open.id

        self.login("instructor@gym.com", "instructor123")
        deleted = self.client.post(
            f"/sessions/{open_id}/remove",
            data={"next": next_week},
            follow_redirects=False,
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertIn(next_week, deleted.headers["Location"])
        self.assertIsNone(db.session.get(GymSession, open_id))

        cancelled = self.client.post(
            f"/sessions/{instructor_booked_id}/cancel",
            data={"next": next_week},
            follow_redirects=True,
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn(b"Session timeline", cancelled.data)
        self.assertIn(b"Session cancelled", cancelled.data)
        instructor_refreshed = db.session.get(GymSession, instructor_booked_id)
        self.assertEqual(instructor_refreshed.status, SESSION_CANCELLED)

        blocked = self.client.post(
            f"/sessions/{trap_id}/remove",
            data={"next": "https://evil.example/timeline"},
            follow_redirects=False,
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertNotIn("evil.example", blocked.headers["Location"])
        self.assertIsNone(db.session.get(GymSession, trap_id))

        self.client.get("/logout")
        self.login("client@gym.com", "client123")
        client_cancel = self.client.post(
            f"/sessions/{client_booked_id}/cancel",
            data={"next": next_week},
            follow_redirects=True,
        )
        self.assertEqual(client_cancel.status_code, 200)
        self.assertIn(b"Session timeline", client_cancel.data)
        self.assertIn(b"available again", client_cancel.data)
        client_refreshed = db.session.get(GymSession, client_booked_id)
        self.assertEqual(client_refreshed.status, SESSION_AVAILABLE)
        self.assertIsNone(client_refreshed.client_id)

        booked = self.client.post(
            f"/sessions/{client_open_id}/book",
            data={"next": next_week},
            follow_redirects=True,
        )
        self.assertEqual(booked.status_code, 200)
        self.assertIn(b"Session timeline", booked.data)
        self.assertIn(b"Session booked", booked.data)
        open_refreshed = db.session.get(GymSession, client_open_id)
        self.assertEqual(open_refreshed.status, SESSION_BOOKED)
        self.assertEqual(open_refreshed.client_id, casey.id)

    def test_home_shows_stats_for_each_role(self):
        from datetime import datetime, timedelta

        from website.utils import stats as home_stats
        from website.utils.timeutils import now_gym

        now = now_gym()
        instructor = User.query.filter_by(email="instructor@gym.com").first()
        casey = User.query.filter_by(email="client@gym.com").first()
        before = home_stats.instructor_dashboard(instructor, now)
        before_booked = before["months"][-1]["booked_hours"]
        before_future_open = before["months"][-1].get("open_future_hours", 0.0)
        before_future_booked = before["months"][-1].get("booked_future_hours", 0.0)

        start = datetime(now.year, now.month, 1, 5, 5)
        past_open_start = (now - timedelta(days=2)).replace(minute=7, second=0, microsecond=0)
        future_open_start = (now + timedelta(hours=6)).replace(minute=7, second=0, microsecond=0)
        future_booked_start = (now + timedelta(hours=8)).replace(minute=17, second=0, microsecond=0)
        if future_open_start.month != now.month:
            future_open_start = datetime(now.year, now.month, now.day, 23, 7)
        if future_booked_start.month != now.month:
            future_booked_start = datetime(now.year, now.month, now.day, 22, 17)
        self.cancel_active_start(instructor.id, start)
        self.cancel_active_start(instructor.id, past_open_start)
        self.cancel_active_start(instructor.id, future_open_start)
        self.cancel_active_start(instructor.id, future_booked_start)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=casey.id,
                datetime_start=start,
                datetime_end=start + timedelta(hours=2),
                status=SESSION_BOOKED,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=past_open_start,
                datetime_end=past_open_start + timedelta(minutes=90),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                datetime_start=future_open_start,
                datetime_end=future_open_start + timedelta(hours=3),
                status=SESSION_AVAILABLE,
            )
        )
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=casey.id,
                datetime_start=future_booked_start,
                datetime_end=future_booked_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        instructor_dash = home_stats.instructor_dashboard(instructor, now)
        self.assertGreaterEqual(instructor_dash["months"][-1]["booked_hours"], before_booked + 2.0)
        past_label = datetime(past_open_start.year, past_open_start.month, 1).strftime("%b %Y")
        before_past_open = next(row["open_hours"] for row in before["months"] if row["label"] == past_label)
        after_past_open = next(
            row["open_hours"] for row in instructor_dash["months"] if row["label"] == past_label
        )
        self.assertAlmostEqual(after_past_open, before_past_open + 1.5, places=5)
        current_row = instructor_dash["months"][-1]
        self.assertTrue(current_row["is_current"])
        self.assertAlmostEqual(
            current_row["open_future_hours"],
            before_future_open + 3.0,
            places=5,
        )
        self.assertAlmostEqual(
            current_row["booked_future_hours"],
            before_future_booked + 1.0,
            places=5,
        )
        self.assertGreaterEqual(current_row["booked_past_hours"], 2.0)
        self.assertTrue(instructor_dash["include_open"])
        self.assertIn("chart", instructor_dash)
        self.assertTrue(instructor_dash["chart"]["include_open"])
        self.assertEqual(len(instructor_dash["chart"]["groups"]), 6)
        current_month = datetime(now.year, now.month, 1).strftime("%b %Y")
        current_group = next(
            group for group in instructor_dash["chart"]["groups"] if current_month in group["summary"]
        )
        self.assertEqual(len(current_group["bars"]), 4)
        past_booked, upcoming_booked, past_unbooked, upcoming_unbooked = current_group["bars"]
        self.assertIn("past booked", past_booked["title"])
        self.assertEqual(past_booked["fill"], "#1565c0")
        self.assertIn("upcoming booked", upcoming_booked["title"])
        self.assertEqual(upcoming_booked["fill"], "#90caf9")
        self.assertEqual(past_booked["x"], upcoming_booked["x"])
        self.assertLess(upcoming_booked["y"], past_booked["y"])
        self.assertIn("past unbooked", past_unbooked["title"])
        self.assertEqual(past_unbooked["fill"], "#2e7d32")
        self.assertIn("upcoming unbooked", upcoming_unbooked["title"])
        self.assertEqual(upcoming_unbooked["fill"], "#a5d6a7")
        self.assertEqual(past_unbooked["x"], upcoming_unbooked["x"])
        self.assertLess(upcoming_unbooked["y"], past_unbooked["y"])
        self.assertGreater(past_unbooked["x"], past_booked["x"])
        older_group = instructor_dash["chart"]["groups"][0]
        self.assertEqual(len(older_group["bars"]), 2)
        self.assertIn("booked", older_group["bars"][0]["title"])
        self.assertEqual(older_group["bars"][0]["fill"], "#1565c0")
        self.assertIn("unbooked", older_group["bars"][1]["title"])
        self.assertEqual(older_group["bars"][1]["fill"], "#2e7d32")
        labels = [card["label"] for card in instructor_dash["cards"]]
        self.assertIn("Booked this month", labels)
        self.assertIn("Average booked / month", labels)
        self.assertIn("Average unbooked / month", labels)
        self.assertIn("Fill rate this month", labels)
        self.assertIn("Clients this month", labels)

        self.login("instructor@gym.com", "instructor123")
        instructor_home = self.client.get("/")
        self.assertEqual(instructor_home.status_code, 200)
        self.assertIn(b"Your teaching stats", instructor_home.data)
        self.assertIn(b"Booked this month", instructor_home.data)
        self.assertIn(b"Average unbooked / month", instructor_home.data)
        self.assertIn(b"Fill rate this month", instructor_home.data)
        self.assertIn(b"stat-chart", instructor_home.data)
        self.assertIn(b"Hours by month", instructor_home.data)
        self.assertIn(b"<svg", instructor_home.data)
        self.assertIn(b"stat-chart__swatch--booked-past", instructor_home.data)
        self.assertIn(b"stat-chart__swatch--booked", instructor_home.data)
        self.assertIn(b"stat-chart__swatch--unbooked-past", instructor_home.data)
        self.assertIn(b"stat-chart__swatch--unbooked", instructor_home.data)
        self.assertIn(b"Past booked", instructor_home.data)
        self.assertIn(b"Booked (upcoming)", instructor_home.data)
        self.assertIn(b"Past unbooked", instructor_home.data)
        self.assertIn(b"Unbooked (upcoming)", instructor_home.data)
        self.assertIn(b"stacks past hours under upcoming hours", instructor_home.data)
        self.assertNotIn(b"stat-table", instructor_home.data)
        self.assertIn(b" h ", instructor_home.data)
        self.assertIn(b" min", instructor_home.data)

        self.client.get("/logout")
        self.login("client@gym.com", "client123")
        client_home = self.client.get("/")
        self.assertEqual(client_home.status_code, 200)
        self.assertIn(b"Your training stats", client_home.data)
        self.assertIn(b"Booked this month", client_home.data)
        self.assertIn(b"Average booked / month", client_home.data)
        self.assertNotIn(b"Average unbooked / month", client_home.data)
        self.assertIn(b"Hours in the last 6 months", client_home.data)
        self.assertIn(b"stat-chart", client_home.data)
        self.assertIn(b"stat-chart__swatch--booked-past", client_home.data)
        self.assertIn(b"stat-chart__swatch--booked", client_home.data)
        self.assertNotIn(b"stat-chart__swatch--unbooked", client_home.data)
        self.assertNotIn(b"Past unbooked", client_home.data)
        self.assertIn(b"Booked (upcoming)", client_home.data)
        client_dash = home_stats.client_dashboard(casey, now)
        client_group = next(
            group for group in client_dash["chart"]["groups"] if current_month in group["summary"]
        )
        self.assertEqual(len(client_group["bars"]), 2)
        self.assertIn("past booked", client_group["bars"][0]["title"])
        self.assertEqual(client_group["bars"][0]["fill"], "#1565c0")
        self.assertIn("upcoming booked", client_group["bars"][1]["title"])
        self.assertEqual(client_group["bars"][1]["fill"], "#90caf9")
        self.assertEqual(client_group["bars"][0]["x"], client_group["bars"][1]["x"])
        self.assertLess(client_group["bars"][1]["y"], client_group["bars"][0]["y"])

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_home = self.client.get("/")
        self.assertEqual(admin_home.status_code, 200)
        self.assertIn(b"Gym stats", admin_home.data)
        self.assertIn(b"Active clients this month", admin_home.data)
        self.assertIn(b"Fill rate this month", admin_home.data)
        self.assertIn(b"Users", admin_home.data)
        self.assertIn(b"stat-chart", admin_home.data)
        self.assertIn(b"stat-chart__swatch--unbooked-past", admin_home.data)
        self.assertIn(b"#90caf9", admin_home.data)
        self.assertIn(b"#1565c0", admin_home.data)
        self.assertIn(b"#a5d6a7", admin_home.data)
        self.assertIn(b"#2e7d32", admin_home.data)

        _status, css = self.static_bytes("/static/css/app.css")
        self.assertIn(b".stat-grid", css)
        self.assertIn(b".stat-card", css)
        self.assertIn(b".stat-chart", css)
        self.assertIn(b".stat-chart__swatch--booked-past {\n  background: #1565c0;", css)
        self.assertIn(b".stat-chart__swatch--booked {\n  background: #90caf9;", css)
        self.assertIn(b".stat-chart__swatch--unbooked-past {\n  background: #2e7d32;", css)
        self.assertIn(b".stat-chart__swatch--unbooked {\n  background: #a5d6a7;", css)
        self.assertNotIn(b".stat-table {", css)

    def test_seed_demo_false_skips_demo_accounts(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        app = create_app(
            {
                "TESTING": True,
                "SEED_DEMO": False,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + handle.name,
            }
        )
        try:
            with app.app_context():
                self.assertIsNone(User.query.filter_by(email="admin@gym.com").first())
                self.assertEqual(User.query.count(), 0)
        finally:
            os.unlink(handle.name)

    def test_secret_key_reads_environment(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        previous = os.environ.get("SECRET_KEY")
        os.environ["SECRET_KEY"] = "from-env-test-key"
        try:
            app = create_app(
                {
                    "TESTING": True,
                    "SEED_DEMO": False,
                    "SQLALCHEMY_DATABASE_URI": "sqlite:///" + handle.name,
                }
            )
            self.assertEqual(app.config["SECRET_KEY"], "from-env-test-key")
        finally:
            if previous is None:
                os.environ.pop("SECRET_KEY", None)
            else:
                os.environ["SECRET_KEY"] = previous
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
