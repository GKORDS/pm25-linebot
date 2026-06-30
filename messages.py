# -*- coding: utf-8 -*-
"""
messages.py
สร้างข้อความที่จะส่งกลับให้ผู้ใช้ผ่าน LINE
- รายงานค่าฝุนแบบการ์ดสวยงาม (Flex Message) พร้อมแถบสีตามระดับคุณภาพอากาศ
- ข้อความแจ้งเตือนอัตโนมัติเมื่อค่าฝุนเกินมาตรฐาน
- เมนูปุ่มกดเร็ว (Quick Reply)
"""

from linebot.v3.messaging import (
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    LocationAction,
)

import aqi
from stations import STATIONS, name_of

UNIT = "มคก./ลบ.ม."
SOURCE = "ข้อมูลจาก Air4Thai กรมควบคุมมลพิษ"


# ---------- ปุ่มกดเร็ว (Quick Reply) ----------
def _trim(text, n=20):
    """ป้ายปุ่ม Quick Reply ยาวได้ไม่เกิน 20 ตัวอักษร"""
    return text if len(text) <= n else text[: n - 1] + "…"


def main_quick_reply(alert_on=True):
    """เมนูหลัก แสดงใต้ข้อความตอบกลับ"""
    toggle = QuickReplyItem(
        action=MessageAction(
            label="ปิดแจ้งเตือน" if alert_on else "เปิดแจ้งเตือน",
            text="ปิดแจ้งเตือน" if alert_on else "เปิดแจ้งเตือน",
        )
    )
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="เช็คฝุน", text="เช็คฝุน")),
            QuickReplyItem(action=MessageAction(label="เปลี่ยนพื้นที่", text="เปลี่ยนพื้นที่")),
            QuickReplyItem(action=LocationAction(label="ส่งตำแหน่งของฉัน")),
            toggle,
            QuickReplyItem(action=MessageAction(label="วิธีใช้", text="วิธีใช้")),
        ]
    )


def station_quick_reply():
    """ปุ่มเลือกสถานีตรวจวัด + ปุ่มส่งตำแหน่ง"""
    items = [
        QuickReplyItem(action=MessageAction(label=_trim(name), text=code))
        for code, name in STATIONS.items()
    ]
    items.append(QuickReplyItem(action=LocationAction(label="ส่งตำแหน่งของฉัน")))
    return QuickReply(items=items)


# ---------- การ์ดรายงานค่าฝุน (Flex Message) ----------
def _bubble(reading, level, alert=False):
    pm = reading["pm25"]
    when = f'{reading.get("date", "")} {reading.get("time", "")} น.'.strip()
    aqi_txt = str(int(reading["aqi"])) if reading.get("aqi") is not None else "-"
    header_text = "⚠️ แจ้งเตือน: ค่าฝุนเกินมาตรฐาน" if alert else "ค่าฝุน PM 2.5 ขณะนี้"

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": level["color_hex"],
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": header_text, "color": "#FFFFFF",
                 "weight": "bold", "size": "md", "wrap": True},
                {"type": "text", "text": reading["name_th"] or reading["station_id"],
                 "color": "#FFFFFFEE", "size": "sm", "wrap": True, "margin": "sm"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "16px",
            "contents": [
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": f"{pm:g}", "size": "5xl", "weight": "bold",
                     "color": level["color_hex"], "flex": 0},
                    {"type": "text", "text": UNIT, "size": "sm", "color": "#999999",
                     "margin": "md", "gravity": "bottom", "flex": 0},
                ]},
                {"type": "text",
                 "text": f'{level["emoji"]} {level["color_th"]} · {level["meaning"]}',
                 "weight": "bold", "size": "md", "wrap": True, "color": level["color_hex"]},
                {"type": "box", "layout": "vertical", "backgroundColor": "#F4F4F6",
                 "cornerRadius": "8px", "paddingAll": "12px", "spacing": "sm", "contents": [
                    {"type": "text", "text": "คำแนะนำการปฏิบัติตน", "size": "xs", "color": "#888888"},
                    {"type": "text", "text": level["advice"], "size": "sm", "wrap": True, "color": "#333333"},
                 ]},
                {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                    {"type": "text", "text": f"AQI {aqi_txt}", "size": "xs", "color": "#888888", "flex": 0},
                    {"type": "text", "text": reading.get("area_th", ""), "size": "xs",
                     "color": "#888888", "align": "end", "wrap": True},
                ]},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"อัปเดต {when} · {SOURCE}",
                 "size": "xxs", "color": "#AAAAAA", "wrap": True},
            ],
        },
    }


