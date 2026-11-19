"""Publish today's iliaCollections | Stories carousel to Instagram.

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
    schedule = json.load(open(os.path.join(HERE, "schedule.json")))
    posted_path = os.path.join(HERE, "posted.json")
    posted = json.load(open(posted_path)) if os.path.exists(posted_path) else {}

    if STORY_NUMBER:
        story = next((s for s in schedule if s["number"] == int(STORY_NUMBER)), None)
        if not story:
            raise SystemExit(f"Story {STORY_NUMBER} not in schedule")
    else:
        # Rule: an item may be posted LATE (even after midnight), never EARLY.
        # Each item is due at its date + POST_TIME (Bucharest). A run posts the
        # oldest item that is due and not yet posted. GitHub may start cron runs
        # hours late, so the run's own clock must never pick the item by itself.
        tz = ZoneInfo("Europe/Bucharest")
        now = datetime.datetime.now(tz)
        hh, mm = map(int, os.environ.get("POST_TIME", "17:37").split(":"))
        def due_at(s):
            d = datetime.date.fromisoformat(s["date"])
            return datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        due = [s for s in schedule if due_at(s) <= now and f"{s['number']:03d}" not in posted]
        if not due:
            nxt = next((s for s in schedule if due_at(s) > now), None)
            log(f"Nothing due now ({now:%Y-%m-%d %H:%M} Bucharest). Next: "
                + (f"{nxt['number']:03d} at {due_at(nxt):%Y-%m-%d %H:%M}" if nxt else "none"))
            return
        story = min(due, key=due_at)
        # Catch-up safety: never post two items within 90 minutes of each other
        # (only matters if a whole day was missed and two items are overdue).
        last = max((v.get("timestamp") or "" for v in posted.values()), default="")
        if last:
            last_dt = datetime.datetime.strptime(last, "%Y-%m-%dT%H:%M:%S%z")
            if now - last_dt < datetime.timedelta(minutes=90):
                log(f"{story['number']:03d} is due, but the last post was at {last_dt.astimezone(tz):%Y-%m-%d %H:%M}. "
                    "Waiting (min. 90 min between posts).")
                return
        late = now - due_at(story)
        log(f"{story['number']:03d} was due at {due_at(story):%Y-%m-%d %H:%M} ({int(late.total_seconds() // 60)} min late).")

    num = f"{story['number']:03d}"
    if num in posted and not DRY_RUN:
        log(f"Story {num} already posted: {posted[num].get('permalink')}. Skipping.")
        return

    log(f"Story {num} - {story['title']} | dry_run={DRY_RUN}")
    # Safety net: if the same caption is already among the latest posts, don't post again.
    recent = api("GET", f"{IG_USER_ID}/media", {"fields": "caption,permalink", "limit": "5"})
    for m in recent.get("data", []):
        if (m.get("caption") or "").strip() == story["caption"].strip() and not DRY_RUN:
            log(f"Story {num} already on Instagram: {m.get('permalink')}. Skipping.")
            return

    children = []
    for i in range(1, 8):
        url = f"{REPO_RAW}/stories/{num}/{i}.jpg"
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
