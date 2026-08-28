# Gym Sessions

Flask app for 1-on-1 gym booking (admin, instructor, client). Gym time is `Europe/Athens`.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_DEBUG=1
export SEED_DEMO=1
export SECRET_KEY=dev
python main.py
```

Open http://127.0.0.1:5000

Demo logins (only when `SEED_DEMO=1` or `FLASK_ENV=development`):

- Admin: `admin@gym.com` / `admin123`
- Instructor: `instructor@gym.com` / `instructor123`
- Clients: `client@gym.com`, `jordan@gym.com`, `riley@gym.com`, `morgan@gym.com` / `client123`

## Tests

```bash
python -m unittest tests.test_booking
```

## Config

- `SECRET_KEY` — Flask secret. Required for any public host. Defaults to an insecure dev value.
- `DATABASE_URL` — SQLAlchemy URI. Default: SQLite in the Flask `instance/` folder.
- `SEED_DEMO` — `1` to create demo users and sample sessions on startup.
- `FLASK_ENV` — `development` also enables demo seed.
- `FLASK_DEBUG` — `1` to run the debug server (local only).
- `GYM_TIMEZONE` — Default `Europe/Athens`.
- `HOST` — Default `0.0.0.0`.
- `PORT` — Default `5000`.

Do not commit `*.db` (SQLite files). Production should set `SECRET_KEY`, leave `SEED_DEMO` unset, and not use `FLASK_DEBUG`.
