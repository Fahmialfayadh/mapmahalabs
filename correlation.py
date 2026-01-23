from scipy import stats
import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

def generate_smart_insight(layer1_name, data1, layer2_name, data2, historical_data=None):
    """
    Advanced Statistical Relationship Analysis Engine for Petasight.
    
    Args:
    - layer1_name (str): Name of first variable
    - data1 (list): Data points for first variable
    - layer2_name (str): Name of second variable
    - data2 (list): Data points for second variable
    - historical_data (dict, optional): For future temporal consistency checks.
    
    Returns:
    - dict: Comprehensive analysis including Pearson, Spearman, Kendall, MI, and insights.
    """
    
    # Basic Validation
    n = len(data1)
    if n < 3:
        return {"error": "Insufficient data points (n < 3)"}
    
    x = np.array(data1)
    y = np.array(data2)

    # --- 1. Calculate Core Metrics ---
    
    # Pearson (Linear)
    pearson_r, pearson_p = stats.pearsonr(x, y)
    
    # Spearman (Monotonic)
    spearman_rho, spearman_p = stats.spearmanr(x, y)
    
    # Kendall's Tau (Robust Monotonic)
    kendall_tau, kendall_p = stats.kendalltau(x, y)
    
    # Mutual Information (Complex Non-linear)
    # Reshape for sklearn
    mi_score = mutual_info_regression(x.reshape(-1, 1), y, random_state=42)[0]
    # Normalize MI roughly to 0-1 range for comparison (entropy based normalization is complex, 
    # so we use a heuristic relative to typical high correlation MI values ~ 0.5-1.0+)
    
    # Correlation Ratio (Eta Squared) - Simplified Logic
    # (Not fully implemented without categorical grouping, but MI covers similar ground)
    
    # --- 2. Classify Relationship Type ---
    
    abs_pearson = abs(pearson_r)
    abs_spearman = abs(spearman_rho)
    
    relationship_type = "No significant relationship"
    
    # Thresholds
    SIG_THRESHOLD = 0.3
    NON_LINEAR_DIFF = 0.08 # Lowered to catch 0.9 vs 1.0 differences
    
    if abs_pearson < SIG_THRESHOLD and abs_spearman < SIG_THRESHOLD and mi_score < 0.2:
        relationship_type = "No significant relationship"
    elif abs_spearman > abs_pearson + NON_LINEAR_DIFF:
        relationship_type = "Non-linear monotonic relationship"
    elif mi_score > 0.4 and abs_pearson < 0.3:
        relationship_type = "Non-linear complex relationship"
    else:
        relationship_type = "Linear relationship"

    # --- 3. Determine Strength (New Rubric) ---
    # Use the primary metric based on relationship type
    primary_score = abs_spearman if "Non-linear" in relationship_type else abs_pearson
    
    strength = "Weak"
    if primary_score > 0.7:
        strength = "Strong"
    elif primary_score > 0.5:
        strength = "Moderate-Strong"
    elif primary_score > 0.3:
        strength = "Moderate"
        
    # --- 4. Outlier Detection ---
    z_scores_x = np.abs(stats.zscore(x))
    z_scores_y = np.abs(stats.zscore(y))
    outliers_x = np.where(z_scores_x > 2.0)[0] # Threshold 2.0 std dev (more sensitive)
    outliers_y = np.where(z_scores_y > 2.0)[0]
    unique_outliers = np.unique(np.concatenate((outliers_x, outliers_y)))
    
    has_outliers = len(unique_outliers) > 0
    outlier_warning = "No significant outliers detected."
    
    if has_outliers:
        # Check influence
        mask = np.ones(n, dtype=bool)
        mask[unique_outliers] = False
        x_clean, y_clean = x[mask], y[mask]
        
        # Only calc clean correlation if enough points remain
        if len(x_clean) > 2:
            r_clean, _ = stats.pearsonr(x_clean, y_clean)
            diff = abs(r_clean - pearson_r)
            if diff > 0.05: # Lowered sensitivity for influence warning
                outlier_warning = f"⚠️ {len(unique_outliers)} outlier(s) detected. Removing them changes correlation from {pearson_r:.2f} to {r_clean:.2f}."
            else:
                outlier_warning = f"{len(unique_outliers)} outlier(s) detected but have minimal impact on correlation."
    
    # --- 5. Generate Text Insight (Cleaner Format) ---
    
    direction = "positive" if pearson_r > 0 else "negative"
    if "Non-linear" in relationship_type and abs_spearman > abs_pearson:
         direction = "positive" if spearman_rho > 0 else "negative"

    trend_desc = "increase" if direction == "positive" else "decrease"
    sig_text = "✓ Significant" if pearson_p < 0.05 else "✗ Not Significant"
    
    # Cleaner, more concise insight
    insight_text = f"""### 📊 Summary

Found a **{strength} {relationship_type}** ({direction}) between the two variables.

---

### 📈 Statistical Metrics

| Metric | Value |
|--------|-------|
| Pearson (r) | {pearson_r:.3f} |
| Spearman (ρ) | {spearman_rho:.3f} |
| MI Score | {mi_score:.3f} |
| p-value | {pearson_p:.4f} ({sig_text}) |
| Sample (n) | {n} |

---

### 💡 Interpretation

When **{layer1_name}** increases, **{layer2_name}** tends to **{trend_desc}**.

---

### ⚠️ Important Notes

- Correlation ≠ Causation
- Regression line is a mathematical approximation"""

    # Add sample size warning if small
    if n < 30:
        insight_text += f"\n- ⚡ Small sample (n={n}), interpret with caution"
    
    # Add outlier warning if significant
    if has_outliers and "Removing them changes" in outlier_warning:
        insight_text += f"\n- {outlier_warning}"
        
    # Add model suggestion for non-linear
    if "Non-linear" in relationship_type:
        insight_text += "\n- 💡 Try Log/Polynomial model for better fit"

    # Confidence Score
    confidence = "High"
    if n < 15 or pearson_p > 0.05:
        confidence = "Low"
    elif n < 30 or "Moderate" in strength:
        confidence = "Medium"
    
    # Check for outliers lowering confidence
    if has_outliers and "Removing them changes" in outlier_warning:
         if confidence == "High": confidence = "Medium"
        
    insight_text += f"\n\n**Confidence: {confidence}**"

    return {
        "score": round(pearson_r, 2), # Keep for backward compatibility
        "metrics": {
            "pearson": round(pearson_r, 3),
            "spearman": round(spearman_rho, 3),
            "kendall": round(kendall_tau, 3),
            "mutual_info": round(mi_score, 3),
            "p_value": float(f"{pearson_p:.4f}"),
            "n": n
        },
        "classification": {
            "type": relationship_type,
            "strength": strength,
            "direction": direction,
            "significance": bool(pearson_p < 0.05),  # Convert numpy bool to Python bool
            "confidence": confidence
        },
        "text": insight_text,
        "chart_data": { 
            "x": data1,
            "y": data2
        }
    }

