#!/usr/bin/env python3
"""
generate.py — Unified Backdrop Generator
-----------------------------------------
Self-contained. No subprocesses. No external scripts called.

Credits:
  Rendering engine + Fanart logic   →  luckynumb3rs/stremio-perfect-setup (backdrop.py)
  MDBList fetch + adult filter       →  bramst0ne/prism-wallpapers (backdrop_T2_flat.py)
  Accent extraction                  →  luckynumb3rs/stremio-perfect-setup (accent.py)

What it does for each entry in backdrop-config.json:
  1. Resolve accent colour (manual → logo scan → label fallback → none)
  2. Fetch titles from TMDB sources (discover or direct endpoint)
  3. Fetch titles from MDBList (via imdb_id → /find → TMDB dict)
  4. Merge + deduplicate + adult-filter all results
  5. Download tile images (Fanart.tv preferred, TMDB fallback)
  6. Composite 1080p tilted landscape grid
  7. Apply gradient overlay (unless no_accent: true)
  8. Save directly as WebP — no .jpg written at all

Dependencies: pip install requests Pillow
"""

import colorsys
import io
import itertools
import json
import math
import os
import re
import shutil
import sys
import time
import random   
import numpy as np
from pathlib import Path
from urllib.parse import parse_qsl

import requests
from PIL import Image, ImageDraw, ImageFilter

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).resolve().parent
CONFIG_PATH  = SCRIPT_DIR / "backdrop-config.json"

TMDB_KEY     = os.environ.get("TMDB_API_KEY", "")
FANART_KEY   = os.environ.get("FANART_API_KEY", "")
MDBLIST_KEY  = os.environ.get("MDBLIST_API_KEY", "")

TMDB_BASE    = "https://api.themoviedb.org/3"
TMDB_IMG     = "https://image.tmdb.org/t/p"
FANART_BASE  = "https://webservice.fanart.tv/v3"
BACKDROP_SZ  = "w1280"

# ─────────────────────────────────────────────────────────────────────────────
# T2 GRID CONSTANTS & CAMERA SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

CARD_RADIUS = 9
TILE_W      = 372
TILE_H      = 210
GAP         = 9
ROWS        = 10
COLS        = 10

# T2 Flat Mode Layout & Panning
TILT_DEG    = 10      # T2 uses a counter-clockwise tilt
STAGGER     = 0.35     # T2 brick wall offset
FADE_LEFT   = 0.30     # Left side opacity (dim)
FADE_RIGHT  = 1.00     # Right side opacity (bright)
OFFSET_X    = 335      # Shift camera right
OFFSET_Y    = 100      # Shift camera down

# T2 Focal Point
FOCUS_X     = 0.5
FOCUS_Y     = 0.0

# T2 Depth of Field Settings
DOF_BLUR_MAX = 0.0     
DOF_FALLOFF  = 1.5     

FOCUS_PRESETS = {
    "center":       (0.50, 0.50),
    "center-right": (0.65, 0.45),
    "top-right":    (0.72, 0.28),
    "top-center":   (0.52, 0.30),
    "t2-default":   (FOCUS_X, FOCUS_Y)
}

# ─────────────────────────────────────────────────────────────────────────────
# ADULT CONTENT FILTER  (from backdrop_T2_flat.py)
# ─────────────────────────────────────────────────────────────────────────────

BLOCKED_KEYWORDS = [
    "hentai", "porn", "pornography", "erotica", "xxx",
    "av girl", "jav", "milf", "fetish", "bondage",
    "bdsm", "ecchi", "yaoi", "yuri",
    "uncensored", "creampie", "bukkake",
]

# Add TMDB IDs here to permanently hard-block specific titles
BLOCKED_IDS = {
    1241752,
    95897,
}


