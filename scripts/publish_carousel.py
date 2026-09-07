#!/usr/bin/env python3
import os, sys, time, json, pathlib, urllib.parse, urllib.request, urllib.error

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
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"  !! HTTP {e.code} on POST {path}")
        print(f"  !! params: { {k: v for k, v in params.items() if k != 'access_token'} }")
        print(f"  !! response: {body}")
        raise SystemExit(1)

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
    dry = folder.name.startswith("drytest")
    urls_file = folder / "urls.txt"
    if urls_file.exists():
        urls = [u.strip() for u in urls_file.read_text(encoding="utf-8").splitlines()
                if u.strip() and not u.strip().startswith("#")]
        names = [f"url[{i+1}]" for i in range(len(urls))]
    else:
        paths = sorted(folder.glob("slide_*.png"))
        urls = [f"{RAW}/{folder.as_posix()}/{p.name}" for p in paths]
        names = [p.name for p in paths]
    if not urls:
        raise SystemExit(f"No slides in {folder}")
    if len(urls) > 10:
        raise SystemExit("Instagram carousels take at most 10 images")
    cap = folder / "caption.txt"
    caption = cap.read_text(encoding="utf-8").strip() if cap.exists() else ""
    print(f"Publishing {folder.name}: {len(urls)} slides (dry_run={dry})")

    if len(urls) == 1:
        print("  single slide, posting as a normal image not a carousel")
        print("  fetching:", urls[0])
        cid = call(f"{IG_USER_ID}/media", {"image_url": urls[0], "caption": caption})["id"]
        wait_ready(cid)
        print("  ok", names[0])
        if dry:
            print("DRY RUN: container", cid, "ready, skipping media_publish")
            return
        print("PUBLISHED:", call(f"{IG_USER_ID}/media_publish", {"creation_id": cid}))
        return

    children = []
    for url, nm in zip(urls, names):
        print("  fetching:", url)
        cid = call(f"{IG_USER_ID}/media",
                   {"image_url": url, "is_carousel_item": "true"})["id"]
        wait_ready(cid)
        children.append(cid)
        print("  ok", nm, "->", cid)
    print("  building CAROUSEL container from", len(children), "children")
    carousel = call(f"{IG_USER_ID}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })["id"]
    wait_ready(carousel)
    print("CAROUSEL CONTAINER OK:", carousel)
    if dry:
        print("DRY RUN: carousel container ready, skipping media_publish")
        return
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
    if folder.name.startswith("drytest"):
        print("DRY RUN: leaving", folder, "in the queue")
        return
    dest = pathlib.Path("published") / folder.name
    dest.parent.mkdir(exist_ok=True)
    folder.rename(dest)
    print(f"Moved {folder} -> {dest}")

if __name__ == "__main__":
    main()
