#!/usr/bin/env python3
"""
Radio Cover Fetcher for Moode + SSE
"""
import os, sys, time, logging, requests, re, sqlite3, signal, unicodedata, html
import json, uuid, functools, socket

from PIL import ImageFile
from threading import Thread, Lock, Event
from queue import Queue, Empty
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import quote
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from logging.handlers import RotatingFileHandler

__version__ = "9.1.1"

# ================= CONFIG GLOBALS (fallback) =================
SPOTIFY_CLIENT_ID     = None
SPOTIFY_CLIENT_SECRET = None
LASTFM_API_KEY        = None
DISCOGS_TOKEN         = None
THEAUDIODB_API_KEY    = "2"

DEBOUNCE_MS             = 0.8
REQUEST_TIMEOUT         = 10.0
MB_TIMEOUT              = (0.5, 1.5)

MAX_SIZE_PX           = 800
COVER_QUALITY         = 85
MIN_SIMILARITY        = 0.75
MIN_SIMILARITY_ITUNES = 0.90

FAST_DEADLINE_S  = 1.5
TOTAL_DEADLINE_S = 2.5
EARLY_STOP_SCORE = 5.0

CACHE_ENABLED         = False
LAST_EVENT_SEND_DELAY = 1.5
PROVIDERS_LIST        = {}
HEALTH_CHECK_INTERVAL = 300

REF_ARTIST = "The Beatles"
REF_TRACK  = "Yesterday"

# Segment cover URLs — GitHub CDN
SEGMENT_COVER_METEO       = "https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main/covers/meteo.jpg"
SEGMENT_COVER_TRAFFIC     = "https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main/covers/traffic.jpg"
SEGMENT_COVER_NEWS        = "https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main/covers/news.jpg"
SEGMENT_COVER_ADVERTISING = "https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main/covers/advertising.jpg"

# Segment type constants
SEGMENT_METEO       = "meteo"
SEGMENT_TRAFFIC     = "traffic"
SEGMENT_NEWS        = "news"
SEGMENT_ADVERTISING = "advertising"

# ================= PATHS =================
LOG_FILE        = "/var/log/radio-cover.log"
MAX_LOG_SIZE    = 512 * 1024
BACKUP_COUNT    = 0
RADIO_LOGOS_DIR = "/var/local/www/imagesw/radio-logos"
MOODE_DB        = "/var/local/www/db/moode-sqlite3.db"

LOG_LEVEL_MAP = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
LOG_LEVEL = "INFO"

# ================= GLOBALS =================
SPOTIFY_TOKEN        = None
SPOTIFY_TOKEN_EXPIRY = 0

_subscribers      = []
_sub_lock         = Lock()
_shutdown_event   = Event()
_last_cover_event = None
_last_cover_lock  = Lock()

# ================= LOGGING =================
handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[handler]
)

# ================= CONFIG =================
ALL_LRU_CACHES = []

