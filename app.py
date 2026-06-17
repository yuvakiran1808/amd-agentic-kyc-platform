import streamlit as st
import asyncio
import pandas as pd
import altair as alt
from orchestrator import KYCPlatformOrchestrator
from utils import prepare_ingestion_file, init_db, log_case, get_all_cases, get_status_counts

# Initialize Database
init_db()

st.set_page_config(page_title="Agentic KYC Platform", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        /* Remove excess top padding to make it feel like a real dashboard */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        /* Hide Streamlit default menus and footers */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("Agentic KYC Intelligence Platform")
st.markdown("**Enterprise Due Diligence Pipeline | Accelerated by AMD ROCm & vLLM**")
st.divider()

if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = KYCPlatformOrchestrator()

tab_scan, tab_history = st.tabs(["Active Identity Scan", "Compliance Dashboard"])

with tab_scan:
    column_left, column_right = st.columns([5, 7], gap="large")

    with column_left:
        # Card: Data Ingestion
        with st.container(border=True):
            st.subheader("Data Ingestion")
            uploaded_file = st.file_uploader("Upload Identity Asset (JPEG/PNG/PDF)", type=["png", "jpg", "jpeg", "pdf"])
            
            st.divider()
            st.markdown("##### Biometric Liveness Check")
            selfie_file = st.camera_input("Capture Live Selfie for 1:1 Matching")
        
        if uploaded_file:
            processed_path = prepare_ingestion_file(uploaded_file)
            
            selfie_path = None
            if selfie_file:
                selfie_path = "temp_storage/selfie.jpg"
                with open(selfie_path, "wb") as f:
                    f.write(selfie_file.getbuffer())

            if processed_path:
                with st.container(border=True):
                    st.markdown("**Active Target Document View**")
                    st.image(processed_path, use_container_width=True)
                
                if st.button("Trigger Core Verification Pipeline", type="primary", use_container_width=True):
                    with st.spinner("Orchestrating AI agents over AMD vLLM compute arrays..."):
                        res = asyncio.run(st.session_state.orchestrator.run_analysis(processed_path, selfie_path))
                        st.session_state.result_payload = res
                        
                        profile = res.get("profile", {})
                        log_case(
                            customer_name=profile.get("full_name", "Unknown"),
                            document_id=profile.get("document_id", "Unknown"),
                            decision=res["status"],
                            risk_score=res["composite_risk_score"]
                        )

    with column_right:
        if "result_payload" in st.session_state:
            res = st.session_state.result_payload
            status = res["status"]
            score = res["composite_risk_score"]
            normalized_score = min(max(int(score), 0), 100)
            
            # Card: Final Decision
            with st.container(border=True):
                st.subheader("Final System Decision")
                if status == "APPROVE": 
                    st.success("Outcome: SYSTEM APPROVED")
                    st.progress(normalized_score, text=f"Composite Risk Score: {normalized_score}/100 (Low Risk)")
                elif status == "REVIEW": 
                    st.warning("Outcome: MANUAL REVIEW REQUIRED")
                    st.progress(normalized_score, text=f"Composite Risk Score: {normalized_score}/100 (Moderate Risk)")
                else: 
                    st.error("Outcome: ESCALATE TO COMPLIANCE TEAM")
                    st.progress(normalized_score, text=f"Composite Risk Score: {normalized_score}/100 (Critical Risk)")
            
            # Card: Risk Metrics
            with st.container(border=True):
                st.subheader("Risk Distribution Metrics")
                metrics = res.get("metrics", {})
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                with m_col1:
                    st.metric("Sanctions", metrics.get("sanctions_risk", "N/A"))
                with m_col2:
                    st.metric("Financial", metrics.get("financial_risk", "N/A"))
                with m_col3:
                    st.metric("ID Verification", metrics.get("id_verification_risk", "N/A"))
                with m_col4:
                    st.metric("Biometric", metrics.get("biometric_risk", "N/A"))
            
            # Card: Audit Trail
            with st.container(border=True):
                st.subheader("Cryptographic Audit Trail")
                st.caption("Step-by-step agent execution evidence.")
                for index, trace in enumerate(res["audit_trail"]):
                    with st.expander(f"Phase {index + 1}: {trace['agent_name']} | Latency: {trace['latency_sec']}s"):
                        st.code(trace["output"], language="json")
        else:
            with st.container(border=True):
                st.info("System Idle. Upload documents and trigger verification to initialize the workspace.")

with tab_history:
    status_df = get_status_counts()
    dash_col1, dash_col2 = st.columns([1, 2], gap="large")
    
    with dash_col1:
        st.markdown("#### Platform Operational Statistics")
        with st.container(border=True):
            total_cases = int(status_df['count'].sum()) if not status_df.empty else 0
            st.metric("Total Cases Processed", total_cases)
            
            approved = int(status_df[status_df['status'] == 'APPROVE']['count'].sum()) if 'APPROVE' in status_df['status'].values else 0
            escalated = int(status_df[status_df['status'] == 'ESCALATE']['count'].sum()) if 'ESCALATE' in status_df['status'].values else 0
            review = int(status_df[status_df['status'] == 'REVIEW']['count'].sum()) if 'REVIEW' in status_df['status'].values else 0
            
            st.metric("Auto-Approved Entities", approved)
            st.metric("Pending Manual Review", review)
            st.metric("Escalated / Rejected", escalated)

    with dash_col2:
        st.markdown("#### Case Decision Distribution")
        with st.container(border=True):
            if not status_df.empty and total_cases > 0:
                chart = alt.Chart(status_df).mark_bar(size=50).encode(
                    x=alt.X('status', title=None, axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                    y=alt.Y('count', title='Total Cases'),
                    color=alt.Color('status', scale=alt.Scale(
                        domain=['APPROVE', 'REVIEW', 'ESCALATE'],
                        range=['#2e7d32', '#f57f17', '#c62828'] 
                    ), legend=None),
                    tooltip=['status', 'count']
                ).properties(height=350)
                
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("Insufficient data to generate dashboard visualizations.")
    st.markdown("#### Secure Enterprise Audit Logs")
    with st.container(border=True):
        cases = get_all_cases()
        if cases:
            try:
                history_df = pd.DataFrame(cases)
                history_df = history_df.rename(columns={
                    "id": "Reference ID",
                    "timestamp": "Timestamp",
                    "customer_name": "Customer Name",
                    "document_id": "Document ID",
                    "decision": "Final Decision",
                    "risk_score": "Composite Risk Score"
                })
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.dataframe(cases, use_container_width=True)
        else:
            st.info("No compliance cases have been logged into the system yet.")