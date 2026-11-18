"""Record the bundled demo from a running local Streamlit application.

Install requirements-test.txt and start the app before running this script.
Optionally set PLAYWRIGHT_CHROMIUM_EXECUTABLE for a local Chromium binary.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import time

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "demo_media"
URL = os.environ.get("DEMO_APP_URL", "http://127.0.0.1:5000")


def caption(page, text):
    page.evaluate(
        """text => {
            let label = document.getElementById('demo-caption');
            if (!label) {
                label = document.createElement('div');
                label.id = 'demo-caption';
                Object.assign(label.style, {
                    position: 'fixed', bottom: '22px', left: '50%',
                    transform: 'translateX(-50%)', zIndex: '999999',
                    background: '#103c3c', color: 'white', padding: '12px 22px',
                    borderRadius: '9px', font: '600 18px sans-serif',
                    boxShadow: '0 3px 14px #0003', pointerEvents: 'none'
                });
                document.body.appendChild(label);
            }
            label.textContent = text;
        }""",
        text,
    )


def move_and_click(page, locator):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if not box:
        raise RuntimeError("Demo control is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
    page.wait_for_timeout(500)
    locator.click()


def main():
    MEDIA.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        with sync_playwright() as playwright:
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            browser = playwright.chromium.launch(
                headless=True, executable_path=executable, args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=temporary,
                record_video_size={"width": 1440, "height": 900},
            )
            page = context.new_page()
            started = time.monotonic()
            page.goto(URL, wait_until="domcontentloaded")
            sample = page.get_by_role("button", name="Explore sample workspace")
            sample.wait_for(timeout=60000)
            page.wait_for_timeout(1000)
            trim_start = time.monotonic() - started
            caption(page, "Start with your data or explore the sample workspace")
            page.wait_for_timeout(4000)

            caption(page, "Load five connected synthetic datasets")
            move_and_click(page, sample)
            page.get_by_role("tab", name="1 · Overview").wait_for(timeout=120000)
            page.mouse.move(1000, 110)
            caption(page, "Explore the workspace and quality overview")
            page.wait_for_timeout(4000)

            caption(page, "Explore detailed findings")
            move_and_click(page, page.get_by_role("tab", name="2 · Issue log"))
            page.get_by_text("Issue explorer").wait_for(timeout=60000)
            page.wait_for_timeout(3500)

            caption(page, "Review issues and choose safe fixes")
            move_and_click(page, page.get_by_role("tab", name="3 · Review & fix"))
            page.wait_for_timeout(3500)

            caption(page, "Preview and prepare your export")
            move_and_click(page, page.get_by_role("tab", name="4 · Preview & export"))
            page.wait_for_timeout(3500)
            video = page.video
            context.close()
            video_path = video.path()
            browser.close()

        mp4 = MEDIA / "smart_data_quality_demo.mp4"
        gif = MEDIA / "smart_data_quality_demo.gif"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(trim_start), "-i", video_path,
            "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4),
        ], check=True)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp4), "-filter_complex",
            "[0:v]fps=5,scale=960:-2:flags=lanczos,split[a][b];"
            "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a",
            "-loop", "0", str(gif),
        ], check=True)


if __name__ == "__main__":
    main()
