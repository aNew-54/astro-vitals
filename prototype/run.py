"""Run a small, independent gateway -> API -> TUI demo."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parent


def port_is_busy(port):
    with socket.socket() as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser(description="ASTRO-VITALS — prototipo local")
    parser.add_argument("--services-only", action="store_true", help="Mantener API y pasarela sin abrir la TUI")
    parser.add_argument("--onboard-port", type=int, default=8000)
    parser.add_argument("--gateway-port", type=int, default=8002)
    args = parser.parse_args()
    if args.onboard_port == args.gateway_port:
        parser.error("La API y la pasarela necesitan puertos diferentes.")
    for port in (args.onboard_port, args.gateway_port):
        if not 1024 <= port <= 65535:
            parser.error("El puerto debe estar entre 1024 y 65535.")
        if port_is_busy(port):
            print(f"El puerto {port} está ocupado. Cierra la demo anterior o elige otros puertos.")
            return 1
    env = os.environ.copy()
    env["ONBOARD_URL"] = f"http://127.0.0.1:{args.onboard_port}"
    env["GATEWAY_URL"] = f"http://127.0.0.1:{args.gateway_port}"
    env["PYTHONUTF8"] = "1"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    processes, handles = [], []
    try:
        for module, port, log_name in (
            ("astro.api:app", args.onboard_port, "onboard.log"),
            ("astro.gateway:app", args.gateway_port, "gateway.log"),
        ):
            handle = (logs / log_name).open("w", encoding="utf-8")
            handles.append(handle)
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            processes.append(process)
        deadline = time.monotonic() + 20
        with httpx.Client(timeout=0.5, trust_env=False) as client:
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
        if args.services_only:
            print(f"API {env['ONBOARD_URL']} | Pasarela {env['GATEWAY_URL']} | Ctrl+C para detener", flush=True)
            while all(process.poll() is None for process in processes):
                time.sleep(0.5)
            raise RuntimeError("Un servicio se detuvo; revisa los logs.")
        from astro.tui import AstroVitalsApp
        AstroVitalsApp(env["ONBOARD_URL"], env["GATEWAY_URL"]).run()
        return 0
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError) as exc:
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
