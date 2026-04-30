#!/usr/bin/env python3
"""
Rewrite git commit timestamps for 1claw repos.
All commits between 19:00 and 08:00 (next day), random intervals, chrono order.
Handles submodule pointer updates in parent repo.
"""
import subprocess, random, os, sys, json, re, datetime

def run(cmd, cwd=None, shell=False):
    """Run a command, return stdout. Exit on error."""
    if shell:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, shell=True)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        print(f"ERROR: {cmd}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def get_commits(repo_path):
    """Get all commits in chronological order (oldest first)."""
    out = run(['git', 'log', '--reverse', '--format=%H|%ai|%s'], cwd=repo_path)
    commits = []
    for line in out.split('\n'):
        if not line: continue
        parts = line.split('|', 2)
        commits.append({'hash': parts[0], 'date': parts[1], 'msg': parts[2] if len(parts) > 2 else ''})
    return commits

def get_commit_tree(repo_path, hashval):
    """Get the tree hash for a commit."""
    return run(['git', 'rev-parse', f'{hashval}^{{tree}}'], cwd=repo_path)

def get_submodule_gitlink(repo_path, commit_hash, submodule_path):
    """Get the gitlink hash in a parent repo commit for a submodule."""
    out = run(['git', 'ls-tree', commit_hash, submodule_path], cwd=repo_path)
    if not out:
        return None
    parts = out.split()
    if len(parts) >= 3:
        return parts[2]  # blob hash (the gitlink)
    return None

def generate_night_timestamps(num_commits, start_date_str="2026-04-30", nights_back=14):
    """
    Generate strictly increasing timestamps between 19:00-07:59.
    Uses slot-based distribution to guarantee no timestamp exceeds 08:00.
    """
    start = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    
    max_per_night = 15
    needed_nights = max(nights_back, (num_commits + max_per_night - 1) // max_per_night)
    
    # For each night, partition 600 min (19:00-05:00) into equal slots per commit
    SLOTS = 600  # 19:00 to 05:00 = 10 hours = 600 minutes → huge buffer
    
    timestamps = []
    for i in range(num_commits):
        night_idx = i // max_per_night
        if night_idx >= needed_nights:
            night_idx = needed_nights - 1
        
        night_start = start - datetime.timedelta(days=night_idx)
        
        # How many commits in this night?
        start_in_night = night_idx * max_per_night
        end_in_night = min(start_in_night + max_per_night, num_commits)
        count_in_night = end_in_night - start_in_night
        
        pos_in_night = i - start_in_night  # 0, 1, 2, ..., count_in_night-1
        
        # Base slot: evenly distribute within the window
        if count_in_night > 1:
            base = int(pos_in_night * SLOTS / (count_in_night - 1))
        else:
            base = SLOTS // 2
        
        # Small jitter (±3 min, but ensure ordering)
        jitter = random.randint(-3, 3)
        offset = max(0, min(SLOTS, base + jitter))
        
        dt = night_start.replace(hour=19, minute=0, second=0, microsecond=0)
        dt += datetime.timedelta(minutes=offset)
        timestamps.append(dt)
    
    # Sort chronologically (cross-night already sorted, but sort for safety)
    timestamps.sort()
    
    # Ensure strictly increasing — only minor adjustments needed
    result = []
    for i, dt in enumerate(timestamps):
        if i == 0:
            result.append(dt)
        else:
            prev = result[-1]
            if dt <= prev:
                dt = prev + datetime.timedelta(minutes=1)
            # Safety: never past 07:59
            if dt.hour >= 8:
                dt = prev + datetime.timedelta(minutes=1)
                if dt.hour >= 8:
                    dt = prev + datetime.timedelta(seconds=30)
                    if dt.hour >= 8:
                        dt = dt.replace(hour=7, minute=59, second=0)
            result.append(dt)
    
    return [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in result]

def rewrite_repo_dates(repo_path, timestamps, repo_name):
    """
    Use git filter-branch --env-filter to rewrite all commit dates.
    timestamps: list of formatted timestamps, oldest-first.
    """
    os.chdir(repo_path)
    commit_count = len(timestamps)
    
    # Build a mapping: commit_hash → new timestamp
    commits = get_commits(repo_path)
    if len(commits) != commit_count:
        # Use all commits
        commits = commits[-commit_count:] if commit_count <= len(commits) else commits
    
    hash_to_time = {}
    old_to_new_hash = {}
    
    # Write a mapping file
    mapping_lines = []
    for i, (commit, ts) in enumerate(zip(commits, timestamps)):
        mapping_lines.append(f"{commit['hash']}|{ts}")
        hash_to_time[commit['hash']] = ts
    
    mapping_content = '\n'.join(mapping_lines)
    
    # Write mapping to a file for the filter-branch script
    with open('/tmp/date_map.txt', 'w') as f:
        f.write(mapping_content)
    
    # Create env-filter script
    env_filter = """cat /tmp/date_map.txt | while IFS='|' read -r h t; do
    if [ "$GIT_COMMIT" = "$h" ]; then
        export GIT_AUTHOR_DATE="$t"
        export GIT_COMMITTER_DATE="$t"
        break
    fi
done"""
    
    # Write the filter script
    filter_script = '''#!/bin/bash
while IFS='|' read -r h t; do
    if [ "$GIT_COMMIT" = "$h" ]; then
        export GIT_AUTHOR_DATE="$t"
        export GIT_COMMITTER_DATE="$t"
        break
    fi
done < /tmp/date_map.txt
'''
    
    with open('/tmp/env_filter.sh', 'w') as f:
        f.write(filter_script)
    os.chmod('/tmp/env_filter.sh', 0o755)
    
    print(f"Rewriting {repo_name}: {len(commits)} commits")
    
    # Run filter-branch — use '.' instead of 'source' for POSIX sh
    result = subprocess.run(
        ['git', 'filter-branch', '-f', '--env-filter',
         '. /tmp/env_filter.sh',
         'HEAD'],
        capture_output=True, text=True, cwd=repo_path
    )
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[-2000:]}")
        return None
    
    # Build old→new hash mapping
    new_commits = get_commits(repo_path)
    for old_c, new_c in zip(commits, new_commits):
        old_to_new_hash[old_c['hash']] = new_c['hash']
    
    return old_to_new_hash

def rewrite_parent_with_gitlinks(repo_path, timestamps, app_hash_map, server_hash_map):
    """
    Rewrite parent repo dates AND update submodule gitlinks.
    """
    os.chdir(repo_path)
    commits = get_commits(repo_path)
    
    hash_to_time = {}
    for c, ts in zip(commits, timestamps):
        hash_to_time[c['hash']] = ts
    
    with open('/tmp/date_map.txt', 'w') as f:
        for c, ts in zip(commits, timestamps):
            f.write(f"{c['hash']}|{ts}\n")
    
    # Build old→new for any submodule
    # Write a more complex filter script that does both env + gitlink update
    # We use --index-filter to update gitlinks and --env-filter for dates
    
    # Create the index-filter script
    index_filter_script = '''#!/bin/bash
# Update gitlinks for submodules using old→new hash maps
# Check 1claw-app gitlink
APP_GITLINK=$(git ls-files --stage -- 1claw-app 2>/dev/null | awk '{print $2}')
if [ -n "$APP_GITLINK" ]; then
    while IFS= read -r hash_info; do
        old_hash=$(echo "$hash_info" | cut -d' ' -f1)
        new_hash=$(echo "$hash_info" | cut -d' ' -f2)
        if [ "$APP_GITLINK" = "$old_hash" ]; then
            git update-index --add --cacheinfo 160000,"$new_hash",1claw-app 2>/dev/null
            break
        fi
    done < /tmp/app_hash_map.txt
fi
# Check 1claw-server gitlink
SRV_GITLINK=$(git ls-files --stage -- 1claw-server 2>/dev/null | awk '{print $2}')
if [ -n "$SRV_GITLINK" ]; then
    while IFS= read -r hash_info; do
        old_hash=$(echo "$hash_info" | cut -d' ' -f1)
        new_hash=$(echo "$hash_info" | cut -d' ' -f2)
        if [ "$SRV_GITLINK" = "$old_hash" ]; then
            git update-index --add --cacheinfo 160000,"$new_hash",1claw-server 2>/dev/null
            break
        fi
    done < /tmp/server_hash_map.txt
fi
'''
    
    with open('/tmp/index_filter.sh', 'w') as f:
        f.write(index_filter_script)
    os.chmod('/tmp/index_filter.sh', 0o755)
    
    # Write hash mapping files
    with open('/tmp/app_hash_map.txt', 'w') as f:
        for old_h, new_h in app_hash_map.items():
            f.write(f"{old_h} {new_h}\n")
    
    with open('/tmp/server_hash_map.txt', 'w') as f:
        for old_h, new_h in server_hash_map.items():
            f.write(f"{old_h} {new_h}\n")
    
    print(f"\n{'='*60}")
    print(f"Rewriting parent repo (1claw): {len(commits)} commits + gitlink updates")
    print(f"{'='*60}")
    
    # Combined filter: --index-filter for gitlinks, --env-filter for dates
    result = subprocess.run(
        ['git', 'filter-branch', '-f',
         '--index-filter', '. /tmp/index_filter.sh',
         '--env-filter', '. /tmp/env_filter.sh',
         'HEAD'],
        capture_output=True, text=True, cwd=repo_path
    )
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[-2000:]}")
        return None
    
    new_commits = get_commits(repo_path)
    old_to_new = {}
    for old_c, new_c in zip(commits, new_commits):
        old_to_new[old_c['hash']] = new_c['hash']
    return old_to_new


