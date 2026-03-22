#!/usr/bin/env python3

import requests
import os
import time
import sys
import subprocess
import threading
import webbrowser
import json
import logging
import glob
import signal
import argparse
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

HOME_DIR = os.path.expanduser("~")
ENV_PATH = os.path.join(HOME_DIR, ".config/waybar/scripts/.env")
SOUND_PATH = os.path.join(HOME_DIR, ".config/sounds/freesound_community-retro-audio-logo-94648.mp3")

load_dotenv(ENV_PATH)

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_PAT = os.getenv("GITHUB_PAT")

if not GITHUB_USERNAME or not GITHUB_PAT:
    print(json.dumps({"text": "⚠️ Config Error", "tooltip": "Check .env file"}))
    sys.exit(1)

ICONS = {
    1: "", 2: "󰊤", 3: "", 4: "", 5: "",
    6: "", 7: "", 8: "", 9: "", 10: ""
}

class GitHubMonitor:
    def __init__(self, repo_mode="all", time_mode="interval", icon_choice=1):
        # Configuration
        self.repo_mode = repo_mode  # all, my_repos_only, or specific_repo
        self.time_mode = time_mode  # manual, fixed, or smart_interval
        self.icon = ICONS.get(icon_choice, ICONS[1])
        
        # State
        self.seen_event_ids = set()
        self.etags = {}
        self.is_startup = True
        self.force_refresh = False
        self.poll_interval = 20 # Default
        
        if time_mode.isdigit():
            self.poll_interval = int(time_mode)
        
        signal.signal(signal.SIGUSR1, self.handle_refresh_signal)

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json"
        })

        self.cleanup_avatars()

    def handle_refresh_signal(self, signum, frame):
        logging.info("Refresh signal received!")
        self.force_refresh = True

    def print_waybar(self, text, tooltip):
        output = {
            "text": f"{self.icon} {text}",
            "tooltip": tooltip,
            "class": "github"
        }
        print(json.dumps(output))
        sys.stdout.flush()

    def play_sound(self):
        if os.path.exists(SOUND_PATH):
            try:
                subprocess.Popen(["mpv", "--no-terminal", "--no-video", SOUND_PATH], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    subprocess.Popen(["paplay", SOUND_PATH], 
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    logging.error(f"Sound error: {e}")

    def cleanup_avatars(self):
        try:
            files = glob.glob('/tmp/github_avatar_*.png')
            for f in files:
                if os.stat(f).st_mtime < time.time() - 86400:
                    os.remove(f)
        except Exception as e:
            logging.error(f"Cleanup error: {e}")

    def download_avatar(self, actor_name, avatar_url):
        avatar_path = f"/tmp/github_avatar_{actor_name}.png"
        if not os.path.exists(avatar_path):
            try:
                res = self.session.get(avatar_url, timeout=5)
                if res.status_code == 200:
                    with open(avatar_path, 'wb') as f:
                        f.write(res.content)
            except Exception as e:
                logging.error(f"Avatar download error: {e}")
                return "github"
        return avatar_path

    def send_notification(self, title, body, repo_full_name, commit_sha, avatar_path, actor, branch):
        def _notify():
            try:
                repo_url = f"https://github.com/{repo_full_name}"
                commit_url = f"https://github.com/{repo_full_name}/commit/{commit_sha}" if commit_sha else repo_url
                actor_url = f"https://github.com/{actor}"
                branch_url = f"https://github.com/{repo_full_name}/tree/{branch}"

                self.play_sound()
                cmd = ["notify-send", "-a", "GitHub Monitor", "-i", avatar_path, 
                       "--action=repo=Open Repo", "--action=actor=User Profile", "--action=branch=View Branch"]
                if commit_sha: cmd.append("--action=commit=View Commit")
                cmd.extend([title, body])
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                action = result.stdout.strip()
                if action == "repo": webbrowser.open(repo_url)
                elif action == "commit": webbrowser.open(commit_url)
                elif action == "actor": webbrowser.open(actor_url)
                elif action == "branch": webbrowser.open(branch_url)
            except Exception as e:
                logging.error(f"Notification error: {e}")
        threading.Thread(target=_notify, daemon=True).start()

    def fetch_events(self, url):
        req_headers = {}
        if url in self.etags: req_headers["If-None-Match"] = self.etags[url]
        res = self.session.get(url, headers=req_headers, timeout=10)
        if res.status_code == 304: return []
        res.raise_for_status()
        if "ETag" in res.headers: self.etags[url] = res.headers["ETag"]
        return res.json()

    def process_events(self):
        url_my_events = f"https://api.github.com/users/{GITHUB_USERNAME}/events"
        url_received = f"https://api.github.com/users/{GITHUB_USERNAME}/received_events"
        last_check = time.strftime("%H:%M:%S")
        
        try:
            events_mine = self.fetch_events(url_my_events)
            events_received = self.fetch_events(url_received)
        except Exception as e:
            logging.error(f"Fetch events error: {e}")
            return

        all_events = events_mine + events_received
        if not all_events:
            if self.force_refresh:
                self.print_waybar("Up to date", f"Checked at {last_check}")
                time.sleep(2)
                self.print_waybar(GITHUB_USERNAME, f"Last check: {last_check}")
            return

        unique_events = {event['id']: event for event in all_events}.values()
        sorted_events = sorted(unique_events, key=lambda x: x.get('created_at', ''))
        
        new_events_found = False
        for event in sorted_events:
            if event["type"] == "PushEvent":
                event_id = event["id"]
                if event_id in self.seen_event_ids: continue
                self.seen_event_ids.add(event_id)
                
                repo_full_name = event["repo"]["name"]
                
                # Filter Logic based on -repo
                if self.repo_mode == "my_repos_only":
                    if repo_full_name.split('/')[0].lower() != GITHUB_USERNAME.lower(): continue
                elif self.repo_mode != "all":
                    if repo_full_name.lower() != self.repo_mode.lower(): continue

                new_events_found = True
                if self.is_startup:
                    actor = event["actor"]["display_login"]
                    self.print_waybar(actor, f"Last activity: {repo_full_name}\nUpdated at: {last_check}")
                    continue

                self._handle_new_push(event, repo_full_name, last_check)

        # Smart Interval Logic
        if self.time_mode == "interval":
            if new_events_found: self.poll_interval = 15
            else: self.poll_interval = min(60, self.poll_interval + 5)

        self.is_startup = False

    def _handle_new_push(self, event, repo_full_name, last_check):
        actor = event["actor"]["display_login"]
        branch = event["payload"].get("ref", "").replace("refs/heads/", "")
        commits = event["payload"].get("commits", [])
        message = commits[0]["message"].split('\n')[0] if commits else "New update"
        commit_sha = commits[0]["sha"] if commits else None
        
        self.print_waybar(f"[{branch}] {message}"[:35], f"Repo: {repo_full_name}\nMsg: {message}")
        self.send_notification(f"Push by @{actor}", message, repo_full_name, commit_sha, self.download_avatar(actor, event["actor"]["avatar_url"]), actor, branch)
        
        time.sleep(3)
        self.print_waybar(repo_full_name.split('/')[-1], f"Updated at: {last_check}")

    def run(self):
        try:
            while True:
                self.process_events()
                self.force_refresh = False
                
                if self.time_mode == "0": # Manual Mode
                    while not self.force_refresh: time.sleep(1)
                else: # Timed Mode
                    wait_time = self.poll_interval
                    while wait_time > 0 and not self.force_refresh:
                        time.sleep(1)
                        wait_time -= 1
        except KeyboardInterrupt:
            sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub Radar Re-structured")
    parser.add_argument("-repo", type=str, default="all", help="all | my_repos_only | username/repo | URL")
    parser.add_argument("-t", type=str, default="interval", help="0 (manual) | <seconds> | interval (smart)")
    parser.add_argument("-icon", type=int, default=1, help="Icon number 1-10")
    
    args = parser.parse_args()
    
    # URL Cleaning for -repo
    repo_val = args.repo
    if "github.com/" in repo_val:
        repo_val = repo_val.split("github.com/")[-1].strip("/")

    monitor = GitHubMonitor(repo_mode=repo_val, time_mode=args.t, icon_choice=args.icon)
    monitor.run()