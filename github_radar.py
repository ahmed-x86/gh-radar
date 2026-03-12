#!/usr/bin/env python3
# Note: This script is AI-generated, not my own work.

import requests
import os
import time
import sys
import subprocess
import threading
import webbrowser
import json
from dotenv import load_dotenv

HOME_DIR = os.path.expanduser("~")
ENV_PATH = os.path.join(HOME_DIR, ".config/waybar/scripts/.env")
SOUND_PATH = os.path.join(HOME_DIR, ".config/sounds/freesound_community-retro-audio-logo-94648.mp3")

load_dotenv(ENV_PATH)

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_PAT = os.getenv("GITHUB_PAT")

if not GITHUB_USERNAME or not GITHUB_PAT:
    print(json.dumps({"text": "⚠️ Config Error", "tooltip": "Check .env file"}))
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {GITHUB_PAT}",
    "Accept": "application/vnd.github.v3+json"
}

last_event_id = None
etags = {} 

def print_waybar(text, tooltip):
    """دالة لطباعة JSON المتوافق مع Waybar"""
    output = {
        "text": f" {text}",
        "tooltip": tooltip,
        "class": "github"
    }
    print(json.dumps(output))
    sys.stdout.flush()

def play_sound():
    if os.path.exists(SOUND_PATH):
        try:
            subprocess.Popen(["mpv", "--no-terminal", "--no-video", SOUND_PATH], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                subprocess.Popen(["paplay", SOUND_PATH], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass

def download_avatar(actor_name, avatar_url):
    avatar_path = f"/tmp/github_avatar_{actor_name}.png"
    if not os.path.exists(avatar_path):
        try:
            res = requests.get(avatar_url, timeout=5)
            if res.status_code == 200:
                with open(avatar_path, 'wb') as f:
                    f.write(res.content)
        except Exception:
            return "github"
    return avatar_path

def send_notification(title, body, repo_full_name, commit_sha, avatar_path):
    def _notify():
        try:
            repo_url = f"https://github.com/{repo_full_name}"
            commit_url = f"https://github.com/{repo_full_name}/commit/{commit_sha}" if commit_sha else repo_url
            play_sound()
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
        except Exception: pass
    threading.Thread(target=_notify, daemon=True).start()

def get_commit_message(repo_name, commit_sha):
    url = f"https://api.github.com/repos/{repo_name}/commits/{commit_sha}"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()
        return data["commit"]["message"].split('\n')[0]
    except Exception: return None

def fetch_events(url):
    req_headers = headers.copy()
    if url in etags:
        req_headers["If-None-Match"] = etags[url]
    # أزلنا try/except من هنا لنتمكن من اصطياد خطأ الإنترنت في الدالة الرئيسية
    res = requests.get(url, headers=req_headers, timeout=10)
    if res.status_code == 304: return [] 
    res.raise_for_status()
    if "ETag" in res.headers:
        etags[url] = res.headers["ETag"]
    return res.json()

def get_latest_push(is_startup=False, my_repos_only=False):
    global last_event_id
    url_my_events = f"https://api.github.com/users/{GITHUB_USERNAME}/events"
    url_received = f"https://api.github.com/users/{GITHUB_USERNAME}/received_events"
    
    # --- التحقق من الاتصال بالإنترنت ---
    try:
        events_mine = fetch_events(url_my_events)
        events_received = fetch_events(url_received)
    except requests.ConnectionError:
        print_waybar("Internet Error", "No internet connection")
        return
    except Exception:
        return # تجاهل الأخطاء الأخرى (مثل مشاكل الصلاحيات) بصمت
    # -----------------------------------

    all_events = events_mine + events_received
    
    if not all_events: return

    all_events.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    for event in all_events:
        if event["type"] == "PushEvent":
            repo_full_name = event["repo"]["name"] 
            
            if my_repos_only:
                repo_owner = repo_full_name.split('/')[0]
                if repo_owner.lower() != GITHUB_USERNAME.lower():
                    continue

            latest_push_id = event["id"]
            repo_name = repo_full_name.split('/')[-1] 
            actor = event["actor"]["display_login"]
            avatar_url = event["actor"]["avatar_url"]
            branch = event["payload"].get("ref", "").replace("refs/heads/", "")
            
            if is_startup:
                last_event_id = latest_push_id
                print_waybar(actor, f"Last activity: {repo_name} (@{actor})")
                return

            if latest_push_id != last_event_id:
                last_event_id = latest_push_id
                commits = event["payload"].get("commits", [])
                commit_count = len(commits)
                message = commits[0]["message"].split('\n')[0] if commits else None
                commit_sha = commits[0]["sha"] if commits else None
                
                if not message and event["payload"].get("head"):
                    commit_sha = event["payload"].get("head")
                    message = get_commit_message(repo_full_name, commit_sha)
                
                if not message:
                    message = "New update"

                title = f"New Push by @{actor}"
                if commit_count > 1: title = f"@{actor} pushed {commit_count} commits"
                
                full_text = f"[{branch}] {message}"
                short_text = full_text[:35] + ".." if len(full_text) > 35 else full_text
                
                print_waybar(short_text, f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}")

                notif_body = f"Repo: {repo_name}\nBranch: {branch}\nMsg: {message}"
                avatar_path = download_avatar(actor, avatar_url)
                send_notification(title, notif_body, repo_full_name, commit_sha, avatar_path)
                
                time.sleep(3)
                
                print_waybar(repo_name, f"Last activity: {repo_name} (@{actor})")
                time.sleep(3)

                print_waybar(actor, f"Last activity: {repo_name} (@{actor})")
            break

if __name__ == "__main__":
    filter_mode = len(sys.argv) > 1 and sys.argv[1] == "my_repos_only"
    
    get_latest_push(is_startup=True, my_repos_only=filter_mode)
    
    try:
        while True:
            time.sleep(20)
            get_latest_push(my_repos_only=filter_mode)
    except KeyboardInterrupt:
        sys.exit(0)