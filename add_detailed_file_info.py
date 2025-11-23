import re
from github import Github, Auth
from typing import Dict, List, Optional
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Thread-safe lock for printing
print_lock = Lock()

def thread_safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


def is_solidity_file(filename):
    """Check if a file is a Solidity file (.sol extension)."""
    return (
        filename.endswith('.sol') and 
        '.t.' not in filename and 
        'interface' not in filename.lower() and
        'mock' not in filename.lower() and
        'test' not in filename.lower()
    )


def parse_commit_url(commit_url: str) -> Dict[str, str]:
    """
    Extract owner, repo, and commit SHA from GitHub commit URL.
    
    Example: https://github.com/frogworksio/anyrand/commit/03fdb1b...
    Returns: {"owner": "frogworksio", "repo": "anyrand", "sha": "03fdb1b..."}
    """
    pattern = r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commit/(?P<sha>[a-f0-9]+)"
    match = re.search(pattern, commit_url)
    
    if not match:
        raise ValueError(f"Invalid GitHub commit URL: {commit_url}")
    
    return match.groupdict()


def parse_hunk_header(header: str) -> Dict[str, int]:
    """
    Parse a hunk header to extract line number information.
    
    Example: "@@ -53,7 +53,8 @@ function requestRandomness(...)"
    Returns: {
        "old_start": 53,
        "old_count": 7,
        "new_start": 53,
        "new_count": 8
    }
    """
    pattern = r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
    match = re.search(pattern, header)
    
    if not match:
        return {}
    
    old_start, old_count, new_start, new_count, context = match.groups()
    
    result = {
        "old_start": int(old_start),
        "old_count": int(old_count) if old_count else 1,
        "new_start": int(new_start),
        "new_count": int(new_count) if new_count else 1
    }
    
    if context:
        result["context"] = context.strip()
    
    return result


def get_blob_url(owner: str, repo: str, sha: str, filepath: str, ref: str) -> str:
    """
    Construct GitHub blob URL for a specific file at a specific commit.
    
    Args:
        owner: Repository owner
        repo: Repository name
        sha: Commit SHA
        filepath: Path to file in repo
        ref: Git reference (commit SHA for before/after)
    
    Returns:
        GitHub blob URL
    """
    return f"https://github.com/{owner}/{repo}/blob/{ref}/{filepath}"


def extract_detailed_commit_info(commit_obj: dict, commit_number: int, total_commits: int) -> Dict:
    """
    Extract detailed information from a commit object including:
    - Before/after blob links
    - Changed functions
    - Line numbers
    - Hunks
    
    Args:
        commit_obj: Dict with 'url', 'score', 'relevant_files'
        commit_number: Current commit number (for progress)
        total_commits: Total number of commits (for progress)
    
    Returns:
        Detailed commit information with file-level details
    """
    try:
        GITHUB_TOKEN = os.getenv("GITHUB_API_KEY")
        if not GITHUB_TOKEN:
            raise ValueError("GITHUB_API_KEY environment variable not set")
        
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)

        commit_url = commit_obj.get('url', '')
        if not commit_url:
            raise ValueError("Missing commit URL in commit object")
        
        relevant_files = commit_obj.get('relevant_files', [])
        
        # Handle case where relevant_files might be a string or empty
        if isinstance(relevant_files, str):
            # Check if it's a string that indicates "no files" or if it's an actual filename
            if relevant_files.lower() in ['', 'no related files provided', 'none', 'n/a']:
                relevant_files = []
            else:
                relevant_files = [relevant_files]
        elif not isinstance(relevant_files, list):
            # If it's not a string or list, convert to empty list
            relevant_files = []
        
        # Parse the commit URL
        url_parts = parse_commit_url(commit_url)
        owner = url_parts['owner']
        repo_name = url_parts['repo']
        sha = url_parts['sha']
        
        thread_safe_print(f"\n[{commit_number}/{total_commits}] Processing: {commit_url}")
        
        # Fetch the commit from GitHub
        repo = g.get_repo(f"{owner}/{repo_name}")
        commit = repo.get_commit(sha)
        
        # Get parent commit SHA (for "before" state)
        parent_sha = commit.parents[0].sha if commit.parents else None
        
        detailed_info = {
            "commit_url": commit_url,
            "sha": sha,
            "parent_sha": parent_sha,
            "message": commit.commit.message,
            "score": commit_obj.get('score', 0),
            "files": []
        }
        
        # Debug: print all files in commit
        thread_safe_print(f"  Files in commit: {[f.filename for f in commit.files]}")
        thread_safe_print(f"  Looking for: {relevant_files}")
        
        # Process each file in the commit
        for file in commit.files:
            # First check if it's a valid Solidity file
            if not is_solidity_file(file.filename):
                thread_safe_print(f"  Skipping {file.filename} (not a valid Solidity file)")
                continue
            
            # Skip if relevant_files is specified and file not in list
            # Check both exact match and basename match
            if relevant_files:
                filename_matches = any(
                    file.filename == rf or 
                    file.filename.endswith('/' + rf) or
                    os.path.basename(file.filename) == rf
                    for rf in relevant_files
                )
                if not filename_matches:
                    thread_safe_print(f"  Skipping {file.filename} (not in relevant_files)")
                    continue
            
            thread_safe_print(f"  Processing file: {file.filename}")
            
            file_info = {
                "filename": file.filename,
                "status": file.status,  # "modified", "added", "removed"
                "additions": file.additions,
                "deletions": file.deletions,
                "changes": file.changes,
                "blob_url_before": get_blob_url(owner, repo_name, sha, file.filename, parent_sha) if parent_sha and file.status != "added" else None,
                "blob_url_after": get_blob_url(owner, repo_name, sha, file.filename, sha) if file.status != "removed" else None,
                "hunks": []
            }
            
            # Parse the patch to extract hunks
            if file.patch:
                current_hunk = None
                
                for line in file.patch.split("\n"):
                    if line.startswith("@@"):
                        # Save previous hunk
                        if current_hunk:
                            file_info["hunks"].append(current_hunk)
                        
                        # Parse hunk header
                        line_info = parse_hunk_header(line)
                        
                        current_hunk = {
                            "header": line,
                            "old_start_line": line_info.get("old_start"),
                            "old_line_count": line_info.get("old_count"),
                            "new_start_line": line_info.get("new_start"),
                            "new_line_count": line_info.get("new_count"),
                            "context": line_info.get("context"),
                            "lines": []
                        }
                    else:
                        if current_hunk:
                            current_hunk["lines"].append(line)
                
                # Don't forget the last hunk
                if current_hunk:
                    file_info["hunks"].append(current_hunk)
            
            detailed_info["files"].append(file_info)
        
        thread_safe_print(f"  ✓ Found {len(detailed_info['files'])} matching Solidity files")
        
        return detailed_info
    
    except Exception as e:
        # Return error info with the problematic commit
        import traceback
        thread_safe_print(f"  ✗ ERROR: {str(e)}")
        return {
            "commit_url": commit_obj.get('url', 'unknown'),
            "error": str(e),
            "traceback": traceback.format_exc(),
            "original_data": commit_obj
        }


