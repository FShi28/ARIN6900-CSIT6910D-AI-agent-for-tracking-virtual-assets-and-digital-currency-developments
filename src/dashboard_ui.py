"""The original four workspace pages, backed exclusively by real sources."""

import sqlite3
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_data import load_corpus, search_evidence
from live_documents import collection_panel, collection_service, document_panel, local_time
from market_data import market_snapshot


@st.cache_data(ttl=15, show_spinner=False)
def corpus(path, modified):
    return load_corpus(path)


def money(value):
    for scale, suffix in [(1e12, 'T'), (1e9, 'B'), (1e6, 'M')]:
        if value >= scale:
            return f'${value / scale:,.2f}{suffix}'
    return f'${value:,.2f}'


def chart(frame, x, y, color=None):
    fig = px.bar(frame, x=x, y=y, color=color, template='plotly_dark')
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)


def evidence(chunk):
    citation = chunk['citation']
    st.write(citation['title'] or 'Untitled publication')
    st.text(chunk['text'])
    location = f"PDF page {chunk['page_start']}" if chunk['page_start'] else 'HTML body'
    st.caption(f"{citation['source_name']} | Published: {citation['published_at'] or 'Unknown'} | "
               f"{location} | Characters {chunk['char_start']}:{chunk['char_end']}")
    st.link_button('Open source', citation['source_url'])
    with st.expander('Citation details: ' + chunk['chunk_id'][:12]):
        st.json(citation)


@st.fragment(run_every='60s')
def market_panel(root, compact=False):
    st.subheader('Market indicators' if compact else 'Market signals')
    st.caption('Public market APIs. Cached for 15 minutes; this view checks every minute while open. '
               'Market observations are separate from regulatory evidence.')
    try:
        snapshots = market_snapshot(root)
    except (ValueError, OSError) as exc:
        st.error(f'Market configuration unavailable: {exc}')
        return
    available = []
    for snapshot in snapshots:
        if snapshot['status'] != 'available':
            st.warning(f"{snapshot['source_id']}: {snapshot['status']}. "
                       f"{snapshot.get('error') or 'A refresh is pending.'}")
        st.caption(f"{snapshot['provider']} / {snapshot['source_id']} | "
                   f"Retrieved: {local_time(snapshot['collected_at'])} | {snapshot['status']}")
        available.extend(dict(row, data_status=snapshot['status']) for row in snapshot['rows'])
    if not available:
        st.info('No verified market observations are available. No sample values are substituted.')
        return
    frame = pd.DataFrame(available)
    btc = frame[(frame.asset_class == 'cryptocurrency') & (frame.metric == 'market_cap')]
    usdc = frame[(frame.instrument == 'USDC') & (frame.metric == 'circulating_amount')]
    usdt = frame[(frame.instrument == 'USDT') & (frame.metric == 'circulating_amount')]
    columns = st.columns(3)
    for col, label, data in zip(columns, ['BTC market cap (USD)', 'USDC circulating (USD at peg)',
                                         'USDT circulating (USD at peg)'], [btc, usdc, usdt]):
        col.metric(label, money(data.iloc[0]['value']) if not data.empty else 'Unavailable')
    dated = frame.dropna(subset=['observed_at'])
    for value in sorted(dated.observed_at.unique()):
        st.caption(f'Provider update time: {local_time(value)}')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value.replace('Z', '+00:00'))).total_seconds()
        if age > 3600:
            st.warning('The provider update timestamp is over one hour old, even if retrieval succeeded.')
    st.caption('DefiLlama does not supply a per-record update timestamp here. Retrieval time does not '
               'establish the age of its underlying measurements.')
    if compact:
        return
    assets = st.multiselect('Market asset class', sorted(frame.asset_class.unique()),
                            default=sorted(frame.asset_class.unique()))
    filtered = frame[frame.asset_class.isin(assets)]
    stable = filtered[filtered.metric == 'circulating_amount'].nlargest(15, 'value')
    if not stable.empty:
        st.write('**Largest tracked USD-pegged circulating amounts**')
        st.caption('Nominal USD at peg, not a price-adjusted market capitalization. Non-USD pegs are excluded.')
        chart(stable, 'instrument', 'value')
    rwa = filtered[filtered.metric == 'protocol_tvl'].nlargest(15, 'value')
    if not rwa.empty:
        st.write('**RWA protocol TVL (USD)**')
        st.caption('Individual protocols classified as RWA by DefiLlama. These are not a tokenized Treasury '
                   'basket or a deduplicated total of the RWA market. Different metrics are plotted separately.')
        chart(rwa, 'instrument', 'value')
    st.dataframe(filtered[['instrument', 'asset_class', 'metric', 'value', 'unit', 'provider',
                           'observed_at', 'collected_at', 'data_status', 'source_url']],
                 use_container_width=True, hide_index=True)
    if not filtered.empty:
        choices = filtered.index.tolist()
        selected = st.selectbox('Inspect market provenance', choices,
            format_func=lambda i: f"{frame.loc[i, 'instrument']} / {frame.loc[i, 'metric']} / {frame.loc[i, 'asset_id']}")
        st.json(frame.loc[selected].to_dict())


