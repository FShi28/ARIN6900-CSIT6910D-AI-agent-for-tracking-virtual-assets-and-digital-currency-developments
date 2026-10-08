from pathlib import Path
import json
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "canonical"

st.set_page_config(page_title="Virtual Asset Intelligence", page_icon="◈", layout="wide")

st.markdown("""
<style>
:root { color-scheme: dark; }
[data-testid="stAppViewContainer"] { background: #08111f; }
[data-testid="stHeader"] { background: rgba(8,17,31,.8); }
.block-container { padding-top: 2rem; max-width: 1400px; }
.hero { padding: 1.8rem 2rem; border: 1px solid #223754; border-radius: 20px; background: linear-gradient(120deg,#10253e,#0d1729); margin-bottom: 1.2rem; }
.hero h1 { color: #f4f8ff; font-size: 2.35rem; margin: 0; letter-spacing: -.04em; }
.hero p { color: #9fb2ca; margin: .5rem 0 0; font-size: 1.02rem; }
.metric { background:#101e32; border:1px solid #223754; border-radius:14px; padding:1rem 1.1rem; }
.metric-label { color:#8da4bf; font-size:.8rem; text-transform:uppercase; letter-spacing:.08em; }
.metric-value { color:#f5f8ff; font-size:1.7rem; font-weight:700; margin-top:.25rem; }
.badge { display:inline-block; padding:.25rem .55rem; border-radius:999px; background:#173b59; color:#7dd3fc; font-size:.75rem; }
.source { border-left:3px solid #38bdf8; padding:.65rem 1rem; margin:.55rem 0; background:#0e1a2c; border-radius:0 10px 10px 0; }
</style>
""", unsafe_allow_html=True)


def load_jsonl(name: str) -> pd.DataFrame:
    with (DATA / name).open(encoding="utf-8") as handle:
        return pd.DataFrame([json.loads(line) for line in handle if line.strip()])


def money(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


documents = load_jsonl("documents.jsonl")
developments = load_jsonl("developments.jsonl")
chunks = load_jsonl("chunks.jsonl")
markets = pd.read_csv(DATA / "market_observations.csv")

with st.sidebar:
    st.markdown("## ◈ Signal Desk")
    st.caption("Virtual asset regulatory intelligence")
    st.divider()
    page = st.radio("Workspace", ["Overview", "Regulatory Monitor", "Market Signals", "Ask the Analyst"], label_visibility="collapsed")
    st.divider()
    st.caption("DEMO DATASET")
    st.caption("All source records currently use illustrative example URLs. Replace them with approved connectors before relying on outputs.")

st.markdown('<div class="hero"><h1>Virtual Asset Intelligence</h1><p>Cross-market regulatory signals, market indicators, and source-grounded analysis.</p></div>', unsafe_allow_html=True)

if page == "Overview":
    st.markdown("### Executive snapshot")
    cols = st.columns(4)
    metrics = [("Tracked publications", len(documents), "Across 4 pilot markets"), ("Flagged developments", len(developments), "All critic-checked"), ("Evidence chunks", len(chunks), "Citation-preserving"), ("Market indicators", len(markets), "Illustrative fixtures")]
    for col, (label, value, note) in zip(cols, metrics):
        with col:
            st.markdown(f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div style="color:#7188a5;font-size:.8rem">{note}</div></div>', unsafe_allow_html=True)
    st.markdown("### Regulatory pulse")
    left, right = st.columns([1.35, 1])
    with left:
        chart_data = developments.groupby(["jurisdiction", "risk_rating"], as_index=False).size().rename(columns={"size": "count"})
        fig = px.bar(chart_data, x="jurisdiction", y="count", color="risk_rating", barmode="stack", color_discrete_map={"low":"#34d399", "medium":"#fbbf24", "high":"#fb7185"}, template="plotly_dark")
        fig.update_layout(height=330, margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="Risk")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("#### Latest signals")
        for row in developments.sort_values("confidence", ascending=False).head(4).itertuples():
            st.markdown(f'<div class="source"><span class="badge">{row.jurisdiction} · {row.risk_rating}</span><br><b>{row.obligation_summary}</b><br><small>Confidence {row.confidence:.0%} · {row.review_status.replace("_", " ")}</small></div>', unsafe_allow_html=True)

elif page == "Regulatory Monitor":
    st.markdown("### Regulatory monitor")
    f1, f2, f3 = st.columns(3)
    jurisdictions = f1.multiselect("Jurisdiction", sorted(developments.jurisdiction.unique()), default=sorted(developments.jurisdiction.unique()))
    assets = f2.multiselect("Asset class", sorted(developments.asset_class.unique()), default=sorted(developments.asset_class.unique()))
    risks = f3.multiselect("Risk rating", ["low", "medium", "high"], default=["low", "medium", "high"])
    filtered = developments[developments.jurisdiction.isin(jurisdictions) & developments.asset_class.isin(assets) & developments.risk_rating.isin(risks)]
    st.caption(f"Showing {len(filtered)} of {len(developments)} developments")
    display = filtered[["jurisdiction", "regulator", "asset_class", "lifecycle_stage", "obligation_summary", "risk_rating", "confidence"]].copy()
    display["confidence"] = display["confidence"].map(lambda x: f"{x:.0%}")
    st.dataframe(display, use_container_width=True, hide_index=True)
    selected = st.selectbox("Inspect evidence", filtered.development_id.tolist() if not filtered.empty else ["No matching records"])
    if selected != "No matching records":
        item = filtered[filtered.development_id == selected].iloc[0]
        st.markdown(f"#### {item.obligation_summary}")
        for chunk_id in item.evidence_chunk_ids:
            evidence = chunks[chunks.chunk_id == chunk_id].iloc[0]
            st.markdown(f'<div class="source">{evidence.text}<br><small>{evidence.citation.label} · <a href="{evidence.citation.url}">Open source</a></small></div>', unsafe_allow_html=True)

elif page == "Market Signals":
    st.markdown("### Market signals")
    st.info("Illustrative fixture values only. Market observations are separate from legal/regulatory evidence.")
    cols = st.columns(len(markets))
    for col, row in zip(cols, markets.itertuples()):
        with col:
            st.markdown(f'<div class="metric"><div class="metric-label">{row.instrument}</div><div class="metric-value">{money(row.value)}</div><div style="color:#7188a5;font-size:.8rem">{row.metric.replace("_", " ")}</div></div>', unsafe_allow_html=True)
    fig = px.treemap(markets, path=["asset_class", "instrument"], values="value", color="asset_class", template="plotly_dark")
    fig.update_layout(height=460, margin=dict(l=0,r=0,t=20,b=0), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(markets, use_container_width=True, hide_index=True)

else:
    st.markdown("### Ask the analyst")
    st.caption("This demo uses local keyword matching over the fixture evidence. Connect an LLM provider and orchestration layer for generated answers.")
    question = st.text_input("Question", placeholder="e.g. What are the stablecoin reserve signals across HK and the UK?")
    if question:
        terms = set(question.lower().replace("?", "").split())
        scores = chunks.text.str.lower().map(lambda text: sum(term in text for term in terms))
        matches = chunks.assign(score=scores).query("score > 0").sort_values("score", ascending=False).head(3)
        if matches.empty:
            st.warning("No matching evidence found. Try a regulator, asset class, or topic such as reserve, custody, or settlement.")
        else:
            st.markdown("#### Evidence-grounded results")
            st.write("The following source excerpts are the closest matches in the local fixture index:")
            for row in matches.itertuples():
                st.markdown(f'<div class="source"><span class="badge">match {row.score}</span><br>{row.text}<br><small>{row.citation.label} · {row.citation.url}</small></div>', unsafe_allow_html=True)

st.divider()
st.caption("Signal Desk · File-first MVP · Source-grounded outputs · Demo fixture data")
