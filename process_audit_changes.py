import json
import sys
from typing import List, Dict, Optional
from get_all_github_commits import GitHubAuditFinder
from get_commit_file_changes import MAX_WORKERS, get_github_changes_with_blobs
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


class AuditChangesProcessor:
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize the audit changes processor.
        
        Args:
            github_token: Optional GitHub personal access token
        """
        self.github_token = github_token
        self.finder = GitHubAuditFinder(github_token)
    
    def process_commit_changes(self, commit_url: str) -> Dict:
        """
        Process a single commit to get its changes.
        
        Args:
            commit: Commit dictionary with 'url' field
            
        Returns:
            Dictionary with commit info and changes
        """

        if not commit_url:
            return {
                'error': 'No URL in commit'
            }
        
        print(f"  Fetching changes for commit {commit_url}")
        
        try:
            changes = get_github_changes_with_blobs(commit_url, self.github_token)
            #print(changes)
            return changes
        except Exception as e:
            print(f"    Error getting changes: {e}")
            return {
                'error': str(e)
            }
    
    def get_finding_commit_data(self, finding: Dict) -> Dict:
        """
        Process a single finding: get commits and their changes.
        
        Args:
            finding: Dictionary containing finding data
            
        Returns:
            Dictionary with finding info, commits, and changes for each commit
        """
        print(f"\n--- Processing finding: {finding.get('finding_number', 'N/A')} ---")
        print(f"Title: {finding.get('title', 'N/A')[:80]}")
    
        
        # Get commits using GitHubAuditFinder
        result = self.finder.process_finding(finding)
        if 'error' in result:
            print(f"Error: {result['error']}")
            return result
        
        
        cleaned_results = []
        for commit_data in result['commits']:
            message = commit_data.get("message", "")
            url = commit_data.get("url", "")
            obj = {
                "url": url,
                "message": message
            }
            cleaned_results.append(obj)

        # Process each commit to get changes in parallel
        commits_with_changes = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all commit processing tasks
            future_to_commit = {
                executor.submit(self._process_single_commit_with_changes, commit): commit
                for commit in cleaned_results
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_commit):
                commit = future_to_commit[future]
                try:
                    result = future.result()
                    if result:  # Only add if we got valid changes
                        print(result)
                        commits_with_changes.append(result)
                except Exception as e:
                    print(f"Error processing commit {commit.get('url', '')}: {e}")
        
        return commits_with_changes

    def _process_single_commit_with_changes(self, commit: Dict) -> Optional[Dict]:
        """
        Helper method to process a single commit and get its changes.
        Used for parallel processing.
        
        Args:
            commit: Dictionary with 'url' and 'message'
            
        Returns:
            Dictionary with commit data and changes, or None if no changes
        """
        commit_changes = self.process_commit_changes(commit.get("url", ""))
        if commit_changes and sum(len(v) for v in commit_changes.values()) > 0:
            return {
                "url": commit.get("url", ""),
                "message": commit.get("message", ""),
                "changes": commit_changes
            }
        return None

        return commits_with_changes
    
    def process_json_file(self, filepath: str) -> List[Dict]:
        """
        Process a JSON file containing findings.
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            List of processed findings with commits and changes
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                findings = json.load(f)
            
            if not isinstance(findings, list):
                findings = [findings]

            results = {}
            for i, finding in enumerate(findings, 1):
                print(f"\n{'='*80}")
                print(f"FINDING {i}/{len(findings)}")
                print(f"{'='*80}")
                title = finding.get('title', 'N/A')
                print(finding)
                result = self.get_finding_commit_data(finding)
                results[title] = result
            
            return results
            
        except Exception as e:
            print(f"Error processing JSON file: {e}")
            return []


def main():
    """Main function to run the script."""
    if len(sys.argv) < 2:
        print("Usage: python process_audit_changes.py <json_file>")
        print("\nExample: python process_audit_changes.py findings.json")
        print("         python process_audit_changes.py findings.json ghp_yourtoken123")
        sys.exit(1)
    
    json_file = sys.argv[1]
    github_token = os.getenv("GITHUB_API_KEY")
    
    # Initialize processor
    processor = AuditChangesProcessor(github_token)
    
    # Process JSON file
    results = processor.process_json_file(json_file)
    
    # Print summary
    print("\n=== SUMMARY ===\n")
    for finding_title, commits_list in results.items():
        print(f"Finding: {finding_title}")
        print(f"Number of commits: {len(commits_list)}")
        
        for commit in commits_list:
            print(f"  URL: {commit['url']}")
            print(f"  Message: {commit['message']}")
            for file, funcs in commit['changes'].items():
                print(f"{file}: {funcs}")


if __name__ == '__main__':
    main()