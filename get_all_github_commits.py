import json
import re
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse
import sys
import os

class GitHubAuditFinder:
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize the GitHub audit finder.
        
        Args:
            github_token: Optional GitHub personal access token for higher rate limits
        """
        self.github_token = github_token
        self.headers = {}
        if github_token:
            self.headers['Authorization'] = f'token {github_token}'
        self.headers['Accept'] = 'application/vnd.github.v3+json'
    
    def parse_github_url(self, url: str) -> Optional[Dict[str, str]]:
        """
        Parse a GitHub URL to extract owner and repo.
        
        Args:
            url: GitHub URL
            
        Returns:
            Dictionary with 'owner' and 'repo' keys, or None if invalid
        """
        pattern = r'github\.com/([^/]+)/([^/]+)'
        match = re.search(pattern, url)
        if match:
            return {
                'owner': match.group(1),
                'repo': match.group(2).replace('.git', '')
            }
        return None
    
    def get_default_branch(self, owner: str, repo: str) -> Optional[str]:
        """
        Get the default branch (main/master) for a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Default branch name or None if error
        """
        url = f'https://api.github.com/repos/{owner}/{repo}'
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get('default_branch', 'main')
        except Exception as e:
            print(f"Error getting default branch for {owner}/{repo}: {e}")
            return None
    
    def extract_commit_sha_from_url(self, url: str) -> Optional[str]:
        """
        Extract commit SHA from a GitHub URL.
        
        Args:
            url: GitHub URL (could be commit, PR, blob, tree, compare, etc.)
            
        Returns:
            Commit SHA if found, None otherwise
        """
        # Match commit URLs like: /commit/abc123 or /commits/abc123
        commit_match = re.search(r'/commits?/([a-f0-9]{7,40})', url)
        if commit_match:
            return commit_match.group(1)
        
        # Match compare URLs like: /compare/abc123...def456 (take the newer/right side)
        compare_match = re.search(r'/compare/[a-f0-9]{7,40}\.\.\.([a-f0-9]{7,40})', url)
        if compare_match:
            return compare_match.group(1)
        
        # Match blob URLs like: /blob/abc123/path/to/file (convert to commit)
        blob_match = re.search(r'/blob/([a-f0-9]{7,40})/', url)
        if blob_match:
            return f'BLOB#{blob_match.group(1)}'  # Mark for conversion
        
        # Match tree URLs like: /tree/abc123 or /tree/abc123/path (convert to commit)
        tree_match = re.search(r'/tree/([a-f0-9]{7,40})(?:/|$)', url)
        if tree_match:
            return f'TREE#{tree_match.group(1)}'  # Mark for conversion
        
        # Match PR URLs - we'll need to fetch the PR to get the commit
        pr_match = re.search(r'/pull/(\d+)', url)
        if pr_match:
            return f'PR#{pr_match.group(1)}'  # Mark as PR for special handling
        
        return None
    
    def resolve_ref_to_commit(self, owner: str, repo: str, ref: str) -> Optional[str]:
        """
        Resolve a git reference (branch, tag, or SHA) to a commit SHA.
        This is used to convert tree/blob references to actual commits.
        
        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git reference (can be SHA, branch name, or tag)
            
        Returns:
            Commit SHA or None if error
        """
        url = f'https://api.github.com/repos/{owner}/{repo}/commits/{ref}'
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get('sha')
        except Exception as e:
            print(f"Error resolving ref {ref}: {e}")
            return None
    
    def get_pr_commits(self, owner: str, repo: str, pr_number: str) -> List[Dict]:
        """
        Get all commits from a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            List of commits in the PR
        """
        url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/commits'
        commits = []
        params = {'per_page': 100}
        
        try:
            while url:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                commits.extend(response.json())
                
                # Check for pagination
                if 'next' in response.links:
                    url = response.links['next']['url']
                    params = {}
                else:
                    break
                    
        except Exception as e:
            print(f"Error fetching PR commits: {e}")
        
        return commits
    
    def get_commit_history_range(self, owner: str, repo: str, base_sha: str, target_sha: str) -> List[Dict]:
        """
        Get the full commit range between base and target, including
        the base and target commits themselves.

        Args:
            owner: Repository owner
            repo: Repository name
            base_sha: Starting commit (older)
            target_sha: Ending commit (newer)
            
        Returns:
            List of commits including base, intermediate, and target.
        """
        compare_url = f'https://api.github.com/repos/{owner}/{repo}/compare/{base_sha}...{target_sha}'

        try:
            # 1. Get the comparison data (intermediate commits)
            response = requests.get(compare_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            commits = data.get('commits', [])

            # 2. Always fetch the base and target commits directly
            base_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{base_sha}'
            target_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{target_sha}'

            base_commit = requests.get(base_url, headers=self.headers).json()
            target_commit = requests.get(target_url, headers=self.headers).json()

            # 3. Prepend base commit, append target commit (ensuring no duplicates)
            result = []
            result.append(base_commit)

            # Add intermediate commits
            for c in commits:
                if c['sha'] not in {base_sha, target_sha}:
                    result.append(c)

            result.append(target_commit)

            return result

        except Exception as e:
            print(f"Error getting commit history range: {e}")
            return []
    
    def get_commits_before(self, owner: str, repo: str, sha: str, count: int = 20) -> List[Dict]:
        """
        Get N commits before a specific commit.
        
        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA to start from
            count: Number of commits to retrieve before the SHA
            
        Returns:
            List of commits
        """
        url = f'https://api.github.com/repos/{owner}/{repo}/commits'
        params = {'sha': sha, 'per_page': count + 1}  # +1 to include the commit itself
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            commits = response.json()
            # Skip the first commit (the SHA itself) and return the next 'count' commits
            return commits[1:count+1] if len(commits) > 1 else []
        except Exception as e:
            print(f"Error fetching commits before {sha}: {e}")
            return []
        """
        Get all commits from a repository branch.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name
            
        Returns:
            List of commit dictionaries
        """
        commits = []
        url = f'https://api.github.com/repos/{owner}/{repo}/commits'
        params = {'sha': branch, 'per_page': 100}
        
        try:
            while url:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                commits.extend(response.json())
                
                # Check for pagination
                if 'next' in response.links:
                    url = response.links['next']['url']
                    params = {}  # URL already contains params
                else:
                    break
                    
        except Exception as e:
            print(f"Error fetching commits for {owner}/{repo}: {e}")
        
        return commits
    
    def get_commit_comments(self, owner: str, repo: str, commit_sha: str) -> List[Dict]:
        """
        Get all comments for a specific commit.
        
        Args:
            owner: Repository owner
            repo: Repository name
            commit_sha: Commit SHA
            
        Returns:
            List of comment dictionaries
        """
        url = f'https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}/comments'
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            comments = response.json()
            
            # Format comments
            formatted_comments = []
            for comment in comments:
                formatted_comments.append({
                    'id': comment.get('id'),
                    'user': comment.get('user', {}).get('login'),
                    'body': comment.get('body'),
                    'path': comment.get('path'),
                    'line': comment.get('line'),
                    'created_at': comment.get('created_at'),
                    'updated_at': comment.get('updated_at'),
                    'html_url': comment.get('html_url')
                })
            
            return formatted_comments
        except Exception as e:
            print(f"Error fetching comments for commit {commit_sha[:7]}: {e}")
            return []
    
    def format_commits(self, commits: List[Dict], owner: str = None, repo: str = None, fetch_comments: bool = True) -> List[Dict]:
        """
        Format commits into a cleaner structure.
        
        Args:
            commits: List of commit dictionaries from GitHub API
            owner: Repository owner (needed for fetching comments)
            repo: Repository name (needed for fetching comments)
            fetch_comments: Whether to fetch commit comments
            
        Returns:
            List of formatted commits
        """
        formatted_commits = []
        
        for commit in commits:
            sha = commit.get('sha')
            formatted_commit = {
                'sha': sha,
                'message': commit.get('commit', {}).get('message'),
                'author': commit.get('commit', {}).get('author', {}).get('name'),
                'date': commit.get('commit', {}).get('author', {}).get('date'),
                'url': commit.get('html_url')
            }
            
            # Fetch comments if requested and we have the necessary info
            if fetch_comments and owner and repo and sha:
                comments = self.get_commit_comments(owner, repo, sha)
                formatted_commit['comments'] = comments
                if comments:
                    print(f"    Found {len(comments)} comment(s) on commit {sha[:7]}")
            
            formatted_commits.append(formatted_commit)
        
        return formatted_commits
    
    def process_finding(self, finding: Dict) -> Dict:
        """
        Process a single finding from the JSON.
        
        Args:
            finding: Dictionary containing finding data
            
        Returns:
            Dictionary with finding info and relevant commits
        """
        result = {
            'finding_number': finding.get('finding_number'),
            'title': finding.get('title'),
            'severity': finding.get('severity'),
            'commits': [],
            'strategy': None
        }
        
        fix_url = finding.get('fix_commit_url')
        source_url = finding.get('source_code_url')
        
        # Parse GitHub URL
        if fix_url:
            github_url = fix_url
            repo_info = self.parse_github_url(github_url)
            if not repo_info:
                result['error'] = 'Invalid GitHub URL in fix_commit_url'
                return result
            
            owner = repo_info['owner']
            repo = repo_info['repo']
            
            # Check if it's a PR
            pr_match = re.search(r'/pull/(\d+)', github_url)
            if pr_match:
                # Strategy: Get all commits from the PR
                pr_number = pr_match.group(1)
                result['strategy'] = 'pull_request'
                result['description'] = f'All commits in PR #{pr_number}'
                result['pr_number'] = pr_number
                result['github_url'] = github_url
                
                print(f"Fetching commits from PR #{pr_number}...")
                commits = self.get_pr_commits(owner, repo, pr_number)
                print(f"Found {len(commits)} commits in PR")
                
                formatted_commits = self.format_commits(commits, owner, repo)
                result['commits'] = formatted_commits
                return result
            else:
                # Strategy: Regular fix commit - get 20 commits before
                result['strategy'] = 'fix_commit'
                result['description'] = 'Checking 20 commits before the fix commit'
                result['github_url'] = github_url
        elif source_url:
            github_url = source_url
            result['strategy'] = 'source_code'
            result['description'] = 'Checking commits from source to main/master'
            result['github_url'] = github_url
            
            repo_info = self.parse_github_url(github_url)
            if not repo_info:
                result['error'] = 'Invalid GitHub URL in source_code_url'
                return result
            
            owner = repo_info['owner']
            repo = repo_info['repo']
        else:
            result['error'] = 'No GitHub URL found'
            return result
        
        # Get default branch (needed for non-PR strategies)
        branch = self.get_default_branch(owner, repo)
        if not branch:
            result['error'] = 'Could not determine default branch'
            return result
        
        result['branch'] = branch
        
        # Extract commit SHA
        commit_ref = self.extract_commit_sha_from_url(github_url)
        if not commit_ref:
            result['error'] = 'Could not extract commit SHA from URL'
            return result
        
        # Handle special reference types that need resolution
        if commit_ref.startswith('BLOB#') or commit_ref.startswith('TREE#'):
            ref_type = commit_ref.split('#')[0]
            sha = commit_ref.split('#')[1]
            print(f"Converting {ref_type} reference {sha[:7]} to commit...")
            commit_ref = self.resolve_ref_to_commit(owner, repo, sha)
            if not commit_ref:
                result['error'] = f'Could not resolve {ref_type} reference to commit'
                return result
            print(f"Resolved to commit {commit_ref[:7]}")
        
        result['commit_sha'] = commit_ref
        
        # Fetch commits based on strategy
        if result['strategy'] == 'fix_commit':
            print(f"Fetching 20 commits before fix commit {commit_ref[:7]}...")
            commits = self.get_commits_before(owner, repo, commit_ref, count=20)
            print(f"Found {len(commits)} commits before the fix")
        else:  # source_code strategy
            print(f"Fetching commits from {commit_ref[:7]} to {branch}...")
            commits = self.get_commit_history_range(owner, repo, commit_ref, branch)
            print(f"Found {len(commits)} commits in range")
        
        # Format commits with comments
        formatted_commits = self.format_commits(commits, owner, repo)
        result['commits'] = formatted_commits
        
        return result
    
    def process_json_file(self, filepath: str) -> List[Dict]:
        """
        Process a JSON file containing findings.
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            List of processed findings with all commits
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                findings = json.load(f)
            
            if not isinstance(findings, list):
                findings = [findings]
            
            results = []
            for i, finding in enumerate(findings, 1):
                print(f"\n--- Processing finding {i}/{len(findings)} ---")
                result = self.process_finding(finding)
                results.append(result)
            
            return results
            
        except Exception as e:
            print(f"Error processing JSON file: {e}")
            return []