import plotly.express as px
import plotly.graph_objects as go

def scatter(x, y, layer1_name, layer2_name):
    """
    Generates scatter plot data with multiple regression models.
    Returns dictionary with traces for Linear, Log, Poly, and Power.
    """
    import numpy as np
    import pandas as pd
    
    # Ensure numpy arrays and handle zeros/negatives for certain models
    x_arr = np.array(x, dtype=float)
    y_arr = np.array(y, dtype=float)
    
    # Sort for clean plotting of curves
    sorted_indices = np.argsort(x_arr)
    x_sorted = x_arr[sorted_indices]
    y_sorted = y_arr[sorted_indices]
    
    regressions = {}
    
    # 1. Linear (y = mx + c)
    try:
        z = np.polyfit(x_arr, y_arr, 1)
        p = np.poly1d(z)
        regressions['linear'] = {
            'x': x_sorted.tolist(),
            'y': p(x_sorted).tolist(),
            'equation': f"y = {z[0]:.2f}x + {z[1]:.2f}",
            'r2': 0 # simplify for now
        }
    except:
        regressions['linear'] = None

    # 2. Polynomial Degree 2 (y = ax^2 + bx + c)
    try:
        z_poly = np.polyfit(x_arr, y_arr, 2)
        p_poly = np.poly1d(z_poly)
        regressions['poly'] = {
            'x': x_sorted.tolist(),
            'y': p_poly(x_sorted).tolist(),
            'equation': f"y = {z_poly[0]:.2e}x² + {z_poly[1]:.2f}x + {z_poly[2]:.2f}"
        }
    except:
        regressions['poly'] = None
        
    # 3. Logarithmic (y = a + b*ln(x))
    # Requires x > 0
    if np.all(x_arr > 0):
        try:
            z_log = np.polyfit(np.log(x_arr), y_arr, 1)
            # y = z[0]*ln(x) + z[1]
            y_log_pred = z_log[0] * np.log(x_sorted) + z_log[1]
            regressions['log'] = {
                'x': x_sorted.tolist(),
                'y': y_log_pred.tolist(),
                'equation': f"y = {z_log[0]:.2f}ln(x) + {z_log[1]:.2f}"
            }
        except:
            regressions['log'] = None
    else:
        regressions['log'] = None
        
    # 4. Power (y = a * x^b) -> ln(y) = ln(a) + b*ln(x)
    # Requires x > 0 and y > 0
    if np.all(x_arr > 0) and np.all(y_arr > 0):
        try:
            z_pow = np.polyfit(np.log(x_arr), np.log(y_arr), 1)
            b = z_pow[0]
            a = np.exp(z_pow[1])
            y_pow_pred = a * (x_sorted ** b)
            regressions['power'] = {
                'x': x_sorted.tolist(),
                'y': y_pow_pred.tolist(),
                'equation': f"y = {a:.2f}x^{{{b:.2f}}}"
            }
        except:
            regressions['power'] = None
    else:
        regressions['power'] = None

    return {
        "regressions": regressions,
        "chart_data": {
            "x": x_arr.tolist(),
            "y": y_arr.tolist(),
            "layer1_name": layer1_name,
            "layer2_name": layer2_name
        }
    }

if __name__ == "__main__":
    # Test Data: Monotonic Non-Linear (Exponential-ish)
    x_test = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y_test = [2, 4, 8, 16, 25, 40, 60, 90, 130, 200]
    
    print("\n--- TEST: Monotonic Non-Linear ---")
    result = generate_smart_insight("Input", x_test, "Output", y_test)
    print(result['text'])
    print(f"\nClassification: {result['classification']['type']}")
    print(f"Metrics: {result['metrics']}")

    # Test Data: Outlier Influence
    x_out = [1, 2, 3, 4, 5, 12] # 12 is mild outlier
    y_out = [2, 4, 6, 8, 10, 50] # 50 is outlier
    
    print("\n--- TEST: Outlier ---")
    result_out = generate_smart_insight("Input", x_out, "Output", y_out)
    print(result_out['text'])
