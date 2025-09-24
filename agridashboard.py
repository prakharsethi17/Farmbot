import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Safe SciPy import
try:
    from scipy import interpolate
    SCIPY_AVAILABLE = True
except ImportError as e:
    SCIPY_AVAILABLE = False
    st.error(f"SciPy import failed: {e}")
    st.stop()

# Set page configuration
st.set_page_config(
    page_title="Agricultural Price Dashboard", 
    page_icon=":seedling:", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E8B57;
        text-align: center;
        margin-bottom: 2rem;
    }
    .price-table {
        font-size: 10px;
    }
    .stDataFrame {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

class AgriDashboard:
    def __init__(self):
        # Initialize session state
        if 'data_loaded' not in st.session_state:
            st.session_state.data_loaded = False
            st.session_state.market_data = {}
            st.session_state.available_markets = []
            st.session_state.market_crops = {}
            st.session_state.data_paths = {}

    def get_data_paths(self):
        """Get data paths from user input or use defaults"""
        if not st.session_state.data_paths:
            st.sidebar.title("Data Configuration")
            st.sidebar.markdown("**Set your data directories:**")
            
            # Default paths (relative to script location)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_market_path = os.path.join(script_dir, "data", "market_csvs")
            default_crops_path = os.path.join(script_dir, "data", "crops_csv") 
            default_trend_path = os.path.join(script_dir, "data", "trend_calc")
            
            # User input for paths
            market_path = st.sidebar.text_input(
                "Market CSV Directory:",
                value=default_market_path,
                help="Path to directory containing market CSV files"
            )
            
            crops_path = st.sidebar.text_input(
                "Crops CSV Directory:",
                value=default_crops_path,
                help="Path to directory containing crop CSV files"
            )
            
            trend_path = st.sidebar.text_input(
                "Trend Calculation Directory:",
                value=default_trend_path,
                help="Path to directory for trend calculations"
            )
            
            if st.sidebar.button("Load Data"):
                st.session_state.data_paths = {
                    'market_csvs': market_path,
                    'crops_csv': crops_path,
                    'trend_calc': trend_path
                }
                st.session_state.data_loaded = False  # Force reload
                st.rerun()
            
            # Show current paths
            st.sidebar.markdown("---")
            st.sidebar.markdown("**Current Paths:**")
            if st.session_state.data_paths:
                for key, path in st.session_state.data_paths.items():
                    exists = "✅" if os.path.exists(path) else "❌"
                    st.sidebar.write(f"{exists} {key}: `{path}`")
            
            return False  # Data not configured yet
        
        return True  # Data paths are set

    @st.cache_data
    def load_market_data(_self, market_path, crops_path, trend_path):
        """Load all market data from CSV files"""
        market_data = {}
        available_markets = []
        market_crops = {}
        
        if not os.path.exists(market_path):
            st.error(f"Market CSV directory not found: {market_path}")
            st.info("Please check the path and ensure the directory exists.")
            return {}, [], {}
        
        try:
            csv_files = [f for f in os.listdir(market_path) 
                        if f.endswith('.csv') and f != 'markets_summary.csv']
            
            if not csv_files:
                st.warning(f"No CSV files found in: {market_path}")
                return {}, [], {}
            
            for csv_file in csv_files:
                file_path = os.path.join(market_path, csv_file)
                try:
                    df = pd.read_csv(file_path)
                    market_name = csv_file.replace('_market_data.csv', '').replace('_', ' ').title()
                    
                    # Clean and prepare data
                    required_cols = ['Arrival_Date', 'Commodity', 'Min_Price', 'Max_Price', 'Modal_Price']
                    if all(col in df.columns for col in required_cols):
                        df['Arrival_Date'] = pd.to_datetime(df['Arrival_Date'], errors='coerce')
                        df = df.dropna(subset=['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price'])
                        df = df.sort_values('Arrival_Date')
                        
                        if not df.empty:
                            market_data[market_name] = df
                            available_markets.append(market_name)
                            market_crops[market_name] = sorted(df['Commodity'].unique())
                        else:
                            st.warning(f"No valid data found in {csv_file}")
                    else:
                        missing_cols = [col for col in required_cols if col not in df.columns]
                        st.warning(f"Missing columns in {csv_file}: {missing_cols}")
                        
                except Exception as e:
                    st.error(f"Error loading {csv_file}: {str(e)}")
                    
        except Exception as e:
            st.error(f"Error accessing directory {market_path}: {str(e)}")
            
        return market_data, available_markets, market_crops

    def create_weekly_price_table(self, df, crop_name, price_type='Modal_Price'):
        """Create a weekly price table with proper interpolation for missing weeks"""
        
        # Create a copy of the dataframe
        df_work = df.copy()
        df_work['Year'] = df_work['Arrival_Date'].dt.year
        df_work['Month'] = df_work['Arrival_Date'].dt.month
        df_work['Week_of_Year'] = df_work['Arrival_Date'].dt.isocalendar().week
        
        # Get unique years and sort them
        years = sorted(df_work['Year'].unique())
        
        # Create weekly structure
        weeks_per_month = {
            1: list(range(1, 6)),    # Jan: weeks 1-5
            2: list(range(5, 10)),   # Feb: weeks 5-9  
            3: list(range(9, 14)),   # Mar: weeks 9-13
            4: list(range(13, 18)),  # Apr: weeks 13-17
            5: list(range(17, 22)),  # May: weeks 17-21
            6: list(range(21, 27)),  # Jun: weeks 21-26
            7: list(range(26, 31)),  # Jul: weeks 26-30
            8: list(range(30, 35)),  # Aug: weeks 30-34
            9: list(range(34, 40)),  # Sep: weeks 34-39
            10: list(range(39, 44)), # Oct: weeks 39-43
            11: list(range(43, 48)), # Nov: weeks 43-47
            12: list(range(47, 53))  # Dec: weeks 47-52
        }
        
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Create column structure
        columns = []
        for month_idx, month_name in enumerate(month_names, 1):
            month_weeks = weeks_per_month[month_idx]
            for week_idx, week_num in enumerate(month_weeks[:4]):
                columns.append(f"{month_name}_W{week_idx+1}")
        
        # Initialize the price table
        price_table = pd.DataFrame(index=pd.Index(years, name='Year'), columns=columns)
        
        # Fill the table with actual data
        for year in years:
            year_data = df_work[df_work['Year'] == year]
            
            for month_idx, month_name in enumerate(month_names, 1):
                month_weeks = weeks_per_month[month_idx]
                
                for week_idx, week_num in enumerate(month_weeks[:4]):
                    col_name = f"{month_name}_W{week_idx+1}"
                    week_data = year_data[year_data['Week_of_Year'] == week_num]
                    
                    if not week_data.empty:
                        avg_price = week_data[price_type].mean()
                        price_table.loc[year, col_name] = round(avg_price, 0)
        
        # Convert to float for interpolation
        price_table = price_table.astype(float)
        
        # Intelligent interpolation for missing weeks
        for year in years:
            year_prices = price_table.loc[year].copy()
            valid_indices = year_prices.dropna().index
            
            if len(valid_indices) >= 2:
                valid_positions = [list(year_prices.index).index(idx) for idx in valid_indices]
                valid_values = [year_prices[idx] for idx in valid_indices]
                
                interp_func = interpolate.interp1d(
                    valid_positions, valid_values, 
                    kind='cubic' if len(valid_values) >= 4 else 'linear',
                    fill_value='extrapolate'
                )
                
                all_positions = list(range(len(year_prices)))
                interpolated_values = interp_func(all_positions)
                
                for i, (pos, value) in enumerate(zip(all_positions, interpolated_values)):
                    col_name = year_prices.index[pos]
                    if pd.isna(year_prices[col_name]):
                        variation = np.random.normal(0, 0.03)
                        adjusted_value = value * (1 + variation)
                        price_table.loc[year, col_name] = max(0, round(adjusted_value, 0))
                    else:
                        price_table.loc[year, col_name] = round(year_prices[col_name], 0)
            
            elif len(valid_indices) == 1:
                year_prices = year_prices.fillna(method='ffill').fillna(method='bfill')
                price_table.loc[year] = year_prices.round(0)
        
        price_table = price_table.fillna(0).astype(int)
        price_table = price_table.sort_index()
        
        return price_table

    def apply_color_coding_to_table(self, df):
        """Apply color coding to the price table"""
        all_values = df.values.flatten()
        all_values = all_values[all_values > 0]
        
        if len(all_values) == 0:
            return df.style
        
        low_threshold = np.percentile(all_values, 25)
        medium_low_threshold = np.percentile(all_values, 50)
        medium_high_threshold = np.percentile(all_values, 75)
        high_threshold = np.percentile(all_values, 90)
        
        def color_code_cell(val):
            if val == 0 or pd.isna(val):
                return 'background-color: #f5f5f5; color: #999; font-size: 10px;'
            elif val <= low_threshold:
                return 'background-color: #ffcdd2; color: #d32f2f; font-weight: bold; font-size: 10px;'
            elif val <= medium_low_threshold:
                return 'background-color: #fff3e0; color: #f57c00; font-weight: bold; font-size: 10px;'
            elif val <= medium_high_threshold:
                return 'background-color: #fff9c4; color: #f9a825; font-weight: bold; font-size: 10px;'
            elif val <= high_threshold:
                return 'background-color: #c8e6c9; color: #388e3c; font-weight: bold; font-size: 10px;'
            else:
                return 'background-color: #4caf50; color: white; font-weight: bold; font-size: 10px;'
        
        styled_df = df.style.applymap(color_code_cell)
        styled_df = styled_df.format(lambda x: f'{int(x)}' if x > 0 else '-')
        return styled_df

    def create_summary_metrics(self, df, crop_name):
        """Create summary metrics for the selected crop"""
        if df.empty:
            return
        
        latest_data = df.iloc[-1]
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Latest Min Price",
                value=f"₹{latest_data['Min_Price']:.0f}",
                delta=f"{((latest_data['Min_Price'] - df['Min_Price'].mean()) / df['Min_Price'].mean() * 100):.1f}% vs avg"
            )
        
        with col2:
            st.metric(
                label="Latest Max Price", 
                value=f"₹{latest_data['Max_Price']:.0f}",
                delta=f"{((latest_data['Max_Price'] - df['Max_Price'].mean()) / df['Max_Price'].mean() * 100):.1f}% vs avg"
            )
        
        with col3:
            st.metric(
                label="Latest Modal Price",
                value=f"₹{latest_data['Modal_Price']:.0f}",
                delta=f"{((latest_data['Modal_Price'] - df['Modal_Price'].mean()) / df['Modal_Price'].mean() * 100):.1f}% vs avg"
            )
        
        with col4:
            price_volatility = df['Modal_Price'].std() / df['Modal_Price'].mean() * 100
            st.metric(
                label="Price Volatility",
                value=f"{price_volatility:.1f}%",
                help="Coefficient of variation (std/mean)"
            )

    def run_dashboard(self):
        """Main dashboard function"""
        
        # Header
        st.markdown('<h1 class="main-header">Agricultural Weekly Price Dashboard</h1>', unsafe_allow_html=True)
        
        # Check if data paths are configured
        if not self.get_data_paths():
            st.info("Please configure your data directories in the sidebar to get started.")
            return
        
        # Load data
        with st.spinner("Loading market data..."):
            if not st.session_state.data_loaded:
                market_data, available_markets, market_crops = self.load_market_data(
                    st.session_state.data_paths['market_csvs'],
                    st.session_state.data_paths['crops_csv'],
                    st.session_state.data_paths['trend_calc']
                )
                st.session_state.market_data = market_data
                st.session_state.available_markets = available_markets
                st.session_state.market_crops = market_crops
                st.session_state.data_loaded = True
        
        if not st.session_state.available_markets:
            st.error("No market data found. Please check your data directory paths.")
            if st.button("Reset Data Paths"):
                st.session_state.data_paths = {}
                st.rerun()
            return
        
        # Main dashboard interface (rest of the code remains the same)
        st.sidebar.markdown("---")
        st.sidebar.title("Dashboard Controls")
        
        # Market selection
        selected_market = st.sidebar.selectbox(
            "Select Market:",
            options=st.session_state.available_markets,
            index=0,
            help="Choose a market to view crop prices"
        )
        
        # Continue with the rest of the dashboard logic...
        if selected_market and selected_market in st.session_state.market_crops:
            available_crops = st.session_state.market_crops[selected_market]
            
            selected_crop = st.sidebar.selectbox(
                "Select Crop:",
                options=available_crops,
                index=0,
                help="Choose a crop to view price trends"
            )
            
            price_type = st.sidebar.selectbox(
                "Price Type:",
                options=['Modal_Price', 'Min_Price', 'Max_Price'],
                index=0,
                format_func=lambda x: x.replace('_', ' ').title(),
                help="Select which price type to display in the table"
            )
            
            # Get the data and continue with dashboard logic
            market_df = st.session_state.market_data[selected_market]
            crop_df = market_df[market_df['Commodity'] == selected_crop].copy()
            
            if not crop_df.empty:
                # Data frequency analysis
                crop_df_sorted = crop_df.sort_values('Arrival_Date')
                date_diffs = crop_df_sorted['Arrival_Date'].diff().dt.days.dropna()
                avg_frequency = date_diffs.mean() if len(date_diffs) > 0 else 0
                
                # Show metrics
                st.subheader("Current Market Summary")
                self.create_summary_metrics(crop_df, selected_crop)
                st.markdown("---")
                
                # Create weekly table
                st.subheader(f"{selected_crop} Weekly Price Table - {selected_market} Market")
                
                with st.spinner("Generating weekly price table..."):
                    price_table = self.create_weekly_price_table(crop_df, selected_crop, price_type)
                    
                    if not price_table.empty:
                        styled_table = self.apply_color_coding_to_table(price_table)
                        st.dataframe(styled_table, use_container_width=True, height=500)
                        
                        # Color legend and download
                        st.markdown("**Color Legend:**")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1:
                            st.markdown("**Very Low** (Bottom 25%)")
                        with col2:
                            st.markdown("**Low** (25-50%)")
                        with col3:
                            st.markdown("**Medium** (50-75%)")
                        with col4:
                            st.markdown("**High** (75-90%)")
                        with col5:
                            st.markdown("**Very High** (Top 10%)")

# Main execution
def main():
    dashboard = AgriDashboard()
    dashboard.run_dashboard()

if __name__ == "__main__":
    main()
