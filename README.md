# TikTok Nudge Automation

Automates sending TikTok **Nudge** notifications to multiple TikTok users using **Appium** and a disposable **Genymotion SaaS** Android instance.

The script automatically:

- Starts a disposable Android device from a Genymotion recipe
- Connects to the device through an ADB tunnel
- Starts an Appium server
- Opens TikTok
- Sends nudges to a list of users
- Sends an email summary
- Cleans up by stopping Appium and destroying the cloud device

---

# Requirements

- Python 3.9+
- Android SDK (`platform-tools`) on your `PATH`
- Node.js 20+
- Appium
- Appium UIAutomator2 driver
- A Genymotion SaaS account
- Authenticated `gmsaas` CLI
- A Genymotion recipe configured for TikTok automation

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Install Appium:

```bash
npm install -g appium
```

Install the UIAutomator2 driver:

```bash
appium driver install uiautomator2
```

---

# Setting up Genymotion

Before running the script, you need to create a reusable Genymotion **Recipe**.

Genymotion SaaS allows you to run disposable Android devices in the cloud.

https://cloud.geny.io/

## 1. Create a Hardware Profile

Before creating the recipe, create a Hardware Profile.

Go to the **Hardware Profiles** tab, click **Create**, and configure the device.

A larger screen allows more conversations to be visible in the TikTok Inbox, reducing the need for scrolling.

**Suggested configuration:**

- Width: **3000 px**
- Height: **2000 px**
- DPI: **320**
- RAM: **8192 MB**
- vCPUs: **8**

---

## 2. Create a Recipe

The Recipe is the Android device template that will be used for the automation.

Go to the **Recipes** tab and click **Create**. Give it a name, select the Hardware Profile you created, and choose an Android image supported by TikTok.

**Suggested image:**

- Android: **14.0**
- Architecture: **arm64**

Once the Recipe has been created, copy its UUID.

Paste it into your `.env` file as:

```env
GM_RECIPE_UUID=<your_recipe_uuid>
```

---

## 3. Start the Instance

Click **Start** on the Recipe you just created.

Wait for the Android device to finish booting.

---

## 4. Install TikTok

After the instance boots, click the **Google Play** icon in the right-side toolbar and install **GAPPS**.

This installs the Google Play Store onto the virtual device.

Install TikTok from Google Play and log into the account that will be sending the nudges.

After logging in, dismiss **every popup** inside TikTok.

For example:

- Contacts permission prompts
- Inbox suggestions
- First-time feature dialogs
- Any other onboarding or promotional popups

Also open every conversation that will be automated and dismiss any popups shown there.

This is important because any unexpected popup can interrupt the automation.

---

## 5. Install the UIAutomator2 Server APKs

This is required for Appium to automate the device.

The script is configured with:

```python
skipServerInstallation = True
```

which means it **expects the UIAutomator2 server APKs to already exist on the device**.

Open the **Install** tab in the Genymotion toolbar and drag both APK files into the device:

```
Repo/apks/appium-uiautomator2-server-debug-androidTest.apk
Repo/apks/appium-uiautomator2-server-v9.1.2.apk
```

Android may ask you to confirm the installation. Accept all prompts and allow both APKs to be installed successfully.

---

## 6. Save the Recipe

Save the Recipe to persist all changes.

This ensures that every disposable instance created from the Recipe already has:

- TikTok installed
- The TikTok account logged in
- UIAutomator2 server APKs installed

Click **Save** in the left-side toolbar and save the Recipe.

---

## 7. Create an API Key

Go to the **API** page from the left sidebar.

Click **Create**, enter a description for the key, and generate it.

Copy the generated API key and add it to your `.env` file:

```env
GM_API_TOKEN=<your_api_token>
```

---


# Notice

If the automation suddenly starts failing, TikTok has most likely introduced a new popup or is waiting for user interaction.

Start the Recipe manually from the Genymotion dashboard, open TikTok, and look for anything blocking the UI.

After dismissing all popups, **save the Recipe again**, otherwise the changes will not persist for future runs.

---

# Configuration

Copy `.env.example` to `.env` and fill in the required values.

| Variable | Description |
|----------|-------------|
| `GM_API_TOKEN` | Genymotion SaaS API token |
| `GM_RECIPE_UUID` | UUID of the Recipe you created |
| `EMAIL_USER` | Gmail address used for notifications |
| `EMAIL_PASS` | Gmail App Password |
| `EMAIL_TO` | Recipient email address |
| `NUDGE_USERS` | Comma-separated list of TikTok usernames |
| `TIKTOK_PACKAGE` | TikTok package name |
| `TIKTOK_ACTIVITY` | TikTok launch activity |
| `APPIUM_SERVER` | Appium server URL |
| `INSTANCE_BOOT_TIMEOUT` | Seconds to wait for the instance to boot |
| `FORCE_DRIVER_INSTALL` | Automatically install/update the UIAutomator2 driver |

### `.env.example`

```env
GM_API_TOKEN=your_token
GM_RECIPE_UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

EMAIL_USER=bot@gmail.com
EMAIL_PASS=your_app_password
EMAIL_TO=you@example.com

NUDGE_USERS=john_doe,jane_doe,user123

TIKTOK_PACKAGE=com.zhiliaoapp.musically
TIKTOK_ACTIVITY=com.ss.android.ugc.aweme.splash.SplashActivity
APPIUM_SERVER=http://localhost:4723/wd/hub

INSTANCE_BOOT_TIMEOUT=180
FORCE_DRIVER_INSTALL=0
```

---

# Target Users

Users can be provided in two ways, in order of priority.

## Environment Variable

```env
NUDGE_USERS=john_doe,jane_doe,user123
```

## Text File

Create a file named `nudge_users.txt`:

```text
john_doe
jane_doe
user123
another_user
```

### Limits

- Up to **200 usernames** can be loaded.
- A maximum of **50 nudges** are sent per execution.

---

# Running

```bash
python tiktok_nudge.py
```

The script automatically:

1. Starts Appium.
2. Creates a disposable Genymotion instance.
3. Opens an ADB tunnel.
4. Connects Appium.
5. Launches TikTok.
6. Sends nudges.
7. Sends an email report.
8. Stops Appium.
9. Destroys the cloud instance.

---

# Email Notifications

If the email variables are configured, the script sends a summary email after every execution.

It uses:

- Gmail SMTP (SSL)
- Port **465**

A **Google App Password** is required.

Enter the **App Password** in `EMAIL_PASS`—**not** your normal Google account password.

Generate an App Password from:

**Google Account → Security → 2-Step Verification → App Passwords**

Copy the generated password into the `EMAIL_PASS` field in your `.env` file.

---

# Android SDK

If the Android SDK cannot be located automatically, set it manually:

```bash
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
```

---

# Notes

- TikTok **must already be installed** in the Genymotion Recipe.
- The TikTok account should already be logged in before saving the Recipe.
- The Recipe should already contain the UIAutomator2 server APKs.
- Disposable instances are automatically destroyed after each run.
- On local machines, installing the UIAutomator2 Appium driver manually is recommended.
