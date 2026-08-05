"""GitHub Actions runner: called every 30 min, sends Tefilin reminders."""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

import pytz

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "state.json"
ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
HOUR_START = 9
HOUR_END = 21


def tg(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"chat_ids": [], "confirmed": {}, "date": "", "last_update_id": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


REMINDER_TEXT = (
    "🔔 *תזכורת יומית – תפילין!*\n\n"
    "הגיע הזמן להניח תפילין ✡️\n"
    "לחץ על הכפתור כשתסיים."
)
DONE_KEYBOARD = {"inline_keyboard": [[{"text": "✅ הנחתי תפילין!", "callback_data": "done"}]]}


def main():
    now = datetime.now(ISRAEL_TZ)
    today = now.strftime("%Y-%m-%d")
    hour = now.hour

    if not (HOUR_START <= hour < HOUR_END):
        print(f"Outside reminder hours ({hour}:00 Israel). Nothing to do.")
        return

    state = load_state()

    if state.get("date") != today:
        state["confirmed"] = {}
        state["date"] = today
        print(f"New day {today} — confirmations reset.")

    # Fetch unprocessed Telegram updates
    offset = state.get("last_update_id", 0) + 1
    try:
        result = tg("getUpdates", {"offset": offset, "timeout": 5})
        updates = result.get("result", [])
    except Exception as e:
        print(f"getUpdates error: {e}")
        updates = []

    for upd in updates:
        uid = upd["update_id"]
        state["last_update_id"] = max(state.get("last_update_id", 0), uid)

        if "message" in upd:
            msg = upd["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")

            if text.startswith("/start"):
                if chat_id not in state["chat_ids"]:
                    state["chat_ids"].append(chat_id)
                    print(f"Registered {chat_id}")
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": (
                        "✡️ *בוט תפילין הופעל!*\n\n"
                        "אני אשלח לך תזכורת כל יום ב-09:00 להניח תפילין.\n"
                        "אם לא תלחץ ✅, אחזור ואתזכיר כל 30 דקות.\n\nב״ה תצליח בכל יום! 🙏"
                    ),
                    "parse_mode": "Markdown",
                })

            elif text.startswith("/status"):
                done = str(chat_id) in state["confirmed"]
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "✅ כבר הנחת תפילין היום!" if done else "⏳ עדיין לא הנחת תפילין היום.",
                    **({} if done else {"reply_markup": DONE_KEYBOARD}),
                })

        if "callback_query" in upd:
            cb = upd["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            if cb.get("data") == "done":
                state["confirmed"][str(chat_id)] = today
                tg("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "כל הכבוד! 🎉"})
                tg("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": cb["message"]["message_id"],
                    "text": "✅ *מצוין! הנחת תפילין היום!*\n\nיישר כח! לא אטריד אותך יותר להיום. 🙏",
                    "parse_mode": "Markdown",
                })
                print(f"User {chat_id} confirmed.")

    save_state(state)

    # Send reminders to unconfirmed users
    for chat_id in state["chat_ids"]:
        if str(chat_id) not in state["confirmed"]:
            print(f"Reminding {chat_id}")
            try:
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": REMINDER_TEXT,
                    "parse_mode": "Markdown",
                    "reply_markup": DONE_KEYBOARD,
                })
            except Exception as e:
                print(f"Failed to remind {chat_id}: {e}")
        else:
            print(f"User {chat_id} already confirmed.")

    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