def read_global():
    global SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, LASTFM_API_KEY, DISCOGS_TOKEN
    global THEAUDIODB_API_KEY, LOG_LEVEL
    global CACHE_ENABLED
    global DEBOUNCE_MS, REQUEST_TIMEOUT, MAX_SIZE_PX, COVER_QUALITY
    global MIN_SIMILARITY, MIN_SIMILARITY_ITUNES
    global FAST_DEADLINE_S, TOTAL_DEADLINE_S, EARLY_STOP_SCORE
    global LAST_EVENT_SEND_DELAY, HEALTH_CHECK_INTERVAL
    global PROVIDERS_LIST
    global SEGMENT_COVER_METEO, SEGMENT_COVER_TRAFFIC, SEGMENT_COVER_NEWS, SEGMENT_COVER_ADVERTISING

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "moode_sse_server.config"
    )
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    values = {}

    if not os.path.isfile(config_path):
        logging.error(f"[read_global] ❌ Config file missing: {config_path}")
        return

    try:
        with open(config_path, "r") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    logging.warning(f"[read_global] ❌ Invalid line {lineno}: {line}")
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip() or None
    except Exception as e:
        logging.error(f"[read_global] ❌ Error reading config: {e}")
        return

    def load_token(name):
        val = values.get(name)
        if not val:
            logging.error(f"[read_global] ❌ Missing or empty token: {name}")
        return val

    def load_float(key, fallback):
        try:
            val = values.get(key)
            if val is not None:
                val = float(val)
                if val < 0: raise ValueError
                return val
        except ValueError:
            logging.error(f"[read_global] ❌ Invalid {key}, fallback={fallback}")
        return fallback

    def load_int(key, fallback):
        try:
            val = values.get(key)
            if val is not None:
                val = int(val)
                if val < 0: raise ValueError
                return val
        except ValueError:
            logging.error(f"[read_global] ❌ Invalid {key}, fallback={fallback}")
        return fallback

    SPOTIFY_CLIENT_ID     = load_token("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = load_token("SPOTIFY_CLIENT_SECRET")
    LASTFM_API_KEY        = load_token("LASTFM_API_KEY")
    DISCOGS_TOKEN         = load_token("DISCOGS_TOKEN")
    THEAUDIODB_API_KEY    = values.get("THEAUDIODB_API_KEY", "2") or "2"

    level = values.get("LOG_LEVEL", "").upper()
    LOG_LEVEL = level if level in valid_levels else "INFO"
    logging.getLogger().setLevel(LOG_LEVEL_MAP[LOG_LEVEL])

    CACHE_ENABLED           = values.get("CACHE_ENABLED",           "").lower() in ("1","true","yes","on")

    DEBOUNCE_MS           = load_float("DEBOUNCE_MS",           0.8)
    REQUEST_TIMEOUT       = load_float("REQUEST_TIMEOUT",       10.0)
    LAST_EVENT_SEND_DELAY = load_float("LAST_EVENT_SEND_DELAY", 1.5)
    MIN_SIMILARITY        = load_float("MIN_SIMILARITY",        0.75)
    MIN_SIMILARITY_ITUNES = load_float("MIN_SIMILARITY_ITUNES", 0.90)
    FAST_DEADLINE_S       = load_float("FAST_DEADLINE_S",       1.5)
    TOTAL_DEADLINE_S      = load_float("TOTAL_DEADLINE_S",      2.5)
    EARLY_STOP_SCORE      = load_float("EARLY_STOP_SCORE",      5.0)
    MAX_SIZE_PX           = load_int("MAX_SIZE_PX",             800)
    COVER_QUALITY         = load_int("COVER_QUALITY",           85)
    HEALTH_CHECK_INTERVAL = load_int("HEALTH_CHECK_INTERVAL",   300)

    # Segment cover URLs override from config (optional)
    SEGMENT_COVER_METEO       = values.get("SEGMENT_COVER_METEO",       SEGMENT_COVER_METEO)
    SEGMENT_COVER_TRAFFIC     = values.get("SEGMENT_COVER_TRAFFIC",     SEGMENT_COVER_TRAFFIC)
    SEGMENT_COVER_NEWS        = values.get("SEGMENT_COVER_NEWS",        SEGMENT_COVER_NEWS)
    SEGMENT_COVER_ADVERTISING = values.get("SEGMENT_COVER_ADVERTISING", SEGMENT_COVER_ADVERTISING)

    PROVIDER_NAMES = ["Spotify","iTunes","Deezer","LastFM","MusicBrainz","Discogs","TheAudioDB"]
    PROVIDERS_LIST = {
        n: values.get(n, "False").lower() in ("1","true","yes","on")
        for n in PROVIDER_NAMES
    }

def log_config_summary():
    def mask(v):
        if not v: return "None"
        return v[:3] + "***" + v[-3:] if len(v) > 6 else "***"
    logging.error("[config] ========== Configuration summary ==========")
    logging.error(f"[config] LOG_LEVEL               = {LOG_LEVEL}")
    logging.error(f"[config] SPOTIFY_CLIENT_ID       = {mask(SPOTIFY_CLIENT_ID)}")
    logging.error(f"[config] SPOTIFY_CLIENT_SECRET   = {mask(SPOTIFY_CLIENT_SECRET)}")
    logging.error(f"[config] LASTFM_API_KEY          = {mask(LASTFM_API_KEY)}")
    logging.error(f"[config] DISCOGS_TOKEN           = {mask(DISCOGS_TOKEN)}")
    logging.error(f"[config] THEAUDIODB_API_KEY      = {THEAUDIODB_API_KEY}")
    logging.error(f"[config] DEBOUNCE_MS             = {DEBOUNCE_MS}")
    logging.error(f"[config] REQUEST_TIMEOUT         = {REQUEST_TIMEOUT}")
    logging.error(f"[config] FAST_DEADLINE_S         = {FAST_DEADLINE_S}")
    logging.error(f"[config] TOTAL_DEADLINE_S        = {TOTAL_DEADLINE_S}")
    logging.error(f"[config] EARLY_STOP_SCORE        = {EARLY_STOP_SCORE}")
    logging.error(f"[config] MIN_SIMILARITY          = {MIN_SIMILARITY}")
    logging.error(f"[config] MIN_SIMILARITY_ITUNES   = {MIN_SIMILARITY_ITUNES}")
    logging.error(f"[config] CACHE_ENABLED           = {CACHE_ENABLED}")
    logging.error(f"[config] LAST_EVENT_SEND_DELAY   = {LAST_EVENT_SEND_DELAY}")
    logging.error(f"[config] HEALTH_CHECK_INTERVAL   = {HEALTH_CHECK_INTERVAL}")
    enabled = [n for n, v in PROVIDERS_LIST.items() if v]
    logging.error(f"[config] Providers enabled       = {enabled}")
    logging.error("[config] ===========================================")

def reload_config(signum=None, frame=None):
    logging.error("[reload_config] 🔄 Reloading configuration (SIGHUP)")
    read_global()
    for c in ALL_LRU_CACHES:
        info = c.cache_info()
        logging.warning(f"[reload_config] Clearing cache size={info.currsize} hits={info.hits}")
        c.cache_clear()
    # Update segment cover map after reload
    SEGMENT_COVER_MAP[SEGMENT_METEO]       = SEGMENT_COVER_METEO
    SEGMENT_COVER_MAP[SEGMENT_TRAFFIC]     = SEGMENT_COVER_TRAFFIC
    SEGMENT_COVER_MAP[SEGMENT_NEWS]        = SEGMENT_COVER_NEWS
    SEGMENT_COVER_MAP[SEGMENT_ADVERTISING] = SEGMENT_COVER_ADVERTISING
    logging.warning("[reload_config] 🧹 All LRU caches cleared")
    log_config_summary()

def graceful_exit(signum, frame):
    logging.info("[graceful_exit] 🛑 STOP received")
    _shutdown_event.set()
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_exit)
signal.signal(signal.SIGINT,  graceful_exit)
signal.signal(signal.SIGHUP,  reload_config)

