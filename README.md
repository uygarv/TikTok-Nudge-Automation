# TikTok Nudge Automation

Automates sending TikTok "nudge" notifications to a list of users via Appium and a Genymotion cloud Android instance.

## How it works

1. Starts a cloud Android instance from a Genymotion recipe
2. Connects to the instance via ADB tunnel
3. Launches an Appium server and opens TikTok on the device
4. Opens the inbox and sends a nudge to each target user
5. Sends an email summary on success or failure
6. Shuts down the instance and Appium server

## Requirements

- Python 3.9+
- Android SDK with `platform-tools` on your PATH
- [Appium](https://appium.io) installed via npm or nvm (Node 20 recommended)
- Appium `uiautomator2` driver installed
- [gmsaas CLI](https://docs.genymotion.com/tools/saas/gmsaas/) authenticated with your Genymotion token
- A Genymotion SaaS account with a recipe that has TikTok pre-installed

Install Python dependencies:

```
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in the values, or export them as environment variables.

| Variable | Description |
|---|---|
| `GM_API_TOKEN` | Genymotion SaaS API token |
| `GM_RECIPE_UUID` | UUID of the Genymotion recipe to start |
| `EMAIL_USER` | Gmail address used to send result emails |
| `EMAIL_PASS` | Gmail app password |
| `EMAIL_TO` | Recipient address for result emails |
| `NUDGE_USERS` | Comma-separated list of TikTok usernames to nudge |
| `TIKTOK_PACKAGE` | TikTok app package (default: `com.zhiliaoapp.musically`) |
| `TIKTOK_ACTIVITY` | TikTok splash activity (default provided) |
| `APPIUM_SERVER` | Appium server URL (default: `http://localhost:4723/wd/hub`) |
| `INSTANCE_BOOT_TIMEOUT` | Seconds to wait for instance to come online (default: 180) |
| `FORCE_DRIVER_INSTALL` | Set to `1` to auto-install the uiautomator2 driver if missing |

Example `.env` file:

```env
GM_API_TOKEN=your_genymotion_api_token_here
GM_RECIPE_UUID=a1b2c3d4-e5f6-7890-abcd-ef1234567890

EMAIL_USER=yourbot@gmail.com
EMAIL_PASS=your_gmail_app_password
EMAIL_TO=you@example.com

NUDGE_USERS=john_doe,jane_smith,tiktok_user99

TIKTOK_PACKAGE=com.zhiliaoapp.musically
TIKTOK_ACTIVITY=com.ss.android.ugc.aweme.splash.SplashActivity
APPIUM_SERVER=http://localhost:4723/wd/hub

INSTANCE_BOOT_TIMEOUT=180
FORCE_DRIVER_INSTALL=0
```

## Target users

Users to nudge can be provided in two ways, in priority order:

1. `NUDGE_USERS` environment variable as a comma-separated list:

```
NUDGE_USERS=john_doe,jane_smith,tiktok_user99
```

2. A file named `nudge_users.txt` in the project root, one username per line:

```
john_doe
jane_smith
tiktok_user99
another_user
```

A maximum of 200 users are loaded per run, and at most 50 nudges are sent per run.

## Usage

```
python tiktok_nudge.py
```

The script will handle starting and stopping Appium and the cloud instance automatically.

## Email notifications

If `EMAIL_USER`, `EMAIL_PASS`, and `EMAIL_TO` are configured, the script sends an email after each run reporting how many nudges were sent. It uses Gmail SMTP with SSL on port 465.

To generate a Gmail app password, go to your Google account under Security > 2-Step Verification > App passwords.

## Notes

- The script assumes TikTok is already installed on the Genymotion instance.
- If the uiautomator2 driver is not installed and `FORCE_DRIVER_INSTALL=1` is set, the script will attempt to install it automatically. On local machines, it is recommended to install it manually: `appium driver install uiautomator2`.
- The script looks for the Android SDK in common locations automatically if `ANDROID_HOME` is not set. If it cannot find it, set the variable manually:

```
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
```
