#!/usr/bin/env python3

import os
import time
import json
import subprocess
import traceback
import dotenv
import shutil
import glob
import signal
import requests
import time

dotenv.load_dotenv()

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC



from appium.options.android import UiAutomator2Options
from appium import webdriver
from email.message import EmailMessage
import smtplib

# -------- CONFIG -------
GM_API_TOKEN    = os.getenv("GM_API_TOKEN")
GM_RECIPE_UUID  = os.getenv("GM_RECIPE_UUID")
EMAIL_USER      = os.getenv("EMAIL_USER")
EMAIL_PASS      = os.getenv("EMAIL_PASS")
EMAIL_TO        = os.getenv("EMAIL_TO")

TIKTOK_PACKAGE  = os.getenv("TIKTOK_PACKAGE",  "com.zhiliaoapp.musically")
TIKTOK_ACTIVITY = os.getenv("TIKTOK_ACTIVITY", "com.ss.android.ugc.aweme.splash.SplashActivity")
APPIUM_SERVER   = os.getenv("APPIUM_SERVER",   "http://localhost:4723/wd/hub")

INSTANCE_BOOT_TIMEOUT = int(os.getenv("INSTANCE_BOOT_TIMEOUT", "180"))  # seconds to wait for instance ONLINE
ADB_POLL_INTERVAL     = float(os.getenv("ADB_POLL_INTERVAL", "1.0"))
ADB_CONNECT_RETRIES   = int(os.getenv("ADB_CONNECT_RETRIES", "10"))

APPIUM_NODE_VERSION = os.getenv("APPIUM_NODE_VERSION", "20")

FORCE_DRIVER_INSTALL = os.getenv("FORCE_DRIVER_INSTALL", "") == "1"

android_guess_paths = [
    os.getenv("ANDROID_HOME"),
    os.getenv("ANDROID_SDK_ROOT"),
    os.path.expanduser("~/Library/Android/sdk"),
    os.path.expanduser("~/Android/Sdk"),
    os.path.expanduser("~/Downloads"),
]

ANDROID_HOME = next((p for p in android_guess_paths if p and os.path.exists(p)), None)
if not ANDROID_HOME:
    ANDROID_HOME = os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT") or os.path.expanduser("~/Downloads")

os.environ["ANDROID_HOME"] = ANDROID_HOME
os.environ["ANDROID_SDK_ROOT"] = os.environ.get("ANDROID_SDK_ROOT", ANDROID_HOME)

android_paths = [
    os.path.join(ANDROID_HOME, "platform-tools"),
    os.path.join(ANDROID_HOME, "emulator"),
    os.path.join(ANDROID_HOME, "tools"),
    os.path.join(ANDROID_HOME, "tools", "bin"),
]

current_path = os.environ.get("PATH", "")
prepend_paths = ":".join([p for p in android_paths if p and os.path.exists(p)])
if prepend_paths:
    os.environ["PATH"] = prepend_paths + ":" + current_path

print(f"ANDROID_HOME set to: {os.environ.get('ANDROID_HOME')}")
print(f"ANDROID_SDK_ROOT set to: {os.environ.get('ANDROID_SDK_ROOT')}")
print("PATH (start):", os.environ["PATH"].split(":")[0:3])

# -------- UTILITIES -------
def send_email(subject, body):
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_TO]):
        print("Email config missing, skipping email.")
        return
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print("Sent email.")
    except Exception as e:
        print("Failed to send email:", e)

def run_cmd(cmd, check=True, capture_output=True, text=True, timeout=None, env=None):
    """Run a list-form command (no shell) and return CompletedProcess."""
    if isinstance(cmd, (list, tuple)):
        print("CMD >", " ".join(cmd))
    else:
        print("CMD >", str(cmd))
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text, timeout=timeout, env=env)

def run_shell(zsh_command, timeout=None, env=None):
    """Run a shell zsh command that loads nvm etc. Returns CompletedProcess. Uses /bin/zsh -lc."""
    print("SHELL >", zsh_command)
    return subprocess.run(zsh_command, shell=True, check=True, capture_output=True, text=True, executable="/bin/zsh", timeout=timeout, env=env)

