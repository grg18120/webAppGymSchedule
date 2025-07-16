
from website.models import User
import html

def sanitize_str_input(input_str):
    # Escaping special characters in HTML
    sanitized_str = html.escape(input_str)
    return sanitized_str
