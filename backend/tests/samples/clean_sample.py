# Clean sample - the scanner should find nothing in this file.
import os
import threading

def get_conn():
    return "mysql://localhost/app"

def run_query(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = ?", [user_id])

def safe_cleanup(target):
    if input("Delete this file? (y/n) ") == "y":
        os.remove(target)

def safe_lock():
    lock = threading.Lock()
    with lock:
        pass

def load_password():
    password = os.environ.get("API_PASSWORD")
    return password

API_KEY = "xxx"
SECRET_KEY = "changeme"