def start_instance_from_recipe():
    if not GM_API_TOKEN or not GM_RECIPE_UUID:
        raise RuntimeError("GM_API_TOKEN or GM_RECIPE_UUID missing in environment")
    url = f"https://api.geny.io/cloud/v1/recipes/{GM_RECIPE_UUID}/start-disposable"
    payload = {"instance_name": f"nudge-{int(time.time())}"}
    try:
        r = run_cmd(
            ["curl", "-s", "-X", "POST", "-H", f"x-api-token: {GM_API_TOKEN}",
             "-H", "Content-Type: application/json", "-d", json.dumps(payload), url]
        )
        data = json.loads(r.stdout)
    except subprocess.CalledProcessError as e:
        print("Failed starting instance:", e.stdout, e.stderr)
        raise
    except Exception as e:
        print("Unexpected error calling start-disposable:", e, getattr(e, "stdout", None))
        raise
    instance_uuid = data.get("uuid")
    adb_url = data.get("adb_url")
    print("Started instance:", instance_uuid, "adb_url:", adb_url)
    return instance_uuid

def stop_instance(instance_uuid):
    if not instance_uuid:
        return
    url = f"https://api.geny.io/cloud/v1/instances/{instance_uuid}/stop-disposable"
    try:
        run_cmd([
            "curl", "-s", "-X", "POST",
            "-H", "Content-Type: application/json;charset=utf-8",
            "-H", f"x-api-token: {GM_API_TOKEN}",
            "--data", "{}",
            url
        ])
        print("Stopped instance:", instance_uuid)
    except Exception as e:
        print("Failed to stop instance:", e)