# ================= CACHE =================
def logging_lru_cache(maxsize=128):
    def decorator(func):
        cached_func = functools.lru_cache(maxsize=maxsize)(func)
        ALL_LRU_CACHES.append(cached_func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not CACHE_ENABLED:
                return func(*args, **kwargs)
            before = cached_func.cache_info().hits
            result = cached_func(*args, **kwargs)
            after  = cached_func.cache_info().hits
            if result is not None:
                if after > before:
                    logging.info(f"[CACHE HIT]  {func.__name__}{args}")
                else:
                    logging.debug(f"[CACHE MISS] {func.__name__}{args}")
            return result

        wrapper.cache_info  = cached_func.cache_info
        wrapper.cache_clear = cached_func.cache_clear
        return wrapper
    return decorator

# ================= LOGO DB =================
@logging_lru_cache(maxsize=1000)
def get_logo_from_db(stream_url):
    if not os.path.exists(MOODE_DB): return None
    try:
        clean_url = stream_url.split('#')[0].split('?')[0]
        conn = sqlite3.connect(MOODE_DB)
        c = conn.cursor()
        c.execute("SELECT logo, name FROM cfg_radio WHERE station LIKE ? LIMIT 1",
                  (f"%{clean_url}%",))
        row = c.fetchone()
        conn.close()
        if row:
            db_logo, st_name = row[0], row[1]
            if db_logo and db_logo != "local":
                p = os.path.join(RADIO_LOGOS_DIR, db_logo)
                if os.path.exists(p): return p
            elif (db_logo == "local" or not db_logo) and st_name:
                for ext in [".jpg", ".png", ".jpeg", ".JPG"]:
                    p = os.path.join(RADIO_LOGOS_DIR, f"{st_name}{ext}")
                    if os.path.exists(p): return os.path.realpath(p)
    except Exception as e:
        logging.error(f"[get_logo_from_db] ⚠️ DB Error: {e}")
    return None

# ================= QUERY UTILITY =================
MOJIBAKE_PATTERN = re.compile(
    r"""
        Ã[\x80-\xBF]
      | Â[\x80-\xBF]
      | â[\x80-\xBF]{2}
      | ð[\x80-\xBF]{3}
      | \ufffd
    """,
    re.VERBOSE,
)

def fix_mojibake_if_needed(text):
    if not MOJIBAKE_PATTERN.search(text):
        return text
    try:
        repaired = text.encode("latin1", "strict").decode("utf-8", "strict")
        before = len(MOJIBAKE_PATTERN.findall(text))
        after  = len(MOJIBAKE_PATTERN.findall(repaired))
        if after < before:
            return repaired
    except UnicodeError:
        pass
    return text

def normalize_id(text):
    """Normalize for hashing/comparison: HTML unescape, NFKC, mojibake fix."""
    if not text: return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    if MOJIBAKE_PATTERN.search(text):
        text = fix_mojibake_if_needed(text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def split_artist_title(full_title):
    if not full_title: return "", ""
    m = re.match(r'^(.*?)\s-\s(.*)$', full_title)
    if m: return m.group(1).strip(), m.group(2).strip()
    if "~" in full_title:
        parts = [p.strip() for p in full_title.split("~") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
    return "", full_title.strip()

def sanitize(text):
    """Light cleanup: & → and."""
    if not text: return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r"\s&\s",  " and ", text)
    text = re.sub(r"\s\+\s", " and ", text)
    text = re.sub(r"[\/\:;\|\~\+]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.replace("Revisted", "Revisited")
    return text.strip()

def similarity(a, b):
    a_s, b_s = sanitize(a.lower()), sanitize(b.lower())
    if not a_s or not b_s: return 0.0
    a_set, b_set = set(a_s.split()), set(b_s.split())
    inter = len(a_set & b_set)
    union = len(a_set | b_set)
    return inter / union if union else 0.0

def prepare_text_for_query(text):
    """Aggressive cleanup: NFKD + ASCII transliteration."""
    if not text: return ""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode()
    text = re.sub(r'\s*&\s*', ' and ', text)
    text = re.sub(r'\s*[\(\[].*?[\)\]]', '', text)
    text = re.sub(r'[\/:;|~+]', ' ', text)
    text = re.sub(r'\b(deluxe|remaster|edition|version|single)\b', '', text, flags=re.I)
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.replace('"', '').replace("'", "'").strip()
    return text.strip()

def prepare_query(artist, title, album=None):
    artist_q = prepare_text_for_query(artist)
    title_q  = prepare_text_for_query(title)
    query = f'artist:"{artist_q}" track:"{title_q}"'
    if album:
        album_q = prepare_text_for_query(album)
        if album_q:
            query += f' album:"{album_q}"'
    return query

def prepare_free_term(artist, title, album=None):
    parts = [prepare_text_for_query(x) for x in [artist, title, album] if x]
    return " ".join(parts)

def normalize_for_search(string):
    """Light cleanup for attempt 1: removes feat/with."""
    t = string
    t = re.sub(r"\(\s*(feat\.?|ft\.?|featuring|w/|with|voc\.?|voice)\s+[^)]*\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[\-,]?\s*(feat\.?|ft\.?|featuring|w/|voc\.?|voice)\s+.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def clean_artist_name(artist):
    """Aggressive artist cleanup for attempt 2."""
    if not artist: return ""
    raw = artist
    cleaned = re.sub(r'(?:www\.|[\w-]+\.(?:com|net|org|io|fm|it)|[\w\s]+:)\s*', '', artist, flags=re.IGNORECASE)
    if ':' in cleaned and len(cleaned.split(':')[0]) < 25:
        cleaned = cleaned.split(':')[-1]
    if ',' in cleaned:
        cleaned = cleaned.split(',')[0]
    cleaned = re.sub(r'\s*[\(\[].*?[\)\]]', '', cleaned).strip()
    if "~" in cleaned: cleaned = cleaned.split("~")[0]
    cleaned = cleaned.replace('*', ' ').strip()
    cleaned = re.sub(r'\b(remix|compilation|dj mix|original mix)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+(feat\.?|ft\.?|featuring|with|starring)\s+.*', '', cleaned, flags=re.IGNORECASE)
    res = cleaned.strip()
    if raw != res:
        logging.info(f"[clean_artist_name] 🧹 '{raw}' → '{res}'")
    return res

def normalize_title(title, artist=None):
    """Aggressive title cleanup for attempt 2. Strips 'Artist - ' prefix if artist is provided."""
    if not title: return ""
    raw = title

    # Strip artist prefix if present
    if artist:
        prefix = f"{artist} - "
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):]

    if "~" in title: title = title.split("~")[0]
    if "/" in title: title = title.split("/")[0]
    if "*" in title: title = title.replace("*", " ")
    title = re.sub(r'(?:www\.[a-z0-9\.]+|[a-z0-9\.]+\.ch)\s*', '', title, flags=re.IGNORECASE).strip()

    title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
    title = re.sub(r'[\s\-\.]+$', '', title).strip()
    res = title.strip()
    if raw != res:
        logging.info(f"[normalize_title] 🧹 '{raw}' → '{res}'")
    return res

# ================= NOISE / SEGMENT GATE =================
def is_noise(raw_title, station_name):
    """
    Returns (True, segment_type) if noise with identified segment.
    Returns (True, None) if pure noise.
    Returns (False, None) if valid track.

    Segment keywords (meteo/traffic/news/advertising) are checked
    only in the part of the title after the ' - ' separator,
    to avoid false positives when the station name contains
    words like 'sport' or 'news' (e.g. 'RADIO MANA SPORT').
    """
    if not raw_title or len(raw_title.strip()) < 3:
        return True, None  # Vacuum gate

    ti = raw_title.lower().strip()
    st = station_name.lower().strip() if station_name else ""

    # Isolated AD block
    if ti == "ad" or ti.endswith(" ad"):
        return True, None

    # Station name equals title exactly
    if st == ti:
        return True, None

    # Segment keywords checked only in the part after ' - '
    if " - " in ti:
        segment_part = ti.split(" - ", 1)[1].strip()
    elif ti.startswith("- "):
        segment_part = ti[2:].strip()
    else:
        segment_part = ""

    if segment_part:
        meteo_keywords = ["meteo", "weather", "wetter", "météo", "previsioni"]
        if any(w in segment_part for w in meteo_keywords):
            return True, SEGMENT_METEO

        traffic_keywords = ["traffico", "traffic", "verkehr", "trafic", "viabilità", "viabilita"]
        if any(w in segment_part for w in traffic_keywords):
            return True, SEGMENT_TRAFFIC

        news_keywords = ["news", "notizie", "nachrichten", "actualités", "noticias", "nieuws"]
        if any(w in segment_part for w in news_keywords) or re.search(r'\bsport\b', segment_part):
            return True, SEGMENT_NEWS

        advertising_keywords = [
            "adbreak", "ad break", "advert", "advertising", "advertisement",
            "live365 - advertisement",
            "pubblicita", "pubblicità", "werbung", "publicité",
            "publicidad", "reklame", "reclame", "spot",
            "adbreak_end"
        ]
        if any(w in segment_part for w in advertising_keywords):
            return True, SEGMENT_ADVERTISING

    # Check meteo/traffic in full title (no separator)
    if any(w in ti for w in ["meteo", "weather", "wetter", "météo", "previsioni"]):
        return True, SEGMENT_METEO
    if any(w in ti for w in ["traffico", "traffic", "verkehr", "trafic", "viabilità", "viabilita"]):
        return True, SEGMENT_TRAFFIC
    if any(w in ti for w in ["adbreak", "ad break", "adbreak_end", "advert", "advertising"]):
        return True, SEGMENT_ADVERTISING

    # Title too similar to station name
    st_parts = st.split()
    if st_parts:
        matches = sum(1 for p in st_parts if p in ti)
        if matches >= len(st_parts) * 0.6:
            return True, None

    # Pure noise without dedicated cover
    # Artist repeated in title with year → station metadata noise
    year_match = re.match(r'^(.+)\s-\s(\d{4})$', raw_title)
    if year_match and year_match.group(1).strip().lower() == ti.split(' - ')[0].strip().lower():
        logging.info(f"[DEBUG year_match] MATCHED: raw='{raw_title}' group1='{year_match.group(1).strip().lower()}' ti_part='{ti.split(' - ')[0].strip().lower()}'")
        return True, None
    noise_pure = ["jingle", "promo", "stationid", "oroscopo", "bollettino"]
    if "~~~" in ti:
        return True, None
    if any(ti.startswith(w) for w in noise_pure):
        return True, None

    return False, None

SEGMENT_COVER_MAP = {}  # Populated in main after read_global

def get_segment_cover_url(segment_type):
    return SEGMENT_COVER_MAP.get(segment_type)

# ================= IMAGE RESOLUTION =================
def get_image_resolution(url, mode="regex"):
    if mode == "regex":
        try:
            m = re.search(r'(\d+)x(\d+)', url)
            if m: return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        return 0, 0

    if mode == "head":
        try:
            r = requests.head(url, timeout=min(REQUEST_TIMEOUT, 3))
            r.raise_for_status()
            size_bytes = int(r.headers.get("Content-Length", 0))
            if size_bytes > 0:
                est = max(1, int(size_bytes ** 0.5))
                return est, est
        except Exception:
            pass
        return 0, 0

    if mode == "pil":
        try:
            parser = ImageFile.Parser()
            r = requests.get(url, stream=True, timeout=min(REQUEST_TIMEOUT, 3))
            r.raise_for_status()
            for chunk in r.iter_content(1024):
                if not chunk or parser.image: break
                parser.feed(chunk)
            if parser.image: return parser.image.size
        except Exception:
            pass
        return 0, 0

    return 0, 0

# ================= PROVIDER SEARCH FUNCTIONS =================
def get_spotify_token():
    global SPOTIFY_TOKEN, SPOTIFY_TOKEN_EXPIRY
    if time.time() < SPOTIFY_TOKEN_EXPIRY and SPOTIFY_TOKEN:
        return SPOTIFY_TOKEN
    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials",
                  "client_id": SPOTIFY_CLIENT_ID,
                  "client_secret": SPOTIFY_CLIENT_SECRET},
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        SPOTIFY_TOKEN        = data["access_token"]
        SPOTIFY_TOKEN_EXPIRY = time.time() + data["expires_in"] - 300
        return SPOTIFY_TOKEN
    except Exception:
        return None

def search_spotify(artist, title, album=None):
    t = get_spotify_token()
    if not t: return None, None, None
    try:
        q = prepare_query(artist, title, album)
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {t}"},
            params={"q": q, "type": "track", "limit": 5},
            timeout=REQUEST_TIMEOUT
        )
        if r.ok:
            items = r.json().get("tracks", {}).get("items", [])
            good = [i for i in items
                    if not artist or similarity(artist, i["artists"][0]["name"]) >= MIN_SIMILARITY]
            if good:
                type_order = {"album": 0, "single": 1, "compilation": 2, "appears_on": 3}
                good.sort(key=lambda x: type_order.get(x.get("album",{}).get("album_type","compilation"), 4))
                sel = good[0]
                cover_url  = sel["album"]["images"][0]["url"] if sel["album"].get("images") else None
                album_name = sel["album"].get("name")
                album_type = sel["album"].get("album_type")
                return cover_url, album_name, album_type
    except Exception as e:
        logging.error(f"[search_spotify] ❌ {e}")
    return None, None, None

