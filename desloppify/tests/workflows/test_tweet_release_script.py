from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "scripts"
    / "tweet_release.py"
)


def _load_tweet_release_module(monkeypatch: pytest.MonkeyPatch):
    anthropic_stub = SimpleNamespace(Anthropic=lambda: SimpleNamespace(messages=None))
    tweepy_stub = SimpleNamespace(
        OAuth1UserHandler=lambda *args, **kwargs: None,
        API=lambda auth: None,
        Client=lambda **kwargs: None,
        errors=SimpleNamespace(TwitterServerError=RuntimeError),
    )
    _RequestException = type("RequestException", (OSError,), {})
    requests_stub = SimpleNamespace(
        get=lambda *args, **kwargs: None,
        post=lambda *args, **kwargs: None,
        RequestException=_RequestException,
        ConnectionError=type("ConnectionError", (_RequestException,), {}),
        Timeout=type("Timeout", (_RequestException,), {}),
        HTTPError=type("HTTPError", (_RequestException,), {}),
        exceptions=SimpleNamespace(RequestException=_RequestException),
    )
    monkeypatch.setitem(sys.modules, "anthropic", anthropic_stub)
    monkeypatch.setitem(sys.modules, "tweepy", tweepy_stub)
    monkeypatch.setitem(sys.modules, "requests", requests_stub)

    module_name = f"tweet_release_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_image_uses_timeout_and_wraps_request_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tweet_release_module(monkeypatch)
    seen: dict[str, object] = {}

    def fake_post(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        raise module.requests.Timeout("too slow")

    monkeypatch.setattr(module.requests, "post", fake_post)

    with pytest.raises(module.ReleaseTweetError, match="fal.ai request failed"):
        module.generate_image("prompt", "key")

    assert seen["timeout"] == module.REQUEST_TIMEOUT_SECONDS


def test_generate_tweet_and_prompt_wraps_bad_claude_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tweet_release_module(monkeypatch)

    class _Messages:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text="{not json}")])

    monkeypatch.setattr(
        module.anthropic,
        "Anthropic",
        lambda: SimpleNamespace(messages=_Messages()),
    )

    with pytest.raises(module.ReleaseTweetError, match="Anthropic returned invalid JSON payload"):
        module.generate_tweet_and_prompt("v1.2.3", ["Feature"], "https://example.com/release")


def test_download_image_uses_timeout_and_wraps_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tweet_release_module(monkeypatch)
    seen: dict[str, object] = {}

    def fake_get(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        raise module.requests.ConnectionError("network down")

    monkeypatch.setattr(module.requests, "get", fake_get)

    with pytest.raises(module.ReleaseTweetError, match="image download failed"):
        module.download_image("https://example.com/image.png")

    assert seen["timeout"] == module.REQUEST_TIMEOUT_SECONDS


def test_main_posts_trimmed_tweet_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_tweet_release_module(monkeypatch)
    image_path = tmp_path / "release.png"
    image_path.write_bytes(b"image")
    posted: dict[str, str] = {}

    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("RELEASE_BODY", "## First\n## Second")
    monkeypatch.setenv("RELEASE_URL", "https://example.com/release")
    monkeypatch.setenv("FAL_KEY", "fal-key")
    monkeypatch.setattr(
        module,
        "generate_tweet_and_prompt",
        lambda *_args: {
            "tweet": "Introducing desloppify v1.2.3!\n" + "\n".join("- feature" for _ in range(80)),
            "image_prompt": "draw a release board",
        },
    )
    monkeypatch.setattr(module, "generate_image", lambda *_args: "https://example.com/img.png")
    monkeypatch.setattr(module, "download_image", lambda *_args: str(image_path))

    def fake_post(tweet_text: str, image_file: str, reply_text: str) -> None:
        posted["tweet"] = tweet_text
        posted["image"] = image_file
        posted["reply"] = reply_text

    monkeypatch.setattr(module, "post_tweet_with_reply", fake_post)

    module.main()

    assert posted["image"] == str(image_path)
    assert len(posted["tweet"]) <= 280
    assert posted["reply"] == "Release notes: https://example.com/release"
    assert not image_path.exists()


def test_post_tweet_with_reply_wraps_media_upload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tweet_release_module(monkeypatch)

    class _Api:
        @staticmethod
        def media_upload(_image_path):
            raise RuntimeError("upload boom")

    monkeypatch.setenv("TWITTER_API_KEY", "key")
    monkeypatch.setenv("TWITTER_API_SECRET", "secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TWITTER_ACCESS_SECRET", "access-secret")
    monkeypatch.setattr(module.tweepy, "API", lambda _auth: _Api())

    with pytest.raises(module.ReleaseTweetError, match="Twitter media upload failed: upload boom"):
        module.post_tweet_with_reply("tweet", "/tmp/image.png", "reply")


def test_post_tweet_with_reply_wraps_non_retryable_create_tweet_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tweet_release_module(monkeypatch)

    class _Media:
        media_id = "m1"

    class _Api:
        @staticmethod
        def media_upload(_image_path):
            return _Media()

    class _Client:
        @staticmethod
        def create_tweet(**_kwargs):
            raise RuntimeError("tweet boom")

    monkeypatch.setenv("TWITTER_API_KEY", "key")
    monkeypatch.setenv("TWITTER_API_SECRET", "secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TWITTER_ACCESS_SECRET", "access-secret")
    monkeypatch.setattr(
        module.tweepy,
        "errors",
        SimpleNamespace(TwitterServerError=type("TwitterServerError", (Exception,), {})),
    )
    monkeypatch.setattr(module.tweepy, "API", lambda _auth: _Api())
    monkeypatch.setattr(module.tweepy, "Client", lambda **_kwargs: _Client())

    with pytest.raises(module.ReleaseTweetError, match="Twitter create_tweet failed: tweet boom"):
        module.post_tweet_with_reply("tweet", "/tmp/image.png", "reply")


def test_main_exits_cleanly_on_bounded_release_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_tweet_release_module(monkeypatch)

    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("RELEASE_BODY", "## First")
    monkeypatch.setenv("RELEASE_URL", "https://example.com/release")
    monkeypatch.setenv("FAL_KEY", "fal-key")
    monkeypatch.setattr(
        module,
        "generate_tweet_and_prompt",
        lambda *_args: {
            "tweet": "Introducing desloppify v1.2.3!",
            "image_prompt": "draw a release board",
        },
    )
    monkeypatch.setattr(
        module,
        "generate_image",
        lambda *_args: (_ for _ in ()).throw(module.ReleaseTweetError("fal.ai request failed")),
    )

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 1
    assert "Release tweet failed: fal.ai request failed" in capsys.readouterr().err
