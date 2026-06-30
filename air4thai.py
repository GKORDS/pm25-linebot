# -*- coding: utf-8 -*-
"""
air4thai.py
ดึงข้อมูลคุณภาพอากาศจากระบบ Air4Thai ของกรมควบคุมมลพิษ

หมายเหตุสำคัญ (ตรวจสอบจาก API จริง):
  * ต้องเรียกที่ URL ลงท้าย ".php" และใช้ http (ไม่ใช่ https เพราะใบรับรองหมดอายุ)
  * ค่าทุกอย่างใน JSON เป็น "สตริง" ต้องแปลงเป็นตัวเลขเอง
  * ถ้าไม่มีข้อมูลจะเป็นค่า "-1"
  * ข้อมูลอัปเดตเป็นรายชั่วโมง จึง cache ไว้ชั่วคราวเพื่อลดการเรียกซ้ำ
"""

import math
import time

import requests

# Endpoint จริงของ Air4Thai (คืนข้อมูลทุกสถานีในครั้งเดียว ~175 สถานี)
API_URL = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"

# เก็บผลลัพธ์ล่าสุดไว้ในหน่วยความจำ เพื่อไม่ให้เรียก API ถี่เกินไป
CACHE_TTL_SECONDS = 600  # 10 นาที
_cache = {"ts": 0.0, "stations": None}


def _to_float(value):
    """แปลงสตริงเป็น float ถ้าเป็น '-1' หรือแปลงไม่ได้ จะคืน None (= ไม่มีข้อมูล)"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def _fetch_all(force=False):
    """ดึงข้อมูลทุกสถานี (ใช้ cache ถ้ายังไม่หมดอายุ) — อาจ raise ถ้าเครือข่ายมีปัญหา"""
    now = time.time()
    if not force and _cache["stations"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["stations"]

    resp = requests.get(API_URL, timeout=15)
    resp.raise_for_status()
    stations = resp.json().get("stations", [])
    _cache["stations"] = stations
    _cache["ts"] = now
    return stations


def _stations_or_cache():
    """พยายามดึงข้อมูลใหม่ ถ้าล้มเหลวให้ใช้ข้อมูลเก่าใน cache (ถ้ามี)"""
    try:
        return _fetch_all()
    except Exception:
        return _cache["stations"]  # อาจเป็น None ถ้ายังไม่เคยดึงสำเร็จเลย


def _parse(station):
    """แปลงข้อมูลดิบของหนึ่งสถานีให้อยู่ในรูปที่ใช้งานง่าย"""
    last = station.get("AQILast", {}) or {}
    pm25 = last.get("PM25", {}) or {}
    aqi = last.get("AQI", {}) or {}
    return {
        "station_id": station.get("stationID", ""),
        "name_th": station.get("nameTH", ""),
        "name_en": station.get("nameEN", ""),
        "area_th": station.get("areaTH", ""),
        "pm25": _to_float(pm25.get("value")),          # ค่าฝุน PM2.5 (มคก./ลบ.ม.) หรือ None
        "pm25_aqi": _to_float(pm25.get("aqi")),         # ดัชนีย่อยของ PM2.5
        "aqi": _to_float(aqi.get("aqi")),               # ดัชนีคุณภาพอากาศรวมของสถานี
        "date": last.get("date", ""),
        "time": last.get("time", ""),
        "lat": _to_float(station.get("lat")),
        "long": _to_float(station.get("long")),
    }


def get_reading(station_id):
    """
    คืนข้อมูลของสถานีตามรหัส ในรูป dict (ดู _parse)
    คืน None ถ้าดึงข้อมูลไม่ได้เลย หรือไม่พบสถานีนั้น
    (ถ้าพบสถานีแต่ค่า PM2.5 เป็น None แปลว่าสถานีนั้นไม่มีข้อมูลในขณะนี้)
    """
    stations = _stations_or_cache()
    if not stations:
        return None
    for s in stations:
        if s.get("stationID") == station_id:
            return _parse(s)
    return None


def _haversine(lat1, lon1, lat2, lon2):
    """คำนวณระยะทางโดยประมาณระหว่างพิกัดสองจุด (กิโลเมตร)"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_station(lat, lng):
    """
    หาสถานีที่ใกล้พิกัดที่ผู้ใช้ส่งมามากที่สุด (เฉพาะสถานีที่มีข้อมูล PM2.5)
    คืน dict เหมือน get_reading พร้อมคีย์ 'distance_km' หรือ None ถ้าหาไม่ได้
    """
    stations = _stations_or_cache()
    if not stations:
        return None

    best, best_d = None, None
    for s in stations:
        slat = _to_float(s.get("lat"))
        slng = _to_float(s.get("long"))
        pm = _to_float(((s.get("AQILast", {}) or {}).get("PM25", {}) or {}).get("value"))
        if slat is None or slng is None or pm is None:
            continue
        d = _haversine(lat, lng, slat, slng)
        if best_d is None or d < best_d:
            best, best_d = s, d

    if best is None:
        return None
    reading = _parse(best)
    reading["distance_km"] = round(best_d, 1)
    return reading
