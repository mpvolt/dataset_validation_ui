import json
from openai import OpenAI
import os
import sys
 

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

# --- Step 2: GPT prompt ranking ---
def rank_with_gpt(finding: dict, commit_data_list: list[dict]) -> list[dict]:
    """
    Given a vulnerability finding and a list of structured commit data,
    ask GPT-4o-mini to assign a relevance score to each commit.
    """

    # Build commit dump for the model - MORE CONCISE FORMAT
    commit_blocks = []
    for idx, commit in enumerate(commit_data_list, 1):
        message = commit.get("message", "")
        url = commit.get("commit_url", "")

        # Collect all changed lines across all files
        all_changes = []
        for file_info in commit.get("files_changed", []):
            fpath = file_info.get("filename", "")
            for hunk in file_info.get("hunks", []):
                # Only include actual code changes (lines starting with +/-)
                changed_lines = [
                    ln.strip() for ln in hunk.get("lines", [])
                    if ln.strip().startswith(('+', '-')) and not ln.strip().startswith(('+++', '---'))
                ]
                if changed_lines:
                    all_changes.append(f"{fpath}: {' | '.join(changed_lines[:5])}")  # Limit to 5 lines per hunk

        changes_summary = "\n".join(all_changes[:10])  # Limit total changes shown

        block = f"""Commit {idx}:
URL: {url}
Message: {message}
Key Changes: {changes_summary if changes_summary else 'No significant changes detected'}
"""
        commit_blocks.append(block)

    commits_text = "\n".join(commit_blocks)

    # Extract key information from finding
    vuln_title = finding.get('title', 'Unknown')
    vuln_description = finding.get('description', '')
    vuln_recommendation = finding.get('recommendation', '')
    broken_code = finding.get('broken_code_snippets', [])
    
    # Create a more focused snippet of broken code
    broken_code_snippet = ""
    if broken_code and len(broken_code) > 0:
        broken_code_snippet = broken_code[0][:500]  # First snippet, max 500 chars

    # Build the prompt - MORE STRUCTURED AND CONCISE
    prompt = f"""You are analyzing commits to find which ones fix a specific vulnerability.

VULNERABILITY:
Title: {vuln_title}
Issue: {vuln_description[:300]}
Fix Needed: {vuln_recommendation[:200]}
Broken Code Pattern: {broken_code_snippet}

COMMITS TO ANALYZE:
{commits_text}

TASK:
Score each commit from 0-100 based on how likely it fixes this specific vulnerability.

SCORING RULES:
1. Score 90-100: Commit directly fixes the exact issue described
   - Message mentions "fix", "H-1", or the vulnerability type
   - Code changes match the recommended fix pattern
   - Changes are in the vulnerable function/location

2. Score 60-89: Commit is highly related but may be partial fix
   - Changes related functions or files
   - Adds tests for the vulnerability
   - Refactors vulnerable code

3. Score 30-59: Commit is somewhat related
   - Touches same files but different functions
   - Related feature changes

4. Score 0-29: Commit is unrelated
   - Different files/features
   - Formatting, comments, dependencies

OUTPUT REQUIRED (valid JSON):
{{
  "rankings": [
    {{"url": "commit_url_1", "score": 95, "reasoning": "Directly fixes the round calculation bug"}},
    {{"url": "commit_url_2", "score": 10, "reasoning": "Unrelated feature addition"}}
  ]
}}

Analyze each commit and provide scores:"""

    # Call GPT with more explicit JSON formatting
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a code security expert. Always respond with valid JSON containing a 'rankings' array."
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

    # Parse JSON with better error handling
    try:
        parsed = json.loads(raw)

        if "rankings" in parsed and isinstance(parsed["rankings"], list):
            # Normalize scores to 0-1 range if they're 0-100
            rankings = parsed["rankings"]
            for ranking in rankings:
                if "score" in ranking and ranking["score"] > 1:
                    ranking["score"] = ranking["score"] / 100.0
            return rankings

        # Fallback: look for any list in the response
        for key, value in parsed.items():
            if isinstance(value, list) and len(value) > 0:
                # Check if it looks like rankings
                if isinstance(value[0], dict) and "url" in value[0]:
                    for item in value:
                        if "score" in item and item["score"] > 1:
                            item["score"] = item["score"] / 100.0
                    return value

        print(f"Unexpected JSON structure: {parsed}")
        return []

    except json.JSONDecodeError as e:
        print(f"Failed to parse GPT output: {e}")
        print(f"Raw output: {raw}")
        return []
