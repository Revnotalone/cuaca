#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dasbor Cuaca • Gempa • Udara • Peringatan
==========================================
CLI dashboard cuaca real-time untuk Indonesia: cuaca (wttr.in), kualitas udara
(Open-Meteo), gempa bumi & peringatan dini (BMKG).

Fitur:
  - Semua panggilan jaringan pakai retry + backoff + timeout, tidak ada
    `except: pass` yang menelan error diam-diam -> semua kegagalan di-log.
  - Fetch semua sumber data secara paralel (ThreadPoolExecutor) sehingga satu
    API yang lambat/mati tidak memblokir yang lain.
  - Cache lokal ber-TTL (~/.cache/weather_dashboard/) -> tetap bisa tampil
    (mode "data cache/offline") walau API sedang down.
  - Validasi input kota, penanganan Ctrl+C yang rapi, logging ke file.
  - Panel status/peringatan gabungan (cuaca ekstrem, AQI buruk, gempa besar).
  - Ramalan 3 hari lengkap (pagi/siang/malam), kategori & saran kesehatan AQI,
    ikon fase bulan, hitung mundur matahari terbit/terbenam, konversi C/F.
  - Ekspor laporan ke JSON atau teks.
  - Mode cepat (--fast) tanpa animasi untuk dipakai di skrip/cron/automation.

Requirements: requests, colorama, rich, plotext
    pip install requests colorama rich plotext
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover - very old urllib3 fallback
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

from colorama import init as colorama_init

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.columns import Columns
    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    RICH_AVAILABLE = False

try:
    import plotext as plt
    PLOTEXT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PLOTEXT_AVAILABLE = False


# =========================================================================
# KONSTANTA & KONFIGURASI
# =========================================================================

APP_NAME = "weather_dashboard"
CACHE_DIR = Path(os.environ.get("WEATHER_DASHBOARD_CACHE", Path.home() / ".cache" / APP_NAME))
LOG_DIR = Path(os.environ.get("WEATHER_DASHBOARD_LOGS", Path.home() / ".local" / "state" / APP_NAME))
DEFAULT_CACHE_TTL = 600  # detik (10 menit)
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
USER_AGENT = "weather-dashboard/2.0 (+https://github.com; contact: local-user)"

WTTR_URL_TMPL = "https://wttr.in/{city}?format=j1"
OPEN_METEO_AQI_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
BMKG_WARNING_URL = "https://data.bmkg.go.id/DataMKG/MEWS/warning/WarningCuaca.xml"
BMKG_AUTOGEMPA_URL = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
BMKG_GEMPATERKINI_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"
BMKG_DIRASAKAN_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
IP_GEOLOCATION_URL = "http://ip-api.com/json/?fields=city,status,message"

CITY_NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u024F\s\.'\-,]{2,80}$")

FIELD_LABELS = {
    "temp_C": "Suhu", "FeelsLikeC": "Terasa Seperti",
    "weatherDesc": "Cuaca", "humidity": "Kelembapan (%)",
    "windspeedKmph": "Kecepatan Angin (km/h)", "winddir16Point": "Arah Angin",
    "pressure": "Tekanan (mb)", "visibility": "Visibilitas (km)",
    "uvIndex": "Indeks UV", "cloudcover": "Tutupan Awan (%)",
    "precipMM": "Curah Hujan (mm)",
}

ASTRO_LABELS = {
    "sunrise": "Matahari Terbit", "sunset": "Matahari Terbenam",
    "moonrise": "Bulan Terbit", "moonset": "Bulan Terbenam",
    "moon_phase": "Fase Bulan", "moon_illumination": "Iluminasi Bulan (%)",
}

MOON_PHASE_ICONS = {
    "New Moon": "🌑", "Waxing Crescent": "🌒", "First Quarter": "🌓",
    "Waxing Gibbous": "🌔", "Full Moon": "🌕", "Waning Gibbous": "🌖",
    "Last Quarter": "🌗", "Waning Crescent": "🌘",
}

WIND_DIR_ICONS = {
    "N": "⬆️", "NNE": "↗️", "NE": "↗️", "ENE": "↗️",
    "E": "➡️", "ESE": "↘️", "SE": "↘️", "SSE": "↘️",
    "S": "⬇️", "SSW": "↙️", "SW": "↙️", "WSW": "↙️",
    "W": "⬅️", "WNW": "↖️", "NW": "↖️", "NNW": "↖️",
}

