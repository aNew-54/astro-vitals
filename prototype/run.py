"""Lanza la demo local de ASTRO-VITALS (API, pasarela, consola web o TUI)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import webbrowser

import httpx

ROOT = Path(__file__).resolve().parent


def port_is_busy(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def _replay_file(client: httpx.Client, onboard_url: str, gateway_url: str, replay_path: Path) -> int:
    from astro.adapters.loader import convert_file

    converted = convert_file(replay_path)
    records = converted.get("records", [])
    if not records:
        return 0

    # Pausar la pasarela simulada para no mezclar marcas temporales durante la reproducción.
    client.post(f"{gateway_url}/control", json={"paused": True}).raise_for_status()

    timestamps = [datetime.fromisoformat(rec["measured_at"]) for rec in records]
    latest_ts = max(timestamps)
    now = datetime.now(timezone.utc)
    if latest_ts > now:
        shift = (latest_ts - now) + timedelta(seconds=1)
        for rec, ts in zip(records, timestamps):
            rec["measured_at"] = (ts - shift).isoformat()

    sent = 0
    for rec in records:
        resp = client.post(f"{onboard_url}/api/v1/telemetry", json=rec)
        if resp.status_code < 300:
            sent += 1
    return sent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ASTRO-VITALS — prototipo local")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--services-only",
        action="store_true",
        help="Mantener API y pasarela sin abrir interfaz interactiva",
    )
    mode.add_argument(
        "--web",
        action="store_true",
        help="Servir la consola web en http://127.0.0.1:<onboard-port>/",
    )
    mode.add_argument(
        "--tui",
        action="store_true",
        help="Abrir la TUI de terminal (modo por defecto)",
    )
    parser.add_argument(
        "--environment",
        choices=("transit", "station", "rover", "base"),
        default="station",
        help="Perfil inicial de entorno simulado",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="Archivo CSV/TSV/JSON/JSONL a convertir y reproducir al iniciar",
    )
    parser.add_argument("--onboard-port", type=int, default=8000)
    parser.add_argument("--gateway-port", type=int, default=8002)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.onboard_port == args.gateway_port:
        parser.error("La API y la pasarela necesitan puertos diferentes.")
    for port in (args.onboard_port, args.gateway_port):
        if not 1024 <= port <= 65535:
            parser.error("El puerto debe estar entre 1024 y 65535.")
        if port_is_busy(port):
            print(f"El puerto {port} está ocupado. Cierra la demo anterior o elige otros puertos.")
            return 1

    if args.replay is not None and not args.replay.exists():
        print(f"No existe el archivo para --replay: {args.replay}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["ONBOARD_URL"] = f"http://127.0.0.1:{args.onboard_port}"
    env["GATEWAY_URL"] = f"http://127.0.0.1:{args.gateway_port}"
    env["PYTHONUTF8"] = "1"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    env.setdefault("ASTRO_DB_PATH", str(logs / "astro_vitals.db"))

    processes, handles = [], []
    try:
        for module, port, log_name in (
            ("astro.api:app", args.onboard_port, "onboard.log"),
            ("astro.gateway:app", args.gateway_port, "gateway.log"),
        ):
            handle = (logs / log_name).open("w", encoding="utf-8")
            handles.append(handle)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    module,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=ROOT,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            processes.append(process)

        deadline = time.monotonic() + 20
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            while time.monotonic() < deadline:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError(f"Un servicio no pudo iniciar. Revisa {logs}")
                try:
                    for url in (env["ONBOARD_URL"], env["GATEWAY_URL"]):
                        client.get(url + "/health").raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"No se pudo conectar con los servicios. Revisa {logs}")

            if args.environment:
                client.post(
                    f"{env['ONBOARD_URL']}/api/control",
                    json={"environment": args.environment},
                ).raise_for_status()

            if args.replay is not None:
                sent = _replay_file(client, env["ONBOARD_URL"], env["GATEWAY_URL"], args.replay)
                print(f"Replay cargado: {sent} registros desde {args.replay}", flush=True)

        if args.web:
            web_url = f"{env['ONBOARD_URL']}/"
            print(
                f"Consola web {web_url} | API {env['ONBOARD_URL']} | Pasarela {env['GATEWAY_URL']} | Ctrl+C para detener",
                flush=True,
            )
            try:
                webbrowser.open(web_url)
            except Exception:
                pass
            while all(process.poll() is None for process in processes):
                time.sleep(0.5)
            raise RuntimeError("Un servicio se detuvo; revisa los logs.")

        if args.services_only:
            print(
                f"API {env['ONBOARD_URL']} | Pasarela {env['GATEWAY_URL']} | Ctrl+C para detener",
                flush=True,
            )
            while all(process.poll() is None for process in processes):
                time.sleep(0.5)
            raise RuntimeError("Un servicio se detuvo; revisa los logs.")

        from astro.tui import AstroVitalsApp

        AstroVitalsApp(env["ONBOARD_URL"], env["GATEWAY_URL"]).run()
        return 0
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, ValueError, httpx.HTTPError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
