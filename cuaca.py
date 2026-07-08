import requests
import sys
import time
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from colorama import Fore, Style, init

# Import Rich untuk UI Dashboard statis
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich.markup import render
# Import Plotext untuk grafik per jam
import plotext as plt

# Inisialisasi Console Rich
console = Console()
init(autoreset=True)

# ---------------------------- EFEK KETIK ----------------------------
def panel_delay(seconds=0.5):
    time.sleep(seconds)
def rich_typewriter_input(text: str, delay: float = 0.03):
    for char in text:
        console.print(char, end="", style="white")
        time.sleep(delay)
    return input().strip()


def rich_typewriter(text: str, delay: float = 0.001, style="cyan"):
    for char in text:
        console.print(char, end="", style=style)
        time.sleep(delay)
    console.print()

def print_banner():
    banner = r"""
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡜⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣤⠤⢀⠀⠀⠀⠀⠀⠀⠐⠒⠒⠒⠶⠮⣅⣿⠛⠶⠖⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠋⢀⢰⢈⣹⠓⣾⢷⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣨⠀⢠⠐⣪⣭⣅⢤⣿⠞⠳⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣟⣶⢃⡃⠟⠓⡁⣫⡄⡀⠐⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⡰⢫⣟⠿⠧⣿⣿⣥⠴⣴⣮⣏⡣⣄⣲⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⣰⣽⡵⢡⠤⠀⠈⢿⣷⠆⢚⡋⡁⢤⣿⡿⠁⠀⠀⠀⠀⢀⡤⠊⠉⠉⠙⣦⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⣠⣤⠖⠶⡟⡧⢿⠀⠀⠀⠀⠀⠛⠶⣾⣷⡶⠟⠛⠉⢣⠀⣀⣀⣀⡜⠁⠀⠀⣠⠏⠁⠀⠀⢹⡠⠤⣄⣄⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⡜⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⠞⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⣇⡀⢅⠀⠀⠀⠀
    ⠀ ⠀⠁⠩⠵⠴⠲⠔⠶⠶⠶⠦⠴⠶⠶⠶⠖⠦⠤⢴⠏⠀⡴⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⡏⡧⡀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⡀⠀⠀⣀⣀⣀⢀⣀⠀⠀⠀⠀⠀⠀⣀⣀⠤⠞⠁⠀⡜⢸⡏⠀⢸⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠽⠕⠋⠘⠓⠒⠲⠤⠤⠤⡖⣛⠴⠶⡲⠮⠭⢶⣭⠦⠤⠎⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⢠⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡀⡀
     ⠀⠀⠀⢀⣀⣔⡽⣧⢄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡤⠴⠢⠤⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠎⠁⠀⠀⠉⢆
     ⠀⠀⠉⠉⠉⠻⡏⡗⠉⠉⠉⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡔⣝⢏⠁⠀⠀⠀⢀⣉⣀⣀⡀⡄⠀⠀⢠⠴⠗⠗⠒⠒⠺⠋⠛⠉⠀
     ⠀⠀⠀⠀⠀⠀⠈⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠤⢉⡩⠟⣓⡿⠁⠀⠀⡖⠁⠀⠀⠀⠀⠀⠉⠳⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⡠⣒⢯⢕⣫⡯⠗⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡗⡆⠀⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⡜⢛⣿⡇⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⡄⠀⠀⠀⠀⠀⠀⠀
     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠁⠉⠛⠛⠉⠉⠉⠉⠁⠉⠁⠁⠁⠉⠉⠉⠒⠉⠁⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀

》 Dasbor Cuaca • Gempa • Udara • Peringatan by S͢i͟g͜it A̷̢̢͕͜m̸̴ru 《
    """
    rich_typewriter(
        banner.strip(),
        delay=0.001,
        style="cyan"
    )

    print()
# ---------------------------- UTILS ----------------------------
def extract_value(val):
    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
        return val[0].get("value", str(val))
    return str(val) if val is not None else "N/A"

def format_time(t: str) -> str:
    try:
        t = str(int(t))
        if len(t) <= 2:
            return f"{int(t):02d}:00"
        elif len(t) == 3:
            return f"{int(t)//100:02d}:{int(t)%100:02d}"
        elif len(t) == 4:
            return f"{t[:2]}:{t[2:]}"
        else:
            return t
    except:
        return t

def auto_detect_city() -> str:
    try:
        resp = requests.get("http://ip-api.com/json/?fields=city", timeout=5)
        resp.raise_for_status()
        city = resp.json().get("city", "").strip()
        if city:
            return city
    except:
        pass
    return "Jakarta"