def search_musicbrainz(artist, title, album=None):
    try:
        artist_q = prepare_text_for_query(artist)
        title_q  = prepare_text_for_query(title)
        q = f'artist:"{artist_q}" AND recording:"{title_q}"'
        if album:
            album_q = prepare_text_for_query(album)
            if album_q: q += f' AND release:"{album_q}"'
        r = requests.get(
            "https://musicbrainz.org/ws/2/recording",
            headers={"User-Agent": "MoodeRadio/9.1.0 ( moode@example.com )"},
            params={"query": q, "fmt": "json", "limit": 3},
            timeout=MB_TIMEOUT
        )
        if r.ok:
            for rec in r.json().get("recordings", []):
                for rel in rec.get("releases", []):
                    mbid = rel.get("id")
                    rel_title = rel.get("title")
                    release_group = rel.get("release-group", {})
                    album_type = release_group.get("primary-type") if release_group else None
                    if not mbid: continue
                    try:
                        cr = requests.get(
                            f"https://coverartarchive.org/release/{mbid}",
                            headers={"User-Agent": "MoodeRadio/9.1.0 ( moode@example.com )"},
                            timeout=MB_TIMEOUT
                        )
                        if cr.ok:
                            for img in cr.json().get("images", []):
                                if img.get("front"):
                                    img_url = (img.get("image")
                                               or img.get("thumbnails", {}).get("large")
                                               or img.get("thumbnails", {}).get("small"))
                                    if img_url:
                                        return img_url, rel_title, album_type
                    except Exception as e:
                        logging.debug(f"[search_musicbrainz] CAA error {mbid}: {e}")
    except Exception as e:
        logging.error(f"[search_musicbrainz] ❌ {e}")
    return None, None, None