def verify_dates(repo_path, repo_name):
    """Verify all commits are between 19:00-08:00."""
    os.chdir(repo_path)
    out = run(['git', 'log', '--format=%H %ai'])
    lines = out.split('\n')
    
    issues = []
    for line in lines:
        if not line: continue
        parts = line.split(' ', 2)
        h, dt_str = parts[0], parts[1] + ' ' + parts[2]
        # %ai format: "2026-04-30 19:07:00 +0800" — strip timezone
        dt_str_clean = dt_str.rsplit(' ', 1)[0] if ' +' in dt_str else dt_str
        dt = datetime.datetime.strptime(dt_str_clean, "%Y-%m-%d %H:%M:%S")
        hour = dt.hour
        if hour >= 8 and hour < 19:
            issues.append(f"{h[:8]} {dt_str} NOT IN RANGE")
    
    if issues:
        print(f"\n⚠️  {repo_name}: {len(issues)} commits outside 19:00-08:00:")
        for iss in issues[:5]:
            print(f"  {iss}")
    else:
        print(f"\n✅ {repo_name}: ALL {len(lines)} commits between 19:00-08:00 ✓")
    
    # Show time span
    first = run(['git', 'log', '--reverse', '--format=%ai', 'HEAD'], cwd=repo_path)
    last = run(['git', 'log', '--format=%ai', '-1', 'HEAD'], cwd=repo_path)
    f_line = first.split('\n')[0] if first else '?'
    print(f"   Span: {f_line} → {last}")
    
    return len(issues) == 0


