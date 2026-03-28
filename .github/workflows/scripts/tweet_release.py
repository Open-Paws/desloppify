#!/usr/bin/env python3
"""
Generate an excalidraw-style release image via fal.ai and tweet it.

Expects env vars:
  RELEASE_TAG, RELEASE_BODY, RELEASE_URL
  FAL_KEY
  ANTHROPIC_API_KEY
  TWITTER_API_KEY, TWITTER_API_SECRET,
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""

import json
import os
import re
import sys
import tempfile
import time

import anthropic
import requests
import tweepy

REQUEST_TIMEOUT_SECONDS = 30


class ReleaseTweetError(RuntimeError):
    """Stage-specific failure surfaced by the release tweet workflow."""


# ── Extract section headers from release markdown ────────────────────────────

def extract_headers(body: str) -> list[str]:
    """Pull ## headers from the release body."""
    return [
        line.lstrip("#").strip()
        for line in body.splitlines()
        if line.startswith("## ")
    ]


# ── Use Claude to write the tweet + image prompt ─────────────────────────────

def generate_tweet_and_prompt(tag: str, headers: list[str], url: str) -> dict:
    """Ask Claude to produce a tweet and an image-gen prompt."""
    headers_text = "\n".join(f"- {h}" for h in headers)
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""You're writing a tweet and an image prompt for a software release announcement.

Project: desloppify — a CLI tool that tracks codebase health and technical debt.
Release: {tag}
Release URL: {url}

Feature headers from the release notes:
{headers_text}

Please produce JSON with exactly two keys:

1. "tweet": Format MUST be:
   Line 1: "Introducing desloppify {tag}!"
   Then as many short bullet points as you can fit (one per line, each starting with "- ").
   Each bullet should be a very short summary of a feature (3-6 words).
   The ENTIRE tweet MUST be under 280 characters. The release link will go in a follow-up reply.
   No hashtags. No URLs. Pack in as many features as possible while keeping bullets scannable.

2. "image_prompt": A prompt for an image generation model to create a 1:1 excalidraw-style
   whiteboard illustration. It should be fun and whimsical like a waitbutwhy blog illustration —
   hand-drawn stick figures, arrows, wobbly boxes, funny labels. The illustration should visually
   represent the key features from the release. Include some readable text labels on the drawing
   that reference the actual features (e.g. "C++", "Rust", "anti-gaming").
   Keep the style loose, sketchy, black-and-white with maybe one or two accent colors.
   The overall vibe should be "someone explaining the release on a whiteboard with too much enthusiasm".

