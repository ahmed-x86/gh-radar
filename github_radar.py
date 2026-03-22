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
    1: "",  # GitHub Default
    2: "󰊤",  # Octocat
    3: "",  # GitHub Alt
    4: "",  # GitHub Logo
    5: "",  # Git
    6: "",  # Git Square
    7: "",  # Code
    8: "",  # Git Branch
    9: "",  # Pull Request
    10: ""  # Git Commit
}

class GitHubMonitor:
    def __init__(self, my_repos_only=False, manual_only=False, icon_choice=1, target_repo=None, poll_interval=20):
        self.my_repos_only = my_repos_only
        self.manual_only = manual_only
        self.target_repo = target_repo                          # The specific repo to track (owner/repo format)
        self.icon = ICONS.get(icon_choice, ICONS[1])
        self.seen_event_ids = set()
        self.etags = {}
        self.base_poll_interval = poll_interval                 # User-defined interval
        self.poll_interval = poll_interval
        self.is_startup = True
        self.force_refresh = False
        
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
                
                
                cmd = [
                    "notify-send", "-a", "GitHub Monitor", "-i", avatar_path, 
                    "--action=repo=Open Repo",
                    "--action=actor=User Profile",
                    "--action=branch=View Branch"
                ]
                

                if commit_sha:
                    cmd.append("--action=commit=View Commit")
                
                cmd.extend([title, body])
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                action = result.stdout.strip()
                

                if action == "repo":
                    webbrowser.open(repo_url)
                elif action == "commit":
                    webbrowser.open(commit_url)
                elif action == "actor":
                    webbrowser.open(actor_url)
                elif action == "branch":
                    webbrowser.open(branch_url)

            except Exception as e:
                logging.error(f"Notification error: {e}")
        threading.Thread(target=_notify, daemon=True).start()

    def get_commit_message(self, repo_name, commit_sha):
        url = f"https://api.github.com/repos/{repo_name}/commits/{commit_sha}"
        try:
            res = self.session.get(url, timeout=5)
            res.raise_for_status()
            return res.json()["commit"]["message"].split('\n')[0]
        except Exception as e:
            logging.error(f"Commit message fetch error: {e}")
            return None

    def fetch_events(self, url):
        req_headers = {}
        if url in self.etags:
            req_headers["If-None-Match"] = self.etags[url]
            
        res = self.session.get(url, headers=req_headers, timeout=10)
        
        if 'X-RateLimit-Remaining' in res.headers:
            remaining = int(res.headers['X-RateLimit-Remaining'])
            if remaining < 10:
                logging.warning(f"Rate limit running low! Remaining: {remaining}")

        if res.status_code == 304:
            return []
            
        res.raise_for_status()
        
        if "ETag" in res.headers:
            self.etags[url] = res.headers["ETag"]
            
        return res.json()

    def process_events(self):
        url_my_events = f"https://api.github.com/users/{GITHUB_USERNAME}/events"
        url_received = f"https://api.github.com/users/{GITHUB_USERNAME}/received_events"
        last_check = time.strftime("%H:%M:%S")
        
        try:
            events_mine = self.fetch_events(url_my_events)
            events_received = self.fetch_events(url_received)
        except requests.ConnectionError:
            self.print_waybar("Internet Error", "No internet connection")
            return
        except Exception as e:
            logging.error(f"Fetch events error: {e}")
            return

        all_events = events_mine + events_received

        if not all_events:
            if self.force_refresh:
                self.print_waybar("Up to date", f"Checked at {last_check}\nNo events found.")
                time.sleep(2) 
                self.print_waybar(GITHUB_USERNAME, f"Last check: {last_check}") 
            return

        unique_events = {event['id']: event for event in all_events}.values()
        sorted_events = sorted(unique_events, key=lambda x: x.get('created_at', ''))
        
        new_events_found = False

        for event in sorted_events:
            if event["type"] == "PushEvent":
                event_id = event["id"]
                
                if event_id in self.seen_event_ids:
                    continue
                    
                self.seen_event_ids.add(event_id)
                
                if len(self.seen_event_ids) > 100:
                    self.seen_event_ids.pop()

                repo_full_name = event["repo"]["name"]
                
                # Check for target specific repository
                if self.target_repo and repo_full_name.lower() != self.target_repo.lower():
                    continue

                # Check for my repos only
                if self.my_repos_only and not self.target_repo:
                    repo_owner = repo_full_name.split('/')[0]
                    if repo_owner.lower() != GITHUB_USERNAME.lower():
                        continue

                new_events_found = True
                
                if self.is_startup:
                    repo_name = repo_full_name.split('/')[-1]
                    actor = event["actor"]["display_login"]
                    self.print_waybar(actor, f"Last activity: {repo_name} (@{actor})\nUpdated at: {last_check}")
                    continue

                self._handle_new_push(event, repo_full_name, last_check)

        if self.force_refresh and not new_events_found and not self.is_startup:
            self.print_waybar("Up to date", f"Checked at {last_check}\nNo new updates.")
            time.sleep(2) 
            self.print_waybar(GITHUB_USERNAME, f"Last check: {last_check}")

        self.is_startup = False

        # Adjust polling interval dynamically
        if new_events_found:
            self.poll_interval = max(10, self.base_poll_interval // 2)  
        else:
            self.poll_interval = min(self.base_poll_interval * 3, self.poll_interval + 5)  

    def _handle_new_push(self, event, repo_full_name, last_check):
        repo_name = repo_full_name.split('/')[-1]
        actor = event["actor"]["display_login"]
        avatar_url = event["actor"]["avatar_url"]
        branch = event["payload"].get("ref", "").replace("refs/heads/", "")
        
        commits = event["payload"].get("commits", [])
        commit_count = len(commits)
        message = commits[0]["message"].split('\n')[0] if commits else None
        commit_sha = commits[0]["sha"] if commits else None
        
        if not message and event["payload"].get("head"):
            commit_sha = event["payload"].get("head")
            message = self.get_commit_message(repo_full_name, commit_sha)
        
        if not message:
            message = "New update"

        title = f"New Push by @{actor}"
        if commit_count > 1: 
            title = f"@{actor} pushed {commit_count} commits"
        
        full_text = f"[{branch}] {message}"
        short_text = full_text[:35] + ".." if len(full_text) > 35 else full_text
        
        tooltip_msg = f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}\nUpdated at: {last_check}"
        self.print_waybar(short_text, tooltip_msg)

        notif_body = f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}"
        avatar_path = self.download_avatar(actor, avatar_url)
        

        self.send_notification(title, notif_body, repo_full_name, commit_sha, avatar_path, actor, branch)
        
        time.sleep(3)
        self.print_waybar(repo_name, tooltip_msg)
        time.sleep(3)
        self.print_waybar(actor, tooltip_msg)

    def run(self):
        try:
            while True:
                self.process_events()

                self.force_refresh = False
                
                if self.manual_only:
                    while not self.force_refresh:
                        time.sleep(1)
                else:
                    wait_time = self.poll_interval
                    while wait_time > 0 and not self.force_refresh:
                        time.sleep(1)
                        wait_time -= 1

        except KeyboardInterrupt:
            logging.info("Exiting...")
            sys.exit(0)

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="GitHub Radar for Waybar")
    parser.add_argument("mode", nargs="?", default="all", help="Use 'my_repos_only' to track only your repos")
    parser.add_argument("-t", type=int, default=-1, help="Set to 0 for manual refresh only")
    parser.add_argument("-icon", type=int, choices=range(1, 11), default=1, help="Choose an icon (1-10)")
    parser.add_argument("--repo", type=str, default=None, help="Track a specific repository (URL or owner/repo)")
    parser.add_argument("--interval", type=int, default=20, help="Set base polling interval in seconds (default: 20)")
    
    args = parser.parse_args()
    
    # Logic to parse the URL and extract 'owner/repo'
    target_repository = args.repo
    if target_repository:
        # If the user passed a full URL, strip the domain part
        if "github.com/" in target_repository:
            target_repository = target_repository.split("github.com/")[-1]
        
        # Remove trailing slashes if they exist
        target_repository = target_repository.strip("/")
    
    filter_mode = (args.mode == "my_repos_only")
    manual_mode = (args.t == 0)
    
    monitor = GitHubMonitor(
        my_repos_only=filter_mode, 
        manual_only=manual_mode, 
        icon_choice=args.icon,
        target_repo=target_repository,  # Passing the cleaned up repo format
        poll_interval=args.interval
    )
    monitor.run()