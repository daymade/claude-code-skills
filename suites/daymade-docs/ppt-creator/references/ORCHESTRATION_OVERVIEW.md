# ORCHESTRATION_OVERVIEW.md

> **Purpose**: Enable ppt-creator to act as an end-to-end workflow coordinator, automatically managing data synthesis, chart generation, PPTX creation, and chart insertion to deliver complete, presentation-ready PowerPoint files with real visualizations.
>
> **Note**: This document provides the orchestration overview. For detailed implementation, see the specialized guides below.

---

## Table of Contents

1. [When to Use Orchestration Mode](#when-to-use-orchestration-mode)
2. [Orchestration Workflow](#orchestration-workflow)
3. **Stage 8b-8c: Data & Charts** → See [ORCHESTRATION_DATA_CHARTS.md](ORCHESTRATION_DATA_CHARTS.md)
4. **Stage 8d-8e: PPTX Creation & Chart Insertion** → See [ORCHESTRATION_PPTX.md](ORCHESTRATION_PPTX.md)

---

## When to Use Orchestration Mode

### Activation Triggers

Orchestration mode activates when user request includes ANY of these patterns:

**Explicit Requests**:
- "Generate complete PPTX with real charts"
- "Create final deliverable ready for presentation"
- "Export to PowerPoint with all visualizations"
- "Deliver presentation-ready file with data"

**Implicit Indicators**:
- User uploads reference documents + requests "presentation"
- Request mentions "final deliverable" or "ready to present"
- User asks for "all assets generated"
- Context suggests this is for actual delivery (meeting/pitch/review)

### Decision Tree

```
User Request
  │
  ├─ Contains "Markdown only" → Manual Mode
  ├─ Contains "slides.md" only → Manual Mode
  ├─ Contains "complete PPTX" → Orchestration Mode ✓
  ├─ Contains "final deliverable" → Orchestration Mode ✓
  ├─ Contains "presentation-ready" → Orchestration Mode ✓
  └─ Ambiguous → Ask user: "Should I create complete PPTX with charts (orchestration mode) or Markdown only (manual mode)?"
```

### User Communication

When activating orchestration mode, inform user explicitly:

```
🎯 Activating end-to-end orchestration mode to deliver complete PPTX with real charts.

Pipeline stages:
  ✓ Stage 1-7: Content creation (slides.md, notes.md, refs.md)
  ⏳ Stage 8b: Data synthesis (generating CSV files from refs.md specs)
  ⏳ Stage 8c: Chart generation (matplotlib rendering)
  ⏳ Stage 8d: Dual-path PPTX creation (Marp + document-skills:pptx in parallel)
  ⏳ Stage 8e: Dual-path chart insertion (2 final PPTX versions)

📦 Will deliver TWO versions:
  - presentation_marp.pptx (Marp CLI export, native Marp styling)
  - presentation_pptx.pptx (document-skills:pptx, reveal.js styling)

Estimated time: 4-6 minutes
```

---

## Orchestration Workflow

### Complete Pipeline (Stages 8b-8e)

After standard content creation (Stages 0-7 → slides.md/notes.md/refs.md), orchestration extends Stage 8:

```
Stage 8: Package Deliverables
  │
  ├─ 8a: Package Markdown deliverables ✓ (baseline)
  │     └─ Output: /output/slides.md, /output/notes.md, /output/refs.md
  │
  ├─ 8b: Synthesize Data (if needed)
  │     ├─ Check: Does refs.md specify data requirements?
  │     ├─ Check: Did user provide data files?
  │     └─ If no user data: Generate synthetic CSV files
  │           → Output: /output/data/*.csv
  │
  ├─ 8c: Generate Charts
  │     ├─ Read: /output/refs.md (chart specifications)
  │     ├─ Read: /output/data/*.csv (generated or user-provided)
  │     ├─ Execute: Python/matplotlib chart generation
  │     └─ Output: /output/assets/*.png (180 DPI, optimized)
  │
  ├─ 8d: Create PPTX
  │     ├─ Tool: Task (subagent_type: document-skills:pptx)
  │     ├─ Input: /output/slides.md content
  │     ├─ Action: Convert Markdown to PPTX structure
  │     └─ Output: /output/presentation.pptx (with placeholder chart text)
  │
  └─ 8e: Insert Charts
        ├─ Tool: Task (subagent_type: document-skills:pptx editing)
        ├─ Input: /output/assets/*.png + slide mapping
        ├─ Action: Replace placeholder text with chart images
        └─ Output: /output/presentation_with_charts.pptx ✓ FINAL
```

### Coordination Approach

Use **sequential execution with quality gates**:
- Stages 8b-c can run in parallel (data synthesis + chart generation)
- Stage 8d waits for 8c completion (PPTX needs chart list)
- Stage 8e waits for 8d completion (insertion needs PPTX file)

---

## Stage 8b: Data Synthesis

### When to Synthesize Data

Generate synthetic data when:
1. refs.md contains data specifications (e.g., "Solar LCOE: $0.38/kWh → $0.05/kWh")
2. User did NOT upload CSV/Excel files
3. Charts require data to render (not just conceptual diagrams)

### Data Synthesis Guidelines

**Source of Truth**: Use refs.md data specifications

Example refs.md content:
```markdown
## Chart 1: Renewable Energy Cost Trends (2010-2024)

Data source: IRENA Renewable Power Generation Costs 2024
- Solar PV LCOE: $0.38/kWh (2010) → $0.05/kWh (2024), -87% decline
- Onshore Wind LCOE: $0.09/kWh (2010) → $0.04/kWh (2024), -56% decline
- Coal baseline (comparison): $0.11/kWh (stable)

Required CSV: data/cost_trend.csv
Columns: year, solar_pv_cost, onshore_wind_cost, coal_cost
```

**Python Code Pattern** (generate CSV):
```python
import pandas as pd
import numpy as np

# Synthesize cost_trend.csv
years = list(range(2010, 2025))
solar_costs = np.linspace(0.38, 0.05, len(years))  # -87% decline
wind_costs = np.linspace(0.09, 0.04, len(years))   # -56% decline
coal_costs = [0.11] * len(years)                   # stable baseline

df = pd.DataFrame({
    'year': years,
    'solar_pv_cost': solar_costs,
    'onshore_wind_cost': wind_costs,
    'coal_cost': coal_costs
})
df.to_csv('output/data/cost_trend.csv', index=False)
```

**Key Principles**:
- Match refs.md specifications exactly (start/end values, trends)
- Add realistic noise (±3-5%) to avoid straight lines
- Use authoritative source calibration (IRENA/IEA/IPCC/WHO/World Bank)
- Document assumptions in data file headers or README

**File Organization**:
```
/output/data/
  ├── cost_trend.csv
  ├── capacity_growth.csv
  ├── employment.csv
  ├── solar_roi.csv
  └── README.md (documents synthesis methodology)
```

---

## Stage 8c: Chart Generation

### Chart Generation Script Pattern

Create a comprehensive `generate_charts.py` script that reads CSV data and generates all PNG charts.

**Template Structure**:
```python
#!/usr/bin/env python3
"""Generate all charts for presentation"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend

# Chinese font configuration
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def create_chart_1():
    """Cost Trend Line Chart"""
    df = pd.read_csv('data/cost_trend.csv')

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df['year'], df['solar_pv_cost'], marker='o', label='太阳能光伏', linewidth=2)
    ax.plot(df['year'], df['onshore_wind_cost'], marker='s', label='陆上风能', linewidth=2)
    ax.plot(df['year'], df['coal_cost'], linestyle='--', label='煤电(对比)', linewidth=2, alpha=0.7)

    ax.set_xlabel('年份', fontsize=12)
    ax.set_ylabel('平准化度电成本 ($/kWh)', fontsize=12)
    ax.set_title('可再生能源成本趋势 (2010-2024)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('assets/cost_trend.png', dpi=180, bbox_inches='tight')
    plt.close()
    print("✓ Generated: assets/cost_trend.png")

# Call all chart generation functions
if __name__ == "__main__":
    create_chart_1()
    create_chart_2()
    # ... (all charts)
    print("\n✅ All charts generated successfully")
```

**Execution Pattern**:
```bash
# Background execution to avoid blocking
cd /output
python generate_charts.py

# OR using uv if dependencies unavailable
uv run --with pandas --with matplotlib generate_charts.py
```

**Quality Standards**:
- DPI: 180 (presentation-quality)
- Size: 10×6 inches (fits 16:9 slide with margins)
- File format: PNG with transparency
- Color palette: Use colorblind-friendly colors from STYLE-GUIDE.md
- Labels: Chinese/English matching slide language
- Source citation: Add footnote to chart (e.g., "数据来源: IRENA 2024")

---
