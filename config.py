# -*- coding: utf-8 -*-
"""
config.py
อ่านค่าตั้งค่าต่าง ๆ จาก Environment Variables (หรือไฟล์ .env)
เพื่อไม่ให้ต้องเขียน Token/Secret ปนไว้ในโค้ดโดยตรง (ปลอดภัยกว่าและไม่หลุดขึ้น GitHub)
"""

import os

# โหลดค่าจากไฟล์ .env ถ้ามี (เฉพาะตอนรันในเครื่อง) — บนเซิร์ฟเวอร์จริงให้ตั้งใน Dashboard
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # ถ้าไม่ได้ติดตั้ง python-dotenv ก็ข้ามไป (ใช้ค่าจากระบบโดยตรง)
    pass


# ---- ข้อมูลเชื่อมต่อ LINE Messaging API (จำเป็น) ----
# นำมาจากหน้า LINE Developers > ช่อง Messaging API ของคุณ
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

# ---- สถานีตรวจวัดเริ่มต้น (ใช้เมื่อผู้ใช้ยังไม่ได้เลือกพื้นที่) ----
# รหัสสถานีจากระบบ Air4Thai เช่น "50t" = รพ.จุฬาฯ (ดูรายชื่อทั้งหมดได้ในไฟล์ stations.py)
DEFAULT_STATION = os.environ.get("DEFAULT_STATION", "50t")

# ---- การแจ้งเตือนอัตโนมัติ (Push message) ----
# เปิด/ปิดตัวจับเวลาตรวจค่าฝุนในตัวโปรแกรม
ALERT_ENABLED = os.environ.get("ALERT_ENABLED", "true").lower() == "true"
# ตรวจทุกกี่นาที (ตามรายงานใช้ทุก 1 ชั่วโมง = 60 นาที)
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
# กันสแปม: หลังแจ้งเตือนแล้วจะเงียบกี่ชั่วโมงก่อนเตือนซ้ำ
ALERT_COOLDOWN_HOURS = float(os.environ.get("ALERT_COOLDOWN_HOURS", "3"))

# โทเค็นลับสำหรับเรียก /check จากภายนอก (เช่น cron-job.org) แทนการตั้งเวลาในตัวโปรแกรม
# ถ้าเว้นว่างไว้ จะอนุญาตให้เรียก /check ได้โดยไม่ต้องมีโทเค็น (เหมาะกับตอนทดสอบ)
CHECK_TOKEN = os.environ.get("CHECK_TOKEN", "")

# ---- ที่เก็บข้อมูลผู้ใช้ที่ลงทะเบียนรับแจ้งเตือน ----
DATA_FILE = os.environ.get("DATA_FILE", "users.json")

# ---- พอร์ตของเว็บเซิร์ฟเวอร์ ----
# บน Render/โฮสต์ทั่วไปจะกำหนด PORT มาให้ผ่าน environment variable อัตโนมัติ
PORT = int(os.environ.get("PORT", "5000"))


def is_configured():
    """ตรวจว่าตั้งค่า Token/Secret ครบหรือยัง"""
    return bool(CHANNEL_ACCESS_TOKEN) and bool(CHANNEL_SECRET)
