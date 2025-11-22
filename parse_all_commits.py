import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from github import Github, Auth
from openai import OpenAI
import os

# ==============================
# CONFIGURATION
# ==============================
GITHUB_TOKEN = os.getenv("GITHUB_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MAX_THREADS = 8  # adjust based on CPU/network capacity

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
client = OpenAI(api_key=OPENAI_API_KEY)

def get_owner_repo_from_url(url):
    """
    Extracts GitHub repo owner and repo name from a URL.

    Returns:
        (owner, repo) tuple or (None, None) if not found
    """
    # Match https://github.com/owner/repo and optional extra paths
    match = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)", url)
    if match:
        owner = match.group("owner")
        repo = match.group("repo")
        return owner, repo
    return None, None

def ensure_list(field):
    if field is None:
        return []
    if isinstance(field, str):
        return [field]
    if isinstance(field, list):
        return field
    raise ValueError(f"Expected string or list, got {type(field)}")


# --------------------------------------------------------
# Extract relevant hunk lines given queries
# --------------------------------------------------------
def filter_hunks_by_query(commit, queries):
    """
    Returns only the hunk lines that contain at least one query match.
    Queries are exact substrings.
    """

    relevant = []

    files = commit.files
    for f in files:
        if not hasattr(f, "patch") or not f.patch:
            continue

        hunks = f.patch.split("\n")
        current_hunk = []
        header = None

        for line in hunks:
            if line.startswith("@@"):
                if current_hunk:
                    # flush the previous hunk if relevant
                    if any(any(q in l for q in queries) for l in current_hunk):
                        relevant.append({
                            "file": f.filename,
                            "header": header,
                            "lines": current_hunk
                        })
                # start new hunk
                header = line
                current_hunk = [line]
            else:
                current_hunk.append(line)

        # final flush
        if current_hunk:
            if any(any(q in l for q in queries) for l in current_hunk):
                relevant.append({
                    "file": f.filename,
                    "header": header,
                    "lines": current_hunk
                })

    return relevant


# --------------------------------------------------------
# Commit-level query search
# --------------------------------------------------------
def search_commit_for_query(commit, query):
    """
    Checks if a commit contains the query (in the message or patch).
    Returns commit metadata if a match is found.
    """

    # match commit message
    if query.lower() in commit.commit.message.lower():
        return [{
            "commit_url": commit.html_url,
            "commit_message": commit.commit.message,
            "query_match": query
        }]

    # match diff patch
    for f in commit.files:
        if hasattr(f, "patch") and f.patch and query in f.patch:
            return [{
                "commit_url": commit.html_url,
                "commit_message": commit.commit.message,
                "query_match": query
            }]

    return None


# ==============================
#  EXTRACT COMMIT HUNKS
# ==============================
def extract_commit_hunks(commit):
    """
    Extracts file changes and hunks from a commit.
    Returns:
    [
        {
            "filename": "contracts/Anyrand.sol",
            "status": "modified",
            "additions": 10,
            "deletions": 2,
            "changes": 12,
            "hunks": [
                {
                    "header": "@@ -53,7 +53,8 @@ function requestRandomness(...)",
                    "lines": [
                        "- old code",
                        "+ new code",
                        "  unchanged line"
                    ]
                },
                ...
            ]
        },
        ...
    ]
    """

    results = []

    for file in commit.files:
        patch = file.patch  # This contains the **unified diff**.
        if not patch:
            continue

        hunks = []
        current_hunk = None

        for line in patch.split("\n"):
            if line.startswith("@@"):
                # Start of a new hunk
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {"header": line, "lines": []}
            else:
                if current_hunk:
                    current_hunk["lines"].append(line)

        # Append the final hunk
        if current_hunk:
            hunks.append(current_hunk)

        results.append({
            "filename": file.filename,
            "status": file.status,
            "additions": file.additions,
            "deletions": file.deletions,
            "changes": file.changes,
            "hunks": hunks
        })

    return results


# ==============================
# GENERATE AI PROMPT
# ==============================
def generate_ai_prompt(vuln_report):
    report_copy = {k: v for k, v in vuln_report.items() if k != "context"}
    report_text = json.dumps(report_copy, indent=2)
    
    prompt = f"""
You are analyzing a Solidity vulnerability report. Based on the following data, 
extract:
- Likely function names
- Likely variable names
- Any unique code patterns that could be searched in the GitHub repo

Return a JSON object with fields:
{{"function_names": [...], "variable_names": [...], "code_patterns": [...]}}

Report:
{report_text}
"""
    return prompt

# ==============================
# CALL GPT-4o-mini
# ==============================
def extract_candidates_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"}

    )
    gpt_output = response.choices[0].message.content

    try:
        candidates = json.loads(gpt_output)
    except:
        candidates = {"function_names": [], "variable_names": [], "code_patterns": []}
    return candidates

# ==============================
# SEARCH SINGLE COMMIT FOR QUERY
# ==============================
def search_commit_for_query(commit, query):
    matches = []
    if commit.commit.message and re.search(query, commit.commit.message, re.IGNORECASE):
        for f in commit.files:
            if f.patch and re.search(query, f.patch, re.IGNORECASE):
                matches.append({
                    "commit_url": commit.html_url,
                    "commit_message": commit.commit.message,
                    "file": f.filename,
                    "query_match": query
                })
    return matches

