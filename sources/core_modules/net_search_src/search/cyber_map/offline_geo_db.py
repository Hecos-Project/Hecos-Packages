"""
search/cyber_map/offline_geo_db.py
Zero-external-request local geographic database for hosts, ccTLDs, known platforms,
infrastructure mirrors, and Tor .onion orbital coordinates.
Ensures 100% Privacy Shield (LOCAL ONLY) compliance and instant fallback resolution.
"""
from __future__ import annotations

import hashlib
import math
from typing import Dict, Optional, Tuple, Any

# (lat, lon, country_name, city)
COUNTRY_CENTROIDS: Dict[str, Tuple[float, float, str, str]] = {
    "US": (39.8283, -98.5795, "United States", "Ashburn/Central"),
    "CA": (56.1304, -106.3468, "Canada", "Toronto/Central"),
    "MX": (23.6345, -102.5528, "Mexico", "Mexico City"),
    "BR": (-14.2350, -51.9253, "Brazil", "Sao Paulo"),
    "AR": (-38.4161, -63.6167, "Argentina", "Buenos Aires"),
    "CL": (-35.6751, -71.5430, "Chile", "Santiago"),
    "CO": (4.5709, -74.2973, "Colombia", "Bogota"),
    "PE": (-9.1900, -75.0152, "Peru", "Lima"),
    "VE": (6.4238, -66.5897, "Venezuela", "Caracas"),
    "GB": (53.4808, -2.2426, "United Kingdom", "London/Manchester"),
    "UK": (53.4808, -2.2426, "United Kingdom", "London"),
    "IE": (53.1424, -7.6921, "Ireland", "Dublin"),
    "FR": (46.2276, 2.2137, "France", "Paris"),
    "DE": (51.1657, 10.4515, "Germany", "Frankfurt"),
    "NL": (52.1326, 5.2913, "Netherlands", "Amsterdam"),
    "BE": (50.8503, 4.3517, "Belgium", "Brussels"),
    "LU": (49.8153, 6.1296, "Luxembourg", "Luxembourg"),
    "CH": (46.8182, 8.2275, "Switzerland", "Zurich"),
    "IT": (41.8719, 12.5674, "Italy", "Rome/Milan"),
    "ES": (40.4637, -3.7492, "Spain", "Madrid"),
    "PT": (39.3999, -8.2245, "Portugal", "Lisbon"),
    "AT": (47.5162, 14.5501, "Austria", "Vienna"),
    "PL": (51.9194, 19.1451, "Poland", "Warsaw"),
    "CZ": (49.8175, 15.4730, "Czechia", "Prague"),
    "SK": (48.6690, 19.6990, "Slovakia", "Bratislava"),
    "HU": (47.1625, 19.5033, "Hungary", "Budapest"),
    "RO": (45.9432, 24.9668, "Romania", "Bucharest"),
    "BG": (42.7339, 25.4858, "Bulgaria", "Sofia"),
    "GR": (39.0742, 21.8243, "Greece", "Athens"),
    "HR": (45.1000, 15.2000, "Croatia", "Zagreb"),
    "SI": (46.1512, 14.9955, "Slovenia", "Ljubljana"),
    "RS": (44.0165, 21.0059, "Serbia", "Belgrade"),
    "DK": (56.2639, 9.5018, "Denmark", "Copenhagen"),
    "NO": (60.4720, 8.4689, "Norway", "Oslo"),
    "SE": (60.1282, 18.6435, "Sweden", "Stockholm"),
    "FI": (61.9241, 25.7482, "Finland", "Helsinki"),
    "IS": (64.9631, -19.0208, "Iceland", "Reykjavik"),
    "EE": (58.5953, 25.0136, "Estonia", "Tallinn"),
    "LV": (56.8796, 24.6032, "Latvia", "Riga"),
    "LT": (55.1694, 23.8813, "Lithuania", "Vilnius"),
    "UA": (48.3794, 31.1656, "Ukraine", "Kyiv"),
    "MD": (47.4116, 28.3699, "Moldova", "Chisinau"),
    "BY": (53.7098, 27.9534, "Belarus", "Minsk"),
    "RU": (55.7558, 37.6173, "Russia", "Moscow"),
    "TR": (38.9637, 35.2433, "Turkey", "Ankara/Istanbul"),
    "IL": (31.0461, 34.8516, "Israel", "Tel Aviv"),
    "AE": (23.4241, 53.8478, "United Arab Emirates", "Dubai"),
    "SA": (23.8859, 45.0792, "Saudi Arabia", "Riyadh"),
    "EG": (26.8206, 30.8025, "Egypt", "Cairo"),
    "ZA": (-30.5595, 22.9375, "South Africa", "Johannesburg"),
    "NG": (9.0820, 8.6753, "Nigeria", "Lagos"),
    "KE": (-0.0236, 37.9062, "Kenya", "Nairobi"),
    "MA": (31.7917, -7.0926, "Morocco", "Casablanca"),
    "IN": (20.5937, 78.9629, "India", "Mumbai/Bangalore"),
    "PK": (30.3753, 69.3451, "Pakistan", "Islamabad"),
    "CN": (35.8617, 104.1954, "China", "Beijing/Shanghai"),
    "HK": (22.3193, 114.1694, "Hong Kong", "Hong Kong"),
    "TW": (23.6978, 120.9605, "Taiwan", "Taipei"),
    "JP": (36.2048, 138.2529, "Japan", "Tokyo"),
    "KR": (35.9078, 127.7669, "South Korea", "Seoul"),
    "SG": (1.3521, 103.8198, "Singapore", "Singapore"),
    "TH": (15.8700, 100.9925, "Thailand", "Bangkok"),
    "VN": (14.0583, 108.2772, "Vietnam", "Hanoi"),
    "MY": (4.2105, 101.9758, "Malaysia", "Kuala Lumpur"),
    "ID": (-0.7893, 113.9213, "Indonesia", "Jakarta"),
    "PH": (12.8797, 121.7740, "Philippines", "Manila"),
    "AU": (-25.2744, 133.7751, "Australia", "Sydney"),
    "NZ": (-40.9006, 174.8860, "New Zealand", "Auckland"),
    "EU": (50.1109, 8.6821, "Europe", "Frankfurt"),
    "IO": (51.5074, -0.1278, "United Kingdom / Global", "London"),
    "AI": (37.7749, -122.4194, "Global / Tech Cloud", "San Francisco"),
    "DEV": (37.7749, -122.4194, "Developer Cloud", "San Francisco"),
    "ME": (42.4411, 19.2636, "Montenegro / Global", "Podgorica"),
    "TV": (37.7749, -122.4194, "Streaming Cloud", "San Francisco"),
    "CC": (37.7749, -122.4194, "Global Cloud", "US West"),
    "TO": (-21.1789, -175.1982, "Tonga / Global", "Nuku'alofa"),
    "SO": (47.3769, 8.5417, "Global / Europe", "Zurich"),
    "WS": (39.0438, -77.4874, "Global / US", "Ashburn"),
    "LY": (37.7749, -122.4194, "Link / Cloud", "San Francisco"),
}

