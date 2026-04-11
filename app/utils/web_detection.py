import os
import base64
import requests


def detect_web_presence(file_path: str) -> dict:
    """Use Google Vision API to find web matches for an image."""
    api_key = os.getenv("GOOGLE_VISION_API_KEY")
    if not api_key:
        return {"error": "Google Vision API key not configured."}

    try:
        with open(file_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "requests": [
                {
                    "image": {"content": image_data},
                    "features": [{"type": "WEB_DETECTION", "maxResults": 10}],
                }
            ]
        }

        response = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload,
            timeout=30,
        )

        if response.status_code != 200:
            return {"error": f"API error: {response.status_code} {response.text}"}

        data = response.json()
        web = data["responses"][0].get("webDetection", {})

        return {
            "best_guess_labels": [
                l.get("label") for l in web.get("bestGuessLabels", [])
            ],
            "full_matches": [
                {"url": m.get("url"), "score": m.get("score")}
                for m in web.get("fullMatchingImages", [])
            ],
            "partial_matches": [
                {"url": m.get("url"), "score": m.get("score")}
                for m in web.get("partialMatchingImages", [])
            ],
            "pages_with_image": [
                {"url": p.get("url"), "title": p.get("pageTitle")}
                for p in web.get("pagesWithMatchingImages", [])
            ],
            "visually_similar": [
                {"url": m.get("url")}
                for m in web.get("visuallySimilarImages", [])
            ],
        }

    except Exception as e:
        return {"error": str(e)}