"""Publish today's carousel to Instagram (iliaCollections | Stories or | Cars, see CONTENT).

Runs in GitHub Actions. Reads schedule.json, finds the story for today's date
(Europe/Bucharest), publishes its 7 slides as a carousel with the hashtag caption,
and records the result in posted.json so a story is never posted twice.

Environment:
  IG_TOKEN      access token (GitHub secret)
  IG_USER_ID    Instagram professional account ID
  STORY_NUMBER  optional: publish this story number instead of today's
  DRY_RUN       "true" = create the media containers but do NOT publish
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

GRAPH = "https://graph.facebook.com/v27.0"
REPO_RAW = "https://raw.githubusercontent.com/raulserban/iliaCollectionStories/main"
HERE = os.path.dirname(os.path.abspath(__file__))

TOKEN = os.environ["IG_TOKEN"].strip()
IG_USER_ID = os.environ.get("IG_USER_ID", "17841424464874525").strip()
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
STORY_NUMBER = os.environ.get("STORY_NUMBER", "").strip()

# Which page: "stories" (default, iliaCollections | Stories) or "cars" (iliaCollection | Cars)
CONTENT = os.environ.get("CONTENT", "stories").strip() or "stories"
CONFIG = {
    "stories": {"data_dir": HERE, "media_dir": "stories", "slides": 7},
    "cars": {"data_dir": os.path.join(HERE, "cars"), "media_dir": "cars", "slides": 5},
}[CONTENT]


def log(msg):
    print(msg.replace(TOKEN, "***"), flush=True)


def api(method, path, params=None, attempts=4):
    params = dict(params or {})
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params)
    url = f"{GRAPH}/{path}"
    for i in range(1, attempts + 1):
        try:
            if method == "GET":
                req = urllib.request.Request(f"{url}?{data}")
            else:
                req = urllib.request.Request(url, data=data.encode(), method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            log(f"HTTP {e.code} on {method} {path} (attempt {i}): {body}")
            if e.code < 500 and e.code != 429:
                raise SystemExit(f"Instagram API error: {body}".replace(TOKEN, "***"))
        except (urllib.error.URLError, TimeoutError) as e:
            log(f"Network error on {method} {path} (attempt {i}): {e}")
        time.sleep(10 * i)
    raise SystemExit(f"Giving up on {method} {path}")


def wait_finished(container_id, label):
    for _ in range(30):
        st = api("GET", container_id, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise SystemExit(f"{label}: container status {st}")
        time.sleep(5)
    raise SystemExit(f"{label}: container not ready in time")


def main():
    schedule = json.load(open(os.path.join(CONFIG["data_dir"], "schedule.json")))
    posted_path = os.path.join(CONFIG["data_dir"], "posted.json")
    posted = json.load(open(posted_path)) if os.path.exists(posted_path) else {}

    if STORY_NUMBER:
        story = next((s for s in schedule if s["number"] == int(STORY_NUMBER)), None)
        if not story:
            raise SystemExit(f"Story {STORY_NUMBER} not in schedule")
    else:
        today = datetime.datetime.now(ZoneInfo("Europe/Bucharest")).date().isoformat()
        story = next((s for s in schedule if s["date"] == today), None)
        if not story:
            log(f"No story scheduled for {today}. Nothing to do.")
            return

    num = f"{story['number']:03d}"
    if num in posted and not DRY_RUN:
        log(f"Story {num} already posted: {posted[num].get('permalink')}. Skipping.")
        return

    log(f"[{CONTENT}] {num} - {story['title']} | dry_run={DRY_RUN}")
    # Safety net: if the same caption is already among the latest posts, don't post again.
    recent = api("GET", f"{IG_USER_ID}/media", {"fields": "caption,permalink", "limit": "5"})
    for m in recent.get("data", []):
        if (m.get("caption") or "").strip() == story["caption"].strip() and not DRY_RUN:
            log(f"Story {num} already on Instagram: {m.get('permalink')}. Skipping.")
            return

    children = []
    for i in range(1, CONFIG["slides"] + 1):
        url = f"{REPO_RAW}/{CONFIG['media_dir']}/{num}/{i}.jpg"
        c = api("POST", f"{IG_USER_ID}/media", {"image_url": url, "is_carousel_item": "true"})
        log(f"  slide {i}: container {c['id']}")
        children.append(c["id"])
    for i, cid in enumerate(children, 1):
        wait_finished(cid, f"slide {i}")

    carousel = api("POST", f"{IG_USER_ID}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": story["caption"],
    })
    wait_finished(carousel["id"], "carousel")
    log(f"  carousel container {carousel['id']} ready")

    if DRY_RUN:
        log("DRY RUN OK - everything is ready, nothing was published.")
        return

    media = api("POST", f"{IG_USER_ID}/media_publish", {"creation_id": carousel["id"]})
    info = api("GET", media["id"], {"fields": "permalink,timestamp"})
    log(f"PUBLISHED story {num}: {info.get('permalink')}")
    posted[num] = {"title": story["title"], "media_id": media["id"],
                   "permalink": info.get("permalink"), "timestamp": info.get("timestamp")}
    with open(posted_path, "w") as f:
        json.dump(posted, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
