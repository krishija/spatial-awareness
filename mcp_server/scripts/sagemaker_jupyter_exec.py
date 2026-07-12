#!/usr/bin/env python3
"""Execute shell on a SageMaker notebook instance via Jupyter REST.

Uses a short-lived presigned notebook URL (no long-lived secrets).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

import urllib.error
import urllib.request


def _aws_env() -> dict[str, str]:
    env = dict(os.environ)
    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        env.pop(k, None)
    return env


def presigned_url(notebook: str, region: str = "us-west-2") -> str:
    out = subprocess.check_output(
        [
            "aws",
            "sagemaker",
            "create-presigned-notebook-instance-url",
            "--notebook-instance-name",
            notebook,
            "--region",
            region,
            "--session-expiration-duration-in-seconds",
            "43200",
            "--query",
            "AuthorizedUrl",
            "--output",
            "text",
        ],
        env=_aws_env(),
        text=True,
    ).strip()
    return out


class JupyterSession:
    def __init__(self, authorized_url: str) -> None:
        parsed = urlparse(authorized_url)
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.jar = urllib.request.HTTPCookieProcessor()
        self.opener = urllib.request.build_opener(self.jar)
        # Hit the authorized URL once to set cookies
        req = urllib.request.Request(authorized_url, method="GET")
        with self.opener.open(req, timeout=60) as resp:
            resp.read(64)

    def _req(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = urljoin(self.base, path)
        data = None
        hdrs = {"Content-Type": "application/json", **(headers or {})}
        if body is not None:
            data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with self.opener.open(req, timeout=120) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {e.code} {path}: {err[:500]}") from e

    def list_contents(self, path: str = "") -> list[dict[str, Any]]:
        data = self._req("GET", f"/api/contents/{path}")
        return (data or {}).get("content") or []

    def start_kernel(self, name: str = "python3") -> str:
        data = self._req("POST", "/api/kernels", {"name": name})
        return str((data or {})["id"])

    def delete_kernel(self, kid: str) -> None:
        try:
            self._req("DELETE", f"/api/kernels/{kid}")
        except Exception:
            pass

    def execute(self, code: str, timeout_s: float = 600.0) -> dict[str, Any]:
        """Run code in a fresh kernel; return stdout/stderr/status."""
        kid = self.start_kernel()
        try:
            # Use terminals API if available — more reliable for long shell jobs.
            # Fall back to kernel execute via sessions is complex; use terminal.
            return self._run_via_terminal(code, timeout_s)
        finally:
            self.delete_kernel(kid)

    def _run_via_terminal(self, command: str, timeout_s: float) -> dict[str, Any]:
        # Create terminal
        term = self._req("POST", "/api/terminals")
        name = (term or {}).get("name")
        if not name:
            raise RuntimeError(f"no terminal: {term}")

        # Websocket would be ideal; without ws, write a script and poll a marker file.
        marker = f"/tmp/jupy_exec_{uuid.uuid4().hex}.done"
        log = f"/tmp/jupy_exec_{uuid.uuid4().hex}.log"
        script = f"/tmp/jupy_exec_{uuid.uuid4().hex}.sh"
        wrapped = (
            f"cat > {script} << 'JUPY_EOF'\n"
            f"{command}\n"
            f"JUPY_EOF\n"
            f"nohup bash {script} >{log} 2>&1; echo $? > {marker}\n"
        )
        # Use contents API to drop a launcher notebook that shells out — simpler:
        # put a shell script via contents and run with terminal POST isn't enough
        # without websocket. Use kernel execute with IPython ! bash.
        return self._run_via_kernel_shell(command, timeout_s, log_hint=log)

    def _run_via_kernel_shell(
        self, command: str, timeout_s: float, log_hint: str = ""
    ) -> dict[str, Any]:
        import base64

        kid = self.start_kernel()
        # Jupyter message protocol over HTTP isn't fully available; use
        # /api/sessions + websocket. Without websocket lib, write script via
        # contents API and poll with a tiny python kernel job that only checks.
        script_name = f"jupy_job_{uuid.uuid4().hex}.sh"
        path = f"SageMaker/{script_name}"
        body = {
            "type": "file",
            "format": "text",
            "content": (
                "#!/usr/bin/env bash\nset -eo pipefail\n"
                f"{command}\n"
                f"echo JUPY_EXIT:$?\n"
            ),
        }
        # Ensure SageMaker dir exists
        try:
            self._req(
                "PUT",
                "/api/contents/SageMaker",
                {"type": "directory"},
            )
        except Exception:
            pass
        self._req("PUT", f"/api/contents/{path}", body)

        marker = f"/home/ec2-user/SageMaker/{script_name}.done"
        log = f"/home/ec2-user/SageMaker/{script_name}.log"
        launcher = (
            "import subprocess, pathlib\n"
            f"script = pathlib.Path('/home/ec2-user/SageMaker/{script_name}')\n"
            f"log = pathlib.Path('{log}')\n"
            f"done = pathlib.Path('{marker}')\n"
            "done.unlink(missing_ok=True)\n"
            "with log.open('wb') as f:\n"
            "    p = subprocess.Popen(['bash', str(script)], stdout=f, stderr=subprocess.STDOUT)\n"
            "    print('PID', p.pid)\n"
            "    p.wait()\n"
            "    done.write_text(str(p.returncode))\n"
            "print(log.read_text()[-8000:])\n"
            "print('DONE_CODE', done.read_text())\n"
        )
        # Execute via temporary notebook cells using nbconvert-less approach:
        # POST /api/kernels/{id}/execute isn't standard. Use sessions + channels
        # requires websocket. Fallback: write a .py and run with `python` via
        # lifecycle — use `nohup` through contents + existing terminal list.

        # Simplest reliable path without websocket: upload script, then use
        # sagemaker's jupyter `terminals` websocket... skip.
        # Instead invoke via AWS SSM? Not available.
        #
        # Practical approach used previously: open websocket. Try `websocket-client`
        # if present; else use urllib only to start background via PUT + poll file.
        try:
            import websocket  # type: ignore
        except ImportError:
            # Background via a short kernel isn't possible; start with
            # create-presigned and hope `websocket-client` is installed locally.
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "websocket-client"]
            )
            import websocket  # type: ignore

        return self._ws_execute(kid, launcher, timeout_s)

    def _ws_execute(self, kid: str, code: str, timeout_s: float) -> dict[str, Any]:
        import websocket

        # Get token/cookie from jar
        cookies = []
        for c in self.jar.cookiejar:
            cookies.append(f"{c.name}={c.value}")
        cookie_hdr = "; ".join(cookies)
        ws_url = self.base.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/api/kernels/{kid}/channels"
        ws = websocket.create_connection(
            ws_url,
            header=[f"Cookie: {cookie_hdr}"],
            timeout=30,
        )
        msg_id = uuid.uuid4().hex
        header = {
            "msg_id": msg_id,
            "username": "ec2-user",
            "session": uuid.uuid4().hex,
            "msg_type": "execute_request",
            "version": "5.3",
        }
        payload = {
            "header": header,
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": False,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
            "channel": "shell",
            "buffers": [],
        }
        ws.send(json.dumps(payload))
        stdout: list[str] = []
        stderr: list[str] = []
        status = "unknown"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            ws.settimeout(max(1.0, deadline - time.time()))
            try:
                raw = ws.recv()
            except Exception:
                break
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = (msg.get("header") or {}).get("msg_type")
            parent = (msg.get("parent_header") or {}).get("msg_id")
            if parent and parent != msg_id:
                continue
            content = msg.get("content") or {}
            if mtype == "stream":
                text = content.get("text") or ""
                if content.get("name") == "stderr":
                    stderr.append(text)
                else:
                    stdout.append(text)
            elif mtype == "error":
                stderr.append("\n".join(content.get("traceback") or []))
                status = "error"
            elif mtype == "execute_reply":
                status = content.get("status") or "ok"
                break
            elif mtype == "status" and content.get("execution_state") == "idle":
                # may arrive before execute_reply
                pass
        ws.close()
        self.delete_kernel(kid)
        return {
            "status": status,
            "stdout": "".join(stdout),
            "stderr": "".join(stderr),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", default="spatial-scldm-gpu")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("command", nargs="?", help="shell command to run")
    args = ap.parse_args()

    url = presigned_url(args.notebook, args.region)
    sess = JupyterSession(url)
    if args.list:
        for item in sess.list_contents(""):
            print(item.get("name"), item.get("type"))
        return 0
    if not args.command:
        ap.error("command required unless --list")
    result = sess.execute(args.command, timeout_s=args.timeout)
    print(result.get("stdout") or "")
    if result.get("stderr"):
        print(result["stderr"], file=sys.stderr)
    print("STATUS", result.get("status"))
    return 0 if result.get("status") in ("ok", "unknown") else 1


if __name__ == "__main__":
    raise SystemExit(main())
