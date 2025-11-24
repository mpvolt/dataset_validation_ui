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

MAX_THREADS = 16  # Increased for better I/O parallelism
CHUNK_SIZE = 50  # Process commits in chunks to manage memory

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth, per_page=100)  # Fetch more items per page
client = OpenAI(api_key=OPENAI_API_KEY)

def get_owner_repo_from_url(url):
    """Extracts GitHub repo owner and repo name from a URL."""
    match = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)", url)
    if match:
        return match.group("owner"), match.group("repo")
    return None, None

def ensure_list(field):
    if field is None:
        return []
    if isinstance(field, str):
        return [field]
    if isinstance(field, list):
        return field
    raise ValueError(f"Expected string or list, got {type(field)}")

def is_solidity_file(filename):
    """Check if a file is a Solidity file (.sol extension)."""
    return (
        filename.endswith('.sol') and 
        '.t.' not in filename and 
        'interface' not in filename.lower() and
        'mock' not in filename.lower() and
        'test' not in filename.lower()
    )

# ==============================
# EXTRACT COMMIT HUNKS (SOL FILES ONLY)
# ==============================
def extract_commit_hunks(commit):
    """Extract file changes and hunks from a commit (only .sol files)."""
    results = []
    for file in commit.files:
        if not is_solidity_file(file.filename):
            continue
            
        patch = file.patch
        if not patch:
            continue

        hunks = []
        current_hunk = None

        for line in patch.split("\n"):
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {"header": line, "lines": []}
            else:
                if current_hunk:
                    current_hunk["lines"].append(line)

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
# OPTIMIZED: BATCH FETCH & FILTER
# ==============================
def fetch_commit_batch(commit_sha, repo):
    """
    Fetch a single commit with full details.
    Returns the commit object or None on error.
    """
    try:
        return repo.get_commit(commit_sha)
    except Exception as e:
        print(f"Error fetching commit {commit_sha}: {e}")
        return None

def matches_any_query_compiled(text, compiled_patterns, original_queries):
    """Check if text matches any of the compiled search patterns."""
    if not text:
        return []
    
    matches = []
    for pattern, query in zip(compiled_patterns, original_queries):
        if pattern.search(text):
            matches.append(query)
    return matches

def filter_commit_in_memory_compiled(commit, compiled_patterns, original_queries):
    """
    Filter a commit in memory using pre-compiled regex patterns.
    Returns result dict or None if no match.
    """
    # Early exit: Check if any .sol files exist first (cheapest check)
    has_sol_files = any(is_solidity_file(f.filename) for f in commit.files)
    if not has_sol_files:
        return None
    
    matched_queries = []
    
    # Check commit message
    if commit.commit.message:
        message_matches = matches_any_query_compiled(commit.commit.message, compiled_patterns, original_queries)
        matched_queries.extend(message_matches)
    
    # Check .sol file patches
    for file in commit.files:
        if is_solidity_file(file.filename) and file.patch:
            patch_matches = matches_any_query_compiled(file.patch, compiled_patterns, original_queries)
            matched_queries.extend(patch_matches)
            
            # Early exit: if we found matches, no need to check all files
            if matched_queries:
                break
    
    if not matched_queries:
        return None
    
    # Remove duplicates while preserving order
    seen = set()
    matched_queries = [q for q in matched_queries if not (q in seen or seen.add(q))]
    
    # Extract hunks only if we have matches
    hunk_data = extract_commit_hunks(commit)
    
    # Skip if no .sol files with patches
    if not hunk_data:
        return None
    
    return {
        "commit_url": commit.html_url,
        "message": commit.commit.message,
        "query_match": ", ".join(matched_queries),
        "files_changed": hunk_data
    }

def search_commits_optimized(commits, all_queries, repo, max_threads=16):
    """
    Optimized search that:
    1. Fetches commits in chunks to manage memory
    2. Filters them in memory (no additional API calls)
    3. Short-circuits on first match per commit
    """
    # Compile regex patterns once for all commits
    

    compiled_patterns = [
        re.compile(re.escape(query), re.IGNORECASE)
        for query in all_queries
    ]
    
    total_commits = len(commits)
    print(f"Processing {total_commits} commits in chunks of {CHUNK_SIZE}...")
    
    all_results = []
    
    # Process in chunks to manage memory
    for chunk_start in range(0, total_commits, CHUNK_SIZE):
        chunk_end = min(chunk_start + CHUNK_SIZE, total_commits)
        chunk = commits[chunk_start:chunk_end]
        
        print(f"Processing commits {chunk_start+1}-{chunk_end}/{total_commits}...")
        
        # Phase 1: Fetch chunk of commits in parallel
        fetch_futures = []
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for commit in chunk:
                fetch_futures.append(executor.submit(fetch_commit_batch, commit.sha, repo))
            
            # Collect fetched commits as they complete
            fetched_commits = []
            for future in as_completed(fetch_futures):
                commit_obj = future.result()
                if commit_obj:
                    fetched_commits.append(commit_obj)
        
        # Phase 2: Filter in memory (parallel processing, no API calls)
        filter_futures = []
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for commit in fetched_commits:
                filter_futures.append(
                    executor.submit(filter_commit_in_memory_compiled, commit, compiled_patterns, all_queries)
                )
            
            for future in as_completed(filter_futures):
                result = future.result()
                if result:
                    all_results.append(result)
        
        print(f"  Found {len([r for r in all_results if chunk_start <= all_results.index(r) < chunk_end])} matches in this chunk")
    
    print(f"Total matches found: {len(all_results)}")
    return all_results