def search_discogs(artist, title, album=None):
    if not DISCOGS_TOKEN: return None, None, None
    try:
        q = prepare_free_term(artist, title, album)
        r = requests.get(
            "https://api.discogs.com/database/search",
            params={"q": q, "type": "release", "token": DISCOGS_TOKEN},
            headers={"User-Agent": "MoodeRadio/9.1.0 ( moode@example.com )"},
            timeout=REQUEST_TIMEOUT
        )
        if r.ok:
            for item in r.json().get("results", []):
                formats   = item.get("format", [])
                item_type = item.get("type")
                if item_type == "release" and "Album" in formats and "Compilation" not in formats:
                    title_str = item.get("title", "")
                    if " - " in title_str:
                        res_artist = title_str.split(" - ", 1)[0]
                        if similarity(artist, res_artist) >= MIN_SIMILARITY:
                            cover_img  = item.get("cover_image")
                            album_name = title_str.split(" - ", 1)[1]
                            return cover_img, album_name, "Album"
    except Exception as e:
        logging.error(f"[search_discogs] ❌ {e}")
    return None, None, None

def search_itunes(artist, title, album=None):
    try:
        term = prepare_free_term(artist, title, album)
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": term, "media": "music", "entity": "song", "limit": 5},
            timeout=REQUEST_TIMEOUT
        )
        if r.ok:
            for i in r.json().get("results", []):
                if not artist or similarity(artist, i.get("artistName","")) >= MIN_SIMILARITY_ITUNES:
                    album_name = i.get("collectionName")
                    album_type = i.get("collectionType")
                    return i.get("artworkUrl100","").replace("100x100","600x600"), album_name, album_type
    except Exception:
        pass
    return None, None, None

def search_deezer(artist, title, album=None):
    try:
        q = prepare_query(artist, title, album)
        r = requests.get("https://api.deezer.com/search", params={"q": q, "limit": 5}, timeout=REQUEST_TIMEOUT)
        if r.ok:
            for i in r.json().get("data", []):
                if not artist or similarity(artist, i["artist"]["name"]) >= MIN_SIMILARITY:
                    album_name = i["album"].get("title")
                    return i["album"].get("cover_xl"), album_name, None
    except Exception:
        pass
    return None, None, None

def search_lastfm(artist, title, album=None):
    if not LASTFM_API_KEY: return None, None, None
    try:
        params = {"method": "track.getInfo", "api_key": LASTFM_API_KEY,
                  "artist": artist, "track": title, "format": "json"}
        if album: params["album"] = prepare_text_for_query(album)
        r = requests.get("http://ws.audioscrobbler.com/2.0/", params=params, timeout=REQUEST_TIMEOUT)
        if r.ok:
            track = r.json().get("track", {})
            imgs  = track.get("album", {}).get("image", [])
            album_name = track.get("album", {}).get("title")
            if imgs:
                return imgs[-1]["#text"], album_name, None
    except Exception:
        pass
    return None, None, None

def search_theaudiodb(artist, title, album=None):
    try:
        r1 = requests.get(
            f"https://www.theaudiodb.com/api/v1/json/{THEAUDIODB_API_KEY}/searchtrack.php",
            params={"s": artist, "t": title},
            timeout=REQUEST_TIMEOUT
        )
        if not r1.ok: return None, None, None
        tracks = r1.json().get("track") or []
        if not tracks: return None, None, None
        id_album   = tracks[0].get("idAlbum")
        album_name = tracks[0].get("strAlbum")
        if not id_album: return None, None, None
        r2 = requests.get(
            f"https://www.theaudiodb.com/api/v1/json/{THEAUDIODB_API_KEY}/album.php",
            params={"m": id_album},
            timeout=REQUEST_TIMEOUT
        )
        if not r2.ok: return None, None, None
        albums = r2.json().get("album") or []
        if not albums: return None, None, None
        thumb = albums[0].get("strAlbumThumb")
        if thumb:
            return thumb, album_name, "Album"
    except Exception as e:
        logging.error(f"[search_theaudiodb] ❌ {e}")
    return None, None, None

