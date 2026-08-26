import html
from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def sanitize_str_input(input_str):
    if input_str is None:
        return ""
    return html.escape(input_str)


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
