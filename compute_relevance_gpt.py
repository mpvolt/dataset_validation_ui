import json
from openai import OpenAI
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Step 1: Embedding-based pre-filtering ---
def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a*b for a,b in zip(vec1, vec2))
    norm1 = sum(a*a for a in vec1)**0.5
    norm2 = sum(b*b for b in vec2)**0.5
    if norm1==0 or norm2==0:
        return 0
    return dot / (norm1 * norm2)

def prefilter_commits(finding: dict, commits: list[dict], top_n=5) -> list[dict]:
    combined_text = f"{finding.get('title','')} {finding.get('description','')} {finding.get('recommendation','')}"
    finding_embedding = get_embedding(combined_text)

    scored = []
    for commit in commits:
        commit_text = commit.get('message','')
        funcs = []
        for fdata in commit.get('changes', {}).values():
            funcs.extend(fdata.get('functions_after', []))
        if funcs:
            commit_text += " " + " ".join(funcs)
        commit_embedding = get_embedding(commit_text)
        score = cosine_similarity(finding_embedding, commit_embedding)
        commit_with_score = commit.copy()
        commit_with_score['embedding_score'] = score
        scored.append(commit_with_score)

    scored.sort(key=lambda x: x['embedding_score'], reverse=True)
    return scored[:top_n]

def vulnerability_block(
    title,
    description,
    recommendation,
    broken_code_snippet,
    fixed_code_snippet,
    files
):
    fields = []

    if title:
        fields.append(f"Title: {title}")

    if description:
        fields.append(f"Issue: {description[:300]}")

    if recommendation:
        fields.append(f"Fix Needed: {recommendation[:200]}")

    if broken_code_snippet:
        fields.append(f"Broken Code Pattern: {broken_code_snippet}")

    if fixed_code_snippet:
        fields.append(f"Fixed Code Pattern: {fixed_code_snippet}")

    if files:
        fields.append(f"Files: {files}")

    return "\n".join(fields)

# --- Step 2: GPT prompt ranking ---
def rank_with_gpt(finding: dict, commit_data_list: list[dict], max_workers: int = 10) -> list[dict]:
    """
    Given a vulnerability finding and a list of structured commit data,
    uses a ThreadPoolExecutor to parallelize the relevance scoring for each commit.
    """
    
    # --- Prepare Static Vulnerability Data ---
    vuln_title = finding.get('title', 'Unknown')
    vuln_description = finding.get('description', '')
    vuln_recommendation = finding.get('recommendation', '')
    broken_code = finding.get('broken_code_snippets', [])
    fixed_code = finding.get('fixed_code_snippet', [])
    broken_code_snippet = broken_code[0][:500] if broken_code and len(broken_code) > 0 else ""
    fixed_code_snippet = broken_code[0][:500] if fixed_code and len(fixed_code) > 0 else ""
    files = finding.get('files', [])

    vuln_text = vulnerability_block(
        vuln_title,
        vuln_description,
        vuln_recommendation,
        broken_code_snippet,
        fixed_code_snippet,
        files
    )

    
    def rank_single_commit(commit: dict) -> dict:
        """
        Internal function to handle the API call and parsing for a single commit.
        This function will be executed in parallel threads.
        """
        url = commit.get("commit_url", "")
        message = commit.get("message", "")
        
        # 1. Build the specific commit block (same logic as before)
        all_changes = []
        for file_info in commit.get("files_changed", []):
            fpath = file_info.get("filename", "")
            for hunk in file_info.get("hunks", []):
                changed_lines = [
                    ln.strip() for ln in hunk.get("lines", [])
                    if ln.strip().startswith(('+', '-')) and not ln.strip().startswith(('+++', '---'))
                ]
                if changed_lines:
                    all_changes.append(f"{fpath}: {' | '.join(changed_lines[:5])}")  

        changes_summary = "\n".join(all_changes[:10])

        commit_text = f"""Commit 1: (ONLY COMMIT TO ANALYZE)
URL: {url}
Message: {message}
Key Changes: {changes_summary if changes_summary else 'No significant changes detected'}
"""
        
        # 2. Build the prompt
        prompt = f"""You are analyzing a single commit to find if it fixes a specific vulnerability.

VULNERABILITY:
{vuln_text}

COMMIT TO ANALYZE:
{commit_text}

TASK:
Score this single commit from 0-100 based on how likely it fixes this specific vulnerability.

IMPORTANT:
- bug_related_files: Files that DIRECTLY relate to the vulnerability (exclude test files, helpers, unrelated contracts)


OUTPUT REQUIRED (valid JSON):
{{
  "url": "{url}",
  "score": 95, 
  "bug_related_files": ["Contract.sol"],
}}

Analyze the commit and provide the score and reasoning:"""
        
        # 3. Call GPT and handle parsing/errors
        try:
            # NOTE: 'client' must be defined outside this function for the thread to access it
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code security expert. Always respond with valid JSON object containing 'url', 'score', and 'reasoning' keys."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            
            # Normalize score and return result
            if "url" in parsed and "score" in parsed:
                if parsed.get("score") > 0:
                    return {
                        "url": parsed["url"],
                        "score": parsed["score"],
                        "relevant_files": parsed.get("bug_related_files", "No related files provided")

                    }
            
            # Fallback for unexpected structure
            return {"url": url, "score": 0.0, "reasoning": "Failed to parse GPT response: Missing keys."}

        except json.JSONDecodeError:
            return {"url": url, "score": 0.0, "reasoning": "JSON decode error from API response."}
        except Exception as e:
            return {"url": url, "score": 0.0, "reasoning": f"Unexpected API error: {str(e)[:50]}"}
    
    # --- Execute Parallel Ranking ---
    all_rankings = []
    
    # Use ThreadPoolExecutor for I/O-bound tasks (API calls)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all commits to the thread pool
        future_to_commit = {
            executor.submit(rank_single_commit, commit): commit 
            for commit in commit_data_list
        }
        
        # Wait for results as they complete
        print(f"Submitting {len(commit_data_list)} commits for parallel ranking with {max_workers} workers...")
        for future in as_completed(future_to_commit):
            result = future.result()
            all_rankings.append(result)

    return all_rankings