def overview(data, root):
    documents, chunks = data['documents'], data['chunks']
    st.subheader('Executive snapshot')
    columns = st.columns(4)
    for col, label, count in zip(columns, ['Tracked publications', 'Ready publications', 'Evidence chunks',
                                          'Regulatory jurisdictions'],
                                 [len(documents), sum(d['state'] == 'ready' for d in documents),
                                  len(chunks), len({d['jurisdiction'] for d in documents})]):
        col.metric(label, count)
    st.subheader('Regulatory pulse')
    st.caption('Publication counts and source excerpts. Legal risks and obligations have not been assessed.')
    if documents:
        frame = pd.DataFrame(documents)
        counts = frame.fillna({'document_type': 'unprocessed'}).groupby(
            ['jurisdiction', 'document_type'], as_index=False).size().rename(columns={'size': 'publications'})
        chart(counts, 'jurisdiction', 'publications', 'document_type')
        st.write('**Latest publications**')
        by_document = {}
        for chunk in chunks:
            by_document.setdefault(chunk['citation']['document_id'], chunk)
        for doc in sorted(documents, key=lambda d: d['published_at'] or '', reverse=True)[:4]:
            st.write(doc['title'] or doc['source_url'])
            st.caption(f"{doc['jurisdiction']} / {doc['regulator']} | Published: {doc['published_at'] or 'Unknown'}")
            if doc['document_id'] in by_document:
                st.text(by_document[doc['document_id']]['text'][:550])
            st.link_button('Read official publication', doc['source_url'])
    else:
        st.info('No real regulatory documents are available yet. Open Collection controls to collect HKMA.')
    market_panel(root, compact=True)


def regulatory(data, root):
    st.subheader('Regulatory monitor')
    st.caption('Official publications replace illustrative developments. Risk, confidence and review status '
               'are not assessed; no automatic obligation summaries are asserted.')
    documents = data['documents']
    filtered = documents
    if documents:
        left, middle, right = st.columns(3)
        jurisdictions = sorted({d['jurisdiction'] for d in documents})
        assets = sorted({a for d in documents for a in (d['asset_classes'] or ['unknown'])})
        types = sorted({d['document_type'] or 'unprocessed' for d in documents})
        selected_j = left.multiselect('Jurisdiction', jurisdictions, default=jurisdictions)
        selected_a = middle.multiselect('Asset class', assets, default=assets)
        selected_t = right.multiselect('Document type', types, default=types)
        filtered = [d for d in documents if d['jurisdiction'] in selected_j
                    and set(d['asset_classes'] or ['unknown']) & set(selected_a)
                    and (d['document_type'] or 'unprocessed') in selected_t]
        st.caption(f'Showing {len(filtered)} of {len(documents)} publications')
        st.dataframe([{'Title': d['title'], 'Jurisdiction': d['jurisdiction'], 'Regulator': d['regulator'],
                       'Asset class': ', '.join(d['asset_classes']), 'Document type': d['document_type'],
                       'Lifecycle': d['lifecycle_stage'], 'Published': d['published_at'] or 'Unknown',
                       'Last observed': local_time(d['last_observed_at']), 'Source': d['source_url']}
                      for d in filtered], hide_index=True, use_container_width=True)
    st.divider()
    # Keep the full-text reader and verified original download within the original monitor page.
    document_panel(root, root / 'data/ingestion/hkma.sqlite', documents_override=filtered)


def analyst(data):
    st.subheader('Ask the analyst')
    st.caption('Search current real regulatory evidence. Results are verbatim excerpts ranked by matching '
               'English words, not an AI-generated answer or a confidence score.')
    jurisdictions = sorted({d['jurisdiction'] for d in data['documents']})
    scope = st.selectbox('Evidence jurisdiction', ['All collected jurisdictions', *jurisdictions])
    st.caption('Available coverage: ' + (', '.join(jurisdictions) or 'No collected documents'))
    question = st.text_input('Question', placeholder='e.g. What are the stablecoin reserve requirements?', max_chars=500)
    if question:
        matches = search_evidence(data, question, jurisdiction=None if scope == 'All collected jurisdictions' else scope)
        if not matches:
            st.info('No matching current evidence found. Try English terms such as reserve, custody or redemption.')
        else:
            st.write('**Source-grounded excerpts**')
            for chunk in matches:
                st.caption('Matched terms: ' + ', '.join(chunk['matched_terms']))
                evidence(chunk)


@st.fragment(run_every='15s')
def regulatory_workspace(page, root):
    path = root / 'data/ingestion/hkma.sqlite'
    try:
        data = corpus(str(path), path.stat().st_mtime_ns) if path.exists() else {'documents': [], 'chunks': []}
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(f'Real regulatory database unavailable: {exc}')
        data = {'documents': [], 'chunks': []}
    if page == 'Overview':
        overview(data, root)
    elif page == 'Regulatory Monitor':
        regulatory(data, root)
    else:
        analyst(data)


def render_dashboard(root):
    st.markdown('''<style>[data-testid="stTextArea"] textarea:disabled {
        -webkit-text-fill-color: #e5e7eb; color: #e5e7eb; opacity: 1;
    }</style>''', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('## Signal Desk')
        st.caption('Virtual asset regulatory intelligence')
        page = st.radio('Workspace', ['Overview', 'Regulatory Monitor', 'Market Signals', 'Ask the Analyst'])
        st.divider()
        st.caption('REAL DATA SOURCES')
        st.caption('HKMA official publications; DefiLlama and CoinGecko market APIs.')
    st.markdown('<div class="hero"><h1>Virtual Asset Intelligence</h1><p>Regulatory publications, '
                'market indicators, and traceable evidence.</p></div>', unsafe_allow_html=True)
    with st.expander('Collection controls'):
        collection_panel(collection_service(str(root)))
    if page == 'Market Signals':
        market_panel(root)
    else:
        regulatory_workspace(page, root)
    st.divider()
    st.caption('Signal Desk | Real source data | Unknown fields remain unknown')