def search_radio_paradise(station_name, artist, title):
    """Radio Paradise API — direct cover for RP stations."""
    def rp_channel_key(name):
        if not name: return None
        lname = name.lower()
        if "radio paradise" not in lname: return None
        if ":" not in lname: return "0"
        if "mellow" in lname: return "1"
        if "rock"   in lname: return "2"
        if "global" in lname: return "3"
        return None

    channel_key = rp_channel_key(station_name)
    if channel_key is None: return None

    try:
        r = requests.get(
            f"https://api.radioparadise.com/api/now_playing?chan={channel_key}",
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        api_artist = data.get("artist") or ""
        api_title  = data.get("title")  or ""
        cover = data.get("cover") or data.get("cover_med") or data.get("cover_small")

        if artist.lower() != api_artist.lower() or title.lower() != api_title.lower():
            logging.debug(f"[RadioParadise] ⚠️ Mismatch MPD:'{artist}-{title}' RP:'{api_artist}-{api_title}'")
            return None

        if cover:
            logging.info(f"[RadioParadise] 🟢 Cover found chan={channel_key}: {cover}")
            return cover
    except Exception as e:
        logging.error(f"[RadioParadise] ❌ {e}")
    return None

# ================= SEARCH COVER PARALLEL =================
def search_cover_parallel(artist, title, attempt=1, uuid_=None):
    """
    Parallel cover search across all enabled providers.
    Timebox: FAST_DEADLINE_S → TOTAL_DEADLINE_S.
    """
    start_time = time.time()
    results = []
    futures = {}

    providers = []
    if PROVIDERS_LIST.get("Spotify"):     providers.append(("Spotify",     search_spotify))
    if PROVIDERS_LIST.get("iTunes"):      providers.append(("iTunes",      search_itunes))
    if PROVIDERS_LIST.get("Deezer"):      providers.append(("Deezer",      search_deezer))
    if PROVIDERS_LIST.get("LastFM"):      providers.append(("LastFM",      search_lastfm))
    if PROVIDERS_LIST.get("MusicBrainz"): providers.append(("MusicBrainz", search_musicbrainz))
    if PROVIDERS_LIST.get("Discogs"):     providers.append(("Discogs",     search_discogs))
    if PROVIDERS_LIST.get("TheAudioDB"):  providers.append(("TheAudioDB",  search_theaudiodb))

    logging.info(f"[search_cover_parallel] START attempt={attempt} fast={FAST_DEADLINE_S}s total={TOTAL_DEADLINE_S}s early>={EARLY_STOP_SCORE} artist='{artist}' title='{title}' uuid={uuid_}")

    with ThreadPoolExecutor(max_workers=len(providers) if providers else 1) as executor:
        for name, func in providers:
            futures[executor.submit(func, artist, title, None)] = name

        done, not_done = wait(futures.keys(), timeout=FAST_DEADLINE_S, return_when=FIRST_COMPLETED)

        def eval_results(d_set):
            best_score = -1.0
            best_res   = None
            for f in d_set:
                prov_name = futures[f]
                try:
                    c, a, t = f.result()
                    if c:
                        score = 0.0
                        w, h = get_image_resolution(c, mode="regex")
                        if w and h:
                            score += min(max(w, h) / 1000.0, 1.5)
                        if t == "Album": score += 2.0
                        elif t == "Single": score += 1.0
                        if prov_name in ("Spotify", "iTunes", "Deezer"):
                            score += 0.5
                        results.append((c, a, prov_name, score))
                        if score > best_score:
                            best_score = score
                            best_res   = (c, a, prov_name, score)
                except Exception as e:
                    logging.debug(f"[search_cover_parallel] {prov_name} error: {e}")
            return best_res, best_score

        best, score = eval_results(done)

        reason = "all_done"
        if not_done:
            if score >= EARLY_STOP_SCORE:
                reason = "early_stop"
            else:
                rem_time = TOTAL_DEADLINE_S - (time.time() - start_time)
                if rem_time > 0:
                    done2, not_done2 = wait(not_done, timeout=rem_time, return_when=FIRST_COMPLETED)
                    best2, score2 = eval_results(done2)
                    if score2 > score:
                        best, score = best2, score2
                    if not_done2: reason = "timeout"
                else:
                    reason = "fast_deadline"

    ms_taken = int((time.time() - start_time) * 1000)
    done_count = len(providers) - len(not_done) if reason != "timeout" else len(providers) - len(not_done) # Approssimativo se timeout

    if best:
        c, a, p, s = best
        logging.info(f"[search_cover_parallel] END attempt={attempt} reason={reason} done={done_count}/{len(providers)} ms={ms_taken} best_score={s:.1f} album='{a}' provider={p} uuid={uuid_}")
        logging.info(f"[search_cover_parallel] ✅ Album chosen: '{a}' provider={p} (weighted votes [{s:.1f}])")
        return c, p, s
    else:
        logging.info(f"[search_cover_parallel] END attempt={attempt} reason={reason} done={done_count}/{len(providers)} ms={ms_taken} best_score=0.0 album='None' provider=None uuid={uuid_}")
        logging.info(f"[search_cover_parallel] ❌ No cover found uuid={uuid_}")
        return None, None, 0.0

@logging_lru_cache(maxsize=256)
def resolve_cover_cached(artist, title, stream_url=None, station_name=None, uuid_=None):
    """
    1. Check Radio Paradise
    2. Try Attempt 1 (normalized strings)
    3. Try Attempt 2 (aggressive clean)
    """
    if stream_url and station_name:
        rp = search_radio_paradise(station_name, artist, title)
        if rp: return rp, "RadioParadise", 10.0

    a_1 = normalize_for_search(artist)
    t_1 = normalize_for_search(title)
    logging.info(f"[worker] 🔍 ATTEMPT 1: '{a_1}' - '{t_1}' uuid={uuid_}")
    c1, p1, s1 = search_cover_parallel(a_1, t_1, attempt=1, uuid_=uuid_)
    if c1 and s1 >= 1.0:
        logging.info(f"[worker] ✅ Attempt 1 accepted score={s1:.1f} provider={p1} uuid={uuid_}")
        return c1, p1, s1
    elif c1:
        logging.info(f"[worker] ⚠️ Attempt 1 score too low ({s1:.1f}), discarding uuid={uuid_}")

    a_2 = clean_artist_name(artist)
    t_2 = normalize_title(title, artist)
    logging.info(f"[worker] 🔄 ATTEMPT 2: '{a_2}' - '{t_2}' uuid={uuid_}")
    c2, p2, s2 = search_cover_parallel(a_2, t_2, attempt=2, uuid_=uuid_)
    if c2:
        logging.info(f"[worker] ✅ Attempt 2 accepted score={s2:.1f} provider={p2} uuid={uuid_}")
        return c2, p2, s2

    logging.info(f"[worker] ❌ No cover after 2 attempts uuid={uuid_}")
    return None, None, 0.0

# ================= BACKGROUND WORKER =================
class BackgroundWorker(Thread):
    def __init__(self, q):
        super().__init__()
        self.q = q
        self.daemon = True

    def run(self):
        logging.info("[worker] 🟢 BackgroundWorker started")
        while not _shutdown_event.is_set():
            try:
                task = self.q.get(timeout=1.0)
            except Empty:
                continue

            uuid_, artist, title, st_url, st_name = task
            logging.info(f"[worker] 🎵 Start uuid={uuid_}")

            # Check noise
            is_n, seg_type = is_noise(title, st_name)
            if is_n:
                if seg_type:
                    seg_url = get_segment_cover_url(seg_type)
                    if seg_url:
                        logging.info(f"[worker] 🟡 Noise Segment: {seg_type} → cover uuid={uuid_}")
                        publish_event("cover_updated", seg_url)
                        self.q.task_done()
                        continue
                
                logging.info(f"[worker] 🧹 Pure Noise detected — restoring logo uuid={uuid_}")
                restore_logo(st_url, st_name)
                self.q.task_done()
                continue

            cover_url, prov, score = resolve_cover_cached(artist, title, st_url, st_name, uuid_=uuid_)

            if cover_url:
                logging.info(f"[worker] 🟩 COVER APPLIED uuid={uuid_} Station='{st_name}' Artist='{artist}' Title='{artist} - {title}' provider={prov}")
                publish_event("cover_updated", cover_url)
            else:
                logging.info(f"[worker] ♻️ No cover — logo restored uuid={uuid_}")
                restore_logo(st_url, st_name)

            self.q.task_done()

# ================= SSE PUBLISHER =================
def publish_event(event_type, cover_url):
    global _last_cover_event
    with _last_cover_lock:
        if event_type == "logo_restored" and _last_cover_event and _last_cover_event["event"] == "logo_restored":
            if _last_cover_event["url"] == cover_url:
                return  # Skip duplicate logo restores
        
        # Add timestamp to force image refresh on client if needed
        ts_url = f"{cover_url}{'&' if '?' in cover_url else '?'}t={int(time.time()*1000)}"
        _last_cover_event = {"event": event_type, "url": ts_url}
        data = json.dumps(_last_cover_event)
        
    logging.info(f"[publish_event] {event_type} → {ts_url}")
    
    with _sub_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(f"data: {data}\n\n")
            except Exception:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)

