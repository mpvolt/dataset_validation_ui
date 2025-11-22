"""
Process audit changes and get commit data for findings
"""
import os
import json
from parse_all_commits import parse_all_commits
from compute_relevance_gpt import rank_with_gpt

class ProcessAuditChanges:
    """Class to process audit changes and get commit data for findings"""
    
    def __init__(self):
        pass
    
    def get_finding_commit_data(self, finding):
        """Get commit data for a finding"""
        try:
            github_token = os.getenv("GITHUB_API_KEY")
            commits = parse_all_commits(finding, github_token)
            result = rank_with_gpt(finding, commits)
            return result
        except Exception as e:
            return {"error": str(e)}

def main():
    with open("/Users/matt/vulnaut/dataset_validation_ui/filtered_Anyrand.json") as f:
        vuln_report = json.load(f)

    processor = ProcessAuditChanges()
    result = processor.get_finding_commit_data(vuln_report)
    print(result)

if __name__ == "__main__":
    main()

