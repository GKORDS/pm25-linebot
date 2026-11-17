# -*- coding: utf-8 -*-
"""
app.py
โปรแกรมหลักของไลน์บอทแจ้งเตือนค่าฝุน PM 2.5
ทำหน้าที่เป็นเว็บฮุก (Webhook) ด้วย Flask รับเหตุการณ์จาก LINE Messaging API
ดึงข้อมูลค่าฝุนจาก Air4Thai มาเปรียบเทียบกับค่ามาตรฐาน แล้วตอบกลับพร้อมคำแนะนำ
และส่งข้อความแจ้งเตือนอัตโนมัติ (Push message) เมื่อค่าฝุนเกินมาตรฐาน

วิธีรันในเครื่อง:  python app.py
วิธีรันบนเซิร์ฟเวอร์ (Render):  gunicorn app:app
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

# ให้คอนโซลแสดงภาษาไทยได้ถูกต้อง (โดยเฉพาะบน Windows ที่ใช้ค่าเริ่มต้น cp1252)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    LocationMessageContent,
    FollowEvent,
)

import config
import aqi
import air4thai
import messages
import storage
import stations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pm25bot")

app = Flask(__name__)

# ตั้งค่าการเชื่อมต่อ LINE (อ่าน Token/Secret จาก environment ผ่าน config.py)
configuration = Configuration(access_token=config.CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.CHANNEL_SECRET or "dummy-secret")


# ---------- ฟังก์ชันช่วยส่งข้อความ ----------
def _as_list(messages_):
    return messages_ if isinstance(messages_, list) else [messages_]


def reply(reply_token, messages_):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=_as_list(messages_))
        )


def push(user_id, messages_):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=_as_list(messages_))
        )


# ---------- เว็บฮุกรับเหตุการณ์จาก LINE ----------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        log.warning("ลายเซ็นไม่ถูกต้อง — ตรวจสอบ Channel secret อีกครั้ง")
        abort(400)
    except Exception:
        # อย่าปล่อยให้ข้อผิดพลาดภายใน handler ทำให้ตอบกลับเป็น 500
        # เพราะ LINE จะถือว่าส่งไม่สำเร็จแล้วส่งเหตุการณ์เดิมซ้ำ (retry) ทำให้ตอบซ้ำ
        log.exception("เกิดข้อผิดพลาดระหว่างประมวลผลเหตุการณ์จาก LINE")
    return "OK"


# ---------- ผู้ใช้ส่งข้อความตัวอักษร ----------
@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event):
    user_id = event.source.user_id
    text = (event.message.text or "").strip()
    storage.register(user_id)  # ลงทะเบียนผู้ใช้อัตโนมัติเมื่อทักเข้ามา
    alert_on = storage.is_alert_on(user_id)
    low = text.lower()

    # 1) ผู้ใช้พิมพ์/กดเลือกรหัสสถานีโดยตรง (เช่น "50t")
    if stations.is_known(text):
        storage.set_station(user_id, text)
        reading = air4thai.get_reading(text)
        reply(event.reply_token, messages.report_message(reading, quick_reply=messages.main_quick_reply(alert_on)))
        return

    # 2) ขอเปลี่ยน/เลือกพื้นที่
    if any(k in text for k in ("เปลี่ยนพื้นที่", "เลือกพื้นที่", "พื้นที่", "สถานี")):
        reply(event.reply_token, messages.text_message(
            "เลือกพื้นที่ตรวจวัด หรือส่งตำแหน่งของคุณ 📍",
            quick_reply=messages.station_quick_reply(),
        ))
        return

    # 3) เปิด/ปิดการแจ้งเตือน
    # หมายเหตุ: ต้องตรวจ "เปิดแจ้งเตือน" ก่อน "ปิดแจ้งเตือน" เสมอ
    # เพราะคำว่า "ปิดแจ้งเตือน" เป็นส่วนหนึ่งของคำว่า "เปิดแจ้งเตือน" (เ + ปิดแจ้งเตือน)
    if "เปิดแจ้งเตือน" in text:
        storage.set_alert(user_id, True)
        reply(event.reply_token, messages.text_message(
            f"🔔 เปิดการแจ้งเตือนแล้ว เมื่อค่าฝุนเกิน {aqi.STANDARD:g} {messages.UNIT} จะแจ้งให้ทราบอัตโนมัติ",
            quick_reply=messages.main_quick_reply(alert_on=True),
        ))
        return
    if "ปิดแจ้งเตือน" in text:
        storage.set_alert(user_id, False)
        reply(event.reply_token, messages.text_message(
            "🔕 ปิดการแจ้งเตือนอัตโนมัติแล้ว พิมพ์ \"เปิดแจ้งเตือน\" เพื่อเปิดอีกครั้ง",
            quick_reply=messages.main_quick_reply(alert_on=False),
        ))
        return

    # 4) ขอความช่วยเหลือ / เมนู
    if any(k in text for k in ("วิธีใช้", "ช่วยเหลือ", "เมนู", "menu", "help", "start", "เริ่ม")):
        reply(event.reply_token, messages.text_message(messages.HELP_TEXT, quick_reply=messages.main_quick_reply(alert_on)))
        return

    # 5) ขอเช็คค่าฝุน (คำว่า ฝุน / เช็ค / pm / aqi / อากาศ)
    if any(k in text for k in ("ฝุน", "เช็ค", "อากาศ")) or any(k in low for k in ("pm", "aqi", "air")):
        reading = air4thai.get_reading(storage.get_station(user_id))
        reply(event.reply_token, messages.report_message(reading, quick_reply=messages.main_quick_reply(alert_on)))
        return

    # 6) อื่น ๆ — แสดงวิธีใช้
    reply(event.reply_token, messages.text_message(messages.HELP_TEXT, quick_reply=messages.main_quick_reply(alert_on)))


# ---------- ผู้ใช้ส่งตำแหน่งที่ตั้ง (Location) ----------
@handler.add(MessageEvent, message=LocationMessageContent)
def on_location(event):
    user_id = event.source.user_id
    storage.register(user_id)
    alert_on = storage.is_alert_on(user_id)

    reading = air4thai.nearest_station(event.message.latitude, event.message.longitude)
    if reading is None:
        reply(event.reply_token, messages.text_message(
            "ขออภัย หาสถานีตรวจวัดใกล้ตำแหน่งของคุณไม่ได้ในขณะนี้",
            quick_reply=messages.main_quick_reply(alert_on),
        ))
        return

    storage.set_station(user_id, reading["station_id"])
    note = messages.text_message(
        f'พบสถานีใกล้คุณที่สุด: {reading.get("name_th")} (ห่าง ~{reading.get("distance_km")} กม.)'
    )
    report = messages.report_message(reading, quick_reply=messages.main_quick_reply(alert_on))
    reply(event.reply_token, [note, report])


# ---------- ผู้ใช้เพิ่มบอทเป็นเพื่อน (Follow) ----------
@handler.add(FollowEvent)
def on_follow(event):
    user_id = event.source.user_id
    storage.register(user_id)
    reading = air4thai.get_reading(storage.get_station(user_id))
    reply(event.reply_token, [
        messages.text_message(messages.WELCOME_TEXT),
        messages.report_message(reading, quick_reply=messages.main_quick_reply(alert_on=True)),
    ])


# ---------- การแจ้งเตือนอัตโนมัติเมื่อค่าฝุนเกินมาตรฐาน ----------
THAILAND_TIME = timezone(timedelta(hours=7))
MAX_ALERT_READING_AGE = timedelta(hours=3)


def is_current_reading(reading, now):
    try:
        observed = datetime.strptime(
            f'{reading.get("date")} {reading.get("time")}', "%Y-%m-%d %H:%M"
        ).replace(tzinfo=THAILAND_TIME)
    except ValueError:
        return False
    return timedelta(0) <= now - observed <= MAX_ALERT_READING_AGE


def check_and_alert():
    """
    ตรวจค่าฝุนของสถานีที่ผู้ใช้แต่ละคนเลือกไว้
    ถ้าเกินมาตรฐาน (> 37.5) และพ้นช่วงพักการเตือนแล้ว จะส่ง Push message
    คืนจำนวนข้อความแจ้งเตือนที่ส่งออกไป
    """
    if not config.is_configured():
        log.warning("ยังไม่ได้ตั้งค่า Token/Secret — ข้ามการแจ้งเตือน")
        return 0

    # จัดกลุ่มผู้ใช้ตามสถานี เพื่อลดการดึงข้อมูลซ้ำ
    by_station = {}
    for uid in storage.alert_users():
        by_station.setdefault(storage.get_station(uid), []).append(uid)

    sent = 0
    for station_id, uids in by_station.items():
        reading = air4thai.get_reading(station_id)
        if not reading or reading.get("pm25") is None:
            continue
        if not aqi.is_over_standard(reading["pm25"]):
            continue
        if not is_current_reading(reading, datetime.now(THAILAND_TIME)):
            log.info("ข้ามการแจ้งเตือนสถานี %s เพราะข้อมูลหมดอายุหรือเวลาไม่ถูกต้อง", station_id)
            continue
        msg = messages.report_message(reading, alert=True, quick_reply=messages.main_quick_reply())
        for uid in uids:
            # จอง (claim) สิทธิ์แจ้งเตือนแบบ atomic ก่อนส่ง เพื่อกันการเตือนซ้ำ
            # หากมีหลายเธรดเรียก check_and_alert พร้อมกัน (ตัวตั้งเวลา + /check)
            if not storage.claim_alert(uid, config.ALERT_COOLDOWN_HOURS, station_id):
                continue
            try:
                push(uid, msg)
                sent += 1
            except Exception as e:  # ผู้ใช้อาจบล็อกบอท หรือเครือข่ายมีปัญหา
                log.warning("ส่งแจ้งเตือน LINE ไม่สำเร็จ (%s, status=%s)",
                            type(e).__name__, getattr(e, "status", None))
    log.info("ตรวจค่าฝุนเสร็จ ส่งแจ้งเตือน %d ข้อความ", sent)
    return sent


# ---------- เส้นทางเสริม ----------
@app.route("/")
def home():
    """หน้าสถานะ (ใช้เป็นปลายทางให้ uptime pinger เรียกเพื่อกันเซิร์ฟเวอร์หลับด้วย)"""
    status = "พร้อมใช้งาน ✅" if config.is_configured() else "ยังไม่ได้ตั้งค่า Token/Secret ⚠️"
    return (
        "<h3>PM2.5 LINE Bot</h3>"
        f"<p>สถานะ: {status}</p>"
        f"<p>ผู้ใช้ที่ลงทะเบียน: {storage.count()} คน · "
        f"แจ้งเตือนอัตโนมัติ: {'เปิด' if config.ALERT_ENABLED else 'ปิด'}</p>"
    )


@app.route("/check")
def check_route():
    """
    ให้ตัวตั้งเวลาภายนอก (เช่น cron-job.org) เรียกเพื่อสั่งตรวจ-แจ้งเตือนหนึ่งรอบ
    ป้องกันด้วย CHECK_TOKEN: เรียกแบบ /check?token=<ค่าลับ>
    ถ้าไม่ได้ตั้ง CHECK_TOKEN จะอนุญาตเฉพาะการเรียกจากเครื่องเดียวกัน (localhost)
    เพื่อไม่ให้ปลายทางสาธารณะถูกเรียกโดยไม่ได้รับอนุญาต (fail-closed)
    """
    if config.CHECK_TOKEN:
        if request.args.get("token") != config.CHECK_TOKEN:
            abort(403)
    elif request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    sent = check_and_alert()
    return f"ตรวจแล้ว ส่งแจ้งเตือน {sent} ข้อความ"


@app.route("/selftest")
def selftest_route():
    """ทดสอบการดึงข้อมูลค่าฝุน (เปิดในเบราว์เซอร์ได้โดยไม่ต้องมี LINE)"""
    station_id = request.args.get("station", config.DEFAULT_STATION)
    reading = air4thai.get_reading(station_id)
    return "<pre>" + messages.report_text(reading) + "</pre>"


# ---------- ตัวตั้งเวลาในตัวโปรแกรม (เหมือนตามรายงาน) ----------
_scheduler_started = False


def start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    if not (config.ALERT_ENABLED and config.is_configured()):
        log.info("ไม่เริ่มตัวตั้งเวลา (ALERT_ENABLED=%s, ตั้งค่าครบ=%s)",
                 config.ALERT_ENABLED, config.is_configured())
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_alert, "interval", minutes=config.CHECK_INTERVAL_MINUTES,
        id="pm25-check", next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    _scheduler_started = True
    log.info("เริ่มตัวตั้งเวลาตรวจค่าฝุนทุก %d นาที", config.CHECK_INTERVAL_MINUTES)


# เริ่มตัวตั้งเวลาเมื่อโมดูลถูกโหลด (รองรับทั้ง python app.py และ gunicorn app:app)
start_scheduler()


if __name__ == "__main__":
    if not config.is_configured():
        log.warning("ยังไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET "
                    "(คัดลอก .env.example เป็น .env แล้วเติมค่า) — ส่วน /selftest ยังทดสอบได้")
    # ปิด reloader เพื่อไม่ให้ตัวตั้งเวลาเริ่มซ้ำสองครั้ง
    app.run(host="0.0.0.0", port=config.PORT, use_reloader=False)
