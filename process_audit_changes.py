"""
Process audit changes and get commit data for findings
"""
import json
from parse_all_commits import Auth, parse_all_commits
from compute_relevance_gpt import rank_with_gpt
from add_detailed_file_info import process_commit_list

class ProcessAuditChanges:
    """Class to process audit changes and get commit data for findings"""
    
    def __init__(self):
        pass
    
    def get_finding_commit_data(self, finding):
        """Get commit data for a finding"""       
        try:
            commits = parse_all_commits(finding)
            result = rank_with_gpt(finding, commits)
            detailed_info = process_commit_list(result)
            return detailed_info
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