def force_push(repo_path, repo_name, remote='github'):
    """Force push rewritten history to GitHub."""
    os.chdir(repo_path)
    print(f"\nForce pushing {repo_name} → {remote}...")
    result = subprocess.run(
        ['git', 'push', '--force', remote, 'HEAD:main'],
        capture_output=True, text=True
    )
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[-2000:]}")
        return False
    
    # Verify remote matches local
    remote_hash = run(['git', 'ls-remote', remote, 'HEAD'], cwd=repo_path).split()[0]
    local_hash = run(['git', 'rev-parse', 'HEAD'], cwd=repo_path)
    if remote_hash == local_hash:
        print(f"✅ {repo_name}: remote HEAD matches local ({local_hash[:12]})")
        return True
    else:
        print(f"⚠️  {repo_name}: remote {remote_hash[:12]} ≠ local {local_hash[:12]}")
        return False


if __name__ == '__main__':
    random.seed(42)
    base = '/home/j/Codes/1claw'
    
    repos = {
        '1claw-app': os.path.join(base, '1claw-app'),
        '1claw-server': os.path.join(base, '1claw-server'),
        '1claw': base,
    }
    
    # Step 1: Check state and generate timestamps for each repo
    print("Analyzing repos...")
    commit_counts = {}
    total_commits = 0
    for name, path in repos.items():
        commits = get_commits(path)
        commit_counts[name] = len(commits)
        total_commits += len(commits)
        print(f"  {name}: {len(commits)} commits, {commits[0]['date'][:10]} → {commits[-1]['date'][:10]}")
    
    print(f"\nTotal: {total_commits} commits across 3 repos")
    
    # Step 2: Generate timestamps for each repo
    # Use last commit date as reference, spread backwards
    last_date_app = get_commits(repos['1claw-app'])[-1]['date'][:10]
    last_date_server = get_commits(repos['1claw-server'])[-1]['date'][:10]
    last_date_parent = get_commits(repos['1claw'])[-1]['date'][:10]
    
    # Each repo gets timestamps relative to its own last commit
    timestamps_app = generate_night_timestamps(commit_counts['1claw-app'], last_date_app, 14)
    timestamps_server = generate_night_timestamps(commit_counts['1claw-server'], last_date_server, 14)
    timestamps_parent = generate_night_timestamps(commit_counts['1claw'], last_date_parent, 14)
    
    # Print sample timestamps for each repo
    for name, ts in [('1claw-app', timestamps_app), ('1claw-server', timestamps_server), ('1claw', timestamps_parent)]:
        print(f"\n{name}: {len(ts)} timestamps")
        print(f"  First: {ts[0]}")
        print(f"  Last:  {ts[-1]}")
        print(f"  Sample: {ts[len(ts)//3]} → {ts[2*len(ts)//3]}")
    
    # Step 3: Create backup branches
    print("\n\nCreating backup branches...")
    for name, path in repos.items():
        os.chdir(path)
        run(['git', 'branch', '-f', f'backup-{name}', 'HEAD'])
        print(f"  Backup backup-{name} created")
    
    # Step 4: Rewrite 1claw-app
    app_hash_map = rewrite_repo_dates(repos['1claw-app'], timestamps_app, '1claw-app')
    if app_hash_map is None:
        print("❌ Failed to rewrite 1claw-app")
        sys.exit(1)
    
    # Step 5: Rewrite 1claw-server
    server_hash_map = rewrite_repo_dates(repos['1claw-server'], timestamps_server, '1claw-server')
    if server_hash_map is None:
        print("❌ Failed to rewrite 1claw-server")
        sys.exit(1)
    
    # Step 6: Rewrite parent repo with gitlink updates
    parent_hash_map = rewrite_parent_with_gitlinks(repos['1claw'], timestamps_parent, app_hash_map, server_hash_map)
    if parent_hash_map is None:
        print("❌ Failed to rewrite parent repo")
        sys.exit(1)
    
    # Step 7: Verify all commits are in range
    print("\n\n=== VERIFICATION ===")
    all_ok = True
    for name, path in repos.items():
        if not verify_dates(path, name):
            all_ok = False
    
    if not all_ok:
        print("\n⚠️  Some commits outside 19:00-08:00 range. Check above.")
        resp = input("Continue with push? (y/N): ")
        if resp.lower() != 'y':
            print("Aborted.")
            # Restore from backup
            for name, path in repos.items():
                os.chdir(path)
                run(['git', 'checkout', f'backup-{name}'])
                run(['git', 'branch', '-D', 'main'])
                run(['git', 'branch', '-m', 'main'])
            sys.exit(1)
    
    # Step 8: Force push to GitHub
    print("\n\n=== PUSHING TO GITHUB ===")
    all_pushed = True
    for name, path in repos.items():
        if not force_push(path, name):
            all_pushed = False
    
    if all_pushed:
        print("\n🎉 ALL REPOS REWRITTEN AND PUSHED SUCCESSFULLY!")
    else:
        print("\n⚠️  Some pushes failed. Check above.")
    
    # Clean up temp files
    for f in ['/tmp/date_map.txt', '/tmp/env_filter.sh', '/tmp/index_filter.sh',
              '/tmp/app_hash_map.txt', '/tmp/server_hash_map.txt']:
        if os.path.exists(f):
            os.remove(f)
