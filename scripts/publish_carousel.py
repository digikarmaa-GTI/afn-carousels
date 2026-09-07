#!/usr/bin/env python3
import os, sys, time, json, pathlib, urllib.parse, urllib.request

GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")
IG_USER_ID = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_ACCESS_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

def call(path, params):
    data = urllib.parse.urlencode({**params, "access_token": TOKEN}).encode()
    req = urllib.request.Request(f"{BASE}/{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def wait_ready(cid, tries=30, delay=4):
    for _ in range(tries):
        url = f"{BASE}/{cid}?fields=status_code,status&access_token={urllib.parse.quote(TOKEN)}"
        with urllib.request.urlopen(url, timeout=60) as r:
            body = json.loads(r.read())
        if body.get("status_code") == "FINISHED":
            return
        if body.get("status_code") == "ERROR":
            raise SystemExit(f"Container {cid} failed: {body.get('status')}")
        time.sleep(delay)
    raise SystemExit(f"Container {cid} never became ready")

def publish(folder):
    slides = sorted(folder.glob("slide_*.png"))
    if not slides:
        raise SystemExit(f"No slides in {folder}")
    if len(slides) > 10:
        raise SystemExit("Instagram carousels take at most 10 images")
    cap = folder / "caption.txt"
    caption = cap.read_text(encoding="utf-8").strip() if cap.exists() else ""
    print(f"Publishing {folder.name}: {len(slides)} slides")
    children = []
    for s in slides:
        image_url = f"{RAW}/{folder.as_posix()}/{s.name}"
        print("  fetching:", image_url)
        cid = call(f"{IG_USER_ID}/media",
                   {"image_url": image_url, "is_carousel_item": "true"})["id"]
        wait_ready(cid)
        children.append(cid)
        print("  ok", s.name)
    carousel = call(f"{IG_USER_ID}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })["id"]
    wait_ready(carousel)
    print("PUBLISHED:", call(f"{IG_USER_ID}/media_publish", {"creation_id": carousel}))

def main():
    queue = pathlib.Path("queue")
    if not queue.exists():
        print("No queue directory. Nothing to do."); return
    folders = sorted(p for p in queue.iterdir() if p.is_dir())
    if not folders:
        print("Queue is empty. Nothing to do."); return
    only = os.environ.get("ONLY_SLUG")
    if only:
        folders = [p for p in folders if p.name == only]
        if not folders: sys.exit(f"No queue/{only}")
    folder = folders[0]
    publish(folder)
    dest = pathlib.Path("published") / folder.name
    dest.parent.mkdir(exist_ok=True)
    folder.rename(dest)
    print(f"Moved {folder} -> {dest}")

if __name__ == "__main__":
    main()
