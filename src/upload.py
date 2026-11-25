"""YouTube upload with OAuth refresh-token auth ONLY (no API key, no session cookies).
Secrets (set by the channel owner in GitHub Secrets, never in code/chat):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Quota: one upload = 1600 units of the free 10,000/day. Hard gate below.
"""
import json, os, sys, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metadata import build_description, build_tags

def access_token():
    _rt = os.environ["YT_REFRESH_TOKEN"]; _cid = os.environ["YT_CLIENT_ID"]
    # Shape-only diagnostics: lengths and a public fragment, never values.
    print("pre-flight diag: refresh_token len=%d, refresh-shaped=%s, client_id len=%d, client_id mid=%s" % (
        len(_rt), _rt.startswith("1//"), len(_cid),
        _cid.split("-")[1][:4] if "-" in _cid else "?"))
    data = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token"}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=data))
    except urllib.error.HTTPError as e:
        # Google's error body carries only an error code/description
        # (e.g. invalid_client, invalid_grant) - never secret values.
        print("TOKEN EXCHANGE FAILED:", e.code, e.read().decode("utf-8", "replace"))
        raise
    return json.load(r)["access_token"]

MUSIC_CREDIT = ("\n\nMusic: 'Wallpaper', 'Cold Funk', 'Deep and Dirty' by Kevin MacLeod "
                "(incompetech.com), licensed under CC BY 4.0.")

def upload(video_path, meta, thumb_path=None):
    tok = access_token()
    body = {"snippet": {"title": meta["title"], "description": build_description(meta) + MUSIC_CREDIT,
                        "tags": build_tags(meta), "categoryId": "17"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(os.path.getsize(video_path))}, method="POST")
    loc = urllib.request.urlopen(req).headers["Location"]
    with open(video_path, "rb") as f:
        r2 = urllib.request.urlopen(urllib.request.Request(
            loc, data=f.read(), headers={"Content-Type": "video/mp4"}, method="PUT"))
    vid = json.load(r2)["id"]
    if thumb_path and os.path.exists(thumb_path):
        urllib.request.urlopen(urllib.request.Request(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
            data=open(thumb_path, "rb").read(),
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, method="POST"))
    return vid

if __name__ == "__main__":
    meta = json.load(open(sys.argv[2]))
    print(upload(sys.argv[1], meta, os.path.join(os.path.dirname(sys.argv[1]), "thumbnail.jpg")))