def _normalize_text(text):
    text = text.lower()
    text = re.sub(r"[_\-.]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_adult(item):
    """Return True if the item should be filtered out."""
    if item.get("id") in BLOCKED_IDS:
        return True
    if item.get("adult") is True:
        return True
    # Low-quality heuristic: obscure content with near-zero engagement
    if item.get("vote_count", 0) < 15 and item.get("popularity", 0) < 5:
        return True

    texts = [
        item.get("title", ""),
        item.get("name", ""),
        item.get("original_title", ""),
        item.get("original_name", ""),
        item.get("overview", ""),
    ]
    combined = " ".join(texts).lower()

    for word in BLOCKED_KEYWORDS:
        if word in combined:
            return True
        if re.search(r"\b" + re.escape(word) + r"\b", combined):
            return True

    # JAV-style codes
    for pattern in [r"\b[a-z]{2,5}-\d{2,5}\b", r"\bfc2\b", r"\b\d{6,}\b"]:
        if re.search(pattern, combined):
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# ACCENT COLOUR  (from accent.py — logic inlined, no subprocess)
# ─────────────────────────────────────────────────────────────────────────────

def _default_accent_for_label(label):
    """Deterministic vibrant colour derived from the label string."""
    seed = sum((i + 1) * ord(c) for i, c in enumerate(label or "Backdrop"))
    hue = (seed % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.88)
    return (int(r * 255), int(g * 255), int(b * 255))


def _scan_cover_color(path):
    """Extract dominant vibrant colour from a logo image."""
    image = Image.open(path).convert("RGBA")
    image.thumbnail((200, 200))
    scored = []
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a < 16:
                continue
            _, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            score = sat * (1 - abs(light - 0.55))
            if light < 0.12 or light > 0.9:
                score *= 0.2
            if sat < 0.12:
                score *= 0.2
            scored.append((score, (r, g, b)))

    if not scored:
        raise ValueError(f"No usable pixels in {path}")

    scored.sort(reverse=True)
    top = [rgb for _, rgb in scored[:max(1, len(scored) // 20)]]
    r = round(sum(c[0] for c in top) / len(top))
    g = round(sum(c[1] for c in top) / len(top))
    b = round(sum(c[2] for c in top) / len(top))

    hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    light = min(0.72, max(0.42, light))
    sat   = min(0.75, max(0.45, sat))
    nr, ng, nb = colorsys.hls_to_rgb(hue, light, sat)
    return (round(nr * 255), round(ng * 255), round(nb * 255))


def _parse_accent_color(value):
    """Parse 'R,G,B' or '#RRGGBB' string into an (R, G, B) tuple."""
    value = value.strip()
    if value.startswith("#"):
        v = value[1:]
        if len(v) != 6:
            raise ValueError(f"Bad hex accent: {value}")
        return tuple(int(v[i:i+2], 16) for i in (0, 2, 4))
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Bad accent: {value}. Use 'R,G,B' or '#RRGGBB'")
    rgb = tuple(int(p) for p in parts)
    if any(c < 0 or c > 255 for c in rgb):
        raise ValueError(f"Accent channels must be 0–255: {value}")
    return rgb


def resolve_accent(entry):
    """
    Return (R, G, B) tuple or None.
    Priority:
      1. no_accent: true  → None (skip gradient)
      2. accent_color set → parse and return
      3. logo exists      → scan image
      4. fallback         → generate from label
    """
    if entry.get("no_accent"):
        return None

    if entry.get("accent_color"):
        color = _parse_accent_color(entry["accent_color"])
        print(f"  🎨 Accent: manual {color}")
        return color

    logo = entry.get("logo", "")
    if logo:
        logo_path = Path(logo)
        if logo_path.is_file():
            try:
                color = _scan_cover_color(logo_path)
                print(f"  🎨 Accent: from logo → rgb{color}")
                return color
            except Exception as exc:
                print(f"  ⚠️  Logo scan failed ({exc}), falling back")
        else:
            print(f"  ⚠️  Logo not found: {logo}")

    label = entry.get("label", entry.get("name", "Backdrop"))
    color = _default_accent_for_label(label)
    print(f"  🎨 Accent: from label → rgb{color}")
    return color


# ─────────────────────────────────────────────────────────────────────────────
# TMDB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _tmdb_get(endpoint, params=None):
    p = dict(params or {})
    p["api_key"] = TMDB_KEY
    p.setdefault("include_adult", False)
    for attempt in range(3):
        try:
            r = requests.get(f"{TMDB_BASE}{endpoint}", params=p, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            if code is None or code < 500 or attempt == 2:
                raise
            time.sleep(1 + attempt)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return {}


def _parse_request_spec(spec):
    """
    Parse a source string into a spec dict.
    Formats:
      movie:sort_by=popularity.desc&with_watch_providers=8   → discover mode
      movie:/trending/movie/week?language=en-US              → endpoint mode
    """
    try:
        raw_type, raw_req = spec.split(":", 1)
    except ValueError:
        raise ValueError(f"Bad source spec '{spec}'. Use 'movie:...' or 'tv:...'")

    media_type = raw_type.strip()
    if media_type == "series":
        media_type = "tv"
    if media_type not in ("movie", "tv"):
        raise ValueError(f"Unknown media type '{media_type}' in spec '{spec}'")

    raw_req = raw_req.strip()
    if raw_req.startswith("/"):
        path, _, qs = raw_req.partition("?")
        params = dict(parse_qsl(qs, keep_blank_values=True))
        mode = "discover" if path.startswith("/discover/") else "endpoint"
        return {"mode": mode, "media_type": media_type, "path": path, "params": params}

    params = dict(parse_qsl(raw_req, keep_blank_values=True))
    return {"mode": "discover", "media_type": media_type, "params": params}


def _fetch_for_spec(spec, max_pages=3):
    """Fetch up to max_pages of results for one parsed spec."""
    items = []
    if spec["mode"] == "discover":
        endpoint = f"/discover/{spec['media_type']}"
        base = dict(spec["params"])
    else:
        endpoint = spec["path"]
        base = dict(spec.get("params", {}))

    for page in range(1, max_pages + 1):
        data = _tmdb_get(endpoint, {**base, "page": page})
        page_results = data.get("results", [])
        if not page_results:
            break
        for item in page_results:
            if not _is_adult(item) and item.get("backdrop_path"):
                items.append((spec["media_type"], item))
        if page >= (data.get("total_pages") or max_pages):
            break
    return items


def fetch_tmdb_titles(sources, count):
    """
    Fetch and interleave results from all TMDB source specs.
    Returns list of (media_type, tmdb_item) tuples, deduplicated, up to count.
    """
    specs = [_parse_request_spec(s) for s in sources]
    per_spec = [_fetch_for_spec(spec) for spec in specs]

    # Round-robin interleave so no single source dominates
    merged = []
    max_len = max((len(s) for s in per_spec), default=0)
    for i in range(max_len):
        for s in per_spec:
            if i < len(s):
                merged.append(s[i])

    seen = set()
    unique = []
    for kind, item in merged:
        key = (kind, item["id"])
        if key not in seen:
            seen.add(key)
            unique.append((kind, item))
            if len(unique) >= count:
                break
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# MDBLIST FETCH  (from backdrop_T2_flat.py)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_mdblist_url(url):
    url = url.strip().rstrip("/")
    m = re.search(r"mdblist\.com/lists/([^/]+)/([^/]+)$", url)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^([^/\s]+)/([^/\s]+)$", url)
    if m and "." not in url and ":" not in url:
        return m.group(1), m.group(2)
    raise ValueError(f"Cannot parse MDBList URL: {url!r}. Use 'username/slug'")


def fetch_mdblist_titles(mdblist_url, sort, count):
    """
    Fetch titles from a MDBList.
    Step 1: GET /lists/user/{username} → find list_id by slug
    Step 2: GET /lists/{list_id}/items → get items with imdb_id
    Step 3: For each item: GET /find/{imdb_id} → full TMDB dict
    Returns list of (media_type, tmdb_item) tuples.
    """
    if not MDBLIST_KEY:
        print("  ❌ MDBLIST_API_KEY not set — skipping MDBList")
        return []

    username, slug = _parse_mdblist_url(mdblist_url)
    key = {"apikey": MDBLIST_KEY}

    print(f"  📋 MDBList: fetching {username}/{slug}")
    try:
        r = requests.get(f"https://api.mdblist.com/lists/user/{username}", params=key, timeout=20)
        r.raise_for_status()
        user_lists = r.json()
    except Exception as exc:
        print(f"  ❌ MDBList user lists failed: {exc}")
        return []

    matched = next((l for l in user_lists if l.get("slug", "").lower() == slug.lower()), None)
    if not matched:
        print(f"  ❌ MDBList: list '{slug}' not found for user '{username}'")
        return []

    list_id = matched["id"]
    print(f"  📋 MDBList: found '{matched.get('name', slug)}' (id={list_id})")

    params = {**key}
    if sort:
        parts = sort.lower().split(".")
        params["sort"] = parts[0]
        params["order"] = parts[1] if len(parts) > 1 else "desc"
    # Only fetch what we need — count * 2 gives buffer for adult/missing filtering
    # without pulling the entire list (saves API quota, 1000 req/day limit)
    params["limit"] = count * 2

    try:
        r = requests.get(f"https://api.mdblist.com/lists/{list_id}/items", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  ❌ MDBList items fetch failed: {exc}")
        return []

    raw = data if isinstance(data, list) else data.get("movies", []) + data.get("shows", [])
    print(f"  📋 MDBList: {len(raw)} raw items")

    results = []
    for entry in raw[:count * 2]:
        imdb_id   = entry.get("imdb_id") or entry.get("imdb")
        mediatype = entry.get("mediatype", "")
        if not imdb_id:
            continue
        kind = "tv" if mediatype == "show" else "movie"
        try:
            find = _tmdb_get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
            hits = find.get("tv_results" if kind == "tv" else "movie_results", [])
            if not hits:
                continue
            tmdb_item = hits[0]
        except Exception:
            continue
        if _is_adult(tmdb_item):
            continue
        if not (tmdb_item.get("backdrop_path") or tmdb_item.get("poster_path")):
            continue
        results.append((kind, tmdb_item))
        if len(results) >= count:
            break

    print(f"  📋 MDBList: {len(results)} titles resolved via TMDB")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE DOWNLOAD + FANART  (from backdrop.py — full 4-tier priority)
# ─────────────────────────────────────────────────────────────────────────────

def _download_url(url, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception as exc:
            if attempt == retries:
                print(f"    ! Download failed {url}: {exc}")
                return None
            time.sleep(1)


def _normalize_lang(v):
    if v is None:
        return None
    v = str(v).strip().lower()
    return None if v in {"", "00", "none", "null"} else v


def _pick_fanart_url(fanart_data, kind, preferred_lang, original_lang):
    """
    4-tier Fanart selection (from backdrop.py):
      1. preferred language
      2. original title language
      3. textless (no language)
      4. any other non-empty language
    """
    if not fanart_data:
        return None, None

    pref = _normalize_lang(preferred_lang)
    orig = _normalize_lang(original_lang)

    if kind == "tv":
        groups = [("thumb", fanart_data.get("tvthumb") or []),
                  ("bg",    fanart_data.get("showbackground") or [])]
    else:
        groups = [("thumb", fanart_data.get("moviethumb") or []),
                  ("bg",    fanart_data.get("moviebackground") or [])]

    buckets = {"preferred": [], "original": [], "textless": [], "other": []}

    for group_rank, (_, candidates) in enumerate(groups):
        for candidate in candidates:
            lang = _normalize_lang(candidate.get("lang"))
            entry = {"c": candidate, "gr": group_rank}
            if pref and lang == pref:
                buckets["preferred"].append(entry)
            elif orig and lang == orig:
                buckets["original"].append(entry)
            elif lang is None:
                buckets["textless"].append(entry)
            elif lang:
                buckets["other"].append(entry)

    for bucket in ("preferred", "original", "textless", "other"):
        if buckets[bucket]:
            best = sorted(buckets[bucket],
                          key=lambda e: (e["gr"], -int(e["c"].get("likes", 0))))[0]["c"]
            if best.get("url"):
                return best["url"], bucket

    return None, None

def _pick_fanart_urls_multi(fanart_data, kind, preferred_lang, original_lang, max_urls=10):
    """Return up to max_urls ranked fanart URLs for a single title."""
    if not fanart_data:
        return []

    pref = _normalize_lang(preferred_lang)
    orig = _normalize_lang(original_lang)

    if kind == "tv":
        groups = [fanart_data.get("tvthumb") or [],
                  fanart_data.get("showbackground") or []]
    else:
        groups = [fanart_data.get("moviethumb") or [],
                  fanart_data.get("moviebackground") or []]

    buckets = {"preferred": [], "original": [], "textless": [], "other": []}

    for group_rank, candidates in enumerate(groups):
        for candidate in candidates:
            lang = _normalize_lang(candidate.get("lang"))
            entry = {"c": candidate, "gr": group_rank}
            if pref and lang == pref:
                buckets["preferred"].append(entry)
            elif orig and lang == orig:
                buckets["original"].append(entry)
            elif lang is None:
                buckets["textless"].append(entry)
            elif lang:
                buckets["other"].append(entry)

    urls = []
    for bucket in ("preferred", "original", "textless", "other"):
        ranked = sorted(buckets[bucket],
                        key=lambda e: (e["gr"], -int(e["c"].get("likes", 0))))
        for entry in ranked:
            url = entry["c"].get("url")
            if url and url not in urls:
                urls.append(url)
            if len(urls) >= max_urls:
                return urls
    return urls

def _fanart_tv(tvdb_id):
    try:
        r = requests.get(f"{FANART_BASE}/tv/{tvdb_id}",
                         params={"api_key": FANART_KEY}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _fanart_movie(tmdb_id):
    try:
        r = requests.get(f"{FANART_BASE}/movies/{tmdb_id}",
                         params={"api_key": FANART_KEY}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_tile_image(kind, item, use_fanart, preferred_lang="en"):
    """
    Download thumbnail for one title.
    Returns (PIL Image, source_label) or (None, "missing").
    """
    tmdb_id   = item["id"]
    orig_lang = item.get("original_language")

    preferred_url  = None
    textless_url   = None
    last_resort_url = None

    if use_fanart and FANART_KEY:
        if kind == "tv":
            ext = {}
            try:
                ext = _tmdb_get(f"/tv/{tmdb_id}/external_ids")
            except Exception:
                pass
            tvdb_id = ext.get("tvdb_id")
            if tvdb_id:
                url, bucket = _pick_fanart_url(
                    _fanart_tv(tvdb_id), "tv", preferred_lang, orig_lang)
                if bucket == "other":
                    last_resort_url = url
                elif bucket == "textless":
                    textless_url = url
                else:
                    preferred_url = url
        else:
            url, bucket = _pick_fanart_url(
                _fanart_movie(tmdb_id), "movie", preferred_lang, orig_lang)
            if bucket == "other":
                last_resort_url = url
            elif bucket == "textless":
                textless_url = url
            else:
                preferred_url = url

    # Priority: fanart preferred → TMDB backdrop → fanart textless → fanart last resort
    if preferred_url:
        img = _download_url(preferred_url)
        if img:
            return img, "fanart"

    if item.get("backdrop_path"):
        img = _download_url(f"{TMDB_IMG}/{BACKDROP_SZ}{item['backdrop_path']}")
        if img:
            return img, "tmdb"

    if textless_url:
        img = _download_url(textless_url)
        if img:
            return img, "fanart_textless"

    if last_resort_url:
        img = _download_url(last_resort_url)
        if img:
            return img, "fanart_other"

    return None, "missing"


# ─────────────────────────────────────────────────────────────────────────────
# GRID COMPOSITING  (from backdrop.py — unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _rounded_mask(w, h, radius=CARD_RADIUS):
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask


def _make_tile(image, tw, th, opacity=1.0):
    sw, sh = image.size
    tr = tw / th
    sr = sw / sh
    if sr > tr:
        nw = int(sh * tr)
        image = image.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
    else:
        nh = int(sw / tr)
        image = image.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
    image = image.resize((tw, th), Image.LANCZOS)
    r = max(8, int(CARD_RADIUS * tw / TILE_W))
    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    result.paste(image, mask=_rounded_mask(tw, th, radius=r))
    
    # Apply T2 Opacity Fading
    if opacity < 1.0:
        rc, gc, bc, ac = result.split()
        ac = ac.point(lambda v: int(v * opacity))
        result = Image.merge("RGBA", (rc, gc, bc, ac))
        
    return result


def _ensure_min_tiles(tiles, minimum=12):
    if len(tiles) >= minimum or not tiles:
        return tiles
    padded = list(tiles)
    for tile in itertools.cycle(tiles):
        if len(padded) >= minimum:
            break
        padded.append(tile.copy())
    return padded
    
def _apply_dof(image, focus_x, focus_y):
    """Applies a cinematic DSLR lens blur based on distance from the focal point."""
    if DOF_BLUR_MAX <= 0:
        return image

    w, h = image.size
    fx = focus_x * w
    fy = focus_y * h
    diag = math.hypot(w, h)

    xs = np.linspace(0, w - 1, w, dtype=np.float32)
    ys = np.linspace(0, h - 1, h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    
    dist_map = np.sqrt((xg - fx)**2 + (yg - fy)**2) / diag
    blur_map = np.clip(dist_map ** DOF_FALLOFF, 0.0, 1.0)

    N = 5
    max_r = DOF_BLUR_MAX
    layers = [image if (i / N) * max_r < 0.5 else
              image.filter(ImageFilter.GaussianBlur(radius=(i / N) * max_r))
              for i in range(N + 1)]

    arrs = [np.array(l, dtype=np.float32) for l in layers]
    out = np.zeros_like(arrs[0])

    for i in range(N):
        lo = i / N
        hi = (i + 1) / N
        in_ = (blur_map >= lo) & (blur_map < hi)
        t = ((blur_map - lo) / (hi - lo + 1e-9))[in_]
        out[in_] = arrs[i][in_] * (1 - t[:, None]) + arrs[i+1][in_] * t[:, None]

    out[blur_map >= (N - 1) / N] = arrs[N][blur_map >= (N - 1) / N]

    return Image.fromarray(out.clip(0, 255).astype(np.uint8), image.mode)


def build_grid(tiles, canvas_w, canvas_h, scale=1.0, focus_x=None, focus_y=None):
    fx = FOCUS_X if focus_x is None else focus_x
    fy = FOCUS_Y if focus_y is None else focus_y

    tw  = int(TILE_W * scale)
    th  = int(TILE_H * scale)
    gap = int(GAP * scale)

    # T2 Logic: Massive Buffer to prevent edge clipping
    cols = COLS + 10
    rows = ROWS + 10
    needed = rows * cols

    # T2 Logic: Core + Shuffled Edges to break the repeating pattern
    tile_list = list(tiles) 
    while len(tile_list) < needed:
        chunk = list(tiles)
        random.shuffle(chunk)
        tile_list.extend(chunk)
        
    tile_list = tile_list[:needed]

    stagger_px = int(STAGGER * (tw + gap))
    grid_w = cols * (tw + gap) + rows * stagger_px
    grid_h = rows * (th + gap)
    grid   = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))

    focal_x   = fx * grid_w
    focal_y   = fy * grid_h
    focal_row = max(0, min(rows - 1, int(focal_y / (th + gap))))
    focal_col = max(0, min(cols - 1, int((focal_x - focal_row * stagger_px) / (tw + gap))))

    cells = [(r, c) for r in range(rows) for c in range(cols)]
    # Sort by distance so the unshuffled core titles land in the focal zone
    cells.sort(key=lambda pos: abs(pos[0] - focal_row) + abs(pos[1] - focal_col))

    for idx, (row, col) in enumerate(cells):
        if idx >= len(tile_list):
            break
        x = row * stagger_px + col * (tw + gap)
        y = row * (th + gap)

        # FIX: Calculate fade relative to the focal point, not the massive off-screen buffer
        col_offset = col - focal_col
        depth = max(0.0, min(1.0, (col_offset + 5) / 5.0)) 
        opacity = FADE_LEFT + (FADE_RIGHT - FADE_LEFT) * depth

        tile = _make_tile(tile_list[idx], tw, th, opacity=opacity)
        grid.paste(tile, (x, y), tile)

    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rw, rh  = rotated.size

    angle_rad  = math.radians(-TILT_DEG)
    pcx = fx * grid_w - grid_w / 2
    pcy = fy * grid_h - grid_h / 2
    rcx = pcx * math.cos(angle_rad) - pcy * math.sin(angle_rad)
    rcy = pcx * math.sin(angle_rad) + pcy * math.cos(angle_rad)

    # FIX: Removed the manual T2 OFFSET_X and OFFSET_Y. 
    # The trigonometry above already perfectly centers the camera!
    paste_x = int(canvas_w / 2 - (rw / 2 + rcx))
    paste_y = int(canvas_h / 2 - (rh / 2 + rcy))

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (10, 10, 12, 255))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

# ─────────────────────────────────────────────────────────────────────────────
# GRADIENT OVERLAY (NumPy Vectorized Edition)
# ─────────────────────────────────────────────────────────────────────────────

def apply_gradient(canvas, accent, shadow_only=False):
    """UI gradient: extremely fast NumPy vectorized shadows and glows."""
    w, h = canvas.size
    
    # 1. Generate a lightning-fast mathematical grid of the entire screen
    xs = np.linspace(0, w - 1, w, dtype=np.float32)
    ys = np.linspace(0, h - 1, h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    diag = math.hypot(w, h)

    def _create_layer(r, g, b, alpha_matrix):
        """Converts a 2D NumPy alpha matrix into a PIL RGBA image."""
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[..., 0] = r
        arr[..., 1] = g
        arr[..., 2] = b
        arr[..., 3] = alpha_matrix.astype(np.uint8)
        return Image.fromarray(arr, 'RGBA')

    # 2. Left Shadow (Stops at 60%, Curve 1.2)
    mix_left = np.clip(1.0 - xg / (w * 0.60), 0.0, 1.0)
    alpha_left = np.clip(220 * (mix_left ** 1.2), 0, 255)
    left_img = _create_layer(6, 6, 8, alpha_left)

    # 3. Bottom Shadow (Starts at 40%, Curve 1.2)
    mix_bottom = np.clip((yg - h * 0.40) / (h * 0.60), 0.0, 1.0)
    alpha_bottom = np.clip(220 * (mix_bottom ** 1.2), 0, 255)
    bottom_img = _create_layer(6, 6, 8, alpha_bottom)

    # 4. Bottom-Left Radial Corner (Spreads 75%, Curve 1.8)
    dist_bl = np.hypot(xg, h - yg)
    mix_bl = np.clip(1.0 - (dist_bl / diag) / 0.75, 0.0, 1.0)
    alpha_bl = np.clip(255 * (mix_bl ** 1.8), 0, 255)
    bl_img = _create_layer(6, 6, 8, alpha_bl)

    # Composite the dark shadows
    result = Image.alpha_composite(canvas, bl_img)
    result = Image.alpha_composite(result, left_img)
    result = Image.alpha_composite(result, bottom_img)

    # 5. Top-Right Accent Glow (Spreads 90%, Curve 1.4)
    if not shadow_only and accent:
        ar, ag, ab = accent
        dist_tr = np.hypot(w - xg, yg)
        mix_tr = np.clip(1.0 - (dist_tr / diag) / 0.40, 0.0, 1.0)
        # Note: I kept your custom tweak of 100 here!
        alpha_tr = np.clip(55 * (mix_tr ** 1.4), 0, 255)
        tr_img = _create_layer(ar, ag, ab, alpha_tr)
        
        # Apply a Gaussian blur to the color layer to make the light diffuse naturally
        tr_img = tr_img.filter(ImageFilter.GaussianBlur(radius=max(28, w // 64)))
        result = Image.alpha_composite(result, tr_img)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# FOCUS PARSING
# ─────────────────────────────────────────────────────────────────────────────

def parse_focus(value):
    if not value:
        return FOCUS_X, FOCUS_Y
    if value in FOCUS_PRESETS:
        return FOCUS_PRESETS[value]
    try:
        rx, ry = value.split(",", 1)
        return float(rx), float(ry)
    except Exception:
        raise ValueError(
            f"Bad focus '{value}'. Use a preset ({', '.join(FOCUS_PRESETS)}) or 'x,y'")


# ─────────────────────────────────────────────────────────────────────────────
# PER-ENTRY GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_entry(entry, index, total):
    name   = entry.get("name", f"entry_{index}")
    label  = entry.get("label", name)
    output = entry.get("output")
    count  = int(entry.get("count", 60))
    fanart = entry.get("fanart", True)
    sort   = entry.get("sort", "score.desc")
    sources     = entry.get("sources", [])
    mdblist_url = entry.get("mdblist_url", "")

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {label}")
    print(f"{'='*60}")

    if not output:
        print(f"  ❌ No 'output' defined — skipping")
        return False

    # ── Accent & Shadows ──────────────────────────────────────────────────────
    no_gradient = entry.get("no_accent", False)
    shadow_only = entry.get("shadow_only", False)

    accent = None
    if not no_gradient:
        if shadow_only:
            print("  🌑 shadow_only: true — applying dark UI shadows without color glow")
            accent = (0, 0, 0) # Dummy color, won't be used
        else:
            accent = resolve_accent(entry)
    else:
        print("  🚫 no_accent: true — all shadows and gradients will be skipped")

    # ── Focus ─────────────────────────────────────────────────────────────────
    try:
        fx, fy = parse_focus(entry.get("focus", "center-right"))
    except ValueError as exc:
        print(f"  ⚠️  {exc} — using center-right")
        fx, fy = FOCUS_PRESETS["center-right"]

    # ── Fetch titles ──────────────────────────────────────────────────────────
    tmdb_titles   = []
    mdblist_titles = []

    if sources:
        print(f"  🔍 Fetching TMDB ({len(sources)} source(s))…")
        try:
            tmdb_titles = fetch_tmdb_titles(sources, count)
            print(f"  ✅ TMDB: {len(tmdb_titles)} titles")
        except Exception as exc:
            print(f"  ❌ TMDB fetch failed: {exc}")

    if mdblist_url:
        # Normalize to list — supports both single string and array
        mdb_urls = mdblist_url if isinstance(mdblist_url, list) else [mdblist_url]
        print(f"  🔍 Fetching MDBList ({len(mdb_urls)} list(s))…")
        per_list = []
        per_count = max(1, math.ceil(count / len(mdb_urls)))  # e.g. ceil(60/2)=30, ceil(50/3)=17
        for mdb_url in mdb_urls:
            try:
                results = fetch_mdblist_titles(mdb_url, sort, per_count)  # ← per_count
                per_list.append(results)
            except Exception as exc:
                print(f"  ❌ MDBList fetch failed ({mdb_url}): {exc}")

        if per_list:
            max_len = max(len(l) for l in per_list)
            for i in range(max_len):
                for lst in per_list:
                    if i < len(lst):
                        mdblist_titles.append(lst[i])
    if not tmdb_titles and not mdblist_titles:
        print(f"  ❌ No titles found — skipping {name}")
        return False

    # ── Merge: round-robin interleave → deduplicate → trim ───────────────────
    all_titles = []
    max_len = max(len(tmdb_titles), len(mdblist_titles))
    for i in range(max_len):
        if i < len(tmdb_titles):
            all_titles.append(tmdb_titles[i])
        if i < len(mdblist_titles):
            all_titles.append(mdblist_titles[i])

    seen = set()
    merged = []
    for kind, item in all_titles:
        key = (kind, item["id"])
        if key not in seen:
            seen.add(key)
            merged.append((kind, item))
            if len(merged) >= count:
                break

    print(f"  📦 Merged: {len(merged)} unique titles")

    # ── Download images ───────────────────────────────────────────────────────
    print(f"  🖼️  Downloading images…")
    tiles = []
    fanart_hits = tmdb_hits = skip = 0
    fanart_cache = {}   # (kind, tmdb_id) → list of all fanart URLs
    used_urls    = set()

    for i, (kind, item) in enumerate(merged, 1):
        title = item.get("title") or item.get("name", "?")
        sys.stdout.write(f"  [{i:02d}/{len(merged)}] {title[:50]:<50}\r")
        sys.stdout.flush()

        tmdb_id   = item["id"]
        orig_lang = item.get("original_language")
        cache_key = (kind, tmdb_id)

        if fanart and FANART_KEY and cache_key not in fanart_cache:
            if kind == "tv":
                ext = {}
                try:
                    ext = _tmdb_get(f"/tv/{tmdb_id}/external_ids")
                except Exception:
                    pass
                tvdb_id = ext.get("tvdb_id")
                fd = _fanart_tv(tvdb_id) if tvdb_id else None
            else:
                fd = _fanart_movie(tmdb_id)
            fanart_cache[cache_key] = _pick_fanart_urls_multi(
                fd, kind, "en", orig_lang, max_urls=10)

        img = None
        for url in fanart_cache.get(cache_key, []):
            if url not in used_urls:
                img = _download_url(url)
                if img:
                    used_urls.add(url)
                    fanart_hits += 1
                    break

        if img is None and item.get("backdrop_path"):
            img = _download_url(f"{TMDB_IMG}/{BACKDROP_SZ}{item['backdrop_path']}")
            if img:
                tmdb_hits += 1

        if img:
            tiles.append(img)
        else:
            skip += 1

        time.sleep(0.2)
        
    sys.stdout.write("\n")

    if FANART_KEY and fanart:
        print(f"  🖼️  {len(tiles)} images: "
              f"{fanart_hits} fanart, {tmdb_hits} TMDB, {skip} skipped")
    else:
        print(f"  🖼️  {len(tiles)} images ({tmdb_hits} TMDB, {skip} skipped)")

    if not tiles:
        print(f"  ❌ No images downloaded — skipping {name}")
        return False

    # ── Pad with extra fanart images if tiles < count ─────────────────────────
    if len(tiles) < count and fanart_cache:
        needed = count - len(tiles)
        print(f"  🔁 {len(tiles)} tiles, fetching extra fanart to reach {count}…")
        exhausted = False
        while needed > 0 and not exhausted:
            exhausted = True
            for pad_kind, pad_item in merged:
                for url in fanart_cache.get((pad_kind, pad_item["id"]), []):
                    if url not in used_urls:
                        exhausted = False
                        img = _download_url(url)
                        if img:
                            used_urls.add(url)
                            tiles.append(img)
                            needed -= 1
                        if needed <= 0:
                            break
                if needed <= 0:
                    break
        if needed > 0:
            print(f"  ⚠️  Fanart exhausted — {len(tiles)} tiles available")

    # ── Ensure minimum tile count ─────────────────────────────────────────────
    tiles = _ensure_min_tiles(tiles, minimum=12)
    
    # ── Composite 1080p ───────────────────────────────────────────────────────
    print(f"  🎨 Compositing 1920×1080…")
    canvas = build_grid(tiles, 1920, 1080, scale=1.0, focus_x=fx, focus_y=fy)

    print(f"  📷 Applying Depth of Field blur…")
    canvas = _apply_dof(canvas, fx, fy)

    if not no_gradient:
        canvas = apply_gradient(canvas, accent, shadow_only=shadow_only)

    # ── Save as WebP directly (no .jpg intermediate) ──────────────────────────
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    final = canvas.convert("RGB")
    final.save(str(out_path), "WEBP", quality=82, method=6)

    size_kb = out_path.stat().st_size // 1024
    print(f"  ✅ Saved: {output} ({size_kb} KB)")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)


def main():
    if not TMDB_KEY:
        print("❌ TMDB_API_KEY environment variable not set")
        sys.exit(1)

    if not CONFIG_PATH.exists():
        print(f"❌ Config not found: {CONFIG_PATH}")
        sys.exit(1)

    entries = json.loads(CONFIG_PATH.read_text())
    total   = len(entries)
    success = 0
    failed  = []

    print(f"\n🎬 Backdrop Generator — {total} entries")
    print(f"   TMDB key:    {'✅ set' if TMDB_KEY else '❌ missing'}")
    print(f"   Fanart key:  {'✅ set' if FANART_KEY else '⚠️  not set (TMDB artwork only)'}")
    print(f"   MDBList key: {'✅ set' if MDBLIST_KEY else '⚠️  not set (MDBList entries skipped)'}")

    for i, entry in enumerate(entries, 1):
        ok = generate_entry(entry, i, total)
        if ok:
            success += 1
        else:
            failed.append(entry.get("name", f"entry_{i}"))

    print(f"\n{'='*60}")
    print(f"DONE — {success}/{total} backdrops generated")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()