# ---------------------------- FETCH DATA ----------------------------
def get_full_weather(city: str) -> Dict[str, Any]:
    url = f"https://wttr.in/{city}?format=j1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        sys.exit(f"❌ Gagal terhubung ke server cuaca: {e}")
    except ValueError:
        sys.exit("❌ Respons bukan JSON.")

def get_air_quality(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "european_aqi,us_aqi,pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
        "timezone": "auto"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("current", {})
    except:
        return None

def get_bmkg_warnings() -> List[Dict[str, str]]:
    url = "https://data.bmkg.go.id/DataMKG/MEWS/warning/WarningCuaca.xml"
    warnings = []
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for warning in root.findall("warning"):
            area = warning.findtext("area", "")
            event = warning.findtext("type", "")
            time_info = warning.findtext("valid_from", "") + " - " + warning.findtext("valid_to", "")
            warnings.append({"area": area, "event": event, "time": time_info})
    except:
        pass
    return warnings

def get_earthquake_data() -> Optional[Dict[str, Any]]:
    url = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("Infogempa", {}).get("gempa", {})
    except:
        return None

# ---------------------------- RENDER RENDERABLES (RICH) ----------------------------
FIELD_LABELS = {
    "temp_C": "Suhu (°C)", "FeelsLikeC": "Terasa (°C)",
    "weatherDesc": "Cuaca", "humidity": "Kelembapan (%)",
    "windspeedKmph": "Kecepatan Angin (km/h)", "winddir16Point": "Arah Angin",
    "pressure": "Tekanan (mb)", "visibility": "Visibilitas (km)",
    "uvIndex": "Indeks UV", "cloudcover": "Tutupan Awan (%)"
}

ASTRO_LABELS = {
    "sunrise": "Matahari Terbit", "sunset": "Matahari Terbenam",
    "moonrise": "Bulan Terbit", "moonset": "Bulan Terbenam",
    "moon_phase": "Fase Bulan", "moon_illumination": "Iluminasi Bulan (%)",
}

def render_current_conditions(data: dict) -> Panel:
    if "current_condition" not in data or not data["current_condition"]:
        return Panel("❌ Data kondisi saat ini tidak tersedia.", title="Kondisi Saat Ini", border_style="red")
    
    current = data["current_condition"][0]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="bold white")

    # Filter parameter utama saja agar rapi
    main_keys = ["weatherDesc", "temp_C", "FeelsLikeC", "humidity", "windspeedKmph", "winddir16Point", "uvIndex", "cloudcover", "visibility"]
    for key in main_keys:
        if key in current:
            val = extract_value(current[key])
            label = FIELD_LABELS.get(key, key)
            table.add_row(label, val)
            
    return Panel(table, title="[bold cyan]📡 KONDISI SAAT INI", border_style="cyan", expand=False)

def render_astronomy(today: dict) -> Panel:
    astro = today.get("astronomy", [{}])[0]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="yellow")
    table.add_column(style="white")
    
    for key, val in astro.items():
        label = ASTRO_LABELS.get(key, key)
        table.add_row(label, val)
        
    return Panel(table, title="[bold yellow]🌅 ASTRONOMI", border_style="yellow", expand=False)

def render_air_quality(aqi_data: dict, lat: float, lon: float) -> Panel:
    if not aqi_data:
        return Panel("🌫️ Data kualitas udara tidak tersedia.", title="Kualitas Udara", border_style="grey50")
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="green")
    table.add_column(style="white")
    
    table.add_row("US AQI", str(aqi_data.get("us_aqi", "N/A")))
    table.add_row("PM2.5", f"{aqi_data.get('pm2_5', 'N/A')} µg/m³")
    table.add_row("PM10", f"{aqi_data.get('pm10', 'N/A')} µg/m³")
    table.add_row("O₃", f"{aqi_data.get('ozone', 'N/A')} µg/m³")
    
    return Panel(table, title=f"[bold green]🌫️ UDARA ({lat:.2f}, {lon:.2f})", border_style="green", expand=False)

def render_forecast(days: List[dict]) -> Panel:
    table = Table(box=None, expand=True)
    table.add_column("Tanggal", style="cyan")
    table.add_column("Suhu", justify="center", style="yellow")
    table.add_column("Cuaca", style="white")

    for day in days[:3]:
        date = day.get("date", "N/A")
        max_t = day.get("maxtempC", "?")
        min_t = day.get("mintempC", "?")
        
        hourly = day.get("hourly", [])
        desc_siang = extract_value(hourly[0].get("weatherDesc", "")) if hourly else "N/A"
        for h in hourly:
            if h.get("time") == "1200":
                desc_siang = extract_value(h.get("weatherDesc", ""))
                break
                
        table.add_row(date, f"{min_t}°C - {max_t}°C", desc_siang)
        
    return Panel(table, title="[bold magenta]📅 RAMALAN 3 HARI", border_style="magenta")

