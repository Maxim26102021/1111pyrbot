import os
from pyrogram import Client

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_name = os.getenv("TELEGRAM_SESSION_NAME", "service1")
sessions_dir = "/app/sessions"
os.makedirs(sessions_dir, exist_ok=True)

if __name__ == "__main__":
    app = Client(session_name, api_id=api_id, api_hash=api_hash, workdir=sessions_dir)
    print("Starting interactive login for service account...")
    with app:
        me = app.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username})")
        print(f"Session stored at: {sessions_dir}/{session_name}.session")
