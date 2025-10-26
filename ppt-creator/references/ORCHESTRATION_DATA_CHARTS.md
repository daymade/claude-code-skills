# ORCHESTRATION_DATA_CHARTS.md

> **Purpose**: Detailed specifications for Stage 8b (Data Synthesis) and Stage 8c (Chart Generation) in orchestration mode.
>
> **Navigation**: [← Back to Overview](ORCHESTRATION_OVERVIEW.md) | [Next: PPTX Creation →](ORCHESTRATION_PPTX.md)

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

**Navigation**: [← Back to Overview](ORCHESTRATION_OVERVIEW.md) | [Next: PPTX Creation →](ORCHESTRATION_PPTX.md)
