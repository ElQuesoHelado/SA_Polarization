"""Download the four open references used by the target-aware study (no credentials)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
    "chae-2024": ("Where do cross-cutting discussions happen?", "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0302030&type=printable"),
    "bessi-2016": ("Users Polarization on Facebook and Youtube", "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0159641&type=printable"),
    "lee-kim-2026": ("Asymmetric Dynamics of Partisan Warriors in YouTube Comments", "https://arxiv.org/pdf/2603.21776"),
    "tran-2022": ("Understanding Political Polarization Based on User Activity", "https://journals.sagepub.com/doi/pdf/10.1177/21582440221094587"),
}


def main():
    folder = ROOT / "pdfs" / "contexto"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    failed = []
    for key, (title, url) in REFERENCES.items():
        path = folder / f"{key}.pdf"
        if not path.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (academic bibliography download)"})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    content = response.read()
            except urllib.error.HTTPError as exc:
                if key != "tran-2022":
                    raise
                # Alternate public download route offered by the same publisher.
                alternative = url + "?download=true"
                try:
                    with urllib.request.urlopen(urllib.request.Request(alternative, headers={"User-Agent": "Mozilla/5.0"}), timeout=90) as response:
                        content = response.read()
                    url = alternative
                except urllib.error.HTTPError as retry:
                    failed.append({"id": key, "url": url, "status": "download_unavailable", "http_status": retry.code})
                    print(f"{key}: descarga rechazada por el editor (HTTP {retry.code}); no se guardó un PDF ficticio", flush=True)
                    continue
            if not content.startswith(b"%PDF-"):
                raise ValueError(f"{key}: el servidor no devolvió un PDF; no se guardó HTML")
            temporary = path.with_suffix(".download")
            temporary.write_bytes(content)
            temporary.replace(path)
        text = subprocess.run(["pdftotext", str(path), "-"], check=True, capture_output=True, text=True).stdout
        compact = " ".join(text.lower().split())
        if " ".join(title.lower().split()) not in compact:
            # PDF ligatures and line-break hyphens may vary; reject unrelated texts.
            words = title.lower().split()
            if sum(word in compact for word in words) < len(words) * 0.9:
                raise ValueError(f"{key}: título no verificado")
        records.append({"id": key, "title": title, "url": url, "local_pdf": str(path.relative_to(ROOT)),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
                        "verified_at": datetime.now(timezone.utc).isoformat()})
        print(f"{key}: PDF y título verificados ({path.stat().st_size:,} bytes)", flush=True)
    (ROOT / "docs" / "referencias" / "targeted-downloads.json").write_text(json.dumps({"downloaded": records, "unavailable": failed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