# Known infrastructure, search, OSINT, archive, and major web hosts
KNOWN_HOST_LOCATIONS: Dict[str, Tuple[float, float, str, str, str, str]] = {
    # host_suffix: (lat, lon, cc, country_name, city, known_ip_hint)
    "127.0.0.1": (41.9028, 12.4964, "LOCAL", "Local Node (Hecos)", "127.0.0.1", "127.0.0.1"),
    "localhost": (41.9028, 12.4964, "LOCAL", "Local Node (Hecos)", "localhost", "127.0.0.1"),
    # SearXNG Fallbacks & Privacy Mirrors
    "searx.be": (50.8503, 4.3517, "BE", "Belgium", "Brussels", ""),
    "search.ononoki.org": (50.1109, 8.6821, "DE", "Germany", "Frankfurt", ""),
    "baresearch.org": (47.3769, 8.5417, "CH", "Switzerland", "Zurich", ""),
    "priv.au": (-33.8688, 151.2093, "AU", "Australia", "Sydney", ""),
    "searx.tiekoetter.com": (51.1657, 10.4515, "DE", "Germany", "Nuremberg", ""),
    "ahmia.fi": (60.1699, 24.9384, "FI", "Finland", "Helsinki", ""),
    "onionsearchengine.com": (52.3676, 4.9041, "NL", "Netherlands", "Amsterdam", ""),
    # Clearnet Search & Open Archives
    "duckduckgo.com": (40.0362, -75.5138, "US", "United States", "Paoli, PA", ""),
    "html.duckduckgo.com": (40.0362, -75.5138, "US", "United States", "Paoli, PA", ""),
    "search.brave.com": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "brave.com": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "archive.org": (37.7822, -122.4715, "US", "United States", "San Francisco (Internet Archive)", ""),
    "commons.wikimedia.org": (37.7897, -122.4014, "US", "United States", "San Francisco (Wikimedia)", ""),
    "wikipedia.org": (39.0438, -77.4874, "US", "United States", "Ashburn, VA (Wikimedia)", ""),
    "wikidata.org": (39.0438, -77.4874, "US", "United States", "Ashburn, VA (Wikidata)", ""),
    "core.ac.uk": (52.0249, -0.7107, "GB", "United Kingdom", "Milton Keynes (CORE)", ""),
    "arxiv.org": (42.4430, -76.5019, "US", "United States", "Ithaca, NY (Cornell)", ""),
    "gutenberg.org": (35.9606, -83.9207, "US", "United States", "Knoxville / UNC", ""),
    "openlibrary.org": (37.7822, -122.4715, "US", "United States", "San Francisco", ""),
    "huggingface.co": (40.7128, -74.0060, "US", "United States", "New York / US East", ""),
    # OSINT & Dev Platforms
    "github.com": (37.7820, -122.3910, "US", "United States", "San Francisco (GitHub)", ""),
    "api.github.com": (37.7820, -122.3910, "US", "United States", "San Francisco (GitHub API)", ""),
    "gist.github.com": (37.7820, -122.3910, "US", "United States", "San Francisco", ""),
    "gitlab.com": (37.7749, -122.4194, "US", "United States", "San Francisco (GitLab)", ""),
    "reddit.com": (37.7749, -122.4194, "US", "United States", "San Francisco (Reddit)", ""),
    "news.ycombinator.com": (37.3861, -122.0839, "US", "United States", "Mountain View (HN)", ""),
    "hn.algolia.com": (48.8566, 2.3522, "FR", "France", "Paris (Algolia HN)", ""),
    "gravatar.com": (37.7749, -122.4194, "US", "United States", "San Francisco (Automattic)", ""),
    "keybase.io": (40.7128, -74.0060, "US", "United States", "New York (Keybase)", ""),
    "crt.sh": (53.4808, -2.2426, "GB", "United Kingdom", "Manchester (Sectigo crt.sh)", ""),
    "stackoverflow.com": (40.7081, -74.0067, "US", "United States", "New York (StackOverflow)", ""),
    "dev.to": (40.7128, -74.0060, "US", "United States", "New York (DEV)", ""),
    # Major Social / Media
    "youtube.com": (37.6213, -122.3790, "US", "United States", "San Bruno, CA", ""),
    "youtu.be": (37.6213, -122.3790, "US", "United States", "San Bruno, CA", ""),
    "google.com": (37.4220, -122.0841, "US", "United States", "Mountain View, CA", ""),
    "news.google.com": (37.4220, -122.0841, "US", "United States", "Mountain View, CA", ""),
    "linkedin.com": (37.3861, -122.0839, "US", "United States", "Sunnyvale, CA", ""),
    "x.com": (37.7765, -122.4167, "US", "United States", "San Francisco", ""),
    "twitter.com": (37.7765, -122.4167, "US", "United States", "San Francisco", ""),
    "instagram.com": (37.4848, -122.1484, "US", "United States", "Menlo Park, CA", ""),
    "facebook.com": (37.4848, -122.1484, "US", "United States", "Menlo Park, CA", ""),
    "tiktok.com": (34.0195, -118.4912, "US", "United States", "Los Angeles / Singapore", ""),
    "bsky.app": (47.6062, -122.3321, "US", "United States", "Seattle, WA", ""),
    "medium.com": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "substack.com": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "pinterest.com": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "imdb.com": (47.6062, -122.3321, "US", "United States", "Seattle, WA", ""),
    "unsplash.com": (45.5017, -73.5673, "CA", "Canada", "Montreal", ""),
    "openverse.org": (37.7749, -122.4194, "US", "United States", "San Francisco", ""),
    "dailymotion.com": (48.8566, 2.3522, "FR", "France", "Paris", ""),
    "soundcloud.com": (52.5200, 13.4050, "DE", "Germany", "Berlin", ""),
    "bandcamp.com": (37.8044, -122.2712, "US", "United States", "Oakland, CA", ""),
    "telegram.org": (25.2048, 55.2708, "AE", "UAE", "Dubai", ""),
    "t.me": (25.2048, 55.2708, "AE", "UAE", "Dubai", ""),
    "yandex.com": (55.7558, 37.6173, "RU", "Russia", "Moscow", ""),
    "yandex.ru": (55.7558, 37.6173, "RU", "Russia", "Moscow", ""),
}