def search_github_commits_parallel(function_names, variable_names, code_patterns,
                                   owner, name, max_threads=16, max_commits=None):
    """
    Search all commits in a repository for matching queries.
    Optimized to fetch once and filter in memory.
    
    Args:
        max_commits: Limit number of commits to search (None = all)
    """
    repo = g.get_repo(f"{owner}/{name}")
    all_queries = function_names + variable_names + code_patterns
    
    # Early exit if no queries
    if not all_queries:
        print("No search queries provided")
        return []
    
    # Get lightweight commit list (only 1 API call)
    print("Fetching commit list...")
    if max_commits:
        commits = list(repo.get_commits()[:max_commits])
        print(f"Limiting to {len(commits)} most recent commits")
    else:
        commits = list(repo.get_commits())
        print(f"Found {len(commits)} total commits")
    
    return search_commits_optimized(commits, all_queries, repo, max_threads)

def search_pr_commits_parallel(pr_number, function_names, variable_names, code_patterns, 
                               owner, name, max_threads=16):
    """
    Search commits in a PR for matching queries.
    Optimized to fetch once and filter in memory.
    """
    repo = g.get_repo(f"{owner}/{name}")
    pr = repo.get_pull(int(pr_number))
    
    all_queries = function_names + variable_names + code_patterns
    
    # Early exit if no queries
    if not all_queries:
        print("No search queries provided")
        return []
    
    # Get lightweight commit list (only 1 API call)
    print(f"Fetching commits for PR #{pr_number}...")
    commits = list(pr.get_commits())
    print(f"Found {len(commits)} commits in PR")
    
    return search_commits_optimized(commits, all_queries, repo, max_threads)

# ==============================
# PARSE GITHUB URL
# ==============================
def parse_github_url(url):
    """
    Returns a dict: {"type": "commit|pull|compare|blob", "owner": ..., "repo": ..., "id_or_path": ...}
    """
    patterns = {
        "pull": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<pr_number>\d+)",
        "commit": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commit/(?P<sha>[a-f0-9]+)",
        "compare": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/compare/(?P<base>[^.]+)\.\.\.(?P<head>[^/]+)",
        "blob": r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
    }

    for t, pat in patterns.items():
        m = re.search(pat, url)
        if m:
            data = m.groupdict()
            data["type"] = t
            return data
    return {"type": "unknown"}

# ==============================
# MAIN
# ==============================
def parse_all_commits(vuln_report):
    prompt = generate_ai_prompt(vuln_report)
    candidates = extract_candidates_with_gpt(prompt)

    urls = ensure_list(vuln_report.get("fix_commit_url")) or ensure_list(vuln_report.get("source_code_url"))

    all_commits = []
    
    for url in urls:
        owner, name = get_owner_repo_from_url(url)
        
        if not owner or not name:
            print(f"Could not parse owner/repo from URL: {url}")
            continue

        print(f"\nAnalyzing repo: {owner}/{name}")
        print("Candidate functions/variables/patterns:", candidates)

        url_info = parse_github_url(url)
        
        if url_info["type"] == "pull":
            pr_number = int(url_info["pr_number"])
            print(f"Searching PR #{pr_number}...")
            commits = search_pr_commits_parallel(
                pr_number,
                candidates.get("function_names", []),
                candidates.get("variable_names", []),
                candidates.get("code_patterns", []),
                owner, 
                name            
            )
        else:
            print("Searching all commits in repository...")
            commits = search_github_commits_parallel(
                candidates.get("function_names", []),
                candidates.get("variable_names", []),
                candidates.get("code_patterns", []),
                owner, 
                name            
            )
        
        print(f"Found {len(commits)} commits matching candidates")
        all_commits.extend(commits)
    
    return all_commits

def main():
    import time
    start_time = time.time()
    
    with open("/Users/matt/vulnaut/dataset_validation_ui/filtered_Anyrand.json") as f:
        vuln_report = json.load(f)
    
    commits = parse_all_commits(vuln_report)

    with open("commits.ndjson", "w") as f:
        for commit in commits:
            f.write(json.dumps(commit) + "\n")
    
    elapsed = time.time() - start_time
    print(f"\n✅ Saved {len(commits)} commits to commits.ndjson")
    print(f"⏱️  Total time: {elapsed:.2f} seconds")
    
    if commits:
        print(f"📊 Average time per commit: {elapsed/len(commits):.3f} seconds")

if __name__ == "__main__":
    main()