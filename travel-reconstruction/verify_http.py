"""Run once against a fresh locally running application: pip install requests; python verify_http.py"""

import requests, re, json
from pathlib import Path

s = requests.Session()
s.trust_env = False
base = "http://127.0.0.1:8080"
checks = []


def get(path):
    r = s.get(base + path)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    return r


def token(r):
    return re.search(r'name="_csrf" value="([^"]+)"', r.text).group(1)


def check(name, ok):
    assert ok, name
    checks.append(name)


r = get("/")
check("home renders", "TravelRecommend" in r.text)
r = get("/signup")
csrf = token(r)
r = s.post(
    base + "/signup",
    data={"_csrf": csrf, "username": "verify_user", "password": "Local-test-123!"},
    allow_redirects=False,
)
check("signup", r.status_code == 302)
r = s.post(
    base + "/login",
    data={"_csrf": csrf, "username": "verify_user", "password": "Local-test-123!"},
    allow_redirects=False,
)
check("login", r.status_code == 302)
r = get("/recommend")
csrf = token(r)
r = s.post(
    base + "/recommend",
    data={
        "_csrf": csrf,
        "style": "힐링",
        "budget": 1500000,
        "country": "일본",
        "purpose": "조용한 휴식",
    },
)
check("recommend renders", r.status_code == 200 and "예약" in r.text)
# Server response rendering is checked without storing session tokens.
check(
    "csrf rejected",
    s.post(base + "/recommend", data={"style": "힐링", "budget": 1500000}).status_code
    == 403,
)
check("admin protected", s.get(base + "/admin").status_code == 403)
ids = re.findall(r"/reservation/form/(\d+)", r.text)
check("three recommendations", len(ids) == 3)
r = get("/reservation/form/" + ids[0])
csrf = token(r)
r = s.post(
    base + "/reservation/save",
    data={"_csrf": csrf, "travelId": ids[0], "people": 2},
    allow_redirects=False,
)
check("reservation saved", r.status_code == 302)
r = get("/reservations")
rid = re.search(r"/reservation/cancel/(\d+)", r.text).group(1)
r = s.post(
    base + "/reservation/cancel/" + rid, data={"_csrf": csrf}, allow_redirects=False
)
check("reservation cancelled", r.status_code == 302)
r = get("/reservations")
check("cancel removes own reservation", "/reservation/cancel/" not in r.text)
print(json.dumps(checks, ensure_ascii=False, indent=2))