# ==============================
# SEARCH ALL COMMITS IN PARALLEL
# ==============================
def search_github_commits_parallel(function_names, variable_names, code_patterns,
                                   owner, name, github_token):
    repo = g.get_repo(f"{owner}/{name}")
    all_queries = function_names + variable_names + code_patterns
    commits = list(repo.get_commits())

    seen = set()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        for commit in commits:
            for query in all_queries:
                futures.append(executor.submit(search_commit_for_query, commit, query))

        for future in as_completed(futures):
            matches = future.result()
            if not matches:
                continue

            for m in matches:
                commit_url = m["commit_url"]

                # ensure unique commit
                if commit_url in seen:
                    continue
                seen.add(commit_url)

                # extract only relevant hunks
                commit = repo.get_commit(commit_url.split("/")[-1])
                relevant_hunks = filter_hunks_by_query(commit, all_queries)

                results.append({
                    "commit_url": commit_url,
                    "message": m["commit_message"],
                    "query_match": m["query_match"],
                    "relevant_hunks": relevant_hunks
                })

    return results


# ==============================
# Search commits in PR in parallel
# ==============================
def search_pr_commits_parallel(pr_number, function_names, variable_names, code_patterns, owner, name):
    repo = g.get_repo(f"{owner}/{name}")
    pr = repo.get_pull(pr_number)
    commits = list(pr.get_commits())

    all_queries = function_names + variable_names + code_patterns
    results = []
    seen = set()       # <-- store commit URLs only


    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        for commit in commits:
            for query in all_queries:
                futures.append(executor.submit(search_commit_for_query, commit, query))
        for future in as_completed(futures):
            matches = future.result()
            if not matches:
                continue

            for m in matches:
                commit_url = m["commit_url"]

                if commit_url not in seen:
                    seen.add(commit_url)
                    hunk_data = extract_commit_hunks(commit)
                    results.append({
                        "commit_url": commit_url,
                        "message": m["commit_message"],
                        "query_match": m["query_match"],
                        "files_changed": hunk_data
                    })
    return results

# ==============================
# PARSE GITHUB URL
# ==============================
def parse_github_url(url):
    """
    Returns a dict: {"type": "commit|pull|compare|blob", "owner": ..., "repo": ..., "id_or_path": ...}
    """
    patterns = {
        "commit": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commit/(?P<sha>[a-f0-9]+)",
        "pull": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<pr_number>\d+)",
        "compare": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/compare/(?P<base>[^.]+)\.\.\.(?P<head>[^/]+)",
        "blob": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
    }

    for t, pat in patterns.items():
        m = re.match(pat, url)
        if m:
            data = m.groupdict()
            data["type"] = t
            return data
    return {"type": "unknown"}

# ==============================
# PROCESS EACH TYPE
# ==============================
def process_commit(owner, repo_name, sha):
    repo = g.get_repo(f"{owner}/{repo_name}")
    commit = repo.get_commit(sha)
    # Do whatever processing you need on the commit
    return commit

def process_pull(owner, repo_name, pr_number):
    repo = g.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(int(pr_number))
    commits = list(pr.get_commits())
    # Process each commit in the PR
    return commits

def process_compare(owner, repo_name, base, head):
    repo = g.get_repo(f"{owner}/{repo_name}")
    comparison = repo.compare(base, head)
    commits = comparison.commits
    return commits

def process_blob(owner, repo_name, ref, path):
    repo = g.get_repo(f"{owner}/{repo_name}")
    contents = repo.get_contents(path, ref=ref)
    return contents.decoded_content.decode("utf-8")

# ==============================
# ROUTER FUNCTION
# ==============================
def process_github_url(url):
    info = parse_github_url(url)
    t = info["type"]
    if t == "commit":
        return process_commit(info["owner"], info["repo"], info["sha"])
    elif t == "pull":
        return process_pull(info["owner"], info["repo"], info["pr_number"])
    elif t == "compare":
        return process_compare(info["owner"], info["repo"], info["base"], info["head"])
    elif t == "blob":
        return process_blob(info["owner"], info["repo"], info["ref"], info["path"])
    else:
        raise ValueError(f"Unknown GitHub URL type: {url}")


# ==============================
# MAIN
# ==============================
def parse_all_commits(vuln_report, github_token):
    prompt = generate_ai_prompt(vuln_report)
    candidates = extract_candidates_with_gpt(prompt)

    urls = ensure_list(vuln_report.get("fix_commit_url")) or ensure_list(vuln_report.get("source_code_url"))

    for url in urls:
        owner, name = get_owner_repo_from_url(url)

        print("Candidate functions/variables/patterns:", candidates)

        commits = search_github_commits_parallel(
            candidates.get("function_names", []),
            candidates.get("variable_names", []),
            candidates.get("code_patterns", []),
            owner, 
            name,
            github_token
        )
        
        print(f"Found {len(commits)} commits matching candidates:")
        for c in commits:
            print(c)
    return commits

def main():
    with open("/Users/matt/vulnaut/dataset_validation_ui/filtered_Anyrand.json") as f:
        vuln_report = json.load(f)
    
    commits = parse_all_commits(vuln_report, GITHUB_TOKEN)

    with open("commits.ndjson", "w") as f:
        for commit in commits:
            f.write(json.dumps(commit) + "\n")
   

if __name__ == "__main__":
    main()