def process_commit_list(commit_objects: List[dict], max_workers: int = 10) -> List[Dict]:
    """
    Process a list of commit objects to extract detailed information in parallel.
    
    Args:
        commit_objects: List of dicts with 'url', 'score', 'relevant_files'
        max_workers: Maximum number of parallel threads (default: 10)
    
    Returns:
        List of detailed commit information
    """
    total_commits = len(commit_objects)
    detailed_commits = [None] * total_commits  # Pre-allocate list to maintain order
    
    print(f"Processing {total_commits} commits with {max_workers} workers...\n")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_index = {
            executor.submit(extract_detailed_commit_info, commit_obj, i+1, total_commits): i
            for i, commit_obj in enumerate(commit_objects)
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                result = future.result()
                detailed_commits[index] = result
                completed += 1
                thread_safe_print(f"\n{'='*60}")
                thread_safe_print(f"Progress: {completed}/{total_commits} commits completed")
                thread_safe_print(f"{'='*60}")
            except Exception as e:
                thread_safe_print(f"\n✗ Unexpected error processing commit {index+1}: {e}")
                detailed_commits[index] = {
                    "error": f"Unexpected error: {str(e)}",
                    "original_data": commit_objects[index]
                }
    
    return detailed_commits


# ==============================
# EXAMPLE USAGE
# ==============================
if __name__ == "__main__":
    # Load your input data from the document you provided
    commit_list = [
        {'url': 'https://github.com/frogworksio/anyrand/commit/95520d26e17beda7da1ac015f505122b6c9df059', 'score': 5, 'relevant_files': ['contracts/Anyrand.sol']}, 
        {'url': 'https://github.com/frogworksio/anyrand/commit/d95dd36ba52697a558a6b4c7826af9d1863a235a', 'score': 0.0, 'reasoning': 'Failed to parse GPT response: Missing keys.'}, 
        {'url': 'https://github.com/frogworksio/anyrand/commit/7d95c0cd685ecdc4f1d0ca935d9572438eb43d82', 'score': 10, 'relevant_files': []}
    ]  # ... add more
    
    # Get GitHub token from environment
    GITHUB_TOKEN = os.getenv("GITHUB_API_KEY")
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_API_KEY environment variable not set")
        exit(1)
    
    # Process all commits in parallel (adjust max_workers as needed)
    all_detailed = process_commit_list(commit_list, max_workers=10)
    
    # Save to file
    with open("detailed_commits.json", "w") as f:
        json.dump(all_detailed, f, indent=2)
    
    print(f"\n✅ Processed {len(all_detailed)} commits")
    print(f"📁 Results saved to detailed_commits.json")