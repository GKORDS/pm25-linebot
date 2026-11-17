# -*- coding: utf-8 -*-
"""
storage.py
เก็บรายชื่อผู้ใช้ที่ลงทะเบียนรับการแจ้งเตือน พื้นที่ (สถานี) ที่แต่ละคนเลือก
และสถานะเปิด/ปิดการแจ้งเตือน บันทึกลงไฟล์ JSON เพื่อให้ข้อมูลไม่หายเมื่อรีสตาร์ตโปรแกรม
โครงสร้างข้อมูล:
    {
        "users": {
            "<userId>": {"station": "50t", "alert": true, "last_alert": 1718000000.0}
        }
    }
"""

import json
import os
import threading
import time

import config
from aqi import STANDARD

_lock = threading.Lock()
_data = {"users": {}}


def _new_record():
    return {"station": config.DEFAULT_STATION, "alert": True, "last_alert": 0}


def _load():
    """โหลดข้อมูลจากไฟล์ (เรียกครั้งเดียวตอนเริ่มโปรแกรม)"""
    global _data
    if os.path.exists(config.DATA_FILE):
        try:
            with open(config.DATA_FILE, "r", encoding="utf-8") as f:
                _data = json.load(f)
            if "users" not in _data:
                _data = {"users": {}}
        except (json.JSONDecodeError, OSError):
            _data = {"users": {}}


def _save():
    """บันทึกข้อมูลลงไฟล์ (เขียนแบบ atomic เพื่อกันไฟล์เสียถ้าโปรแกรมหยุดกลางคัน)"""
    tmp = config.DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.DATA_FILE)


def register(user_id, station=None):
    """ลงทะเบียนผู้ใช้ (เรียกทุกครั้งที่ผู้ใช้ทักเข้ามา) และอัปเดตสถานีถ้าระบุมา"""
    with _lock:
        u = _data["users"].setdefault(user_id, _new_record())
        if station:
            u["station"] = station
        _save()


def set_station(user_id, station):
    """ตั้งค่าพื้นที่/สถานีที่ผู้ใช้เลือก"""
    with _lock:
        u = _data["users"].setdefault(user_id, _new_record())
        u["station"] = station
        _save()


def get_station(user_id):
    """ดูสถานีที่ผู้ใช้เลือกไว้ (ถ้าไม่มีจะใช้สถานีเริ่มต้น)"""
    with _lock:
        u = _data["users"].get(user_id)
        return u["station"] if u else config.DEFAULT_STATION


def set_alert(user_id, enabled):
    """เปิด/ปิดการแจ้งเตือนอัตโนมัติของผู้ใช้คนนี้"""
    with _lock:
        u = _data["users"].setdefault(user_id, _new_record())
        u["alert"] = bool(enabled)
        _save()


def set_threshold(user_id, threshold):
    with _lock:
        u = _data["users"].setdefault(user_id, _new_record())
        u["threshold"] = threshold
        _save()


def get_threshold(user_id):
    with _lock:
        return _data["users"].get(user_id, {}).get("threshold", STANDARD)


def is_alert_on(user_id):
    with _lock:
        u = _data["users"].get(user_id)
        return bool(u.get("alert", True)) if u else True


def all_users():
    """คืน userId ทั้งหมดที่ลงทะเบียนไว้ (สำเนา เพื่อความปลอดภัยขณะวนลูป)"""
    with _lock:
        return list(_data["users"].keys())


def alert_users():
    """คืนเฉพาะ userId ที่เปิดรับการแจ้งเตือนอัตโนมัติไว้"""
    with _lock:
        return [uid for uid, u in _data["users"].items() if u.get("alert", True)]


def get_user(user_id):
    with _lock:
        u = _data["users"].get(user_id)
        return dict(u) if u else None


def count():
    with _lock:
        return len(_data["users"])


def claim_alert(user_id, cooldown_hours, station_id, threshold):
    """
    ตรวจว่าพ้นช่วงพักการเตือน (cooldown) แล้วหรือยัง — ถ้าพ้นแล้วจะ "จอง" สิทธิ์
    โดยบันทึกเวลาแจ้งเตือนทันทีภายใต้ล็อกเดียวกัน แล้วคืน True
    การตรวจและบันทึกในล็อกเดียวกันนี้กันการแจ้งซ้ำเมื่อมีหลายเธรดเรียกพร้อมกัน
    (เช่น ตัวตั้งเวลาในตัวโปรแกรมทำงานพร้อมกับการเรียก /check จากภายนอก)
    """
    with _lock:
        u = _data["users"].get(user_id)
        if (not u or not u.get("alert", True) or u["station"] != station_id
                or u.get("threshold", STANDARD) != threshold):
            return False
        elapsed = time.time() - u.get("last_alert", 0)
        if elapsed < cooldown_hours * 3600:
            return False
        u["last_alert"] = time.time()
        _save()
        return True


# โหลดข้อมูลทันทีเมื่อ import โมดูลนี้
_load()