def wait_instance_online(instance_uuid, timeout=INSTANCE_BOOT_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cp = run_cmd(["gmsaas", "--format", "json", "instances", "get", instance_uuid])
            data = json.loads(cp.stdout)
            instance = data.get("instance", {})
            state = instance.get("state", "")
            if state == "ONLINE":
                print("Instance is ONLINE")
                return instance
            else:
                print("Instance state:", state)
        except Exception as e:
            print("Instance not ready yet, retrying...", e)
        time.sleep(2)
    raise TimeoutError("Timed out waiting for instance to become ONLINE")

def ensure_gmsaas_authenticated():
    try:
        run_cmd(["gmsaas", "auth", "token", GM_API_TOKEN], timeout=20)
        #run_cmd(["gmsaas", "doctor"], timeout=20)
        print("gmsaas authenticated.")
    except Exception as e:
        print("gmsaas auth attempted:", e)

def adb_connect_via_gmsaas(instance_uuid):
    ensure_gmsaas_authenticated()
    for attempt in range(ADB_CONNECT_RETRIES):
        try:
            cp = run_cmd(["gmsaas", "--format", "json", "instances", "adbconnect", instance_uuid])
            data = json.loads(cp.stdout)
            adb_serial = data.get("instance", {}).get("adb_serial")
            if adb_serial:
                print("ADB tunnel ready:", adb_serial)
                return adb_serial
        except Exception as e:
            print(f"adbconnect attempt {attempt+1} failed, retrying:", e)
        time.sleep(ADB_POLL_INTERVAL)
    raise RuntimeError("Failed to establish adb tunnel via gmsaas")

def adb_disconnect_via_gmsaas(instance_uuid, serial):
    try:
        run_cmd(["gmsaas", "instances", "adbdisconnect", instance_uuid], check=False)
    except Exception:
        pass
    try:
        run_cmd(["adb", "disconnect", serial], check=False)
    except Exception:
        pass

def _appium_status_ok(status_url="http://localhost:4723/wd/hub/status"):
    try:
        resp = requests.get(status_url, timeout=1)
        # If server responds 200, we assume it’s ready
        return resp.status_code == 200
    except requests.RequestException:
        return False


def find_nvm_appium_bin(preferred_node_prefix=APPIUM_NODE_VERSION):
    """
    Find Appium binary under ~/.nvm/versions/node/v{preferred_node_prefix}*
    Returns tuple
    """
    node_dirs = glob.glob(os.path.expanduser(f"~/.nvm/versions/node/v{preferred_node_prefix}*"))
    node_bin_dir = None
    if node_dirs:
        node_bin_dir = os.path.join(node_dirs[0], "bin")
        appium_bin = os.path.join(node_bin_dir, "appium")
        node_bin = os.path.join(node_bin_dir, "node")
        if os.path.exists(appium_bin) and os.access(appium_bin, os.X_OK):
            return appium_bin, node_bin_dir
    which_appium = shutil.which("appium")
    which_node = shutil.which("node")
    return which_appium, os.path.dirname(which_node) if which_node else None

def kill_port(port):
    """Kill any processes listening on port"""
    try:
        out = subprocess.check_output(f"lsof -ti:{port}", shell=True).decode().strip()
        if not out:
            return
        pids = [p for p in out.splitlines() if p.strip()]
        for pid in pids:
            try:
                pgid = int(subprocess.check_output(f"ps -o pgid= {pid}", shell=True).decode().strip())
                print(f"Killing process group {pgid} for pid {pid}")
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    print(f"Killing pid {pid}")
                    os.kill(int(pid), signal.SIGKILL)
                except Exception as e:
                    print("Failed to kill pid", pid, e)
    except subprocess.CalledProcessError:
        pass
    except Exception as e:
        print("Could not kill port:", e)

def start_appium_server(timeout=40):
    import shutil

    appium_bin, node_bin_dir = find_nvm_appium_bin()
    if not appium_bin:
        raise RuntimeError("Could not find Appium binary. Install Appium globally or via nvm.")

    env = os.environ.copy()
    if node_bin_dir:
        env["PATH"] = node_bin_dir + ":" + env.get("PATH", "")

    kill_port(4723)

    try:
        print("Checking installed Appium drivers:", appium_bin)
        res = subprocess.run(
            [appium_bin, "driver", "list", "--installed"],
            capture_output=True, text=True, env=env, check=True
        )
        stdout = res.stdout.strip()
        if "uiautomator2" not in stdout:
            msg = "uiautomator2 driver missing."
            if os.getenv("CI") or FORCE_DRIVER_INSTALL:
                print(msg, "Installing/updating because CI or FORCE_DRIVER_INSTALL is set.")

                subprocess.run([appium_bin, "driver", "update", "uiautomator2"], env=env, check=True)
            else:
                print(msg, "Skipping automatic install on local machine. Set FORCE_DRIVER_INSTALL=1 to force.")
        else:
            print("uiautomator2 driver already installed. Skipping installation.")
    except subprocess.CalledProcessError as e:
        print("Could not list drivers:", e.stdout, e.stderr)
        if os.getenv("CI") or FORCE_DRIVER_INSTALL:
            print("Attempting to update/install uiautomator2 in forced mode.")
            subprocess.run([appium_bin, "driver", "update", "uiautomator2"], env=env, check=True)

    appium_cmd = [appium_bin, "--log-level", "error", "--base-path", "/wd/hub"]
    print("Starting Appium:", " ".join(appium_cmd))
    proc = subprocess.Popen(
        appium_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, preexec_fn=os.setsid
    )

    start = time.time()
    while time.time() - start < timeout:
        if _appium_status_ok():
            print("Appium server ready.")
            try:
                node_v = subprocess.run(
                    [os.path.join(node_bin_dir, "node"), "-v"] if node_bin_dir else ["node", "-v"],
                    capture_output=True, text=True, env=env, check=True
                )
                print("Node in use:", node_v.stdout.strip())
            except Exception:
                pass
            try:
                drv = subprocess.run(
                    [appium_bin, "driver", "list", "--installed"],
                    capture_output=True, text=True, env=env, check=True
                )
                print("Installed drivers snippet:", drv.stdout.strip().splitlines()[:5])
            except Exception:
                pass
            return True, proc

        print("Appium is not ready yet...")
        time.sleep(1)

    stderr = ""
    try:
        _, stderr = proc.communicate(timeout=1)
        stderr = stderr.decode(errors="ignore")
    except Exception:
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    raise RuntimeError("Appium failed to start. Stderr snippet:\n" + (stderr[:2000] if stderr else "<no-stderr>"))

def stop_appium_server(proc):
    if not proc:
        return
    try:
        print("Stopping Appium process group...")
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        time.sleep(1)
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception as e:
        print("Error stopping Appium process:", e)

# -------- APPIUM DRIVER --------
def make_driver_with_serial(serial):
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = "GenymotionSaaS"
    options.udid = serial
    options.app_package = TIKTOK_PACKAGE
    options.app_activity = TIKTOK_ACTIVITY
    options.no_reset = True
    options.new_command_timeout = 300

    options.enforce_app_install = False
    options.skipDeviceInitialization = True
    options.skipServerInstallation = True
    options.disableWindowAnimation = True


    options.uiautomator2_server_install_timeout = 60000  # 1 minute

    try:
        driver = webdriver.Remote(APPIUM_SERVER, options=options)
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        msg = str(e)
        if "Could not find a driver for automationName 'UIAutomator2'" in msg:
            appium_bin, node_bin = find_nvm_appium_bin()
            if os.getenv("CI") or FORCE_DRIVER_INSTALL:
                print("UIAutomator2 driver missing — installing via appium binary...")
                subprocess.run([appium_bin, "driver", "install", "uiautomator2"], check=True)
                # retry
                driver = webdriver.Remote(APPIUM_SERVER, options=options)
                driver.implicitly_wait(5)
                return driver
            else:
                raise RuntimeError(
                    "Appium reports UIAutomator2 driver missing. Locally, prefer to install it manually:\n"
                    f"  {appium_bin} driver install uiautomator2\n"
                    "Or set FORCE_DRIVER_INSTALL=1 to let this script attempt to install it."
                )
        raise

# -------- TIKTOK -------
def load_nudge_targets():
    """
    Load usernames to nudge in priority order.
    Sources tried:
      1) Environment variable NUDGE_USERS (comma separated)
      2) File ./nudge_users.txt (one username per line)
    Returns a list of cleaned usernames (max 200).
    """
    env = os.getenv("NUDGE_USERS")
    targets = []
    if env:
        targets = [t.strip() for t in env.split(",") if t.strip()]
    elif os.path.exists("nudge_users.txt"):
        with open("nudge_users.txt", "r", encoding="utf-8") as f:
            targets = [line.strip() for line in f if line.strip()]
    cleaned = []
    for t in targets:
        if len(cleaned) >= 200:
            break
        cleaned.append(t)
    return cleaned


TOP_HEADER_Y_RATIO = 0.12
CLICK_STABILIZE = 0.45
DEFAULT_PER_ACTION_TIMEOUT = 1.5
INBOX_OPEN_TIMEOUT = 1
SCROLL_ATTEMPTS_PER_USER = 1
SCROLL_PAUSE = 0.25



def open_inbox_and_wait(driver, open_timeout=INBOX_OPEN_TIMEOUT):
    """Open the Inbox and wait for a scrollable inbox container to appear."""
    print("[run] Trying to open Inbox...")

    def _tap_center(el):
        r = el.rect
        cx = int(r["x"] + r["width"] / 2)
        cy = int(r["y"] + r["height"] / 2)
        driver.execute_script("mobile: tap", {"x": cx, "y": cy})

    def _tap_xy(x, y):
        driver.execute_script("mobile: tap", {"x": int(x), "y": int(y)})

    def _click_or_tap(el):
        try:
            el.click()
            return True
        except Exception as e:
            print("[run] normal click failed, trying tap:", e)
            try:
                _tap_center(el)
                return True
            except Exception as e2:
                print("[run] tap failed:", e2)
                return False

    def _dismiss_possible_overlay():
        """
        Tap slightly above the center of the screen to dismiss promo/pop-up overlays.
        """
        try:
            size = driver.get_window_size()
            x = int(size["width"] * 0.5)
            y = int(size["height"] * 0.38)

            print(f"[run] Trying overlay dismiss tap at ({x}, {y})")
            _tap_xy(x, y)
            time.sleep(0.7)
            return True
        except Exception as e:
            print("[run] overlay dismiss tap failed:", e)
            return False

    def _try_open_inbox_once():
        attempts = [
            (By.ID, "com.zhiliaoapp.musically:id/n18"),
            (By.ID, "com.zhiliaoapp.musically:id/mso"),
            (By.XPATH, "//android.widget.TextView[@text='Inbox']"),
            (By.ID, "com.zhiliaoapp.musically:id/myf"),
        ]

        for by, sel in attempts:
            try:
                print(f"[run] trying selector {by} / {sel}")

                el = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((by, sel))
                )

                if el and el.is_displayed():
                    print("[run] Clicking inbox element.")
                    if not _click_or_tap(el):
                        continue

                    time.sleep(0.8)
                    c = wait_for_inbox_container(driver, timeout=open_timeout)
                    if c:
                        print("[run] Inbox container available.")
                        return c
                    else:
                        print("[run] Inbox click succeeded but container not found yet.")

            except Exception as e:
                print("[run] inbox selector failed:", e)
                continue

        try:
            print("[run] Trying bottom-nav index fallback...")
            nav_children = driver.find_elements(
                By.XPATH,
                "//*[@resource-id='com.zhiliaoapp.musically:id/mym']/*"
            )

            print(f"[run] bottom-nav child count: {len(nav_children)}")

            if len(nav_children) >= 4:
                inbox_el = nav_children[3]  # 4th item
                if _click_or_tap(inbox_el):
                    time.sleep(0.8)
                    c = wait_for_inbox_container(driver, timeout=open_timeout)
                    if c:
                        print("[run] Inbox container available (bottom-nav fallback).")
                        return c
                    else:
                        print("[run] bottom-nav click worked but container not found.")
            else:
                print("[run] bottom-nav fallback: not enough children found.")
        except Exception as e:
            print("[run] bottom-nav fallback failed:", e)

        try:
            print("[run] Trying coordinate fallback for Inbox...")
            size = driver.get_window_size()

            x = int(size["width"] * 0.7)
            y = int(size["height"] * 0.94)

            _tap_xy(x, y)
            time.sleep(0.8)

            c = wait_for_inbox_container(driver, timeout=open_timeout)
            if c:
                print("[run] Inbox container available (coordinate fallback).")
                return c
        except Exception as e:
            print("[run] coordinate inbox tap failed:", e)

        return None

    c = _try_open_inbox_once()
    if c:
        return c

    print("[run] Inbox not opened. Trying to dismiss possible overlay...")
    _dismiss_possible_overlay()

    c = _try_open_inbox_once()
    if c:
        print("[run] Inbox opened after dismissing overlay.")
        return c

    print("[run] Could not open inbox.")
    return None

