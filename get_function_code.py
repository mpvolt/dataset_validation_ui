import re
from typing import Optional
import os
import requests


class FunctionRetriever:
    """Main class for matching vulnerability reports to source files."""
    
    def __init__(self, github_token: Optional[str] = None):
        """Initialize the matcher with API credentials."""
        self.github_token = github_token
        self.session = requests.Session()
        if github_token:
            self.session.headers.update({'Authorization': f'token {github_token}'})
            
    def fetch_file_content(self, blob_url: str) -> Optional[str]:
            """Fetch content from a GitHub blob URL."""
            try:
                # Convert blob URL to raw content URL
                if 'github.com' in blob_url and '/blob/' in blob_url:
                    raw_url = blob_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                else:
                    raw_url = blob_url
                
                response = self.session.get(raw_url, timeout=30)
                response.raise_for_status()
                
                # Only process text files
                content_type = response.headers.get('content-type', '')
                if 'text' not in content_type and 'application/json' not in content_type:
                    try:
                        return response.content.decode('utf-8')
                    except UnicodeDecodeError:
                        return None
                
                return response.text
            
            except Exception as e:
                print(f"Error fetching {blob_url}: {e}")
                return None
                
    def extract_function_code(self, file_content: str, function_name: str, line_number: Optional[int] = None) -> str:
            """Extract a specific function or modifier from source code."""
            if not file_content or not function_name:
                return ""

            clean_code = self.remove_comments(file_content)

            patterns = [
                rf"\bfunction\s+{re.escape(function_name)}\s*\([^\)]*\)[^\{{;]*\{{",
                rf"\bmodifier\s+{re.escape(function_name)}\s*\([^\)]*\)[^\{{;]*\{{",
                rf"\bfn\s+{re.escape(function_name)}\s*\([^\)]*\)[^\{{;]*\{{",
                rf"(?:public\s+)?fun\s+{re.escape(function_name)}\s*\([^\)]*\)[^\{{;]*\{{",
                rf"func\s+(?:\([^\)]*\)\s*)?{re.escape(function_name)}\s*\([^\)]*\)[^\{{;]*\{{",
                rf"def\s+{re.escape(function_name)}\s*\([^\)]*\)\s*(?:->[^\:]+)?\s*\:",
            ]

            match = None
            for pat in patterns:
                m = re.search(pat, clean_code)
                if m:
                    match = m
                    break

            if not match:
                if line_number:
                    lines = clean_code.splitlines()
                    start = max(line_number - 10, 0)
                    end = min(line_number + 40, len(lines))
                    return "\n".join(lines[start:end])
                return ""

            start_idx = match.start()
            block_start = match.end() - 1

            if match.group().strip().endswith("{"):
                brace_count = 0
                end_idx = None
                for i, ch in enumerate(clean_code[block_start:], start=block_start):
                    if ch == "{":
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                return clean_code[start_idx:end_idx].strip() if end_idx else clean_code[start_idx:start_idx + 1000].strip()
            else:
                lines = clean_code.splitlines()
                line_index = clean_code[:match.start()].count("\n")
                indent_match = re.match(r"(\s*)", lines[line_index])
                base_indent = len(indent_match.group(1)) if indent_match else 0

                block_lines = [lines[line_index]]
                for next_line in lines[line_index + 1:]:
                    if not next_line.strip():
                        block_lines.append(next_line)
                        continue
                    indent = len(re.match(r"(\s*)", next_line).group(1))
                    if indent <= base_indent:
                        break
                    block_lines.append(next_line)
                return "\n".join(block_lines).strip()


def main():
    github_token = os.getenv("GITHUB_API_KEY")
    functionRetriever = FunctionRetriever(github_token)