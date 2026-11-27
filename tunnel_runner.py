from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent
ENV_PATH = DIR / ".env"
BIN_CLOUDFLARED = DIR / "bin" / "cloudflared"


def update_env(url: str) -> None:
    if not ENV_PATH.is_file():
        return
    text = ENV_PATH.read_text(encoding="utf-8")
    if re.search(r"^#?\s*MINI_APP_URL=.*$", text, flags=re.MULTILINE):
        new_text = re.sub(
            r"^#?\s*MINI_APP_URL=.*$", f"MINI_APP_URL={url}", text, flags=re.MULTILINE
        )
    else:
        new_text = text.rstrip() + f"\nMINI_APP_URL={url}\n"
    ENV_PATH.write_text(new_text, encoding="utf-8")


def get_cmd() -> list[str]:
    cf_path = shutil.which("cloudflared")
    if cf_path:
        return [cf_path, "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:8000"]
    if BIN_CLOUDFLARED.is_file() and os.access(BIN_CLOUDFLARED, os.X_OK):
        return [str(BIN_CLOUDFLARED), "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:8000"]

    # Try downloading cloudflared
    try:
        BIN_CLOUDFLARED.parent.mkdir(parents=True, exist_ok=True)
        print("[*] Downloading cloudflared for Linux x86_64...")
        subprocess.run(
            [
                "curl",
                "-sSL",
                "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
                "-o",
                str(BIN_CLOUDFLARED),
            ],
            check=True,
            timeout=60,
        )
        BIN_CLOUDFLARED.chmod(0o755)
        print("[✓] cloudflared downloaded successfully.")
        return [str(BIN_CLOUDFLARED), "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:8000"]
    except Exception:
        pass

    # Fallback to localhost.run over SSH
    print("[*] Using zero-install SSH HTTPS tunnel (localhost.run)...")
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-R",
        "80:localhost:8000",
        "nokey@localhost.run",
    ]


def main() -> None:
    cmd = get_cmd()
    print("=" * 60)
    print("   CyberLearn Studio - Public HTTPS Tunnel   ")
    print("=" * 60)

    url_pattern = re.compile(
        r"https://(?!api\.)[a-zA-Z0-9.-]+\.(?:trycloudflare\.com|lhr\.life)"
    )

    while True:
        print(f"[*] Starting tunnel process: {' '.join(cmd[:2])} ...")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        url_detected = False
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()

                if not url_detected:
                    match = url_pattern.search(line)
                    if match:
                        detected_url = match.group(0)
                        url_detected = True
                        update_env(detected_url)
                        (DIR / ".tunnel_ready").write_text(detected_url, encoding="utf-8")
                        print("\n" + "=" * 64)
                        print(f" [✓] PUBLIC HTTPS URL: {detected_url}")
                        print(" [✓] AUTOMATICALLY UPDATED MINI_APP_URL IN .env!")
                        print("=" * 64 + "\n")

                if "Tunnel not found" in line:
                    print("\n[!] Cloudflare server reported 'Tunnel not found'. Terminating to generate a fresh tunnel...")
                    proc.terminate()
                    break
        except KeyboardInterrupt:
            print("\nStopping tunnel...")
            proc.terminate()
            proc.wait()
            break
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        print("[!] Tunnel process exited. Reconnecting in 3 seconds...")
        time.sleep(3)


if __name__ == "__main__":
    main()