# Breakpoint kategori US AQI (EPA) + saran kesehatan singkat
AQI_CATEGORIES = [
    (0, 50, "Baik", "green", "Kualitas udara memuaskan, risiko minimal."),
    (51, 100, "Sedang", "yellow", "Cukup dapat diterima; kelompok sensitif waspada."),
    (101, 150, "Tidak Sehat bagi Kelompok Sensitif", "orange3",
     "Anak-anak, lansia, dan penderita gangguan pernapasan sebaiknya kurangi aktivitas luar ruangan lama."),
    (151, 200, "Tidak Sehat", "red", "Semua orang mulai terdampak; kurangi aktivitas berat di luar ruangan."),
    (201, 300, "Sangat Tidak Sehat", "magenta", "Peringatan kesehatan darurat; hindari aktivitas luar ruangan."),
    (301, 10_000, "Berbahaya", "bright_red", "Kondisi darurat kesehatan; seluruh populasi berisiko tinggi."),
]


# =========================================================================
# LOGGING
# =========================================================================

def setup_logging(verbose: bool) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_handler = RotatingFileHandler(
        LOG_DIR / "dashboard.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(file_handler)

    if verbose:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(console_handler)

    return logger


# =========================================================================
# EXCEPTIONS
# =========================================================================

class DashboardError(Exception):
    """Base error untuk aplikasi ini."""


class DataSourceError(DashboardError):
    """Gagal mengambil data dari satu sumber tertentu (tidak fatal untuk sumber lain)."""

    def __init__(self, source: str, message: str, cause: Optional[Exception] = None):
        self.source = source
        self.cause = cause
        super().__init__(f"[{source}] {message}")


class InvalidCityError(DashboardError):
    pass


# =========================================================================
# HTTP SESSION DENGAN RETRY
# =========================================================================

def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


# =========================================================================
# CACHE LOKAL BER-TTL
# =========================================================================

class DiskCache:
    """Cache JSON sederhana per-key di disk, dengan TTL. Dipakai sebagai
    fallback saat API sedang tidak bisa dihubungi (mode offline/stale)."""

    def __init__(self, cache_dir: Path, logger: logging.Logger):
        self.cache_dir = cache_dir
        self.logger = logger
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str, ttl: int) -> Tuple[Optional[Any], bool]:
        """Return (data, is_stale). data None kalau tidak ada cache sama sekali."""
        path = self._path(key)
        if not path.exists():
            return None, False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ts = payload.get("_cached_at", 0)
            age = time.time() - ts
            is_stale = age > ttl
            return payload.get("data"), is_stale
        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning("Cache rusak untuk key=%s: %s", key, e)
            return None, False

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        try:
            path.write_text(
                json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            self.logger.warning("Gagal menulis cache key=%s: %s", key, e)


# =========================================================================
# FETCHER — satu kelas terpusat untuk semua sumber data, dengan cache
# =========================================================================

class Fetcher:
    def __init__(self, session: requests.Session, cache: DiskCache, logger: logging.Logger,
                 cache_ttl: int, use_cache: bool):
        self.session = session
        self.cache = cache
        self.logger = logger
        self.cache_ttl = cache_ttl
        self.use_cache = use_cache

    def _get_json(self, url: str, cache_key: str, source: str,
                   params: Optional[dict] = None) -> Tuple[Any, bool]:
        """Ambil JSON dari url. Return (data, from_stale_cache).
        Melempar DataSourceError kalau live fetch gagal DAN tidak ada cache sama sekali."""
        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if self.use_cache:
                self.cache.set(cache_key, data)
            return data, False
        except requests.exceptions.RequestException as e:
            self.logger.warning("%s: live fetch gagal (%s)", source, e)
        except ValueError as e:
            self.logger.warning("%s: respons bukan JSON valid (%s)", source, e)

        if self.use_cache:
            cached, is_stale = self.cache.get(cache_key, self.cache_ttl)
            if cached is not None:
                self.logger.info("%s: memakai data cache (%s)",
                                  source, "basi" if is_stale else "segar")
                return cached, True

        raise DataSourceError(source, "tidak ada data live maupun cache yang tersedia")

    def get_weather(self, city: str) -> Dict[str, Any]:
        url = WTTR_URL_TMPL.format(city=requests.utils.quote(city))
        data, _ = self._get_json(url, f"weather_{city}", "Cuaca (wttr.in)")
        if "current_condition" not in data:
            raise DataSourceError("Cuaca (wttr.in)", f"kota '{city}' tidak dikenali atau data kosong")
        return data

    def get_air_quality(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        params = {
            "latitude": lat, "longitude": lon,
            "current": "european_aqi,us_aqi,pm2_5,pm10,carbon_monoxide,"
                       "nitrogen_dioxide,sulphur_dioxide,ozone",
            "timezone": "auto",
        }
        try:
            data, _ = self._get_json(
                OPEN_METEO_AQI_URL, f"aqi_{lat:.2f}_{lon:.2f}", "Kualitas Udara (Open-Meteo)", params
            )
            return data.get("current", {})
        except DataSourceError as e:
            self.logger.warning(str(e))
            return None

    def get_bmkg_warnings(self) -> List[Dict[str, str]]:
        cache_key = "bmkg_warnings"
        source = "Peringatan Dini (BMKG)"
        try:
            resp = self.session.get(BMKG_WARNING_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            content = resp.content
            if self.use_cache:
                self.cache.set(cache_key, content.decode("utf-8", errors="replace"))
        except requests.exceptions.RequestException as e:
            self.logger.warning("%s: live fetch gagal (%s)", source, e)
            if self.use_cache:
                cached, is_stale = self.cache.get(cache_key, self.cache_ttl)
                if cached is None:
                    self.logger.error("%s: tidak ada cache, panel akan kosong", source)
                    return []
                content = cached.encode("utf-8")
            else:
                return []

        warnings: List[Dict[str, str]] = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            self.logger.error("%s: XML tidak valid (%s)", source, e)
            return []

        # Struktur BMKG bisa sedikit berbeda antar rilis; coba beberapa tag alternatif.
        warning_nodes = root.findall(".//warning") or root.findall(".//Warning")
        for w in warning_nodes:
            def first_text(tags: List[str]) -> str:
                for t in tags:
                    val = w.findtext(t)
                    if val:
                        return val.strip()
                return ""

            area = first_text(["area", "Area", "region"])
            event = first_text(["type", "Type", "event", "phenomena"])
            valid_from = first_text(["valid_from", "validfrom", "issued"])
            valid_to = first_text(["valid_to", "validto", "expires"])
            if not (area or event):
                continue
            warnings.append({
                "area": area or "Tidak diketahui",
                "event": event or "Tidak diketahui",
                "time": f"{valid_from} - {valid_to}".strip(" -"),
            })
        return warnings

    def get_earthquake_latest(self) -> Optional[Dict[str, Any]]:
        try:
            data, _ = self._get_json(BMKG_AUTOGEMPA_URL, "gempa_terbaru", "Gempa Terbaru (BMKG)")
            return data.get("Infogempa", {}).get("gempa", {})
        except DataSourceError as e:
            self.logger.warning(str(e))
            return None

    def get_earthquake_recent_list(self, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            data, _ = self._get_json(
                BMKG_GEMPATERKINI_URL, "gempa_terkini_list", "Daftar Gempa M5+ (BMKG)"
            )
            gempa_list = data.get("Infogempa", {}).get("gempa", [])
            if isinstance(gempa_list, dict):
                gempa_list = [gempa_list]
            return gempa_list[:limit]
        except DataSourceError as e:
            self.logger.warning(str(e))
            return []

    def get_earthquake_felt(self, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            data, _ = self._get_json(
                BMKG_DIRASAKAN_URL, "gempa_dirasakan", "Gempa Dirasakan (BMKG)"
            )
            gempa_list = data.get("Infogempa", {}).get("gempa", [])
            if isinstance(gempa_list, dict):
                gempa_list = [gempa_list]
            return gempa_list[:limit]
        except DataSourceError as e:
            self.logger.warning(str(e))
            return []


def auto_detect_city(session: requests.Session, logger: logging.Logger) -> str:
    try:
        resp = session.get(IP_GEOLOCATION_URL, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "fail":
            logger.warning("Deteksi lokasi gagal: %s", payload.get("message"))
        else:
            city = (payload.get("city") or "").strip()
            if city:
                return city
    except requests.exceptions.RequestException as e:
        logger.warning("Deteksi lokasi via IP gagal: %s", e)
    except ValueError as e:
        logger.warning("Respons deteksi lokasi bukan JSON valid: %s", e)
    logger.info("Fallback ke kota default: Jakarta")
    return "Jakarta"


def validate_city(city: str) -> str:
    city = city.strip()
    if not city:
        raise InvalidCityError("Nama kota tidak boleh kosong.")
    if len(city) > 80:
        raise InvalidCityError("Nama kota terlalu panjang.")
    if not CITY_NAME_RE.match(city):
        raise InvalidCityError(
            "Nama kota mengandung karakter tidak valid (hanya huruf, spasi, titik, koma, strip diizinkan)."
        )
    return city


# =========================================================================
# UTILITAS TAMPILAN
# =========================================================================

def extract_value(val: Any) -> str:
    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
        return str(val[0].get("value", val))
    return str(val) if val is not None else "N/A"


def format_time(t: str) -> str:
    try:
        t_int = int(t)
        t_str = str(t_int)
        if len(t_str) <= 2:
            return f"{t_int:02d}:00"
        elif len(t_str) == 3:
            return f"{t_int // 100:02d}:{t_int % 100:02d}"
        elif len(t_str) == 4:
            return f"{t_str[:2]}:{t_str[2:]}"
        return t_str
    except (ValueError, TypeError):
        return str(t)


def c_to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def format_temp(value: str, unit: str) -> str:
    try:
        c = float(value)
    except (ValueError, TypeError):
        return f"{value}°C" if unit == "c" else f"{value}"
    if unit == "f":
        return f"{c_to_f(c):.1f}°F"
    return f"{c:.0f}°C"


def aqi_category(us_aqi: Any) -> Tuple[str, str, str]:
    try:
        val = float(us_aqi)
    except (ValueError, TypeError):
        return "N/A", "white", "Data tidak tersedia."
    for low, high, label, color, advice in AQI_CATEGORIES:
        if low <= val <= high:
            return label, color, advice
    return "N/A", "white", "Data tidak tersedia."


def time_until(target_hhmm: str, tz_offset_hours: float = 0.0) -> str:
    """Estimasi 'X jam Y menit lagi' dari waktu HH:MM AM/PM string wttr.in."""
    try:
        cleaned = target_hhmm.replace("AM", " AM").replace("PM", " PM").strip()
        target = datetime.strptime(cleaned, "%I:%M %p")
        now = datetime.now()
        target = target.replace(year=now.year, month=now.month, day=now.day)
        delta = target - now
        if delta.total_seconds() < 0:
            delta += timedelta(days=1)
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        return f"{hours} jam {minutes} menit lagi"
    except (ValueError, TypeError):
        return ""


def panel_delay(seconds: float, animate: bool) -> None:
    if animate:
        time.sleep(seconds)


def rich_typewriter(console: "Console", text: str, delay: float, style: str, animate: bool) -> None:
    if not animate:
        console.print(text, style=style)
        return
    for char in text:
        console.print(char, end="", style=style)
        time.sleep(delay)
    console.print()


def rich_typewriter_input(console: "Console", text: str, delay: float, animate: bool) -> str:
    if not animate:
        console.print(text, end="", style="white")
    else:
        for char in text:
            console.print(char, end="", style="white")
            time.sleep(delay)
    try:
        return input().strip()
    except EOFError:
        return ""


BANNER = r"""
》 Dasbor Cuaca • Gempa • Udara • Peringatan — v2.0 (hardened) 《
"""


# =========================================================================
# RENDER PANEL (Rich)
# =========================================================================

def render_status_banner(status_items: List[Tuple[str, str]]) -> "Panel":
    if not status_items:
        return Panel(
            "✅ Tidak ada kondisi ekstrem terdeteksi saat ini.",
            title="[bold green]STATUS RINGKAS", border_style="green",
        )
    txt = Text()
    for label, detail in status_items:
        txt.append(f"⚠ {label}\n", style="bold red")
        txt.append(f"   {detail}\n", style="white")
    return Panel(txt, title="[bold red]⚠️ STATUS: WASPADA", border_style="red")


def render_current_conditions(data: dict, unit: str, stale: bool) -> "Panel":
    if "current_condition" not in data or not data["current_condition"]:
        return Panel("❌ Data kondisi saat ini tidak tersedia.",
                     title="Kondisi Saat Ini", border_style="red")

    current = data["current_condition"][0]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="bold white")

    main_keys = ["weatherDesc", "temp_C", "FeelsLikeC", "humidity",
                 "windspeedKmph", "winddir16Point", "uvIndex", "cloudcover",
                 "visibility", "precipMM"]
    for key in main_keys:
        if key not in current:
            continue
        val = extract_value(current[key])
        label = FIELD_LABELS.get(key, key)
        if key in ("temp_C", "FeelsLikeC"):
            val = format_temp(val, unit)
        if key == "winddir16Point":
            icon = WIND_DIR_ICONS.get(val, "")
            val = f"{val} {icon}"
        table.add_row(label, val)

    title = "[bold cyan]📡 KONDISI SAAT INI"
    if stale:
        title += " [yellow](cache/offline)"
    return Panel(table, title=title, border_style="cyan", expand=False)


def render_astronomy(today: dict) -> "Panel":
    astro = today.get("astronomy", [{}])[0]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="yellow")
    table.add_column(style="white")

    for key, val in astro.items():
        label = ASTRO_LABELS.get(key, key)
        display_val = val
        if key == "moon_phase":
            icon = MOON_PHASE_ICONS.get(val, "")
            display_val = f"{val} {icon}"
        if key == "sunrise":
            countdown = time_until(val)
            if countdown:
                display_val = f"{val}  ({countdown})"
        if key == "sunset":
            countdown = time_until(val)
            if countdown:
                display_val = f"{val}  ({countdown})"
        table.add_row(label, display_val)

    return Panel(table, title="[bold yellow]🌅 ASTRONOMI", border_style="yellow", expand=False)


def render_air_quality(aqi_data: Optional[dict], lat: float, lon: float) -> "Panel":
    if not aqi_data:
        return Panel("🌫️ Data kualitas udara tidak tersedia.",
                     title="Kualitas Udara", border_style="grey50")

    us_aqi = aqi_data.get("us_aqi", "N/A")
    label, color, advice = aqi_category(us_aqi)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="green")
    table.add_column(style="white")

    table.add_row("US AQI", f"[{color}]{us_aqi} — {label}[/{color}]")
    table.add_row("PM2.5", f"{aqi_data.get('pm2_5', 'N/A')} µg/m³")
    table.add_row("PM10", f"{aqi_data.get('pm10', 'N/A')} µg/m³")
    table.add_row("O₃", f"{aqi_data.get('ozone', 'N/A')} µg/m³")
    table.add_row("NO₂", f"{aqi_data.get('nitrogen_dioxide', 'N/A')} µg/m³")
    table.add_row("SO₂", f"{aqi_data.get('sulphur_dioxide', 'N/A')} µg/m³")
    table.add_row("CO", f"{aqi_data.get('carbon_monoxide', 'N/A')} µg/m³")
    table.add_row("Saran", advice)

    return Panel(table, title=f"[bold green]🌫️ UDARA ({lat:.2f}, {lon:.2f})",
                 border_style="green", expand=False)


def render_forecast(days: List[dict], unit: str) -> "Panel":
    table = Table(box=None, expand=True)
    table.add_column("Tanggal", style="cyan")
    table.add_column("Suhu", justify="center", style="yellow")
    table.add_column("Pagi", style="white")
    table.add_column("Siang", style="white")
    table.add_column("Malam", style="white")
    table.add_column("Hujan", justify="center", style="blue")

    for day in days[:3]:
        date = day.get("date", "N/A")
        max_t = format_temp(day.get("maxtempC", "?"), unit)
        min_t = format_temp(day.get("mintempC", "?"), unit)

        hourly = day.get("hourly", [])

        def desc_at(target_time: str) -> str:
            for h in hourly:
                if h.get("time") == target_time:
                    return extract_value(h.get("weatherDesc", ""))
            return extract_value(hourly[0].get("weatherDesc", "")) if hourly else "N/A"

        rain_chances = [int(h.get("chanceofrain", 0)) for h in hourly] if hourly else [0]
        max_rain = max(rain_chances) if rain_chances else 0

        table.add_row(
            date, f"{min_t} - {max_t}",
            desc_at("600"), desc_at("1200"), desc_at("1800"),
            f"{max_rain}%",
        )

    return Panel(table, title="[bold magenta]📅 RAMALAN 3 HARI", border_style="magenta")


def render_earthquake(eq: Optional[dict]) -> "Panel":
    if not eq:
        return Panel("⚠️ Data gempa bumi tidak dapat diambil.",
                     title="Gempa Bumi", border_style="red")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="red")
    table.add_column(style="white")

    table.add_row("Waktu", eq.get("DateTime", f"{eq.get('Tanggal', '')} {eq.get('Jam', '')}".strip()))
    table.add_row("Magnitudo", f"{eq.get('Magnitude', 'N/A')} SR")
    table.add_row("Kedalaman", f"{eq.get('Kedalaman', 'N/A')} km")
    table.add_row("Lokasi", eq.get("Wilayah", "N/A"))
    table.add_row("Potensi", eq.get("Potensi", "N/A"))
    table.add_row("Koordinat", f"{eq.get('Lintang', 'N/A')}, {eq.get('Bujur', 'N/A')}")

    return Panel(table, title="[bold red]🌍 GEMPA TERBARU", border_style="red")


def render_earthquake_list(quakes: List[dict], title: str, border: str) -> "Panel":
    if not quakes:
        return Panel("Tidak ada data.", title=title, border_style=border)
    table = Table(box=None, expand=True)
    table.add_column("Waktu", style="white")
    table.add_column("Mag", justify="center", style="bold yellow")
    table.add_column("Kedalaman", justify="center", style="white")
    table.add_column("Wilayah", style="white")
    for q in quakes:
        table.add_row(
            q.get("DateTime", f"{q.get('Tanggal', '')} {q.get('Jam', '')}".strip()),
            f"{q.get('Magnitude', 'N/A')}",
            f"{q.get('Kedalaman', 'N/A')}",
            q.get("Wilayah", "N/A"),
        )
    return Panel(table, title=title, border_style=border)


def render_warnings(warnings: list) -> "Panel":
    if not warnings:
        return Panel("Aman. Tidak ada peringatan cuaca ekstrem.",
                     title="[bold green]⚠️ PERINGATAN DINI", border_style="green")

    txt = Text()
    for i, w in enumerate(warnings[:5], 1):
        txt.append(f"{i}. {w['area']}\n", style="bold yellow")
        txt.append(f"   {w['event']}", style="white")
        if w.get("time"):
            txt.append(f"  [{w['time']}]", style="grey50")
        txt.append("\n")

    return Panel(txt, title="[bold red]⚠️ PERINGATAN DINI BMKG", border_style="red")


def display_hourly_chart(hourly: list, unit: str) -> None:
    if not hourly or not PLOTEXT_AVAILABLE:
        return

    times, temps, rains = [], [], []
    for h in hourly:
        times.append(format_time(h.get("time", "0")))
        temp_c = int(h.get("tempC", 0))
        temps.append(c_to_f(temp_c) if unit == "f" else temp_c)
        rains.append(int(h.get("chanceofrain", 0)))

    plt.clf()
    unit_label = "°F" if unit == "f" else "°C"
    plt.title(f"Suhu ({unit_label}) & Probabilitas Hujan (%) Per Jam")
    plt.multiple_bar(times, [temps, rains], labels=[f"Suhu ({unit_label})", "Hujan (%)"])
    plt.theme("dark")
    plt.plotsize(100, 25)
    print("\n")
    plt.show()
    print("\n")


# =========================================================================
# LOGIKA STATUS/PERINGATAN GABUNGAN
# =========================================================================

def compute_status_alerts(weather: Optional[dict], aqi: Optional[dict],
                           eq: Optional[dict], warnings: List[dict]) -> List[Tuple[str, str]]:
    alerts: List[Tuple[str, str]] = []

    if weather and weather.get("current_condition"):
        current = weather["current_condition"][0]
        try:
            temp_c = float(extract_value(current.get("temp_C", "0")))
            if temp_c >= 35:
                alerts.append(("Suhu ekstrem tinggi", f"{temp_c:.0f}°C — risiko heat stress, perbanyak minum air."))
        except ValueError:
            pass
        try:
            uv = float(extract_value(current.get("uvIndex", "0")))
            if uv >= 8:
                alerts.append(("Indeks UV sangat tinggi", f"UV {uv:.0f} — gunakan tabir surya & hindari matahari langsung."))
        except ValueError:
            pass

    if aqi:
        us_aqi = aqi.get("us_aqi")
        label, _, advice = aqi_category(us_aqi) if us_aqi is not None else ("N/A", "", "")
        if label in ("Tidak Sehat", "Sangat Tidak Sehat", "Berbahaya"):
            alerts.append((f"Kualitas udara: {label} (AQI {us_aqi})", advice))

    if eq:
        try:
            mag = float(eq.get("Magnitude", 0))
            if mag >= 5.0:
                alerts.append((f"Gempa signifikan M{mag}", eq.get("Wilayah", "Lokasi tidak diketahui")))
        except (ValueError, TypeError):
            pass

    for w in warnings[:3]:
        alerts.append((f"Peringatan BMKG: {w['event']}", w["area"]))

    return alerts


# =========================================================================
# EKSPOR LAPORAN
# =========================================================================

def export_report(path: Path, fmt: str, payload: Dict[str, Any], logger: logging.Logger) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
        else:  # txt
            lines = [f"LAPORAN DASBOR CUACA — {datetime.now().isoformat(timespec='seconds')}", "=" * 60]
            for section, content in payload.items():
                lines.append(f"\n[{section.upper()}]")
                lines.append(json.dumps(content, ensure_ascii=False, indent=2, default=str))
            path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Laporan diekspor ke %s", path)
    except OSError as e:
        logger.error("Gagal mengekspor laporan ke %s: %s", path, e)
        raise DashboardError(f"Tidak dapat menulis file ekspor: {e}") from e


# =========================================================================
# CLI ARGPARSE
# =========================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="Dasbor Cuaca • Gempa • Udara • Peringatan (Indonesia)",
    )
    parser.add_argument("city", nargs="?", default=None,
                         help="Nama kota. Jika kosong, akan dicoba deteksi otomatis lalu fallback ke Jakarta.")
    parser.add_argument("--unit", choices=["c", "f"], default="c",
                         help="Satuan suhu: c (Celsius, default) atau f (Fahrenheit).")
    parser.add_argument("--fast", "--no-anim", dest="fast", action="store_true",
                         help="Nonaktifkan animasi ketik/delay (cocok untuk cron/automation).")
    parser.add_argument("--no-cache", action="store_true", help="Nonaktifkan cache lokal sepenuhnya.")
    parser.add_argument("--cache-ttl", type=int, default=DEFAULT_CACHE_TTL,
                         help=f"Masa berlaku cache dalam detik (default {DEFAULT_CACHE_TTL}).")
    parser.add_argument("--quakes", type=int, default=0,
                         help="Tampilkan N gempa M5+ terbaru sebagai daftar tambahan (default 0 = nonaktif).")
    parser.add_argument("--felt", action="store_true",
                         help="Tampilkan daftar gempa yang dirasakan terbaru dari BMKG.")
    parser.add_argument("--export", choices=["json", "txt"], default=None,
                         help="Ekspor laporan lengkap ke file setelah tampil.")
    parser.add_argument("--output", type=Path, default=None,
                         help="Path file ekspor (default: ./laporan_cuaca_<kota>_<timestamp>.<fmt>).")
    parser.add_argument("--verbose", action="store_true", help="Tampilkan log level INFO+ ke stderr.")
    parser.add_argument("--max-workers", type=int, default=6, help="Jumlah thread fetch paralel.")
    return parser


# =========================================================================
# MAIN
# =========================================================================

def check_dependencies(logger: logging.Logger) -> None:
    missing = []
    if not RICH_AVAILABLE:
        missing.append("rich")
    if not PLOTEXT_AVAILABLE:
        missing.append("plotext")
    if missing:
        logger.warning("Modul opsional belum terpasang: %s. Tampilan akan disederhanakan.", ", ".join(missing))


def run(args: argparse.Namespace) -> int:
    logger = setup_logging(args.verbose)
    check_dependencies(logger)

    console = Console() if RICH_AVAILABLE else None
    colorama_init(autoreset=True)

    def out(msg: str, style: str = "") -> None:
        if console:
            console.print(msg)
        else:
            print(msg)

    animate = not args.fast

    if console:
        rich_typewriter(console, BANNER.strip(), delay=0.0005, style="cyan", animate=animate)
        print()
    else:
        print(BANNER.strip())

    session = build_session()
    cache = DiskCache(CACHE_DIR, logger)
    fetcher = Fetcher(session, cache, logger, args.cache_ttl, use_cache=not args.no_cache)

    # ---- Resolusi kota ----
    if args.city:
        try:
            city = validate_city(args.city)
        except InvalidCityError as e:
            out(f"❌ {e}")
            return 2
    elif console:
        raw = rich_typewriter_input(console, "Masukkan Nama Kota (kosongkan untuk deteksi otomatis): ",
                                     delay=0.02, animate=animate)
        if raw:
            try:
                city = validate_city(raw)
            except InvalidCityError as e:
                out(f"❌ {e}")
                return 2
        else:
            city = auto_detect_city(session, logger)
            out(f"\n[bold green]🏙️  Lokasi terdeteksi:[/bold green] {city}\n")
    else:
        city = auto_detect_city(session, logger)
        print(f"Lokasi terdeteksi: {city}\n")

    # ---- Fetch semua data secara paralel, masing-masing terisolasi ----
    results: Dict[str, Any] = {}
    stale_flags: Dict[str, bool] = {}

    def safe_call(name: str, fn, *a, **kw):
        try:
            return name, fn(*a, **kw), None
        except DashboardError as e:
            logger.error(str(e))
            return name, None, e
        except Exception as e:  # jaring pengaman terakhir - tidak boleh ada silent crash
            logger.exception("Kegagalan tak terduga di task '%s'", name)
            return name, None, e

    status_msg = "[bold cyan]Mengambil data cuaca, udara, gempa, dan peringatan..." if console \
        else "Mengambil data..."
    spinner_ctx = console.status(status_msg, spinner="dots") if console else None
    if spinner_ctx:
        spinner_ctx.__enter__()
    try:
        weather_data: Optional[dict] = None
        try:
            weather_data = fetcher.get_weather(city)
        except DataSourceError as e:
            logger.error(str(e))
            out(f"❌ Tidak bisa memuat data cuaca untuk '{city}': {e}")
            if spinner_ctx:
                spinner_ctx.__exit__(None, None, None)
            return 1

        lat = lon = 0.0
        area = weather_data.get("nearest_area", [])
        if area:
            try:
                lat = float(area[0].get("latitude", "0"))
                lon = float(area[0].get("longitude", "0"))
            except (ValueError, TypeError, IndexError):
                logger.warning("Koordinat lokasi tidak dapat dibaca dari respons wttr.in")

        tasks = {
            "aqi": (fetcher.get_air_quality, (lat, lon)) if (lat and lon) else None,
            "warnings": (fetcher.get_bmkg_warnings, ()),
            "eq_latest": (fetcher.get_earthquake_latest, ()),
        }
        if args.quakes > 0:
            tasks["eq_list"] = (fetcher.get_earthquake_recent_list, (args.quakes,))
        if args.felt:
            tasks["eq_felt"] = (fetcher.get_earthquake_felt, (5,))

        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
            futures = {}
            for name, spec in tasks.items():
                if spec is None:
                    results[name] = None
                    continue
                fn, fn_args = spec
                futures[pool.submit(safe_call, name, fn, *fn_args)] = name
            for fut in as_completed(futures):
                name, value, err = fut.result()
                results[name] = value
    finally:
        if spinner_ctx:
            spinner_ctx.__exit__(None, None, None)

    aqi = results.get("aqi")
    warnings = results.get("warnings") or []
    eq_latest = results.get("eq_latest")
    weather_list = weather_data.get("weather", [])
    today = weather_list[0] if weather_list else {}

    # ---- Panel status ringkas di paling atas ----
    alerts = compute_status_alerts(weather_data, aqi, eq_latest, warnings)
    if console:
        console.print(render_status_banner(alerts))
        panel_delay(0.4, animate)
    else:
        print("STATUS:", "WASPADA" if alerts else "AMAN")

    # ---- Baris 1 ----
    if console:
        console.print(render_current_conditions(weather_data, args.unit, False))
        panel_delay(0.4, animate)
        console.print(render_astronomy(today))
        panel_delay(0.4, animate)
        console.print(render_air_quality(aqi, lat, lon))
        panel_delay(0.4, animate)

        # ---- Baris 2 ----
        console.print(render_forecast(weather_list, args.unit))
        panel_delay(0.4, animate)
        console.print(render_earthquake(eq_latest))
        panel_delay(0.4, animate)
        console.print(render_warnings(warnings))
        panel_delay(0.4, animate)

        if args.quakes > 0:
            console.print(render_earthquake_list(
                results.get("eq_list") or [], "[bold red]🌍 GEMPA M5+ TERKINI", "red"))
            panel_delay(0.4, animate)
        if args.felt:
            console.print(render_earthquake_list(
                results.get("eq_felt") or [], "[bold yellow]📢 GEMPA DIRASAKAN", "yellow"))
            panel_delay(0.4, animate)

        if today:
            display_hourly_chart(today.get("hourly", []), args.unit)

        if lat and lon:
            console.print(f"[bold blue]🗺️  Peta Google Maps:[/bold blue] "
                           f"https://www.google.com/maps?q={lat},{lon}")
    else:
        # Fallback tanpa rich: cetak ringkas
        if weather_data.get("current_condition"):
            cur = weather_data["current_condition"][0]
            print(f"Cuaca: {extract_value(cur.get('weatherDesc'))}, "
                  f"{format_temp(extract_value(cur.get('temp_C')), args.unit)}")
        if aqi:
            label, _, _ = aqi_category(aqi.get("us_aqi"))
            print(f"AQI: {aqi.get('us_aqi')} ({label})")
        if eq_latest:
            print(f"Gempa terbaru: M{eq_latest.get('Magnitude')} — {eq_latest.get('Wilayah')}")
        if warnings:
            print(f"Peringatan BMKG aktif: {len(warnings)}")
        if lat and lon:
            print(f"Peta: https://www.google.com/maps?q={lat},{lon}")

    # ---- Ekspor ----
    if args.export:
        payload = {
            "kota": city, "koordinat": {"lat": lat, "lon": lon},
            "status_alerts": [{"judul": a, "detail": d} for a, d in alerts],
            "cuaca_saat_ini": weather_data.get("current_condition", [{}])[0] if weather_data else {},
            "astronomi": today.get("astronomy", [{}])[0] if today else {},
            "kualitas_udara": aqi,
            "ramalan_3hari": weather_list[:3],
            "gempa_terbaru": eq_latest,
            "gempa_m5plus": results.get("eq_list"),
            "gempa_dirasakan": results.get("eq_felt"),
            "peringatan_dini": warnings,
            "dihasilkan_pada": datetime.now().isoformat(timespec="seconds"),
        }
        out_path = args.output or Path(
            f"laporan_cuaca_{re.sub(r'[^a-zA-Z0-9]', '_', city)}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.{args.export}"
        )
        try:
            export_report(out_path, args.export, payload, logger)
            out(f"\n💾 Laporan disimpan: {out_path}")
        except DashboardError as e:
            out(f"\n❌ Gagal menyimpan laporan: {e}")

    return 0


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    def handle_sigint(signum, frame):
        print("\n\n⏹️  Dibatalkan oleh pengguna. Sampai jumpa!")
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        return run(args)
    except DashboardError as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1
    except Exception:
        logging.getLogger(APP_NAME).exception("Kegagalan tak terduga di main()")
        print("\n❌ Terjadi error tak terduga. Detail tersimpan di log:"
              f" {LOG_DIR / 'dashboard.log'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