def wait_for_inbox_container(driver, timeout=INBOX_OPEN_TIMEOUT):
    """
    Look for a visible scrollable inbox container
    """
    check_xpath = ("//*[(@scrollable='true') or "
                   "contains(@class,'RecyclerView') or "
                   "contains(@class,'ListView') or "
                   "contains(@resource-id,'list') or "
                   "contains(@resource-id,'inbox') or "
                   "contains(@resource-id,'message')]")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cands = driver.find_elements(By.XPATH, check_xpath)
            for c in cands:
                try:
                    rect = c.rect
                    # visible and reasonably large
                    if rect and rect.get("height", 0) > 50 and rect.get("width", 0) > 50:
                        print("[run] Found inbox-like container:", c.get_attribute("class") or "element")
                        return c
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.4)
    return None

def _find_username_in_container(container, username):
    """
    Search only inside the container for exact text.
    Retries 2 times with 5s delay if not found then raises an exception.
    """
    attempts = 0
    max_attempts = 3  # initial try + 2 retries

    while attempts < max_attempts:
        try:
            # exact-text match inside container
            els = container.find_elements(By.XPATH, f".//android.widget.TextView[@text='{username}']")
            if els:
                return els[0]

            # fallback for custom layouts
            els2 = container.find_elements(By.XPATH, f".//*[normalize-space(@text)='{username}']")
            if els2:
                return els2[0]

        except Exception:
            pass

        attempts += 1

        if attempts < max_attempts:
            print(f"[run] Username '{username}' not found in container, retrying after 5 seconds...")
            time.sleep(5)


