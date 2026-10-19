"""Verify the frozen runtime without opening WeChat, calling an AI, or installing a hook."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback


def check_frozen_runtime(report_path):
    report = {"ok": False, "checks": []}
    try:
        assert sys.platform == "win32" and getattr(sys, "frozen", False)
        for module in (
            "src.config", "src.bot", "src.web.server", "src.web.update", "src.web.api_handlers",
            "src.agent.engine", "src.skill.engine", "src.mcp.client", "src.mcp.manager",
            "src.im.plugins.feishu.adapter", "src.im.plugins.qqbot.adapter",
            "src.wechat.extract_key", "src.wechat.wcdb_backend", "src.wechat.db_crypto",
            "src.wechat.image_decrypt", "src.wechat.voice_decode", "src.wechat.content_codec",
            "src.voice.providers", "src.voice.realtime_relay", "src.voice.volc_relay",
            "webview", "pystray", "yaml", "cryptography.hazmat.primitives.ciphers.aead",
        ):
            importlib.import_module(module)
            report["checks"].append(f"import:{module}")

        import ctypes
        base = Path(sys._MEIPASS)
        dll = ctypes.WinDLL(str(base / "lib/wx_key.dll"))
        for name in ("InitializeHook", "PollKeyData", "CleanupHook"):
            assert getattr(dll, name)
        report["checks"].append("wx_key.dll:loads and exports present; hook NOT called")
        for relative in (
            "ui/dist/index.html", ".env.example", "favicon.ico",
            "lib/wasm/wasm_decrypt_service.js", "lib/wasm/wasm_video_decode.js",
            "lib/wasm/wasm_video_decode.wasm",
        ):
            assert (base / relative).is_file(), relative
            report["checks"].append(f"asset:{relative}")

        # Exercise the real HTTP handler on an ephemeral loopback-only test port.
        from http.server import HTTPServer
        import threading
        import urllib.request
        from src.web.server import _UIHandler
        server = HTTPServer(("127.0.0.1", 0), _UIHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with opener.open(url + "/api/load-config", timeout=10) as response:
                payload = json.load(response)
            assert payload["ok"] and not payload["config"]["auto_check_update"]
            assert not payload["config"]["ai_provider_api_key"]
            with opener.open(url + "/", timeout=10) as response:
                assert b"<html" in response.read().lower()
            report["checks"].append("loopback HTTP API and packaged React index:200")
            report["checks"].append("fresh config:no AI key; automatic update check disabled")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        report["ok"] = True
    except BaseException:
        report["error"] = traceback.format_exc()
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise SystemExit(1)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--inside":
        check_frozen_runtime(Path(sys.argv[2]))
        return
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/smoke_windows_exe.py dist/wx-assist_no_rag.exe")
    exe = Path(sys.argv[1]).resolve()
    result = Path("build/smoke-result.json").resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    result.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="wx-assist-exe-smoke-") as home:
        env = os.environ.copy()
        env["WEBOT_APP_HOME"] = home
        env["WEBOT_ENV_FILE"] = str(Path(home) / ".env")
        proc = subprocess.run(
            [str(exe), "--run-script", str(Path(__file__).resolve()), "--inside", str(result)],
            env=env, cwd=home, timeout=120, check=False,
        )
        if not result.is_file():
            raise SystemExit(f"Frozen process exited {proc.returncode} without a smoke report")
        report = json.loads(result.read_text(encoding="utf-8"))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if proc.returncode != 0 or not report["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