def render_earthquake(eq: dict) -> Panel:
    if not eq:
        return Panel("⚠️ Data gempa bumi tidak dapat diambil.", title="Gempa Bumi", border_style="red")
        
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="red")
    table.add_column(style="white")
    
    table.add_row("Waktu", eq.get("DateTime", f"{eq.get('Tanggal')} {eq.get('Jam')}"))
    table.add_row("Magnitudo", f"{eq.get('Magnitude', 'N/A')} SR")
    table.add_row("Kedalaman", f"{eq.get('Kedalaman', 'N/A')} km")
    table.add_row("Lokasi", eq.get("Wilayah", "N/A"))
    table.add_row("Potensi", eq.get("Potensi", "N/A"))
    
    return Panel(table, title="[bold red]🌍 GEMPA TERBARU", border_style="red")

def render_warnings(warnings: list) -> Panel:
    if not warnings:
        return Panel("Aman. Tidak ada peringatan cuaca ekstrem.", title="[bold green]⚠️ PERINGATAN DINI", border_style="green")
        
    txt = Text()
    for i, w in enumerate(warnings[:3], 1): # Ambil 3 teratas agar tidak kepanjangan
        txt.append(f"{i}. {w['area']}\n", style="bold yellow")
        txt.append(f"   {w['event']}\n", style="white")
    
    return Panel(txt, title="[bold red]⚠️ PERINGATAN DINI BMKG", border_style="red")

# ---------------------------- GRAFIK PLOTEXT ----------------------------
def display_hourly_chart(hourly: list):
    if not hourly:
        return

    times, temps, rains = [], [], []
    for h in hourly:
        times.append(format_time(h.get("time", "0")))
        temps.append(int(h.get("tempC", 0)))
        rains.append(int(h.get("chanceofrain", 0)))

    plt.clf()
    plt.title("Suhu (°C) & Probabilitas Hujan (%) Per Jam")
    plt.multiple_bar(times, [temps, rains], labels=["Suhu (°C)", "Hujan (%)"])
    plt.theme("dark") # Tema gelap khas terminal
    plt.plotsize(100, 25) # Menyesuaikan ukuran lebar/tinggi grafik
    print("\n")
    plt.show()
    print("\n")

# ---------------------------- MAIN EXECUTOR ----------------------------
def main():
    print_banner()

    city = rich_typewriter_input("Masukkan Nama Kota: ")
    if not city:
        city = auto_detect_city()
        console.print(f"\n[bold green]🏙️  Lokasi terdeteksi:[/bold green] {city}\n")
    else:
        print()

    # Mengambil semua data
    with console.status("[bold cyan]Mengambil data cuaca dan metrik lainnya...", spinner="dots"):
        data = get_full_weather(city)
        weather_list = data.get("weather", [])
        
        area = data.get("nearest_area", [])
        lat = lon = 0.0
        if area:
            try:
                lat = float(area[0].get("latitude", "0"))
                lon = float(area[0].get("longitude", "0"))
            except: pass
            
        aqi = get_air_quality(lat, lon) if (lat and lon) else None
        warnings = get_bmkg_warnings()
        eq = get_earthquake_data()

    # RENDER BARIS 1: Kondisi, Astronomi, Udara
    panel_current = render_current_conditions(data)
    today = weather_list[0] if weather_list else {}
    panel_astro = render_astronomy(today)
    panel_aqi = render_air_quality(aqi, lat, lon)
    
    console.print(panel_current)
    panel_delay(0.5)

    console.print(panel_astro)
    panel_delay(0.5)

    console.print(panel_aqi)
    panel_delay(0.5)
    
    # RENDER BARIS 2: Ramalan, Gempa, Peringatan
    panel_forecast = render_forecast(weather_list)
    panel_eq = render_earthquake(eq)
    panel_warn = render_warnings(warnings)
    
    console.print(panel_forecast)
    panel_delay(0.5)

    console.print(panel_eq)
    panel_delay(0.5)

    console.print(panel_warn)
    panel_delay(0.5)

    # RENDER BARIS 3: Grafik Plotext per Jam
    if today:
        display_hourly_chart(today.get("hourly", []))

    # Tampilkan link peta
    if lat and lon:
        console.print(f"[bold blue]🗺️  Peta Google Maps:[/bold blue] https://www.google.com/maps?q={lat},{lon}")

if __name__ == "__main__":
    main()
