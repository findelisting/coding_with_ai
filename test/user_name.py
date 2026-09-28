#user_name.py
def user_name(first, last):
    first = first.capitalize()
    last = last.capitalize()
    username = first[0] + last
    return f"{first} {last} ({username})"