def clear_last_cover_event():
    global _last_cover_event
    with _last_cover_lock:
        _last_cover_event = None
    logging.info("[clear_last_cover_event] 🧹 Last cover event cleared")

def restore_logo(st_url, st_name):
    logo = get_logo_from_db(st_url) if st_url else None
    if logo:
        target = f"/imagesw/radio-logos/{quote(os.path.basename(logo))}"
        publish_event("logo_restored", target)
    else:
        publish_event("logo_restored", "/images/default-cover-v6.svg")

# ================= HTTP SERVER (SSE) =================
class SSEHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/client-log':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8', errors='replace')
            try:
                import json
                log_data = json.loads(post_data)
                msg = log_data.get('message', 'No message')
                logging.error(f"[KIOSK ERROR] {msg}")
                # Also write to a dedicated file
                with open("/var/log/radio-kiosk-crash.log", "a", encoding="utf-8") as lf:
                    lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [KIOSK] {msg}\n")
            except Exception as e:
                logging.error(f"[KIOSK ERROR] Failed to parse log: {e} - Data: {post_data}")
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path != '/cover-events':
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        q = Queue(maxsize=10)
        with _sub_lock:
            _subscribers.append(q)

        # Send last event immediately
        with _last_cover_lock:
            if _last_cover_event:
                try:
                    init_data = json.dumps(_last_cover_event)
                    self.wfile.write(f"data: {init_data}\n\n".encode('utf-8'))
                    self.wfile.flush()
                    logging.info(f"[SSEHandler] 🔄 Replay last event to new client: {init_data}")
                except Exception:
                    pass

        try:
            while not _shutdown_event.is_set():
                try:
                    msg = q.get(timeout=2.0)
                    self.wfile.write(msg.encode('utf-8'))
                    self.wfile.flush()
                except Empty:
                    # Keep-alive ping
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _sub_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def run_sse_server():
    server = ThreadedHTTPServer(('127.0.0.1', 5000), SSEHandler)
    logging.info("[SSE] 🟢 Server listening on 127.0.0.1:5000/cover-events")
    while not _shutdown_event.is_set():
        server.handle_request()

# ================= MPD LISTENER =================
def fetch_mpd_status():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(('127.0.0.1', 6600))
        res = s.recv(1024).decode()
        if not res.startswith("OK MPD"):
            return None
        
        s.sendall(b"status\n")
        status_data = {}
        while True:
            line = s.recv(1024).decode()
            for l in line.split('\n'):
                if l.startswith("OK"): break
                if ": " in l:
                    k, v = l.split(": ", 1)
                    status_data[k] = v.strip()
            if "OK\n" in line: break

        s.sendall(b"currentsong\n")
        song_data = {}
        while True:
            line = s.recv(1024).decode()
            for l in line.split('\n'):
                if l.startswith("OK"): break
                if ": " in l:
                    k, v = l.split(": ", 1)
                    if k in song_data: song_data[k] += f" ~ {v.strip()}"
                    else: song_data[k] = v.strip()
            if "OK\n" in line: break
            
        s.close()
        
        return {
            "state": status_data.get("state"),
            "file": song_data.get("file", ""),
            "Name": song_data.get("Name", ""),
            "Title": song_data.get("Title", song_data.get("Name", "")),
            "Artist": song_data.get("Artist", "")
        }
    except Exception as e:
        logging.error(f"[fetch_mpd_status] MPD socket error: {e}")
        return None