# Known Tor dark web search engines with logical labels
KNOWN_ONION_ENGINES: Dict[str, str] = {
    "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion": "Ahmia (.onion)",
    "xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion": "Torch (.onion)",
    "2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion": "Excavator (.onion)",
    "tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion": "Tor66 (.onion)",
    "tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion": "TorDex (.onion)",
    "haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion": "Haystak (.onion)",
    "phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion": "Phobos (.onion)",
    "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion": "DuckDuckGo (.onion)",
    "37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion": "OnionSearchEngine (.onion)",
    "danschat356lctri3zavzh6fbxg2a7lo6z3etms423k27l7k2k6ad.onion": "DanEx / DanielTore (.onion)",
}


def deterministic_jitter(seed: str, radius_deg: float = 1.6) -> Tuple[float, float]:
    """Deterministic small lat/lon offset so co-located hosts don't stack on identical pixels."""
    h = hashlib.sha256(seed.encode("utf-8", errors="ignore")).digest()
    angle = (int.from_bytes(h[:2], "big") / 65535.0) * (2.0 * math.pi)
    dist = (0.25 + 0.75 * (int.from_bytes(h[2:4], "big") / 65535.0)) * radius_deg
    return round(math.sin(angle) * dist, 4), round(math.cos(angle) * dist, 4)


