"""Exercise real HTTP services and the Textual UI, saving a reviewable screenshot."""
import os

# Render the preview in color even when the checking shell has NO_COLOR set.
# The interactive app itself continues to respect the user's terminal settings.
os.environ.pop("NO_COLOR", None)
os.environ["COLORTERM"] = "truecolor"
os.environ["TERM"] = "xterm-256color"

import asyncio
from pathlib import Path

import httpx
from textual.widgets import Static

from astro.tui import AstroVitalsApp

OUT = Path(__file__).parent / "previews"


async def wait_for(client, predicate, timeout=12):
    for _ in range(timeout * 4):
        state = (await client.get("http://127.0.0.1:8000/api/v1/state")).json()
        if predicate(state):
            return state
        await asyncio.sleep(0.25)
    raise AssertionError("The expected state was not reached within the timeout period.")


async def main():
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
        await client.post("http://127.0.0.1:8002/control", json={"scenario": "cabin", "paused": False})
        await wait_for(client, lambda s: "ambiental" in s["assessment"]["title"])
        app = AstroVitalsApp()
        async with app.run_test(size=(140, 48)) as pilot:
            await pilot.pause(1.2)
            assert "ambiental" in str(app.query_one("#hypothesis", Static).render())
            app.save_screenshot("consola-cabina.svg", path=str(OUT))
            await pilot.press("a")
            acknowledged = (await client.get("http://127.0.0.1:8000/api/v1/state")).json()
            assert any("reconocida" in e["text"] for e in acknowledged["events"])
            assert acknowledged["assessment"]["level"] == "alert"
            await pilot.press("6")
            state = await wait_for(client, lambda s: s["latest"]["source"] == "bidmc")
            assert state["latest"]["co2"] is None
            assert state["latest"]["dose_rate"] is None
            assert state["latest"]["original_time_s"] is not None
            await pilot.pause(1.2)
            app.save_screenshot("consola-bidmc.svg", path=str(OUT))
            await pilot.press("p")
            await wait_for(client, lambda s: s["age_s"] > 5)
            await pilot.pause(1.2)
            assert "desactualizada" in str(app.query_one("#hypothesis", Static).render())
            await pilot.press("4")
            solar = await wait_for(client, lambda s: s["latest"]["dose_rate"] is not None and s["latest"]["dose_rate"] > 40)
            await pilot.press("s")
            sheltered = await wait_for(client, lambda s: s["latest"]["dose_rate"] < 10)
            assert sheltered["dose_total"] >= solar["dose_total"]
            await pilot.press("5")
            missing = await wait_for(client, lambda s: s["latest"]["hr"] is None)
            assert missing["assessment"]["level"] == "unknown"
            await pilot.resize_terminal(100, 32)
            await pilot.pause(1.2)
            app.save_screenshot("consola-compacta.svg", path=str(OUT))
            await pilot.press("1")
            await pilot.pause(1)
    print("OK: TUI, API scenarios, BIDMC, signal loss, data age, recognition, and dose/shelter.")
    print(f"Screenshots: {OUT}")

if __name__ == "__main__":
    asyncio.run(main())
