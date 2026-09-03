# Vulnerable sample used to exercise the ReviewX AST scanner.
import os
import shutil
import threading

API_KEY = "sk-proj-abcdefghij0123456789abcdefghij"
auth_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
password = "P@ssw0rd!991"
db_url = "mysql://admin:hunter2@db.example.com:3306/app"

def build_query(uid):
    return "SELECT * FROM users WHERE id=" + uid

def run_user_code(code):
    eval(code)
    exec("print('hello')")

def dangerous_formatted_query(name):
    sql = "SELECT * FROM users WHERE name = '{}'".format(name)
    return sql

def unsafe_fstring(user_id):
    return f"SELECT id FROM accounts WHERE owner_id = {user_id}"

def nuke_dir(path):
    shutil.rmtree(path)

def broken_lock():
    lock = threading.Lock()
    lock.acquire()

def odbc_dsn():
    return "Driver={ODBC Driver 17 for SQL Server};Server=tcp:db.local;Database=app;Uid=sa;Pwd=c0mple!Pass;"

def get_secret_config():
    cfg = {"api_key": "AKIAIOSFODNN7EXAMPLE", "token": "ghp_1234567890abcdefghijklmopqrstuvwx"}
    return cfg

DEFAULT_PWD = "hunter2"