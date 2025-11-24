"""
Commit-related operations: fetching, ranking, filtering
"""
import os
import json
import threading
from tkinter import messagebox
from process_audit_changes import ProcessAuditChanges
from utils.url_helpers import add_clickable_urls
import re
from typing import Dict, List, Any

FUNC_RE = re.compile(
    r'\b(function|modifier)\s+([A-Za-z0-9_]+)\s*\('
)

def extract_functions_from_hunk(hunk_lines: List[str]) -> List[str]:
    """Given raw hunk lines, return a list of function names that appear."""
    seen = set()
    for line in hunk_lines:
        # strip +/- prefix that git adds
        clean = line.lstrip("+- ").strip()
        m = FUNC_RE.search(clean)
        if m:
            seen.add(m.group(2))
    return sorted(seen)

def parse_hunk_header(header: str) -> Dict[str, Any]:
    """
    Parse a header like '@@ -124,13 +124,15 @@ contract Anyrand is'
    Returns from/to line numbers and lengths.
    """
    # Example: @@ -124,13 +124,15 @@
    m = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", header)
    if not m:
        return {
            "from_line": None,
            "from_len": None,
            "to_line": None,
            "to_len": None,
        }

    from_line, from_len, to_line, to_len = m.groups()
    return {
        "from_line": int(from_line),
        "from_len": int(from_len) if from_len else 1,
        "to_line": int(to_line),
        "to_len": int(to_len) if to_len else 1,
    }


def extract_changed_files_functions_and_hunks(commit_obj: Dict) -> List[Dict]:
    """
    Extract:
    - files changed
    - functions touched in those files
    - hunks + line metadata
    """
    results = []

    for file in commit_obj.get("files_changed", []):
        file_entry = {
            "filename": file["filename"],
            "status": file["status"],
            "functions_changed": set(),
            "hunks": []
        }

        for hunk in file.get("hunks", []):
            header = hunk["header"]
            lines = hunk["lines"]

            # Parse @@ header
            hunk_meta = parse_hunk_header(header)

            # Detect functions referenced in hunk
            functions = extract_functions_from_hunk(lines)
            for fn in functions:
                file_entry["functions_changed"].add(fn)

            file_entry["hunks"].append({
                "header": header,
                "meta": hunk_meta,
                "lines": lines,
                "functions_in_hunk": functions,
            })

        file_entry["functions_changed"] = sorted(file_entry["functions_changed"])
        results.append(file_entry)

    return results

def parse_commit_for_dataset(commit: dict) -> dict:
    """Convert a raw commit dict to structured dataset format"""
    dataset_entry = {
        "commit_url": commit.get("commit_url"),
        "message": commit.get("message"),
        "query_match": commit.get("query_match", ""),
        "files_changed": []
    }

    for file_info in commit.get("relevant_hunks", []):
        fpath = file_info.get("file")
        hunks_list = []

        for hunk_lines in file_info.get("lines", []):
            changed_lines = [
                ln.strip() for ln in hunk_lines
                if ln.strip().startswith(('+', '-')) and not ln.strip().startswith(('+++', '---'))
            ]

            # Attempt to extract function name from hunk header
            func_name = None
            header_line = file_info.get("header", "")
            if header_line.startswith("@@"):
                import re
                match = re.search(r"(function|def)\s+(\w+)", header_line)
                if match:
                    func_name = match.group(2)

            hunks_list.append({
                "header": header_line,
                "changed_lines": changed_lines,
                "function_name": func_name
            })

        dataset_entry["files_changed"].append({
            "filename": fpath,
            "hunks": hunks_list
        })

    return dataset_entry