def main():
    """Main function to run the script."""
    if len(sys.argv) < 2:
        print("Usage: python script.py <json_file> [github_token]")
        print("\nExample: python script.py findings.json")
        print("         python script.py findings.json ghp_yourtoken123")
        sys.exit(1)
    
    json_file = sys.argv[1]
    github_token = os.getenv("GITHUB_API_KEY")
    
    # Initialize finder
    finder = GitHubAuditFinder(github_token)
    
    # Process JSON file
    results = finder.process_json_file(json_file)
    
    # Print summary
    print("\n=== Summary ===")
    for result in results:
        print(f"\nFinding: {result.get('finding_number')} - {result.get('title', 'N/A')[:60]}...")
        if 'error' in result:
            print(f"  Error: {result['error']}")
        else:
            print(f"  Repository: {result.get('github_url')}")
            print(f"  Branch: {result.get('branch')}")
            print(f"  Strategy: {result.get('strategy')} - {result.get('description')}")
            print(f"  Reference commit: {result.get('commit_sha', 'N/A')[:7]}")
            print(f"  Total commits: {len(result.get('commits', []))}")
            print(f"\n  Commits:")
            for commit in result.get('commits', []):
                print(f"    [{commit['sha'][:7]}] {commit['date']} - {commit['author']}")
                print(f"      {commit['message'].split(chr(10))[0][:80]}")  # First line only
                print(f"      {commit['url']}")
                print()


if __name__ == '__main__':
    main()