def _find_username(driver, container, username):
    """
    Searches for a username in the UI with detailed logging.
    1) container search (contains first, then exact)
    2) global search (contains first, then exact)
    3) accessibility search
    """

    max_attempts = 3
    retry_delay = 5

    print(f"[find] START -> Searching for username: '{username}'")

    for attempt_index in range(max_attempts):
        print(f"\n[find] Attempt {attempt_index + 1}/{max_attempts}")

        try:
            if container:
                print("[find] Using: container search")

                container_contains_xpath = f".//*[contains(@text,'{username}')]"
                print(f"[find] Trying XPATH (container contains): {container_contains_xpath}")
                elements = container.find_elements(By.XPATH, container_contains_xpath)
                print(f"[find] Result -> {len(elements)} elements found")
                if elements:
                    print("[find] FOUND via container contains")
                    return elements[0]

                container_exact_xpath = f".//*[@text='{username}']"
                print(f"[find] Trying XPATH (container exact): {container_exact_xpath}")
                elements = container.find_elements(By.XPATH, container_exact_xpath)
                print(f"[find] Result -> {len(elements)} elements found")
                if elements:
                    print("[find] FOUND via container exact")
                    return elements[0]

            print("[find] Using: global search")

            global_contains_xpath = f"//*[contains(@text,'{username}')]"
            print(f"[find] Trying XPATH (global contains): {global_contains_xpath}")
            elements = driver.find_elements(By.XPATH, global_contains_xpath)
            print(f"[find] Result -> {len(elements)} elements found")
            if elements:
                print("[find] FOUND via global contains")
                return elements[0]

            global_exact_xpath = f"//*[@text='{username}']"
            print(f"[find] Trying XPATH (global exact): {global_exact_xpath}")
            elements = driver.find_elements(By.XPATH, global_exact_xpath)
            print(f"[find] Result -> {len(elements)} elements found")
            if elements:
                print("[find] FOUND via global exact")
                return elements[0]

            print("[find] Using: content-desc search")

            accessibility_contains_xpath = f"//*[contains(@content-desc,'{username}')]"
            print(f"[find] Trying XPATH (content-desc contains): {accessibility_contains_xpath}")
            elements = driver.find_elements(By.XPATH, accessibility_contains_xpath)
            print(f"[find] Result -> {len(elements)} elements found")
            if elements:
                print("[find] FOUND via content-desc contains")
                return elements[0]

        except Exception as err:
            print(f"[find] ERROR during attempt {attempt_index + 1}: {repr(err)}")

        if attempt_index < max_attempts - 1:
            print(f"[find] Not found — retrying in {retry_delay}s...")
            time.sleep(retry_delay)

    print(f"[find] FINAL - Username '{username}' not found in UI")


