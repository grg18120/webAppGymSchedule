import os
import tempfile
import unittest

from website import create_app, db
from website.models import GymSession, ROLE_CLIENT, SESSION_AVAILABLE, SESSION_BOOKED, User
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
        self.assertEqual(User.query.filter_by(role="instructor").count(), 2)
        self.assertEqual(User.query.filter_by(role="admin").count(), 1)

        self.login("jordan@gym.com", "client123")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Client", home.data)
        self.assertEqual(self.client.get("/users").status_code, 403)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        users_page = self.client.get("/users")
        self.assertEqual(users_page.status_code, 200)
        for email in emails + ["sam@gym.com", "instructor@gym.com"]:
            self.assertIn(email.encode(), users_page.data)
        self.assertIn(b"filterRole", users_page.data)

    def test_calendar_labels_open_slots_and_past_bookings(self):
        from datetime import datetime, timedelta

        from website.models import SESSION_BOOKED

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        past_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=2)
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
        css = self.client.get("/static/css/trainers_book.css")
        self.assertEqual(css.status_code, 200)
        self.assertIn(b"#1565c0", css.data)
        self.assertIn(b"rgba(21, 101, 192", css.data)
        self.assertNotIn(b"#8e24aa", css.data)
        self.assertNotIn(b"#ce93d8", css.data)
        self.assertIn(b"a.day.no-slots:hover", css.data)
        self.assertIn(b"color: #ffffff", css.data)
        self.assertIn(b"color: #000000", css.data)

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
        self.assertIn(b"Delete all Available slots", html)
        self.assertIn(b"Delete all Booked Slots", html)
        self.assertIn(
            b"Delete ALL booked slots on this day? Clients will lose those sessions.",
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

        deleted_booked = self.client.post(
            "/book/2099/6/17/bookings/delete-booked",
            follow_redirects=True,
        )
        self.assertIn(b"Deleted 1 booked slot", deleted_booked.data)
        self.assertEqual(
            GymSession.query.filter(
                GymSession.instructor_id == instructor.id,
                GymSession.datetime_start >= datetime(2099, 6, 17),
                GymSession.datetime_start < datetime(2099, 6, 18),
            ).count(),
            0,
        )

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
            self.client.post("/book/2099/6/15/bookings/delete-booked").status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