def onion_orbital_coord(onion_host: str, anchor_lat: float = 18.0, anchor_lon: float = -35.0) -> Tuple[float, float]:
    """
    Deterministically places .onion hidden services on a distinct Darknet Layer ring
    anchored near the Atlantic/neutral zone or the current Tor Rendezvous node.
    """
    clean = (onion_host or "").lower().strip()
    h = hashlib.sha256(clean.encode("utf-8", errors="ignore")).digest()
    angle = (int.from_bytes(h[:2], "big") / 65535.0) * (2.0 * math.pi)
    ring_r = 7.5 + (int.from_bytes(h[2:4], "big") / 65535.0) * 11.0
    lat = max(-68.0, min(68.0, anchor_lat + math.sin(angle) * ring_r))
    lon = anchor_lon + math.cos(angle) * (ring_r * 1.25)
    if lon > 179.0:
        lon -= 360.0
    elif lon < -179.0:
        lon += 360.0
    return round(lat, 4), round(lon, 4)


def lookup_country_coords(country_code: str, seed: str = "") -> Optional[Dict[str, Any]]:
    cc = (country_code or "").upper().strip()
    if cc in COUNTRY_CENTROIDS:
        base_lat, base_lon, cname, city = COUNTRY_CENTROIDS[cc]
        dlat, dlon = deterministic_jitter(seed or cc, radius_deg=1.4) if seed else (0.0, 0.0)
        return {
            "lat": round(base_lat + dlat, 4),
            "lon": round(base_lon + dlon, 4),
            "country_code": cc,
            "country_name": cname,
            "city": city,
        }
    return None


