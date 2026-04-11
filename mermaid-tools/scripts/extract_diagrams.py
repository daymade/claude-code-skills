#!/usr/bin/env python3
"""
Extract Mermaid diagrams from markdown file and create numbered .mmd files
"""

import re
import sys
from pathlib import Path

def extract_mermaid_diagrams(markdown_file, output_dir):
    """Extract Mermaid diagrams from markdown file and create numbered .mmd files"""
    
    try:
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR: Cannot read markdown file: {e}")
        return []
    
    # Find all mermaid code blocks with their content
    mermaid_pattern = r'```mermaid\n(.*?)\n```'
    matches = re.findall(mermaid_pattern, content, re.DOTALL)
    
    if not matches:
        print("No Mermaid diagrams found in markdown file")
        return []
    
    # Extract diagram names from context (look backwards for section headers)
    diagrams = []
    lines = content.split('\n')
    
    for i, match in enumerate(matches, 1):
        # Find the position of this diagram in the content
        diagram_pattern = f'```mermaid\n{re.escape(match)}\n```'
        diagram_match = re.search(diagram_pattern, content)
        
        if not diagram_match:
            # Fallback: use simple search
            diagram_start = content.find(f'```mermaid\n{match}\n```')
        else:
            diagram_start = diagram_match.start()
        
        # Count lines up to this point to find context
        if diagram_start >= 0:
            lines_before = content[:diagram_start].count('\n')
        else:
            lines_before = 0
        
        # Look backwards for the most recent section header or meaningful context
        diagram_name = f"diagram-{i:02d}"  # Default fallback
        
        # Look for context clues in the 20 lines before the diagram
        context_start = max(0, lines_before - 20)
        context_lines = lines[context_start:lines_before] if lines_before > 0 else []
        
        # Priority 1: Look for specific diagram descriptions
        for line in reversed(context_lines):
            line = line.strip().lower()
            if 'system architecture' in line:
                diagram_name = f"{i:02d}-system-architecture"
                break
            elif 'authentication flow' in line:
                diagram_name = f"{i:02d}-authentication-flow"
                break
            elif 'caching architecture' in line or 'multi-layer cache' in line:
                diagram_name = f"{i:02d}-caching-architecture"
                break
            elif 'data flow' in line or 'redshift schema' in line:
                diagram_name = f"{i:02d}-data-flow"
                break
            elif 'api request' in line or 'dashboard metrics endpoints' in line:
                diagram_name = f"{i:02d}-api-request-response"
                break
            elif 'dashboard layout' in line or 'presentation layer' in line:
                diagram_name = f"{i:02d}-dashboard-layout"
                break
            elif 'agency' in line and ('hierarchy' in line or 'filter' in line):
                diagram_name = f"{i:02d}-agency-hierarchy"
                break
        
        # Priority 2: Look for section headers (## or ###)
        if diagram_name.startswith('diagram-'):
            for line in reversed(context_lines):
                line = line.strip()
                if line.startswith('###') or line.startswith('##'):
                    # Extract meaningful part from header
                    header = re.sub(r'^#+\s*\*?\*?', '', line)
                    header = re.sub(r'\*?\*?$', '', header)
                    header = header.strip()
                    
                    # Convert to filename-friendly format
                    name_part = re.sub(r'[^\w\s-]', '', header)
                    name_part = re.sub(r'\s+', '-', name_part.strip())
                    name_part = name_part.lower()[:30]  # Limit length
                    
                    if name_part and name_part != 'detailed-design':
                        diagram_name = f"{i:02d}-{name_part}"
                        break
        
        diagrams.append({
            'number': i,
            'name': diagram_name,
            'content': match.strip()
        })
        
        print(f"Found diagram {i}: {diagram_name}")
    
    # Write .mmd files
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    created_files = []
    for diagram in diagrams:
        mmd_file = output_path / f"{diagram['name']}.mmd"
        try:
            with open(mmd_file, 'w', encoding='utf-8') as f:
                f.write(diagram['content'])
            created_files.append(str(mmd_file))
            print(f"Created: {mmd_file}")
        except Exception as e:
            print(f"ERROR: Cannot create {mmd_file}: {e}")
    
    return created_files

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 extract_diagrams.py <markdown_file> <output_directory>")
        sys.exit(1)
    
    markdown_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    files = extract_mermaid_diagrams(markdown_file, output_dir)
    print(f"\nExtracted {len(files)} diagrams successfully")