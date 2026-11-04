import os
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime

from flask import Flask, render_template_string, redirect, url_for

# ----------------------------- Config -----------------------------
REPO_URL   = "https://github.com/pqwsel455/1.git"
REPO_DIR   = "1"
BINARY     = "1"
HOST       = "127.0.0.1"
PORT       = 8080

# ----------------------------- State ------------------------------
state = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "current_step": "",
    "logs_revealed": False,        # runner logs (4 double-clicks)
    "binary_revealed": False,      # binary logs (10 double-clicks)
}
log_lines = deque(maxlen=500)
binary_log_lines = deque(maxlen=500)   # NEW: output of ./1 only
state_lock = threading.Lock()


def log(msg: str, target=None):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with state_lock:
        log_lines.append(line)
        if target is not None:
            target.append(line)


def set_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def run_command(command, cwd=None, capture_key=None):
    """Run a command. If capture_key == 'binary', mirror its output into
    binary_log_lines as well."""
    sink = binary_log_lines if capture_key == "binary" else None
    log(f"$ {command}" + (f"   (cwd={cwd})" if cwd else ""))
    try:
        proc = subprocess.run(
            command, shell=True, cwd=cwd, check=True,
            capture_output=True, text=True
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                log("  " + line, target=sink)
        log(f"✅ succeeded: {command}")
        return True, proc.stdout
    except subprocess.CalledProcessError as e:
        if e.stdout:
            for line in e.stdout.splitlines():
                log("  " + line, target=sink)
        if e.stderr:
            for line in e.stderr.splitlines():
                log("  ❌ " + line, target=sink)
        log(f"❌ failed: {command} (rc={e.returncode})")
        return False, (e.stdout or "") + (e.stderr or "")


def run_pipeline():
    set_state(status="running", started_at=datetime.now(), finished_at=None,
              current_step="cloning")

    if os.path.isdir(REPO_DIR):
        log(f"Directory '{REPO_DIR}' already exists, removing...")
        ok, _ = run_command(f"rm -rf {REPO_DIR}")
        if not ok:
            set_state(status="failed", finished_at=datetime.now())
            return

    log(f"Cloning {REPO_URL}")
    ok, _ = run_command(f"git clone {REPO_URL} {REPO_DIR}")
    if not ok:
        set_state(status="failed", finished_at=datetime.now())
        return

    if not os.path.exists(os.path.join(REPO_DIR, BINARY)):
        log(f"❌ '{BINARY}' not found in {REPO_DIR}")
        set_state(status="failed", finished_at=datetime.now())
        return

    set_state(current_step="chmod")
    ok, _ = run_command(f"chmod +x {BINARY}", cwd=REPO_DIR)
    if not ok:
        set_state(status="failed", finished_at=datetime.now())
        return

    set_state(current_step="running binary")
    log(f"Running ./{BINARY}")
    # capture_key="binary" mirrors ./1's output into binary_log_lines
    ok, _ = run_command(f"./{BINARY}", cwd=REPO_DIR, capture_key="binary")
    if not ok:
        set_state(status="failed", finished_at=datetime.now())
        return

    set_state(status="success", current_step="done",
              finished_at=datetime.now())
    log("🎉 pipeline finished successfully")


# --------------------------- Flask app ----------------------------
app = Flask(__name__)

PAGE = """<!doctype html>
<html>
<head>
  <title>Runner UI</title>
  <meta http-equiv="refresh" content="3">
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, sans-serif;
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #fdf2f8 0%, #ede9fe 100%);
      padding: 24px;
      user-select: none;
      -webkit-user-select: none;
    }

    .face {
      width: 320px;
      height: 320px;
      position: relative;
      cursor: pointer;
      transition: transform 0.15s ease;
      -webkit-tap-highlight-color: transparent;
      outline: none;
    }
    .face:active { transform: scale(0.97); }

    .face-inner {
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 35% 30%, #ffe680 0%, #ffcc33 55%, #ffb300 100%);
      border-radius: 50%;
      box-shadow:
        inset -18px -18px 40px rgba(180, 100, 0, 0.25),
        inset 14px 14px 30px rgba(255, 255, 220, 0.6),
        0 20px 40px rgba(200, 120, 0, 0.35);
    }

    .eye {
      position: absolute;
      top: 38%;
      width: 52px;
      height: 62px;
      background: #1f2937;
      border-radius: 50%;
      box-shadow: inset 0 -6px 0 rgba(255,255,255,0.15);
    }
    .eye::after {
      content: "";
      position: absolute;
      top: 10px;
      left: 12px;
      width: 16px;
      height: 16px;
      background: #fff;
      border-radius: 50%;
      opacity: 0.9;
    }
    .eye.left  { left: 26%; }
    .eye.right { right: 26%; }

    .blush {
      position: absolute;
      top: 58%;
      width: 46px;
      height: 26px;
      background: #ff6b8a;
      border-radius: 50%;
      opacity: 0.55;
      filter: blur(3px);
    }
    .blush.left  { left: 12%; }
    .blush.right { right: 12%; }

    .smile {
      position: absolute;
      bottom: 24%;
      left: 50%;
      transform: translateX(-50%);
      width: 110px;
      height: 55px;
      border-bottom: 10px solid #1f2937;
      border-radius: 0 0 110px 110px;
    }

    .tuft {
      position: absolute;
      top: -14px;
      left: 50%;
      transform: translateX(-50%);
      width: 60px;
      height: 40px;
      background: #ffb300;
      border-radius: 50% 50% 0 0;
      box-shadow: 0 -4px 0 rgba(180,100,0,0.2);
    }

    .logs-panel {
      width: 100%;
      max-width: 900px;
      margin-top: 24px;
    }
    .logs-panel.hidden { display: none; }

    h2 { margin: 0 0 8px; font-size: 18px; color: #4c1d95; }
    pre {
      background: #0f172a;
      color: #e2e8f0;
      padding: 16px;
      border-radius: 12px;
      overflow: auto;
      max-height: 360px;
      font-size: 13px;
      line-height: 1.45;
      margin: 0;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
    }

    /* binary panel uses a slightly different accent so it's distinguishable */
    .binary-panel h2 { color: #b91c1c; }
    .binary-panel pre {
      background: #1c0f0f;
      color: #fecaca;
    }

    .status-line {
      margin-top: 20px;
      font-size: 14px;
      color: #6b7280;
      display: flex;
      gap: 16px;
      align-items: center;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 600;
      color: #fff;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .idle    { background: #6b7280; }
    .running { background: #2563eb; }
    .success { background: #16a34a; }
    .failed  { background: #dc2626; }
  </style>
</head>
<body>

  <div class="face" id="face" title="">
    <div class="face-inner"></div>
    <div class="tuft"></div>
    <div class="eye left"></div>
    <div class="eye right"></div>
    <div class="blush left"></div>
    <div class="blush right"></div>
    <div class="smile"></div>
  </div>

  <div class="status-line">
    <span class="badge {{ status }}">{{ status }}</span>
    <span>{% if step %}{{ step }}{% endif %}</span>
    {% if started %}<span>started {{ started }}</span>{% endif %}
    {% if finished %}<span>finished {{ finished }}</span>{% endif %}
  </div>

  <!-- Runner logs: revealed after 4 double-clicks -->
  <div class="logs-panel {% if not logs_revealed %}hidden{% endif %}" id="logs-panel">
    <h2>Logs</h2>
    <pre>{{ logs }}</pre>
  </div>

  <!-- Binary logs: revealed after 10 double-clicks -->
  <div class="logs-panel binary-panel {% if not binary_revealed %}hidden{% endif %}" id="binary-panel">
    <h2>Executable <code>1</code> Output</h2>
    <pre>{{ binary_logs }}</pre>
  </div>

  <script>
    // Double-click counter. 4 double-clicks -> runner logs.
    // 10 double-clicks -> binary (./1) output.
    // No visual feedback on individual clicks.
    (function () {
      const face        = document.getElementById('face');
      const runnerPanel = document.getElementById('logs-panel');
      const binaryPanel = document.getElementById('binary-panel');
      const RUNNER_AT   = 4;   // double-clicks to reveal runner logs
      const BINARY_AT   = 10;  // double-clicks to reveal ./1 output

      let dbls      = 0;
      let lastClick = 0;

      face.addEventListener('click', function () {
        const now = Date.now();
        if (now - lastClick < 350) {
          dbls += 1;
          lastClick = 0;
          if (dbls >= RUNNER_AT) runnerPanel.classList.remove('hidden');
          if (dbls >= BINARY_AT) binaryPanel.classList.remove('hidden');
        } else {
          lastClick = now;
        }
      });
    })();
  </script>

</body>
</html>
"""


@app.route("/")
def index():
    with state_lock:
        snapshot      = dict(state)
        logs          = "\n".join(log_lines) or "(no logs yet)"
        binary_logs   = "\n".join(binary_log_lines) or "(binary has produced no output yet)"
    return render_template_string(
        PAGE,
        status=snapshot["status"],
        step=snapshot["current_step"],
        started=snapshot["started_at"].strftime("%H:%M:%S") if snapshot["started_at"] else None,
        finished=snapshot["finished_at"].strftime("%H:%M:%S") if snapshot["finished_at"] else None,
        logs=logs,
        binary_logs=binary_logs,
        logs_revealed=snapshot["logs_revealed"],
        binary_revealed=snapshot["binary_revealed"],
    )


@app.route("/start", methods=["POST"])
def start():
    with state_lock:
        if state["status"] == "running":
            return redirect(url_for("index"))
    threading.Thread(target=run_pipeline, daemon=True).start()
    time.sleep(0.1)
    return redirect(url_for("index"))


# ----------------------------- Main -------------------------------
if __name__ == "__main__":
    log("Starting Flask UI on http://%s:%d" % (HOST, PORT))
    log("4 double-clicks = runner logs, 10 double-clicks = binary output.")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
