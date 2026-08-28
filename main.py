import os

from website import create_app

app_flask = create_app()


def _env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    app_flask.run(
        debug=_env_flag("FLASK_DEBUG"),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )
