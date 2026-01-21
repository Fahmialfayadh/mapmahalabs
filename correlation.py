from scipy import stats
import numpy as np
def generate_smart_insight(layer1_name, data1, layer2_name, data2):
    """
    Menghitung korelasi dan menghasilkan kalimat insight otomatis.
    
    Args:
    - layer1_name: Nama layer pertama (str), misal "Upah Minimal"
    - data1: List angka untuk layer 1
    - layer2_name: Nama layer kedua (str), misal "Tingkat Bunuh Diri"
    - data2: List angka untuk layer 2 (urutan negara harus sama dengan data1)
    """
    
    # 1. Hitung Pearson Correlation
    # Nilai r berkisar antara -1 hingga 1
    # mendekati 1: Korelasi Positif Kuat (Satu naik, yang lain naik)
    # mendekati -1: Korelasi Negatif Kuat (Satu naik, yang lain turun)
    # mendekati 0: Tidak ada hubungan
    correlation, p_value = stats.pearsonr(data1, data2)
    
    # 2. Logika untuk membuat kalimat
    abs_corr = abs(correlation)
    strength = ""
    
    if abs_corr > 0.7:
        strength = "Very Strong"
        explanation = "Correlation is very strong."
    elif abs_corr > 0.5:
        strength = "Strong"
        explanation = "Correlation is strong."
    elif abs_corr > 0.3:
        strength = "Moderate"
        explanation = "Correlation is moderate."
    else:
        return {
            "score": round(correlation, 2),
            "text": f"No clear correlation found between {layer1_name} and {layer2_name}."
        }

    direction = "positive" if correlation > 0 else "negative"
    trend = "increasing" if correlation > 0 else "decreasing"
    
    # 3. Format Output JSON untuk Frontend
    insight_text = (
        f"Found **correlation {direction} {strength}** ({correlation:.2f}) between {layer1_name} and {layer2_name}. "
        f"Statistically, regions with higher {layer1_name} tend to have {layer2_name} that is {trend.replace('increasing', 'high').replace('decreasing', 'low')}."
    )

    return {
        "score": round(correlation, 2),
        "strength": strength,
        "direction": direction,
        "text": insight_text,
        "chart_data": { 
            # jaga2 buat scatter plot
            "x": data1,
            "y": data2
        }
    }

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

def scatter(x, y, layer1_name, layer2_name):
    # 1. Gunakan nama kolom static untuk DataFrame agar aman dari karakter aneh di layer_name
    df = pd.DataFrame({
        'val_x': x,
        'val_y': y
    })

    # 2. Membuat Scatter Plot
    fig = px.scatter(
        df, 
        x='val_x', 
        y='val_y', 
        trendline="ols", 
        labels={'val_x': layer1_name, 'val_y': layer2_name}, 
        title=f"{layer1_name} vs {layer2_name}",
        template="plotly_white", 
        opacity=0.8
    )

    # 3. Kustomisasi axes titles manual
    fig.update_xaxes(title_text=layer1_name)
    fig.update_yaxes(title_text=layer2_name)

    # 3. Kustomisasi "Kosmetik" agar terlihat pro
    fig.update_traces(
        marker=dict(size=10, color='#6366f1', line=dict(width=1, color='white')), # Indigo markers
        selector=dict(mode='markers')
    )
    
    # Kustomisasi Garis Regresi (Merah)
    fig.update_traces(
        line=dict(color="#ef4444", width=2), # Red-500
        selector=dict(type='scatter', mode='lines')
    )

    # 4. Kustomisasi Layout (Font, Margin, Grid) - Optimized for Mobile Sidebar
    fig.update_layout(
        font_family="Inter, sans-serif",
        font_color="#334155", # Dark text for visibility
        title_font_size=12,
        title_x=0.5,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        height=300,
        paper_bgcolor='rgba(255,255,255,0.5)', # Semi-transparent white
        plot_bgcolor='rgba(255,255,255,0.5)',
        showlegend=False,
        dragmode='pan',
        xaxis=dict(
            tickfont=dict(size=9),
            title_font=dict(size=10),
            rangeslider=dict(visible=False),
            fixedrange=False,
            showgrid=True,
            gridcolor='#e2e8f0',
            zeroline=False,
            autorange=True # Force auto range
        ),
        yaxis=dict(
            tickfont=dict(size=9),
            title_font=dict(size=10),
            fixedrange=False,
            showgrid=True,
            gridcolor='#e2e8f0',
            zeroline=False,
            autorange=True
        )
    )
    
    # Config simple - Enable ModeBar agar user bisa Reset Zoom
    config = {
        'scrollZoom': True, 
        'displayModeBar': True, # Munculkan toolbar
        'modeBarButtonsToRemove': ['lasso2d', 'select2d', 'autoScale2d'], # Hapus yg ga perlu
        'displaylogo': False,
        'responsive': True
    }
    
    # Linear regression equation
    z = np.polyfit(x, y, 1)
    equation = f"y = {z[0]:.5f}x + {z[1]:.5f}"
    
    # Return chart configuration data for frontend Plotly rendering
    return {
        "equation": equation,
        "chart_data": {
            "x": x,
            "y": y,
            "layer1_name": layer1_name,
            "layer2_name": layer2_name,
            "slope": float(z[0]),
            "intercept": float(z[1])
        }
    }
# tes fungsi gengs

if __name__ == "__main__":
    upah_minimal = [1200, 1500, 800, 2000, 1100, 900, 2500, 600, 2800, 1000]
    bunuh_diri =   [12.4, 9.8, 15.2, 8.5, 11.0, 14.5, 7.2, 18.1, 6.5, 13.3]

    result = generate_smart_insight(
        "Upah Minimal", upah_minimal, 
        "Tingkat Bunuh Diri", bunuh_diri
    )
    
    scatter(result['chart_data']['x'], result['chart_data']['y'], "Upah Minimal", "Tingkat Bunuh Diri")
