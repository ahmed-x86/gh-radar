
# 📡 gh-radar

A dynamic and interactive Waybar module that monitors your GitHub activity in real-time. It features an animated ticker (Commit ➔ Repo ➔ Username), sound alerts, and desktop notifications with user avatars. Never miss a push again!

## ✨ Features
- **Animated Ticker**: Waybar text changes dynamically when a new push occurs (shows the branch and commit message, then the repository name, and returns to your username).
- **Audio Alerts**: Plays a retro notification sound upon detecting a new push.
- **Avatar Notifications**: Sends a desktop notification containing the committer's GitHub avatar and commit details.
- **Interactive**: Left-click to open your GitHub profile, Right-click to open notifications.
- **Optimized**: Uses GitHub's `ETag` headers to respect API rate limits.

## 📂 File Structure
```text
.
├── .env
├── .env.example
├── github_radar.py
├── README.md
└── sounds
    └── freesound_community-retro-audio-logo-94648.mp3

```

## 🚀 Installation

**1. Clone the repository**

```bash
git clone https://github.com/ahmed-x86/gh-radar.git
cd gh-radar
```

**2. Copy files to your `.config` directory**

```bash
# Copy the sound file to your config folder
cp -r sounds ~/.config/

# Create the scripts directory for Waybar if it doesn't exist
mkdir -p ~/.config/waybar/scripts

# Copy the Python script and make it executable
cp github_radar.py ~/.config/waybar/scripts/
chmod +x ~/.config/waybar/scripts/github_radar.py
```

**3. Set up your Credentials (.env)**
The script requires a GitHub Personal Access Token (PAT) to read your events. Create a `.env` file in the scripts folder:

```bash
nano ~/.config/waybar/scripts/.env
```

Add the following lines (replace with your actual username and token):

```env
GITHUB_USERNAME=your_github_username
GITHUB_PAT=your_personal_access_token_here
```

**4. Install Dependencies**
Make sure you have the required Python libraries and system tools:
```bash
pip install requests python-dotenv
# Ensure you have 'mpv' (or 'paplay') and 'libnotify' installed on your system
```

## ⚙️ Waybar Configuration

### 1. Module Configuration (`config.jsonc`)

Add the following module to your Waybar config file (under `modules-left`, `modules-center`, or `modules-right`):

```jsonc
"custom/github-radar": {
    "format": "{}",
    "return-type": "json",
    "exec": "python3 -u ~/.config/waybar/scripts/github_radar.py",
    "on-click": "xdg-open [https://github.com/ahmed-x86](https://github.com/ahmed-x86)",
    "on-click-right": "xdg-open [https://github.com/notifications](https://github.com/notifications)",
    "restart-interval": 20
}
```

### 2. Styling (`style.css`)

Add these lines to your Waybar `style.css` to give it that authentic GitHub look:

```css
/* GitHub Radar Styling */
#custom-github-radar {
    background-color: #24292e; /* Dark GitHub background */
    color: #ffffff; /* Text and icon color */
    border-radius: 10px; /* Rounded corners */
    padding: 0px 10px;
    margin: 4px 5px;
    font-weight: bold;
    border: 1px solid #444c56; /* Light border */
    transition: all 0.3s ease; /* Smooth hover transition */
}

/* Hover effect */
#custom-github-radar:hover {
    background-color: #2ea043; /* Famous GitHub green */
    color: #ffffff;
    border-color: #2ea043;
}

```

## 🔄 Restart Waybar

Apply the changes by restarting Waybar:

```bash
killall waybar && waybar & disown 
```
#for testing

---