def scroll_container_small(driver, container, direction="up"):
    """
    Perform a short swipe inside the container rect
    """
    try:
        r = container.rect
        start_x = int(r['x'] + r['width'] * 0.5)
        if direction == "up":
            start_y = int(r['y'] + r['height'] * 0.75)
            end_y = int(r['y'] + r['height'] * 0.35)
        else:
            start_y = int(r['y'] + r['height'] * 0.35)
            end_y = int(r['y'] + r['height'] * 0.75)

        driver.execute_script("mobile: swipe", {
            "startX": start_x, "startY": start_y,
            "endX": start_x, "endY": end_y,
            "duration": 200
        })
        time.sleep(0.3) 
        return True
    except Exception as e:
        print("[run] scroll_container_small failed:", e)
        return False

def wait_until(driver, condition, timeout=10, poll=0.4, label="condition"):
    try:
        WebDriverWait(driver, timeout, poll_frequency=poll).until(lambda d: condition(d))
        return True
    except TimeoutException:
        print(f"[wait] Timeout waiting for {label}")
        return False

def ensure_app_foreground(driver, package, retries=3, timeout_each=5):
    for attempt in range(1, retries + 1):
        try:
            print(f"[app] Activating {package}, attempt {attempt}")
            driver.activate_app(package)

            ok = wait_until(
                driver,
                lambda d: (
                    getattr(d, "current_package", None) == package
                    or d.query_app_state(package) == 4
                ),
                timeout=timeout_each,
                label=f"{package} in foreground"
            )

            if ok:
                print("[app] App is in foreground")
                return True

        except Exception as e:
            print("[app] activate/check failed:", e)

        time.sleep(1)

    print("[app] Failed to bring app to foreground")
    return False