Return ONLY valid JSON, no markdown fences.""",
                }
            ],
        )
    except Exception as exc:
        raise ReleaseTweetError(f"Anthropic request failed: {exc}") from exc

    try:
        text = msg.content[0].text
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ReleaseTweetError("Anthropic response did not include text content") from exc
    # Strip markdown fences if Claude adds them anyway
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    try:
        result = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ReleaseTweetError("Anthropic returned invalid JSON payload") from exc
    if not isinstance(result, dict):
        raise ReleaseTweetError("Anthropic returned a non-object JSON payload")
    return result


# ── Generate image via fal.ai Nano Banana 2 ──────────────────────────────────

FAL_ENDPOINT = "https://fal.run/fal-ai/nano-banana-2"


def generate_image(prompt: str, api_key: str) -> str:
    """Call fal.ai and return the image URL."""
    try:
        resp = requests.post(
            FAL_ENDPOINT,
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
                "num_images": 1,
                "aspect_ratio": "1:1",
                "resolution": "1K",
                "output_format": "png",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise ReleaseTweetError(f"fal.ai request failed: {exc}") from exc
    if not resp.ok:
        raise ReleaseTweetError(f"fal.ai error {resp.status_code}: {resp.text}")

    try:
        images = resp.json().get("images", [])
    except (ValueError, AttributeError) as exc:
        raise ReleaseTweetError("fal.ai returned invalid JSON payload") from exc
    if not images:
        raise ReleaseTweetError("fal.ai returned no images")
    image_url = images[0].get("url") if isinstance(images[0], dict) else None
    if not isinstance(image_url, str) or not image_url:
        raise ReleaseTweetError("fal.ai returned an image without a URL")
    return image_url


def download_image(url: str) -> str:
    """Download image to a temp file and return the path."""
    try:
        resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ReleaseTweetError(f"image download failed: {exc}") from exc
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    try:
        for chunk in resp.iter_content(8192):
            if chunk:
                tmp.write(chunk)
    except requests.RequestException as exc:
        os.unlink(tmp.name)
        raise ReleaseTweetError(f"image download failed while streaming: {exc}") from exc
    finally:
        tmp.close()
    return tmp.name


# ── Post tweet with image ────────────────────────────────────────────────────

def post_tweet_with_reply(tweet_text: str, image_path: str, reply_text: str):
    """Post main tweet with image, then reply with the release link."""
    # v1.1 auth for media upload
    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    api_v1 = tweepy.API(auth)

    # Upload image
    try:
        media = api_v1.media_upload(image_path)
    except Exception as exc:
        raise ReleaseTweetError(f"Twitter media upload failed: {exc}") from exc
    print(f"Uploaded media: {media.media_id}")

    # v2 client for tweeting
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    # Main tweet with image (retry on transient errors)
    for attempt in range(3):
        try:
            response = client.create_tweet(
                text=tweet_text,
                media_ids=[media.media_id],
            )
            break
        except tweepy.errors.TwitterServerError as exc:
            if attempt < 2:
                print(f"  Twitter 5xx error, retrying in {5 * (attempt + 1)}s...")
                time.sleep(5 * (attempt + 1))
            else:
                raise ReleaseTweetError("Twitter create_tweet failed after retries") from exc
        except Exception as exc:
            raise ReleaseTweetError(f"Twitter create_tweet failed: {exc}") from exc

    tweet_id = response.data["id"]
    print(f"Posted tweet: https://twitter.com/i/web/status/{tweet_id}")

    # Reply with release link
    for attempt in range(3):
        try:
            reply = client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id,
            )
            break
        except tweepy.errors.TwitterServerError as exc:
            if attempt < 2:
                print(f"  Twitter 5xx error, retrying in {5 * (attempt + 1)}s...")
                time.sleep(5 * (attempt + 1))
            else:
                raise ReleaseTweetError("Twitter reply failed after retries") from exc
        except Exception as exc:
            raise ReleaseTweetError(f"Twitter reply failed: {exc}") from exc

    reply_id = reply.data["id"]
    print(f"Posted reply: https://twitter.com/i/web/status/{reply_id}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    tag = os.environ["RELEASE_TAG"]
    body = os.environ["RELEASE_BODY"]
    url = os.environ["RELEASE_URL"]

    headers = extract_headers(body)
    if not headers:
        print("No ## headers found in release body, skipping tweet.")
        sys.exit(0)

    print(f"Release: {tag}")
    print(f"Headers: {headers}")

    image_path: str | None = None
    try:
        # Step 1: Generate tweet text + image prompt via Claude
        print("\nGenerating tweet and image prompt...")
        result = generate_tweet_and_prompt(tag, headers, url)
        tweet_text = result["tweet"]
        image_prompt = result["image_prompt"]

        print(f"\nTweet: {tweet_text}")
        print(f"\nImage prompt: {image_prompt[:200]}...")

        # Step 2: Generate image via fal.ai
        print("\nGenerating image...")
        fal_key = os.environ["FAL_KEY"]
        image_url = generate_image(image_prompt, fal_key)
        print(f"Image URL: {image_url}")

        image_path = download_image(image_url)
        print(f"Downloaded to: {image_path}")

        # Step 3: Post main tweet with image, reply with release link
        if len(tweet_text) > 280:
            lines = tweet_text.strip().splitlines()
            while len(chr(10).join(lines)) > 280 and len(lines) > 1:
                lines.pop()
            tweet_text = chr(10).join(lines)

        reply_text = f"Release notes: {url}"

        print(f"\nPosting tweet ({len(tweet_text)} chars):")
        print(tweet_text)
        print(f"\nReply: {reply_text}")
        post_tweet_with_reply(tweet_text, image_path, reply_text)
    except ReleaseTweetError as exc:
        print(f"Release tweet failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

    print("\nDone!")


if __name__ == "__main__":
    main()
