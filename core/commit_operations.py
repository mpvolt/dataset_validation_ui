"""
Commit-related operations: fetching, ranking, filtering
"""
import os
import json
import threading
from tkinter import messagebox
from parse_all_commits import parse_all_commits
from compute_relevance_gpt import rank_with_gpt
from utils.url_helpers import add_clickable_urls

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
    
    # Clear results and cache
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
            github_token = os.getenv("GITHUB_API_KEY")
            
            # Step 1: Parse all commits from the finding
            commits = parse_all_commits(finding, github_token)
            print(f"Parsed {len(commits)} commits")
            
            # Step 2: Rank commits with GPT
            # Returns: [{'url': '...', 'score': 0.95, 'reasoning': '...'}, ...]
            ranked_results = rank_with_gpt(finding, commits)
            print(f"Ranked {len(ranked_results)} commits")
            
            # Step 3: Combine rankings with full commit data
            combined_results = []
            
            # Create a URL to commit mapping for quick lookup
            commit_map = {c.get("url"): c for c in commits if c.get("url")}
            
            for ranked in ranked_results:
                ranked_url = ranked.get("url")
                if not ranked_url:
                    print(f"Warning: Ranked result missing URL: {ranked}")
                    continue
                
                # Find the full commit data
                full_commit = commit_map.get(ranked_url)
                if not full_commit:
                    print(f"Warning: No matching commit found for URL: {ranked_url}")
                    continue
                
                # Build the combined result with all available data
                details = {
                    "url": ranked_url,
                    "score": ranked.get("score", 0),
                    "reasoning": ranked.get("reasoning", "No reasoning provided"),
                    "message": full_commit.get("message", ""),
                    "files": [],
                    "before_blob": [],
                    "after_blob": [],
                    "functions_before": [],
                    "functions_after": [],
                }
                
                # Extract file and function data from the full commit's changes
                changes = full_commit.get("changes", {})
                for file_path, change in changes.items():
                    # Add filename
                    details["files"].append(file_path)
                    
                    # Add before blob if available
                    before_blob = change.get("before_blob")
                    if before_blob:
                        details["before_blob"].append(before_blob)
                    
                    # Add after blob if available
                    after_blob = change.get("after_blob")
                    if after_blob:
                        details["after_blob"].append(after_blob)
                    
                    # Add functions_before if available
                    funcs_before = change.get("functions_before")
                    if funcs_before:
                        details["functions_before"].extend(funcs_before)
                    
                    # Add functions_after if available
                    funcs_after = change.get("functions_after")
                    if funcs_after:
                        details["functions_after"].extend(funcs_after)
                
                combined_results.append(details)
            
            # Sort by score descending
            combined_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            result_commits = combined_results
            
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
            
            # Store results in state
            if isinstance(result_commits, list):
                state['ranked_commits'] = result_commits
            else:
                state['ranked_commits'] = [result_commits]
            
            # Populate the results list
            for idx, commit_obj in enumerate(state['ranked_commits']):
                if isinstance(commit_obj, dict):
                    if "error" in commit_obj:
                        label = f"Error: {commit_obj['error'][:100]}"
                    elif "url" in commit_obj:
                        url = commit_obj["url"]
                        commit_hash = url.split("/")[-1] if "/" in url else url[:8]
                        score = commit_obj.get("score", 0)
                        
                        # Format score nicely
                        if isinstance(score, float):
                            score_str = f"{score:.2f}"
                        else:
                            score_str = str(score)
                        
                        # Get commit message preview
                        msg = commit_obj.get("message", "")
                        msg_preview = msg[:40] + "..." if len(msg) > 40 else msg
                        
                        label = f"#{idx+1} [{score_str}] {commit_hash[:8]} - {msg_preview}"
                    else:
                        label = f"Result {idx}"
                else:
                    label = f"Result {idx}"
                
                if results_list:
                    results_list.insert("", "end", iid=str(idx), values=(label,))
            
            # Show summary message
            if not state['ranked_commits']:
                if results_text:
                    results_text.insert("1.0", "No results returned")
            elif state['ranked_commits'] and "error" not in state['ranked_commits'][0]:
                if results_text:
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
    
    # Only add fields if they exist and have values
    before_blobs = commit.get("before_blob", [])
    if before_blobs and len(before_blobs) > 0:
        context_entry["source"] = before_blobs[0]
    
    after_blobs = commit.get("after_blob", [])
    if after_blobs and len(after_blobs) > 0:
        context_entry["fix"] = after_blobs[0]
    
    funcs_before = commit.get("functions_before", [])
    if funcs_before and len(funcs_before) > 0:
        context_entry["functions_before"] = funcs_before
    
    funcs_after = commit.get("functions_after", [])
    if funcs_after and len(funcs_after) > 0:
        context_entry["functions_after"] = funcs_after
    
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