def run_nudge_flow_fast(driver, targets=None, max_to_process=50):
    """
      Clicks chat, nudges, returns to inbox
    """
    if targets is None:
        targets = load_nudge_targets()
    if not targets:
        print("[run] No nudge targets found.")
        return

    print(f"[run] Starting fast nudge flow for {len(targets)} targets (max {max_to_process})")

    try:
        driver.update_settings({"waitForIdleTimeout": 0})
    except Exception as e:
        print("[settings] update_settings failed, continuing:", e)

    try:
        print("[run] Activating TikTok...")

        if not ensure_app_foreground(driver, TIKTOK_PACKAGE, retries=3, timeout_each=5):
            print("[run] Could not open TikTok; aborting.")
            return

    except Exception as e:
        print("[run] activate_app failed:", e)

    time.sleep(3)

    processed = 0
    wait = WebDriverWait(driver, DEFAULT_PER_ACTION_TIMEOUT)

    container = open_inbox_and_wait(driver, open_timeout=INBOX_OPEN_TIMEOUT)
    if not container:
        print("[run] Inbox container not found; aborting.")
        return
    
    time.sleep(2.0)

    for username in targets:
        if processed >= max_to_process:
            break

        print(f"\n[run] Trying to find chat: {username}")

        # search directly in the container
        #found_el = _find_username_in_container(container, username)
        #if not found_el:
        #    print(f"[run] Could not locate chat for {username}. Skipping.")
        #    continue

        found_el = _find_username(driver, container, username)
        if not found_el:
            print(f"[run] Could not locate chat for {username} with global search.")
            continue

        click_target = found_el
        try:
            ancestor = found_el
            for i in range(3):
                print(f"[run] Checking ancestor level {i+1} for clickable...")
                parent = ancestor.find_element(By.XPATH, "..")
                if parent and parent.get_attribute("clickable") in ("true", "1"):
                    click_target = parent
                    break
                ancestor = parent
        except Exception:
            click_target = found_el

        # click the chat
        try:
            print(f"[run] Clicking chat for {username}")
            click_target.click()
            time.sleep(CLICK_STABILIZE)
        except Exception as e:
            print("[run] click() failed, trying coordinate tap:", e)
            try:
                r = click_target.rect
                cx = int(r['x'] + r['width'] / 2)
                cy = int(r['y'] + r['height'] / 2)
                driver.execute_script("mobile: tap", {"x": cx, "y": cy})
                time.sleep(CLICK_STABILIZE)
            except Exception as e2:
                print("[run] Failed to open chat:", e2)
                try:
                    driver.back()
                except:
                    pass
                continue

        # click nudge button
        nudged = False
        nudge_xps = [
            "//*[contains(translate(@text,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nudge')]",
            "//*[contains(translate(@content-desc,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nudge')]",
            "//*[contains(translate(@text,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'Nudge back')]",

            #fallbacks if no nudge (special days, etc.)
            "//*[@content-desc='ThumbsUp']/parent::*", 
            "//*[@content-desc='Heart']/parent::*"

            "//android.widget.Button[contains(@text,'Nudge') or contains(@content-desc,'Nudge')]",
        ]
        for xp in nudge_xps:
            try:
                btn = driver.find_element(By.XPATH, xp)
                print("[run] Clicking nudge via", xp)
                btn.click()
                nudged = True
                time.sleep(0.25)
                break
            except Exception:
                pass

        if not nudged:
            print(f"[run] No Nudge button for {username} (UI variant or already nudged).")
        else:
            processed += 1

        # return to inbox
        try:
            print("[run] returning to inbox")
            driver.back()
            time.sleep(0.25)
        except Exception:
            pass

    

    print(f"[run] Completed: processed {processed} nudges (targets provided: {len(targets)})")
    return processed

