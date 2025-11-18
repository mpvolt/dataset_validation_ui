import re
import requests
from typing import Dict, List, Optional
from urllib.parse import urlparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 10
GITHUB_API_URL = "https://api.github.com"
github_token = os.getenv("GITHUB_API_KEY")


def get_github_changes_with_blobs(url: str, github_token: Optional[str] = None) -> Dict[str, Dict[str, any]]:
    headers = {}
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    else:
        print("Github token not found")
        return {}

    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 4:
        raise ValueError("URL does not appear to be a valid GitHub commit or PR URL")
    owner, repo, kind = parts[0], parts[1], parts[2]

    if kind == "commit":
        commit_sha = parts[3]
        return _get_commit_changes(owner, repo, commit_sha, headers)
    elif kind == "pull":
        pr_number = int(parts[3])
        return _get_pr_changes(owner, repo, pr_number, headers)
    else:
        raise ValueError("URL must be a commit or pull request")


def _get_commit_changes(owner, repo, commit_sha, headers):
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{commit_sha}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GitHub API error: {resp.status_code} {resp.text}")
    commit_data = resp.json()
    parent_sha = commit_data["parents"][0]["sha"] if commit_data.get("parents") else commit_sha

    changes = {}

    def process_file(file):
        if not file["filename"].endswith(".sol"):
            return None
        before_blob_path = file.get("previous_filename") or file["filename"]
        after_blob_path = file["filename"]
        status = file["status"]

        before_content = _fetch_contents_fallback(owner, repo, before_blob_path, parent_sha, headers) if status != "added" else ""
        after_content = _fetch_contents_fallback(owner, repo, after_blob_path, commit_sha, headers) if status != "removed" else ""

        before_funcs = _get_changed_functions(before_content, file.get("patch", "")) if before_content else []
        after_funcs  = _get_changed_functions(after_content, file.get("patch", "")) if after_content else []

        before_blob_url = f"https://github.com/{owner}/{repo}/blob/{parent_sha}/{before_blob_path}" if status != "added" else None
        after_blob_url = f"https://github.com/{owner}/{repo}/blob/{commit_sha}/{after_blob_path}" if status != "removed" else None

        return after_blob_path, {
            "functions_before": before_funcs,
            "functions_after": after_funcs,
            "before_blob": before_blob_url,
            "after_blob": after_blob_url
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_file, f): f for f in commit_data.get("files", [])}
        for future in as_completed(future_to_file):
            result = future.result()
            if result:
                file_path, data = result
                changes[file_path] = data

    return changes


def _get_pr_changes(owner: str, repo: str, pr_number: int, headers: dict) -> Dict[str, Dict[str, any]]:
    """Process all commits in a PR and return Solidity files with before/after funcs and blobs."""
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.status_code} {response.text}")

    commits = response.json()
    file_results: Dict[str, Dict[str, any]] = {}

    def process_commit(commit):
        commit_sha = commit['sha']
        commit_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{commit_sha}"
        commit_resp = requests.get(commit_url, headers=headers)
        if commit_resp.status_code != 200:
            return {}
        commit_data = commit_resp.json()
        parent_sha = commit_data["parents"][0]["sha"] if commit_data.get("parents") else commit_sha

        result = {}
        for file in commit_data.get("files", []):
            filename = file["filename"]
            if not filename.endswith(".sol"):
                continue

            status = file.get("status")
            previous_filename = file.get("previous_filename", None)

            before_blob = f"https://github.com/{owner}/{repo}/blob/{parent_sha}/{previous_filename or filename}" if status != "added" else None
            after_blob = f"https://github.com/{owner}/{repo}/blob/{commit_sha}/{filename}" if status != "removed" else None

            before_content = _fetch_contents_fallback(owner, repo, previous_filename or filename, parent_sha, headers) if status != "added" else ""
            after_content = _fetch_contents_fallback(owner, repo, filename, commit_sha, headers) if status != "removed" else ""

            funcs_before = _get_changed_functions(before_content, file.get("patch", ""))
            funcs_after  = _get_changed_functions(after_content, file.get("patch", ""))

            result[filename] = {
                "functions_before": funcs_before,
                "functions_after": funcs_after,
                "before_blob": before_blob,
                "after_blob": after_blob
            }
        return result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_commit, c) for c in commits]
        for future in as_completed(futures):
            commit_files = future.result()
            for f, data in commit_files.items():
                if f not in file_results:
                    file_results[f] = {
                        "functions_before": set(),
                        "functions_after": set(),
                        "before_blob": data["before_blob"],
                        "after_blob": data["after_blob"]
                    }
                file_results[f]["functions_before"].update(data["functions_before"])
                file_results[f]["functions_after"].update(data["functions_after"])

    # Convert function sets to sorted lists
    for f, data in file_results.items():
        data["functions_before"] = sorted(list(data["functions_before"]))
        data["functions_after"] = sorted(list(data["functions_after"]))

    return file_results


