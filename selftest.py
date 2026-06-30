# -*- coding: utf-8 -*-
"""
selftest.py
ทดสอบการดึงข้อมูลค่าฝุนจาก Air4Thai และการแปลงเป็นระดับคุณภาพอากาศ
โดยไม่ต้องเชื่อมต่อ LINE (ติดตั้งแค่ requests ก็รันได้)

วิธีรัน:  python selftest.py
"""

import sys

# ให้คอนโซลแสดงภาษาไทยได้ถูกต้อง (โดยเฉพาะบน Windows ที่ใช้ค่าเริ่มต้น cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import aqi
import air4thai
from stations import STATIONS, name_of

UNIT = "มคก./ลบ.ม."


def show(station_id):
    reading = air4thai.get_reading(station_id)
    label = name_of(station_id)
    if reading is None:
        print(f"  [{station_id}] {label}: ดึงข้อมูลไม่ได้")
        return
    pm = reading["pm25"]
    if pm is None:
        print(f"  [{station_id}] {label}: ไม่มีข้อมูล PM2.5 ในขณะนี้")
        return
    lv = aqi.get_level(pm)
    flag = "  *** เกินมาตรฐาน ***" if aqi.is_over_standard(pm) else ""
    print(f"  [{station_id}] {label}: PM2.5 = {pm:g} {UNIT} "
          f"| {lv['emoji']} {lv['color_th']} {lv['meaning']}"
          f" | อัปเดต {reading['date']} {reading['time']}{flag}")


def main():
    print("=" * 60)
    print("ทดสอบการดึงข้อมูลค่าฝุน PM 2.5 จาก Air4Thai")
    print(f"Endpoint: {air4thai.API_URL}")
    print(f"ค่ามาตรฐาน 24 ชม.: {aqi.STANDARD:g} {UNIT}")
    print("=" * 60)

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(STATIONS.keys())
    for sid in targets:
        show(sid)

    print("-" * 60)
    print("เสร็จสิ้น ถ้าเห็นค่าฝุนด้านบน แปลว่าการเชื่อมต่อ Air4Thai ใช้งานได้ปกติ")


if __name__ == "__main__":
    main()