def run_get_commit_data(state, root):
    """Fetch and rank commit data for selected finding"""
    object_list = state.get('object_list')
    results_list = state.get('results_list')
    results_text = state.get('results_text')

    selected = object_list.selection() if object_list else None
    if not selected:
        messagebox.showerror("Error", "Select an object first.")
        return

    idx = int(selected[0])
    finding = state['loaded_objects'][idx]

    # Clear previous UI results
    if results_list:
        results_list.delete(*results_list.get_children())
    if results_text:
        results_text.delete("1.0", "end")
        results_text.insert("1.0", "⏳ Fetching commit data... please wait...\n")
        results_text.update()

    state['ranked_commits_cache'] = {}

    # Clear file/function lists
    for key in ['files_checklist', 'functions_before_list', 'functions_after_list']:
        widget = state.get(key)
        if widget:
            widget.delete(*widget.get_children())

    def worker():
        try:
            processor = ProcessAuditChanges()
            print(finding)
            result_commits = processor.get_finding_commit_data(finding)
            print(result_commits)

            # Sort by score descending

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            print(f"Error in worker thread: {error_msg}")
            result_commits = [{"error": error_msg}]

        def update_ui():
            if results_text:
                results_text.delete("1.0", "end")
            if results_list:
                results_list.delete(*results_list.get_children())

            state['ranked_commits'] = result_commits if isinstance(result_commits, list) else [result_commits]

            for idx, commit_obj in enumerate(state['ranked_commits']):
                label = f"Result {idx}"
                if isinstance(commit_obj, dict):
                    if "error" in commit_obj:
                        label = f"Error: {commit_obj['error'][:100]}"
                    elif "commit_url" in commit_obj:
                        url = commit_obj["commit_url"]
                        commit_hash = commit_obj.get("sha", url.split("/")[-1] if "/" in url else "unknown")[:8]
                        score = commit_obj.get("score", 0)
                        score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
                        msg_preview = (commit_obj.get("message", "")[:40] + "...") if len(commit_obj.get("message", "")) > 40 else commit_obj.get("message", "")
                        label = f"#{idx+1} [{score_str}] {commit_hash} - {msg_preview}"
                if results_list:
                    results_list.insert("", "end", iid=str(idx), values=(label,))

            # Show summary
            if results_text:
                if not state['ranked_commits']:
                    results_text.insert("1.0", "No results returned")
                elif "error" not in state['ranked_commits'][0]:
                    summary = f"✓ Found {len(state['ranked_commits'])} commits\n"
                    summary += f"Top score: {state['ranked_commits'][0].get('score', 'N/A')}\n\n"
                    summary += "Select a commit to view details"
                    results_text.insert("1.0", summary)

        root.after(0, update_ui)

    threading.Thread(target=worker, daemon=True).start()

def fix_finding(state):
    """Update the context field with the selected result_commit"""
    object_list = state.get('object_list')
    results_list = state.get('results_list')
    text_view = state.get('text_view')
    
    obj_selected = object_list.selection() if object_list else None
    if not obj_selected:
        messagebox.showerror("Error", "Select an object first.")
        return
    
    result_selected = results_list.selection() if results_list else None
    if not result_selected:
        messagebox.showerror("Error", "Select a ranked commit from the results list.")
        return
    
    if not state.get('ranked_commits'):
        messagebox.showerror("Error", "No ranked commits available. Run 'Get Commit Data' first.")
        return
    
    obj_idx = int(obj_selected[0])
    result_idx = int(result_selected[0])
    
    obj = state['loaded_objects'][obj_idx]
    commit = state['ranked_commits'][result_idx]
    
    if "error" in commit:
        messagebox.showerror("Error", "Cannot use an error result.")
        return
    
    context_entry = {}
    
    # Extract blob URLs from files
    files = commit.get("files", [])
    
    before_blobs = []
    after_blobs = []
    functions_before = []
    functions_after = []
    
    for file_data in files:
        # Collect blob URLs
        if "blob_url_before" in file_data and file_data["blob_url_before"]:
            before_blobs.append(file_data["blob_url_before"])
        if "blob_url_after" in file_data and file_data["blob_url_after"]:
            after_blobs.append(file_data["blob_url_after"])
        
        # Extract function names from hunks (basic regex pattern for function declarations)
        import re
        hunks = file_data.get("hunks", [])
        for hunk in hunks:
            context_line = hunk.get("context", "")
            lines = hunk.get("lines", [])
            
            # Look for function patterns in context and lines
            all_text = context_line + "\n" + "\n".join(lines)
            
            # Match common function patterns (Solidity, JavaScript, Python, etc.)
            func_patterns = [
                r'function\s+(\w+)\s*\(',  # Solidity/JavaScript
                r'def\s+(\w+)\s*\(',  # Python
                r'(\w+)\s*\([^)]*\)\s*{',  # C-style
            ]
            
            for pattern in func_patterns:
                matches = re.findall(pattern, all_text)
                for match in matches:
                    if match not in functions_before:
                        functions_before.append(match)
                    if match not in functions_after:
                        functions_after.append(match)
    
    # Only add fields if they exist and have values
    if before_blobs:
        context_entry["source"] = before_blobs
    
    if after_blobs:
        context_entry["fix"] = after_blobs
    
    if functions_before:
        context_entry["functions_before"] = functions_before
    
    if functions_after:
        context_entry["functions_after"] = functions_after
    
    # Check if we have at least some data
    if not context_entry:
        messagebox.showwarning(
            "Warning", 
            "No blob URLs or functions found in the selected commit. "
            "The commit may not have parseable code changes."
        )
        return
    
    # Update the object's context
    obj["context"] = context_entry
    
    if text_view:
        pretty = json.dumps(obj, indent=4, ensure_ascii=False)
        text_view.delete("1.0", "end")
        text_view.insert("end", pretty)
        add_clickable_urls(text_view, pretty)
    
    messagebox.showinfo("Success", "Context entry added from selected commit.")