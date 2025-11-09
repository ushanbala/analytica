from flask import Flask, render_template, request, jsonify
import requests, json, os, time
import yt_dlp
from threading import Thread

from collections import Counter
from datetime import datetime

app = Flask(__name__)
yt_dlp.utils.std_headers['User-Agent'] = "Mozilla/5.0"

CHANNEL_FILE = "channels.json"
ANALYTICS_FILE = "analytics.json"

progress = {"status": "idle", "percent": 0, "message": ""}
# Cache dictionary: channel_url -> {"videos": [...], "timestamp": <epoch_time>}
cache = {}

CACHE_EXPIRY = 300  # seconds, e.g. 5 minutes


def load_channels():
    if os.path.exists(CHANNEL_FILE):
        with open(CHANNEL_FILE, "r") as f:
            return json.load(f)
    return []

def load_analytics():
    if os.path.exists(ANALYTICS_FILE):
        with open(ANALYTICS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_analytics(data):
    with open(ANALYTICS_FILE, "w") as f:
        json.dump(data, f, indent=2)



def save_channels(data):
    with open(CHANNEL_FILE, "w") as f:
        json.dump(data, f, indent=2)


def scrape_videos(channel_url):
    global progress
    progress = {"status": "working", "percent": 0, "message": "Starting scrape..."}
    videos = []

    if not channel_url.endswith("/videos"):
        channel_url = channel_url.rstrip("/") + "/videos"

    ydl_opts = {
        "quiet": True,
        "extract_flat": False,
        "skip_download": True,
        "noplaylist": False,
        "playlistend": 20,
        "outtmpl": "%(id)s",
        "ignoreerrors": True,   # This line ignores errors (like premieres)
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            entries = info.get("entries", [])
            total = len(entries)
            for i, entry in enumerate(entries, start=1):
                if not entry:
                    continue
                videos.append({
                    "title": entry.get("title"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "views": entry.get("view_count", 0),
                    "published": entry.get("upload_date", ""),
                    "duration": entry.get("duration"),
                    "description": entry.get("description", "")[:200],
                    "thumbnail": entry.get("thumbnail"),
                    "like_count": entry.get("like_count", 0),
                    "channel": entry.get("uploader"),
                    "channel_id": entry.get("channel_id")
                })
                progress = {
                    "status": "working",
                    "percent": int((i / total) * 100),
                    "message": f"Scraped {i}/{total} videos"
                }
        progress = {"status": "done", "percent": 100, "message": "Completed!"}
    except Exception as e:
        progress = {"status": "error", "percent": 0, "message": str(e)}

    return videos


def analyze_videos(videos):
    if not videos:
        return {}

    # Convert upload_date (YYYYMMDD string) to datetime objects
    dates = []
    for v in videos:
        try:
            dt = datetime.strptime(v.get("published", ""), "%Y%m%d")
            dates.append(dt)
        except Exception:
            pass

    # Calculate average views, likes, duration
    total_views = sum(int(v.get("views") or 0) for v in videos)
    total_likes = sum(int(v.get("like_count") or 0) for v in videos)
    total_duration = sum(int(v.get("duration") or 0) for v in videos if v.get("duration") is not None)
    count = len(videos)

    avg_views = total_views // count if count else 0
    avg_likes = total_likes // count if count else 0
    avg_duration = total_duration // count if count else 0

    # Engagement ratio: likes/views (avoid divide by zero)
    engagement_ratios = [
        (int(v.get("like_count") or 0) / v.get("views"))
        for v in videos if v.get("views", 0) > 0
    ]
    avg_engagement = sum(engagement_ratios) / len(engagement_ratios) if engagement_ratios else 0

    # Title keyword frequency (top 10 excluding common stopwords)
    stopwords = set([
        "the", "and", "a", "to", "of", "in", "for", "on", "with", "is", "at", "by", "an", "be",
        "this", "that", "it", "from", "as", "are", "was", "but", "or", "if", "you", "i", "we"
    ])
    words = []
    for v in videos:
        if v.get("title"):
            ws = v["title"].lower().split()
            filtered = [w.strip(".,!?") for w in ws if w not in stopwords]
            words.extend(filtered)
    word_freq = Counter(words).most_common(10)

    # Upload frequency: calculate avg days between uploads
    dates.sort()
    if len(dates) > 1:
        diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
        avg_upload_freq = sum(diffs) / len(diffs)
    else:
        avg_upload_freq = None

    return {
        "average_views": avg_views,
        "average_likes": avg_likes,
        "average_duration_seconds": avg_duration,
        "average_engagement_ratio": round(avg_engagement, 4),
        "top_keywords": word_freq,
        "average_upload_frequency_days": avg_upload_freq
    }



@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/channels", methods=["GET", "POST", "DELETE"])
def manage_channels():
    channels = load_channels()
    if request.method == "POST":
        url = request.json.get("url")
        name = url.split("/")[-1]
        if url not in [c["url"] for c in channels]:
            channels.append({"name": name, "url": url})
            save_channels(channels)
        return jsonify(channels)
    elif request.method == "DELETE":
        url = request.json.get("url")
        channels = [c for c in channels if c["url"] != url]
        save_channels(channels)
        return jsonify(channels)
    return jsonify(channels)


@app.route("/api/videos", methods=["POST"])
def get_videos():
    channel_url = request.json.get("url")
    now = time.time()

    # Check cache
    if channel_url in cache:
        cached = cache[channel_url]
        if now - cached["timestamp"] < CACHE_EXPIRY:
            # Return cached data immediately
            global progress
            progress = {"status": "done", "percent": 100, "message": "Loaded from cache"}
            # Store latest videos for frontend
            global latest_videos
            latest_videos = cached["videos"]
            return jsonify({"status": "cached"})

    # Otherwise scrape in background and update cache
    def run_scrape():
        videos = scrape_videos(channel_url)
        cache[channel_url] = {"videos": videos, "timestamp": time.time()}
        global latest_videos
        latest_videos = videos

    thread = Thread(target=run_scrape)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/progress")
def get_progress():
    return jsonify(progress)


@app.route("/api/videos/latest")
def videos_latest():
    return jsonify(latest_videos)

@app.route("/api/videos/analytics", methods=["POST"])
def videos_analytics():
    videos = request.json.get("videos", [])
    channel_url = request.json.get("channel_url")
    analytics = analyze_videos(videos)

    if channel_url:
        all_analytics = load_analytics()
        all_analytics[channel_url] = analytics
        save_analytics(all_analytics)

    return jsonify(analytics)

@app.route("/api/analytics/<path:channel_url>", methods=["GET"])
def get_saved_analytics(channel_url):
    all_analytics = load_analytics()
    analytics = all_analytics.get(channel_url)
    if analytics:
        return jsonify(analytics)
    else:
        return jsonify({"error": "No analytics found"}), 404


if __name__ == "__main__":
    app.run(debug=True)