def listen_events(task_queue):
    import subprocess
    logging.info("[listen_events] 🟢 MPD Idle listener started")
    
    last_id = None
    debounce_timer = None
    
    while not _shutdown_event.is_set():
        try:
            # Block until MPD event
            p = subprocess.Popen(["mpc", "idle", "player"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while p.poll() is None and not _shutdown_event.is_set():
                time.sleep(0.5)
            
            if _shutdown_event.is_set():
                p.terminate()
                break
                
            status = fetch_mpd_status()
            if not status: continue
            
            state = status.get("state")
            file_url = status.get("file", "")
            st_name = status.get("Name", "")
            title = status.get("Title", "")
            artist = status.get("Artist", "")
            
            if state != "play":
                continue
                
            if not file_url.startswith("http"):
                logging.info("[listen_events] 🎵 Local music — skipping")
                clear_last_cover_event()
                continue
                
            if not artist and " - " in title:
                artist, title = split_artist_title(title)
                
            current_id = f"{st_name}|{artist}|{title}"
            if current_id == last_id:
                logging.info(f"[listen_events] ⚠️ Skipping repeated track: {artist} - {title}")
                continue
                
            last_id = current_id
            
            if st_name != getattr(listen_events, "last_station", None):
                logging.info(f"[listen_events] 🟩 Station: {getattr(listen_events, 'last_station', 'None')} → {st_name}")
                listen_events.last_station = st_name
                clear_last_cover_event()
                restore_logo(file_url, st_name)
            
            uuid_ = str(uuid.uuid4())
            
            if debounce_timer:
                debounce_timer.cancel()
                
            def push_task(u, a, t, f, sn):
                logging.info(f"[worker] 🎵 Station='{sn}' Artist='{a}' Title='{a} - {t}' uuid={u}")
                task_queue.put((u, a, t, f, sn))

            # Se cambio stazione (o prima volta), esegui subito
            if not hasattr(listen_events, "last_station_uuid") or getattr(listen_events, "last_station_uuid") != st_name:
                listen_events.last_station_uuid = st_name
                logging.info(f"[POST_SWITCH] RUN immediately: {artist} - {title}")
                from threading import Timer
                logging.info(f"[starter] ▶️ Worker started immediately uuid={uuid_}")
                push_task(uuid_, artist, title, file_url, st_name)
            else:
                from threading import Timer
                logging.info(f"[worker] ⏳ Debounce {DEBOUNCE_MS:.2f}s uuid={uuid_}")
                debounce_timer = Timer(DEBOUNCE_MS, push_task, args=[uuid_, artist, title, file_url, st_name])
                debounce_timer.start()
                
        except Exception as e:
            logging.error(f"[listen_events] Error: {e}")
            time.sleep(2)

# ================= HEALTH CHECK =================
def health_check_loop():
    logging.info("[health] 🟢 Health check started")
    while not _shutdown_event.is_set():
        time.sleep(HEALTH_CHECK_INTERVAL)
        if _shutdown_event.is_set(): break
        
        statuses = []
        for name in ["Spotify", "Deezer", "iTunes", "MusicBrainz", "LastFM", "Discogs", "TheAudioDB"]:
            if not PROVIDERS_LIST.get(name):
                continue
            res = False
            try:
                if name == "Spotify":
                    t = get_spotify_token()
                    res = bool(t)
                elif name == "Deezer":
                    r = requests.get("https://api.deezer.com/search?q=test", timeout=3)
                    res = r.ok
                elif name == "iTunes":
                    r = requests.get("https://itunes.apple.com/search?term=test", timeout=3)
                    res = r.ok
                elif name == "MusicBrainz":
                    r = requests.get("https://musicbrainz.org/ws/2/recording?query=test&fmt=json", timeout=3)
                    res = r.ok
                elif name == "LastFM":
                    if LASTFM_API_KEY:
                        r = requests.get(f"http://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key={LASTFM_API_KEY}&artist=cher&track=believe&format=json", timeout=3)
                        res = r.ok
                elif name == "Discogs":
                    if DISCOGS_TOKEN:
                        r = requests.get(f"https://api.discogs.com/database/search?q=test&token={DISCOGS_TOKEN}", timeout=3)
                        res = r.ok
                elif name == "TheAudioDB":
                    r = requests.get(f"https://www.theaudiodb.com/api/v1/json/{THEAUDIODB_API_KEY}/searchtrack.php?s=coldplay&t=yellow", timeout=3)
                    res = r.ok
            except Exception:
                pass
            
            icon = "✅" if res else "❌"
            status_name = "MusicB" if name == "MusicBrainz" else name
            statuses.append(f"{status_name} {icon}")
            
        logging.info(f"🩺 [{time.strftime('%d/%m %H:%M')}] " + " | ".join(statuses))

# ================= MAIN =================
def main():
    read_global()
    
    # Init segment mapping
    global SEGMENT_COVER_MAP
    SEGMENT_COVER_MAP = {
        SEGMENT_METEO:       SEGMENT_COVER_METEO,
        SEGMENT_TRAFFIC:     SEGMENT_COVER_TRAFFIC,
        SEGMENT_NEWS:        SEGMENT_COVER_NEWS,
        SEGMENT_ADVERTISING: SEGMENT_COVER_ADVERTISING
    }
    
    log_config_summary()

    task_queue = Queue()
    
    worker = BackgroundWorker(task_queue)
    worker.start()
    
    sse_thread = Thread(target=run_sse_server, daemon=True)
    sse_thread.start()
    
    health_thread = Thread(target=health_check_loop, daemon=True)
    health_thread.start()
    
    listen_events(task_queue)
    
if __name__ == "__main__":
    main()