"""Install pinned public Kokoro assets, verifying their identities before use.

Run with the home server's Python after installing requirements-voice-local.txt.
This never saves keys, changes providers, or downloads during lesson playback.
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import data_dir
from tutoring.local_audio import ASSETS, MODEL


def main():
    target = data_dir() / "models" / MODEL
    target.mkdir(parents=True, exist_ok=True)
    provenance = {}
    for name, expected in ASSETS.items():
        url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/" + name
        dest = target / name
        if not dest.exists():
            print("Downloading", name, flush=True)
            temporary = dest.with_suffix(dest.suffix + ".partial")
            urllib.request.urlretrieve(url, temporary)
            with temporary.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                    raise ValueError("Model download failed its integrity check")
            temporary.replace(dest)
        with dest.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError("Existing model failed its integrity check")
        provenance[name] = {"url": url, "sha256": expected, "bytes": dest.stat().st_size}
    for name, url in {
        "LICENSE-model.txt": "https://www.apache.org/licenses/LICENSE-2.0.txt",
        "MODEL-CARD.md": "https://huggingface.co/hexgrad/Kokoro-82M/raw/main/README.md",
        "LICENSE-runtime.txt": "https://raw.githubusercontent.com/thewh1teagle/kokoro-onnx/main/LICENSE",
    }.items():
        urllib.request.urlretrieve(url, target / name)
    (target / "assets.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print("Local narration installed. Select it in Settings on the home computer.")


if __name__ == "__main__":
    main()