def lookup_host_offline(host: str) -> Dict[str, Any]:
    """
    Purely offline geolocation for any hostname or .onion address.
    Never issues any external network/DNS calls.
    """
    clean_host = (host or "").strip().lower().split(":")[0]
    if not clean_host:
        return {
            "lat": 41.9028,
            "lon": 12.4964,
            "country_code": "LOCAL",
            "country_name": "Local Node",
            "city": "127.0.0.1",
            "source": "local",
            "is_virtual": False,
        }

    # 1. Local loopback / private IPv4
    if (
        clean_host in ("127.0.0.1", "localhost", "::1")
        or clean_host.startswith("192.168.")
        or clean_host.startswith("10.")
        or clean_host.startswith("172.16.")
    ):
        return {
            "lat": 41.9028,
            "lon": 12.4964,
            "country_code": "LOCAL",
            "country_name": "Local Network",
            "city": clean_host,
            "source": "local",
            "is_virtual": False,
        }

    # 2. .onion Hidden Services (Darknet Layer)
    if clean_host.endswith(".onion"):
        lat, lon = onion_orbital_coord(clean_host)
        friendly = KNOWN_ONION_ENGINES.get(clean_host, "Tor Hidden Service (.onion)")
        return {
            "lat": lat,
            "lon": lon,
            "country_code": "ONION",
            "country_name": "Tor Darknet Layer",
            "city": friendly,
            "source": "darknet_orbit",
            "is_virtual": True,
        }

    # 3. Exact or subdomain match against curated infrastructure database
    parts = clean_host.split(".")
    for i in range(len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in KNOWN_HOST_LOCATIONS:
            lat, lon, cc, cname, city, _ = KNOWN_HOST_LOCATIONS[suffix]
            dlat, dlon = deterministic_jitter(clean_host, radius_deg=0.75)
            return {
                "lat": round(lat + dlat, 4),
                "lon": round(lon + dlon, 4),
                "country_code": cc,
                "country_name": cname,
                "city": city,
                "source": "offline_db",
                "is_virtual": False,
            }

    # 4. ccTLD heuristic (.it, .de, .fr, .uk, .jp, etc.)
    tld = parts[-1].upper() if len(parts) >= 2 else ""
    if tld in COUNTRY_CENTROIDS:
        info = lookup_country_coords(tld, seed=clean_host)
        if info:
            info["source"] = "offline_cctld"
            info["is_virtual"] = False
            return info

    # 5. Regional deterministic hash fallback for .com/.org/.net in LOCAL ONLY mode
    regional_clusters = [
        (39.0438, -77.4874, "US", "United States (Est.)", "US East / Cloud"),
        (37.7749, -122.4194, "US", "United States (Est.)", "US West / Cloud"),
        (50.1109, 8.6821, "DE", "Germany (Est.)", "Frankfurt / EU"),
        (52.3676, 4.9041, "NL", "Netherlands (Est.)", "Amsterdam / EU"),
        (51.5074, -0.1278, "GB", "United Kingdom (Est.)", "London / EU"),
        (1.3521, 103.8198, "SG", "Singapore (Est.)", "APAC Cloud"),
    ]
    h = hashlib.sha256(clean_host.encode("utf-8", errors="ignore")).digest()
    cluster = regional_clusters[h[0] % len(regional_clusters)]
    dlat, dlon = deterministic_jitter(clean_host, radius_deg=2.2)
    return {
        "lat": round(cluster[0] + dlat, 4),
        "lon": round(cluster[1] + dlon, 4),
        "country_code": cluster[2],
        "country_name": cluster[3],
        "city": cluster[4],
        "source": "offline_hash",
        "is_virtual": True,
    }