def _fetch_contents_fallback(owner, repo, path, commit_sha, headers):
    if not path:
        return None
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}?ref={commit_sha}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None
    data = r.json()
    import base64
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return None


def _get_changed_functions(source: str, patch: str) -> List[str]:
    """
    Returns only the contracts and functions that contain changes from the patch.
    """
    if not source or not patch:
        return []

    changed_lines = _parse_changed_lines_from_patch(patch)
    lines = source.split("\n")
    entries = []
    current_contract = None
    stack = []

    for i, line in enumerate(lines, 1):
        # Contract/library/interface signature
        cm = re.match(r'^\s*(contract|interface|library)\s+([a-zA-Z0-9_]+)\s*(.*)\{?', line)
        if cm:
            ctype, cname, crest = cm.groups()
            current_contract = cname
            signature = cname
            if crest:
                signature += " " + crest.strip()
            stack.append({"name": signature, "contract": None, "start": i, "depth": 0, "started": True, "is_contract": True})

        # Functions/modifiers
        fm = re.match(r'^\s*function\s+([a-zA-Z0-9_]+)\s*\(', line)
        sm = re.match(r'^\s*(constructor|receive|fallback)\s*\(', line)
        mm = re.match(r'^\s*modifier\s+([a-zA-Z0-9_]+)\s*\(', line)
        fn_match = fm or sm or mm
        if fn_match:
            fn_name = fn_match.group(1)
            stack.append({"name": fn_name, "contract": current_contract, "start": i, "depth": 0, "started": False, "is_contract": False})

        # Track braces
        for f in stack:
            if '{' in line: f["started"] = True
            if f["started"]: f["depth"] += line.count('{') - line.count('}')

        # Close completed functions/contracts
        completed = [f for f in stack if f["started"] and f["depth"] == 0]
        for f in completed:
            start, end = f["start"], i
            # Only include if this function contains changed lines
            if any(l in changed_lines for l in range(start, end + 1)):
                if f["is_contract"]:
                    entries.append(f"{f['name']}")
                else:
                    entries.append(f"{f['contract']}::{f['name']}" if f['contract'] else f"{f['name']}")
            stack.remove(f)

    return entries


def _parse_changed_lines_from_patch(patch: str) -> set:
    """
    Returns the set of changed line numbers in the NEW file from a git diff patch.
    """
    changed_lines = set()
    current_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            # hunk header format: @@ -old_start,old_count +new_start,new_count @@
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                current_line = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            changed_lines.add(current_line)
            current_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            # removed line: does not increment new file line counter
            pass
        else:
            current_line += 1
    return changed_lines


# ------------------- Example Usage -------------------
if __name__ == "__main__":
    url = "https://github.com/bcnmy/nexus/pull/216"
    changes = get_github_changes_with_blobs(url, github_token)
    for file, data in changes.items():
        print(f"{file}:")
        print(f"  Functions Before: {data['functions_before']}")
        print(f"  Functions After: {data['functions_after']}")
        print(f"  Before Blob: {data['before_blob']}")
        print(f"  After Blob: {data['after_blob']}")
        print("\n")
