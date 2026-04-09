import streamlit as st
import sys
import logging
import os
import time

# Add the project root to path to allow importing dashboard modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Configure logging
os.makedirs(os.path.join(project_root, 'logs'), exist_ok=True)
# Use in-memory logging instead of file-based logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('streamlit_dashboard')
logger.info("Starting Streamlit dashboard")

# Import dashboard components
from src.dashboard.components.evaluation_setup import EvaluationSetupComponent
from src.dashboard.components.model_configuration import ModelConfigurationComponent
from src.dashboard.components.evaluation_monitor import EvaluationMonitorComponent
from src.dashboard.components.results_viewer import ResultsViewerComponent
from src.dashboard.components.report_viewer import ReportViewerComponent
from src.dashboard.components.unprocessed_viewer import UnprocessedRecordsViewer
from src.dashboard.utils.state_management import initialize_session_state
from src.dashboard.utils.constants import APP_TITLE, SIDEBAR_INFO, PROJECT_ROOT, reload_model_data

# Initialize session state at module level to ensure it's available before component rendering
if "evaluations" not in st.session_state:
    initialize_session_state()
    
# Debug session state
print("Session state initialized at module level:")
print(f"Evaluations: {len(st.session_state.evaluations)}")
print(f"Active evaluations: {len(st.session_state.active_evaluations)}")
print(f"Completed evaluations: {len(st.session_state.completed_evaluations)}")

def main():
    """Main Streamlit dashboard application."""
    try:
        # Set page title and layout with custom icon
        logger.info("Initializing Streamlit dashboard")
        
        icon_path = os.path.join(PROJECT_ROOT, "assets", "scale_icon.png")
        
        st.set_page_config(
            page_title=APP_TITLE,
            page_icon=icon_path,
            layout="wide"
        )
        
        # Ensure models_profiles.jsonl exists and pricing is fresh
        if "models_profiles_checked" not in st.session_state:
            try:
                sys.path.insert(0, os.path.join(project_root, "360-eval", "src"))
                from bedrock_pricing import ensure_models_profiles, MODELS_PROFILE_PATH, PRICING_REFRESH_DAYS

                needs_generate = not MODELS_PROFILE_PATH.exists()
                needs_refresh = False
                if not needs_generate:
                    try:
                        file_age_days = (time.time() - MODELS_PROFILE_PATH.stat().st_mtime) / 86400
                        needs_refresh = file_age_days >= PRICING_REFRESH_DAYS
                    except OSError:
                        needs_refresh = False

                if needs_generate or needs_refresh:
                    msg = (
                        "Generating model catalog from AWS..."
                        if needs_generate
                        else f"Refreshing Bedrock model pricing (over {PRICING_REFRESH_DAYS} days old)..."
                    )
                    status_placeholder = st.empty()
                    with status_placeholder.status(msg, expanded=True):
                        st.write("Fetching models, regions, and pricing from AWS APIs.")
                        st.write("This may take **20-30 seconds**.")
                        ensure_models_profiles()
                    status_placeholder.empty()
                    # Reload constants that were empty at import time
                    reload_model_data()
            except Exception as e:
                logger.warning("Failed to ensure models profiles: %s", e)
            st.session_state.models_profiles_checked = True

        # Initialize session state again to ensure all variables are set
        initialize_session_state()
        logger.info("Session state initialized")
        
        # Display log file path for debugging
        log_dir = os.path.join(PROJECT_ROOT, 'logs')
        
        # Add log information to sidebar
        with st.sidebar:
            with st.expander("📋 Debug Information"):
                st.info(f"Log Directory: {log_dir}")
                st.info(f"Project Root: {PROJECT_ROOT}")
                # Add button to show latest logs
                if st.button("Show Latest Logs"):
                    log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                    if log_files:
                        latest_log = max(log_files, key=lambda x: os.path.getmtime(os.path.join(log_dir, x)))
                        with open(os.path.join(log_dir, latest_log), 'r') as f:
                            log_content = f.read()
                        st.text_area("Latest Log Entries", log_content[-5000:], height=300)
                    else:
                        st.warning("No log files found")
        
        # Header with logo and title
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.image(icon_path, width=150)
        
        with col2:
            st.title(APP_TITLE)
            st.markdown("Create, manage, and visualize LLM benchmark evaluations using LLM-as-a-JURY methodology")
        
        # Sidebar with info
        with st.sidebar:
            st.markdown(SIDEBAR_INFO)
            st.divider()
            
            # Navigation tabs in sidebar - include Unprocessed tab
            tab_names = ["Setup", "Monitor", "Evaluations", "Reports", "Unprocessed"]

            # Check if we need to navigate to Setup tab
            if "navigate_to_setup" in st.session_state and st.session_state.navigate_to_setup:
                st.session_state.nav_radio = "Setup"
                del st.session_state.navigate_to_setup

            active_tab = st.radio("Navigation", tab_names, key="nav_radio")
            logger.info(f"Selected tab: {active_tab}")
        
        # Main area - show different components based on active tab
        if active_tab == "Setup":
            # Use session-state-backed radio for sub-tab persistence across reruns
            setup_sections = ["Evaluation Setup", "Model Configuration", "Advanced Configuration"]
            active_setup = st.radio(
                "Setup Section",
                setup_sections,
                key="setup_sub_tab",
                horizontal=True,
                label_visibility="collapsed",
            )

            if active_setup == "Evaluation Setup":
                logger.info("Rendering Evaluation Setup component")
                EvaluationSetupComponent().render()
            elif active_setup == "Model Configuration":
                logger.info("Rendering Model Configuration component")
                ModelConfigurationComponent().render()
            elif active_setup == "Advanced Configuration":
                logger.info("Rendering Advanced Configuration component")
                EvaluationSetupComponent().render_advanced_config()
                
        elif active_tab == "Monitor":
            logger.info("Rendering Evaluation Monitor component")
            EvaluationMonitorComponent().render()
            
        elif active_tab == "Evaluations":
            logger.info("Rendering Results Viewer component")
            ResultsViewerComponent().render()

        elif active_tab == "Unprocessed":
            logger.info("Rendering Unprocessed Records Viewer component")
            UnprocessedRecordsViewer().render()

        elif active_tab == "Reports":
            logger.info("Rendering Report Viewer component")
            ReportViewerComponent().render()
            
    except Exception as e:
        logger.exception(f"Unhandled exception in main dashboard: {str(e)}")
        st.error(f"An error occurred: {str(e)}")
        st.info(f"Check logs for details at: {log_dir}")

if __name__ == "__main__":
    main()