# -------- ANDROID SDK -------
def check_android_sdk():
    android_home = os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT")
    if not android_home:
        raise RuntimeError(
            "ANDROID_HOME or ANDROID_SDK_ROOT is not set. "
            "Please set it before running the script. Example:\n"
            "export ANDROID_HOME=$HOME/Library/Android/sdk\n"
            "export ANDROID_SDK_ROOT=$ANDROID_HOME\n"
            "export PATH=$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin:$ANDROID_HOME/platform-tools"
        )
    if not os.path.exists(android_home):
        raise RuntimeError(f"ANDROID_HOME / ANDROID_SDK_ROOT path does not exist: {android_home}")
    print(f"Android SDK found at: {android_home}")

# -------- MAIN -------
def main():
    check_android_sdk()
    instance_uuid = None
    serial = None
    driver = None
    appium_started = False
    appium_proc = None
    try:
        # setup appium
        appium_started, appium_proc = start_appium_server()

        # Start genymotion instance and wait until ONLINE
        instance_uuid = start_instance_from_recipe()

        ensure_gmsaas_authenticated()

        instance_data = wait_instance_online(instance_uuid)

        # create adb tunnel via gmsaas
        serial = adb_connect_via_gmsaas(instance_uuid)
        time.sleep(1) 
        os.environ["ANDROID_ADB_SERVER_PORT"] = serial.split(":")[-1]
       
        if not serial:
            raise RuntimeError("No adb serial found after gmsaas adbconnect")

        print("Creating appium driver...")
        # create appium driver and run flow
        driver = make_driver_with_serial(serial)
        print("Driver created. Running nudge flow.")

        targets = load_nudge_targets()   # uses NUDGE_USERS env or nudge_users.txt
        proccesed = run_nudge_flow_fast(driver, targets=targets, max_to_process=50)


        # cleanup
        try: driver.quit()
        except: pass
        adb_disconnect_via_gmsaas(instance_uuid, serial)
        stop_instance(instance_uuid)
        print("Completed run successfully.")

        if proccesed == len(targets):
            send_email("TikTok Nudge Automation Succeeded", "Successfully nudged all users. (" + time.ctime() + ")")
        else:
            send_email("TikTok Nudge Automation Failed", f"Nudged {proccesed} out of {len(targets)} users. (" + time.ctime() + ")")

    except Exception as e:
        tb = traceback.format_exc()
        print("Fatal error:", tb)
        try:
            if driver:
                driver.quit()
        except:
            pass
        try:
            if serial and instance_uuid:
                adb_disconnect_via_gmsaas(instance_uuid, serial)
        except:
            pass
        try:
            if instance_uuid:
                stop_instance(instance_uuid)
        except Exception as stop_err:
            print("Error stopping instance:", stop_err)
        send_email("TikTok Nudge Automation Failed", tb)
        raise
    finally:
        if appium_started and appium_proc:
            stop_appium_server(appium_proc)
            stop_instance(instance_uuid=instance_uuid)

if __name__ == "__main__":
    main()
