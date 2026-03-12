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

class GitHubMonitor:
    def __init__(self, my_repos_only=False):
        self.my_repos_only = my_repos_only
        self.seen_event_ids = set()
        self.etags = {}
        self.poll_interval = 20
        self.is_startup = True
        
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json"
        })
        
        
        self.cleanup_avatars()

    def print_waybar(self, text, tooltip):
        output = {
            "text": f" {text}",
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
        """تنظيف الصور القديمة من مجلد tmp (نصيحة المراجع)"""
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

    def send_notification(self, title, body, repo_full_name, commit_sha, avatar_path):
        def _notify():
            try:
                repo_url = f"https://github.com/{repo_full_name}"
                commit_url = f"https://github.com/{repo_full_name}/commit/{commit_sha}" if commit_sha else repo_url
                self.play_sound()
                cmd = ["notify-send", "-a", "GitHub Monitor", "-i", avatar_path, "--action=repo=Open Repo"]
                if commit_sha:
                    cmd.append("--action=commit=View Commit")
                cmd.extend([title, body])
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                action = result.stdout.strip()
                if action == "repo":
                    webbrowser.open(repo_url)
                elif action == "commit":
                    webbrowser.open(commit_url)
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
                if self.my_repos_only:
                    repo_owner = repo_full_name.split('/')[0]
                    if repo_owner.lower() != GITHUB_USERNAME.lower():
                        continue

                new_events_found = True
                
                if self.is_startup:
                    
                    repo_name = repo_full_name.split('/')[-1]
                    actor = event["actor"]["display_login"]
                    self.print_waybar(actor, f"Last activity: {repo_name} (@{actor})")
                    continue

                
                self._handle_new_push(event, repo_full_name)

        self.is_startup = False

        
        if new_events_found:
            self.poll_interval = 10  
        else:
            self.poll_interval = min(60, self.poll_interval + 5)  

    def _handle_new_push(self, event, repo_full_name):
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
        
        self.print_waybar(short_text, f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}")

        notif_body = f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}"
        avatar_path = self.download_avatar(actor, avatar_url)
        self.send_notification(title, notif_body, repo_full_name, commit_sha, avatar_path)
        
        
        time.sleep(3)
        self.print_waybar(repo_name, f"Last activity: {repo_name} (@{actor})")
        time.sleep(3)
        self.print_waybar(actor, f"Last activity: {repo_name} (@{actor})")

    def run(self):
        try:
            while True:
                self.process_events()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logging.info("Exiting...")
            sys.exit(0)

if __name__ == "__main__":
    filter_mode = len(sys.argv) > 1 and sys.argv[1] == "my_repos_only"
    monitor = GitHubMonitor(my_repos_only=filter_mode)
    monitor.run()