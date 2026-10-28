import importlib.util, sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "voiceapp", Path(__file__).with_name("app.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "DATA", tmp_path)
    monkeypatch.delenv("ENABLE_WHISPER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(m, "MODEL", None)
    with TestClient(m.app) as c:
        yield c


def auth(c, name="tester"):
    assert (
        c.post(
            "/api/signup", json={"username": name, "password": "test-only-1234"}
        ).status_code
        == 201
    )
    r = c.post("/api/login", json={"username": name, "password": "test-only-1234"})
    assert r.status_code == 200
    return {"x-csrf-token": r.json()["csrf"]}


def test_text_lifecycle_and_protection(client):
    c = client
    assert c.get("/api/jobs").status_code == 401
    h = auth(c)
    assert (
        c.post(
            "/api/jobs/text",
            json={
                "text": "오늘 회의에서 예약 기능을 점검했습니다. 다음 회의에서 테스트 결과를 확인합니다."
            },
        ).status_code
        == 403
    )
    r = c.post(
        "/api/jobs/text",
        headers=h,
        json={
            "text": "오늘 회의에서 예약 기능을 점검했습니다. 다음 회의에서 테스트 결과를 확인합니다."
        },
    )
    assert r.status_code == 202
    job = r.json()["task_id"]
    d = c.get("/api/jobs/" + job).json()
    assert d["status"] == "done" and "AI 요약 아님" in d["mode"]
    assert len(c.get("/api/jobs").json()) == 1
    assert c.delete("/api/jobs/" + job, headers=h).status_code == 200
    assert c.get("/api/jobs/" + job).status_code == 404


def test_owner_isolation(client):
    c = client
    h = auth(c, "owner")
    job = c.post(
        "/api/jobs/text",
        headers=h,
        json={
            "text": "첫 번째 사용자의 개인 테스트 문서입니다. 다른 사용자는 읽을 수 없어야 합니다."
        },
    ).json()["task_id"]
    h2 = auth(c, "other")
    assert c.get("/api/jobs").json() == []
    assert c.get("/api/jobs/" + job).status_code == 404
    assert c.delete("/api/jobs/" + job, headers=h2).status_code == 404


def test_audio_cleanup_success_failure_and_limit(client, monkeypatch):
    c = client
    h = auth(c)
    monkeypatch.setattr(m, "MODEL", object())
    monkeypatch.setattr(
        m,
        "transcribe",
        lambda p: "테스트 대역으로 음성 처리 흐름을 확인합니다. 실제 Whisper 정확도 검증은 아닙니다.",
    )
    r = c.post(
        "/api/jobs/audio",
        headers=h,
        files={"file": ("sample.wav", b"test bytes", "audio/wav")},
    )
    assert r.status_code == 202
    assert c.get("/api/jobs/" + r.json()["task_id"]).json()["status"] == "done"
    assert list((m.DATA / "uploads").iterdir()) == []

    def fail(p):
        raise ValueError("decoder failure")

    monkeypatch.setattr(m, "transcribe", fail)
    r = c.post(
        "/api/jobs/audio",
        headers=h,
        files={"file": ("sample.wav", b"test bytes", "audio/wav")},
    )
    assert c.get("/api/jobs/" + r.json()["task_id"]).json()["status"] == "failed"
    assert list((m.DATA / "uploads").iterdir()) == []
    monkeypatch.setattr(m, "LIMIT", 3)
    assert (
        c.post(
            "/api/jobs/audio",
            headers=h,
            files={"file": ("big.wav", b"1234", "audio/wav")},
        ).status_code
        == 413
    )
    assert list((m.DATA / "uploads").iterdir()) == []


def test_restart_and_password_storage(client):
    auth(client)
    with m.db() as c:
        stored = c.execute("SELECT password FROM users").fetchone()[0]
    assert stored != "test-only-1234"
    job = m.create_job(1, "interrupted")
    (m.DATA / "uploads" / "stale.wav").write_bytes(b"old")
    m.init()
    with m.db() as c:
        assert (
            c.execute("SELECT status FROM jobs WHERE id=?", (job,)).fetchone()[0]
            == "failed"
        )
    assert list((m.DATA / "uploads").iterdir()) == []


def test_placeholder_and_api_failure_use_fallback(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your_api_key_here")

    def never(*args, **kwargs):
        raise AssertionError("placeholder must not call API")

    monkeypatch.setattr(m.requests, "post", never)
    assert "AI 요약 아님" in m.summarize("첫 번째 문장입니다. 두 번째 문장입니다.")[1]
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-real-key")

    def timeout(*args, **kwargs):
        raise m.requests.Timeout("simulated timeout")

    monkeypatch.setattr(m.requests, "post", timeout)
    assert (
        "AI 요약 아님" in m.summarize("외부 API 오류 시에도 원문 일부를 보여줍니다.")[1]
    )