def report_message(reading, alert=False, quick_reply=None):
    """
    สร้างข้อความรายงานค่าฝุน
      - ถ้า reading เป็น None  -> ข้อความว่าดึงข้อมูลไม่ได้
      - ถ้าไม่มีค่า PM2.5       -> ข้อความว่าสถานีไม่มีข้อมูล
      - ปกติ                    -> การ์ด Flex สวยงาม
    """
    if reading is None:
        return TextMessage(
            text="ขออภัย ขณะนี้ไม่สามารถดึงข้อมูลค่าฝุนได้ กรุณาลองใหม่อีกครั้งภายหลัง",
            quick_reply=quick_reply,
        )
    if reading.get("pm25") is None:
        return TextMessage(
            text=f'สถานี {reading.get("name_th") or reading.get("station_id")} '
                 f"ยังไม่มีข้อมูล PM 2.5 ในขณะนี้ ลองเลือกพื้นที่อื่นดูนะครับ",
            quick_reply=quick_reply,
        )

    level = aqi.get_level(reading["pm25"])
    alt = (f'PM2.5 {reading["pm25"]:g} {UNIT} · {level["color_th"]} {level["meaning"]} '
           f'ที่ {reading.get("name_th") or reading.get("station_id")}')
    return FlexMessage(
        alt_text=alt[:399],
        contents=FlexContainer.from_dict(_bubble(reading, level, alert=alert)),
        quick_reply=quick_reply,
    )


def report_text(reading):
    """รายงานแบบข้อความล้วน (ใช้กรณีต้องการข้อความสั้น ๆ หรือทดสอบ)"""
    if reading is None:
        return "ขออภัย ขณะนี้ไม่สามารถดึงข้อมูลค่าฝุนได้"
    if reading.get("pm25") is None:
        return f'สถานี {reading.get("name_th") or reading.get("station_id")} ยังไม่มีข้อมูล PM 2.5 ในขณะนี้'
    level = aqi.get_level(reading["pm25"])
    when = f'{reading.get("date", "")} {reading.get("time", "")}'.strip()
    return (
        f'📍 {reading.get("name_th") or reading.get("station_id")}\n'
        f'ค่าฝุน PM 2.5: {reading["pm25"]:g} {UNIT}\n'
        f'ระดับ: {level["emoji"]} {level["color_th"]} · {level["meaning"]}\n'
        f'คำแนะนำ: {level["advice"]}\n'
        f'(อัปเดต {when} · {SOURCE})'
    )


# ---------- ข้อความช่วยเหลือ / ต้อนรับ ----------
HELP_TEXT = (
    "🌫️ บอทแจ้งเตือนค่าฝุน PM 2.5\n"
    "พิมพ์หรือกดเมนูด้านล่างได้เลย:\n"
    "• เช็คฝุน — ดูค่าฝุนพื้นที่ของคุณตอนนี้\n"
    "• เปลี่ยนพื้นที่ — เลือกสถานีตรวจวัด หรือส่งตำแหน่ง 📍\n"
    "• เปิดแจ้งเตือน / ปิดแจ้งเตือน — ตั้งค่าการแจ้งเตือนอัตโนมัติ\n\n"
    f"เมื่อค่าฝุนเกินมาตรฐาน {aqi.STANDARD:g} {UNIT} บอทจะส่งข้อความแจ้งเตือนให้อัตโนมัติ\n"
    f"{SOURCE}"
)

WELCOME_TEXT = (
    "สวัสดีครับ 🙏 ยินดีต้อนรับสู่บอทแจ้งเตือนค่าฝุน PM 2.5\n"
    "คุณได้ลงทะเบียนรับการแจ้งเตือนอัตโนมัติเรียบร้อยแล้ว\n"
    'ลองพิมพ์ "เช็คฝุน" เพื่อดูค่าฝุนตอนนี้ได้เลย'
)


def text_message(text, quick_reply=None):
    return TextMessage(text=text, quick_reply=quick_reply)
