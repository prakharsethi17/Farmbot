import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Safe SciPy import (optional, not used after WMA-only change)
try:
    from scipy import interpolate
    SCIPY_AVAILABLE = True
except ImportError as e:
    SCIPY_AVAILABLE = False
    st.warning(f"SciPy not available: {e}")

# Page configuration
st.set_page_config(
    page_title="Agricultural Price Dashboard",
    page_icon=":seedling:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
    .metric-container {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


class AgriDashboard:
    def __init__(self):
        if 'data_loaded' not in st.session_state:
            st.session_state.data_loaded = False
            st.session_state.market_data = {}
            st.session_state.available_markets = []
            st.session_state.market_crops = {}
            st.session_state.data_paths = {}
            st.session_state.market_meta = None
        if 'screener_distances' not in st.session_state:
            st.session_state.screener_distances = pd.DataFrame()
        if 'debug_mode' not in st.session_state:
            st.session_state.debug_mode = False

    def debug_log(self, message):
        """Debug logging function"""
        if st.session_state.debug_mode:
            st.sidebar.text(f"DEBUG: {message}")

    def get_data_paths(self):
        """Get data paths from user input or use defaults"""
        if not st.session_state.data_paths:
            st.sidebar.title("Data Configuration")
            st.sidebar.markdown("**Set data directories:**")
            
            # Debug mode toggle
            st.session_state.debug_mode = st.sidebar.checkbox("Debug Mode", value=st.session_state.debug_mode)

            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_market_path = os.path.join(script_dir, "data", "market_csvs")
            default_crops_path = os.path.join(script_dir, "data", "crops_csv")
            default_trend_path = os.path.join(script_dir, "data", "trend_calc")

            market_path = st.sidebar.text_input(
                "Market CSV Directory:",
                value=default_market_path,
                help="Directory with market CSV files"
            )

            crops_path = st.sidebar.text_input(
                "Crops CSV Directory:",
                value=default_crops_path,
                help="Directory with crop CSV files"
            )

            trend_path = st.sidebar.text_input(
                "Trend Calculation Directory:",
                value=default_trend_path,
                help="Directory for trend calculations (optional)"
            )

            if st.sidebar.button("Load Data"):
                st.session_state.data_paths = {
                    'market_csvs': market_path,
                    'crops_csv': crops_path,
                    'trend_calc': trend_path
                }
                st.session_state.data_loaded = False
                st.rerun()

            st.sidebar.markdown("---")
            st.sidebar.markdown("**Current Paths:**")
            if st.session_state.data_paths:
                for key, path in st.session_state.data_paths.items():
                    exists = "✅" if os.path.exists(path) else "❌"
                    st.sidebar.write(f"{exists} {key}: `{path}`")
            return False

        return True

    @st.cache_data
    def load_market_data(_self, market_path, crops_path, trend_path):
        """Load all market data from CSV files with error handling"""
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

            progress_bar = st.progress(0)
            for i, csv_file in enumerate(csv_files):
                progress_bar.progress((i + 1) / len(csv_files))
                file_path = os.path.join(market_path, csv_file)
                try:
                    df = pd.read_csv(file_path)
                    market_name = csv_file.replace('_market_data.csv', '').replace('_', ' ').title()

                    required_cols = ['Arrival_Date', 'Commodity', 'Min_Price', 'Max_Price', 'Modal_Price']
                    if all(col in df.columns for col in required_cols):
                        # Clean and validate data
                        df['Arrival_Date'] = pd.to_datetime(df['Arrival_Date'], errors='coerce')
                        
                        # Ensure numeric columns
                        for col in ['Min_Price', 'Max_Price', 'Modal_Price']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        
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
            
            progress_bar.empty()

        except Exception as e:
            st.error(f"Error accessing directory {market_path}: {str(e)}")

        return market_data, available_markets, market_crops

    # ----------------------------
    # Weighted Moving Average utils
    # ----------------------------
    def _fill_missing_with_wma(self, s: pd.Series, window: int = 5) -> pd.Series:
        """Fill NaNs using backward-looking weighted moving average"""
        try:
            arr = s.astype(float).values
            n = len(arr)
            result = arr.copy()
            base_w = np.arange(1, window + 1, dtype=float)

            def wma_at(idx: int):
                left = max(0, idx - window + 1)
                window_vals = arr[left:idx + 1]
                w = base_w[-len(window_vals):]
                mask = ~np.isnan(window_vals)
                if mask.sum() == 0:
                    return np.nan
                w_used = w[mask]
                v_used = window_vals[mask]
                return float(np.dot(w_used, v_used) / w_used.sum())

            for i in range(n):
                if np.isnan(result[i]):
                    result[i] = wma_at(i)

            return pd.Series(result, index=s.index)
        except Exception as e:
            self.debug_log(f"Error in WMA calculation: {e}")
            return s.fillna(s.mean())

    def compute_wma_series(self, s: pd.Series, window: int = 5) -> pd.Series:
        """Compute full WMA series"""
        try:
            if s.empty or s.isna().all():
                return s
            
            def rolling_wma(values):
                if len(values) == 0 or np.isnan(values).all():
                    return np.nan
                weights = np.arange(1, len(values) + 1)
                mask = ~np.isnan(values)
                if not mask.any():
                    return np.nan
                return np.average(values[mask], weights=weights[mask])
            
            return s.rolling(window=window, min_periods=1).apply(rolling_wma, raw=True)
        except Exception as e:
            self.debug_log(f"Error in WMA series: {e}")
            return s.rolling(window=window).mean()

    # ----------------------------
    # Weekly price table with WMA
    # ----------------------------
    def create_weekly_price_table(self, df, crop_name, price_type='Modal_Price', wma_window=5):
        """Create weekly price table with WMA imputation"""
        try:
            self.debug_log(f"Creating weekly table for {crop_name}, price_type: {price_type}")
            
            df_work = df.copy()
            df_work['Year'] = df_work['Arrival_Date'].dt.year
            df_work['Month'] = df_work['Arrival_Date'].dt.month
            df_work['Week_of_Year'] = df_work['Arrival_Date'].dt.isocalendar().week.astype(int)

            years = sorted(df_work['Year'].unique())
            self.debug_log(f"Processing years: {years}")

            weeks_per_month = {
                1: list(range(1, 6)), 2: list(range(5, 10)), 3: list(range(9, 14)),
                4: list(range(13, 18)), 5: list(range(17, 22)), 6: list(range(21, 27)),
                7: list(range(26, 31)), 8: list(range(30, 35)), 9: list(range(34, 40)),
                10: list(range(39, 44)), 11: list(range(43, 48)), 12: list(range(47, 53))
            }

            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

            columns = []
            for month_idx, month_name in enumerate(month_names, 1):
                month_weeks = weeks_per_month[month_idx]
                for week_idx in range(4):
                    columns.append(f"{month_name}_W{week_idx+1}")

            price_table = pd.DataFrame(index=pd.Index(years, name='Year'), columns=columns)

            # Fill from actual data
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

            price_table = price_table.astype(float)

            # WMA imputation
            for year in years:
                year_prices = price_table.loc[year].astype(float)
                wma_series = self._fill_missing_with_wma(year_prices, window=wma_window)
                filled = year_prices.copy()
                need_fill = filled.isna()
                filled[need_fill] = wma_series[need_fill]
                price_table.loc[year] = filled

            price_table = price_table.fillna(0).astype(int)
            price_table = price_table.sort_index()
            price_table.index = price_table.index.map(lambda y: str(int(y)))

            self.debug_log(f"Created table shape: {price_table.shape}")
            return price_table
            
        except Exception as e:
            st.error(f"Error creating weekly price table: {e}")
            self.debug_log(f"Table creation error: {e}")
            return pd.DataFrame()

    # ----------------------------
    # Color coding (merged low+medium)
    # ----------------------------
    def apply_color_coding_to_table(self, df):
        """Apply color coding with merged low+medium bands"""
        try:
            all_values = df.values.flatten()
            all_values = all_values[all_values > 0]

            if len(all_values) == 0:
                return df.style

            p25 = np.percentile(all_values, 25)
            p75 = np.percentile(all_values, 75)
            p90 = np.percentile(all_values, 90)

            def color_code_cell(val):
                if val == 0 or pd.isna(val):
                    return 'background-color: #f5f5f5; color: #999; font-size: 10px;'
                elif val <= p25:
                    return 'background-color: #ffcdd2; color: #b71c1c; font-weight: bold; font-size: 10px;'
                elif val <= p75:
                    return 'background-color: #fff9c4; color: #f57f17; font-weight: bold; font-size: 10px;'
                elif val <= p90:
                    return 'background-color: #c8e6c9; color: #2e7d32; font-weight: bold; font-size: 10px;'
                else:
                    return 'background-color: #4caf50; color: white; font-weight: bold; font-size: 10px;'

            styled_df = df.style.applymap(color_code_cell)
            styled_df = styled_df.format(lambda x: f'₹{int(x)}' if x > 0 else '-')
            return styled_df
        except Exception as e:
            st.error(f"Error applying color coding: {e}")
            return df.style

    # ----------------------------
    # Summary metrics
    # ----------------------------
    def create_summary_metrics(self, df):
        """Create summary metrics cards"""
        try:
            if df.empty:
                st.warning("No data available for metrics")
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
                price_volatility = df['Modal_Price'].std() / df['Modal_Price'].mean() * 100 if df['Modal_Price'].mean() > 0 else 0
                st.metric(
                    label="Price Volatility",
                    value=f"{price_volatility:.1f}%",
                    help="Coefficient of variation (std/mean)"
                )
        except Exception as e:
            st.error(f"Error creating metrics: {e}")

    # ----------------------------
    # Trend graphs and stock-style views
    # ----------------------------
    def add_range_selector(self, fig: go.Figure):
        """Add range selector buttons for stock-style navigation"""
        try:
            fig.update_layout(
                xaxis=dict(
                    rangeselector=dict(
                        buttons=list([
                            dict(count=1, label="1Y", step="year", stepmode="backward"),
                            dict(count=5, label="5Y", step="year", stepmode="backward"),
                            dict(count=1, label="YTD", step="year", stepmode="todate"),
                            dict(step="all", label="MAX")
                        ])
                    ),
                    rangeslider=dict(visible=True),
                    type="date"
                )
            )
            return fig
        except Exception as e:
            self.debug_log(f"Error adding range selector: {e}")
            return fig

    def make_line_trend(self, df, y_col, title):
        """Create line trend chart with duplicate column protection"""
        try:
            self.debug_log(f"Creating line trend for {y_col}")
            
            # Create clean dataframe with only needed columns
            df_clean = df.copy()
            
            # Remove duplicate columns
            df_clean = df_clean.loc[:, ~df_clean.columns.duplicated()]
            
            # Ensure required columns exist
            if 'Arrival_Date' not in df_clean.columns or y_col not in df_clean.columns:
                raise ValueError(f"Required columns missing: Arrival_Date or {y_col}")
            
            # Select only the two columns we need
            plot_df = df_clean[['Arrival_Date', y_col]].copy()
            
            # Ensure proper data types
            plot_df['Arrival_Date'] = pd.to_datetime(plot_df['Arrival_Date'], errors='coerce')
            plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors='coerce')
            
            # Remove invalid data
            plot_df = plot_df.dropna().sort_values('Arrival_Date')
            
            if plot_df.empty:
                st.warning("No valid data for line chart")
                return go.Figure()
            
            self.debug_log(f"Plot data shape: {plot_df.shape}")
            
            fig = px.line(plot_df, x='Arrival_Date', y=y_col, title=title)
            fig = self.add_range_selector(fig)
            return fig
            
        except Exception as e:
            st.error(f"Error creating line trend: {e}")
            self.debug_log(f"Line trend error: {e}")
            return go.Figure()

    def make_candles_from_prices(self, df, title):
        """Create candlestick chart from OHLC derived from price data"""
        try:
            self.debug_log("Creating candlestick chart")
            
            if df.empty:
                return go.Figure()
            
            work = df[['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']].copy()
            work['Arrival_Date'] = pd.to_datetime(work['Arrival_Date'])
            work = work.set_index('Arrival_Date').sort_index()

            # Create weekly OHLC
            o = work['Modal_Price'].resample('W').first()
            h = work['Max_Price'].resample('W').max()
            l = work['Min_Price'].resample('W').min()
            c = work['Modal_Price'].resample('W').last()
            
            ohlc = pd.DataFrame({'Open': o, 'High': h, 'Low': l, 'Close': c}).dropna()

            if ohlc.empty:
                st.warning("No data for candlestick chart")
                return go.Figure()

            fig = go.Figure(data=[go.Candlestick(
                x=ohlc.index,
                open=ohlc['Open'],
                high=ohlc['High'],
                low=ohlc['Low'],
                close=ohlc['Close']
            )])
            
            fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price")
            fig = self.add_range_selector(fig)
            return fig
            
        except Exception as e:
            st.error(f"Error creating candlestick: {e}")
            return go.Figure()

    # ----------------------------
    # Best months per year
    # ----------------------------
    def best_months_by_year(self, df, price_type='Modal_Price', top_k=1):
        """Identify best performing months per year"""
        try:
            work = df[['Arrival_Date', price_type]].copy()
            work['Year'] = work['Arrival_Date'].dt.year
            work['Month'] = work['Arrival_Date'].dt.month
            
            monthly = work.groupby(['Year', 'Month'])[price_type].mean().reset_index()
            monthly['Rank'] = monthly.groupby('Year')[price_type].rank(method='first', ascending=False)
            top = monthly[monthly['Rank'] <= top_k].copy()
            
            month_names = {i: m for i, m in enumerate(['Jan','Feb','Mar','Apr','May','Jun',
                                                     'Jul','Aug','Sep','Oct','Nov','Dec'], start=1)}
            top['MonthName'] = top['Month'].map(month_names)
            top = top.sort_values(['Year', 'Rank'])
            top['AvgPrice'] = top[price_type].round(0).astype(int)
            
            return top[['Year', 'MonthName', 'AvgPrice', 'Rank']]
        except Exception as e:
            st.error(f"Error identifying best months: {e}")
            return pd.DataFrame()

    # ----------------------------
    # Forecast with WMA + seasonality
    # ----------------------------
    def forecast_prices(self, df, price_col='Modal_Price', wma_window=8, horizon_weeks=12):
        """Simple forecast using WMA trend + seasonal adjustment"""
        try:
            work = df[['Arrival_Date', price_col]].sort_values('Arrival_Date').copy()
            work['WMA'] = self.compute_wma_series(work[price_col], window=wma_window)

            # Monthly seasonality
            work['Month'] = work['Arrival_Date'].dt.month
            overall = work[price_col].mean()
            season = work.groupby('Month')[price_col].mean() - overall
            season = season.reindex(range(1, 13), fill_value=0.0)

            last_date = work['Arrival_Date'].max()
            future_dates = pd.date_range(last_date + timedelta(days=7), periods=horizon_weeks, freq='W')
            
            last_wma = work['WMA'].dropna().iloc[-1] if not work['WMA'].dropna().empty else work[price_col].iloc[-1]
            
            future = []
            for d in future_dates:
                m = d.month
                fut = max(0.0, last_wma + float(season.get(m, 0.0)))
                future.append((d, fut))
                
            forecast_df = pd.DataFrame(future, columns=['Arrival_Date', 'Forecast'])
            return work, forecast_df
        except Exception as e:
            st.error(f"Error creating forecast: {e}")
            return df, pd.DataFrame()

    # ----------------------------
    # Crop Screener
    # ----------------------------
    def compute_returns(self, s: pd.Series, periods_back: int):
        """Compute percentage returns over given period"""
        try:
            if s.empty or len(s) < 2:
                return np.nan
            
            s_clean = s.dropna()
            if len(s_clean) < 2:
                return np.nan
                
            current_val = float(s_clean.iloc[-1])
            
            # Find value from periods_back days ago
            target_date = s_clean.index[-1] - pd.DateOffset(days=periods_back)
            past_idx = s_clean.index.get_indexer([target_date], method='nearest')[0]
            
            if past_idx >= 0 and past_idx < len(s_clean):
                past_val = float(s_clean.iloc[past_idx])
                if past_val > 0:
                    return (current_val / past_val - 1.0) * 100.0
            
            return np.nan
        except Exception as e:
            self.debug_log(f"Error computing returns: {e}")
            return np.nan

    def build_screener(self, market_data, per_km_cost=0.0, distances_df=None, price_col='Modal_Price'):
        """Build comprehensive crop screener with performance metrics"""
        try:
            rows = []
            for market, df in market_data.items():
                d = df[['Arrival_Date', 'Commodity', price_col]].copy().dropna()
                if d.empty:
                    continue
                    
                d['Arrival_Date'] = pd.to_datetime(d['Arrival_Date'])
                
                for crop, g in d.groupby('Commodity'):
                    g = g.sort_values('Arrival_Date').set_index('Arrival_Date')
                    ser = g[price_col]
                    
                    if len(ser) < 10:  # Need minimum data points
                        continue
                    
                    # Performance metrics
                    r1y = self.compute_returns(ser, 365)
                    r5y = self.compute_returns(ser, 365*5)
                    
                    # Volatility (annualized)
                    vol = np.nan
                    if len(ser) > 2:
                        returns = ser.pct_change().dropna()
                        if len(returns) > 1:
                            vol = returns.std() * np.sqrt(252) * 100
                    
                    # 90-day momentum
                    mom = self.compute_returns(ser, 90)
                    
                    latest = float(ser.iloc[-1])

                    # Distance-adjusted net price
                    net_price = latest
                    if distances_df is not None and not distances_df.empty:
                        market_dist = distances_df[distances_df['Market'] == market]
                        if not market_dist.empty:
                            dist = market_dist.iloc[0].get('Distance_km', np.nan)
                            if pd.notna(dist) and dist > 0:
                                net_price = max(0, latest - per_km_cost * float(dist))

                    rows.append({
                        'Market': market,
                        'Crop': crop,
                        'LatestPrice': round(latest, 0),
                        'NetPrice': round(net_price, 0),
                        'Return_1Y_%': round(r1y, 1) if pd.notna(r1y) else np.nan,
                        'Return_5Y_%': round(r5y, 1) if pd.notna(r5y) else np.nan,
                        'Volatility_%': round(vol, 1) if pd.notna(vol) else np.nan,
                        'Momentum_90d_%': round(mom, 1) if pd.notna(mom) else np.nan,
                        'DataPoints': len(ser)
                    })
            
            if not rows:
                return pd.DataFrame()
            
            out = pd.DataFrame(rows)
            # Sort by net price descending, then by 1Y return descending
            return out.sort_values(['NetPrice', 'Return_1Y_%'], ascending=[False, False], na_position='last')
            
        except Exception as e:
            st.error(f"Error building screener: {e}")
            return pd.DataFrame()

    # ----------------------------
    # Main Dashboard Page
    # ----------------------------
    def page_market_dashboard(self):
        """Main market analysis dashboard"""
        st.markdown('<h1 class="main-header">Agricultural Weekly Price Dashboard</h1>', unsafe_allow_html=True)

        if not self.get_data_paths():
            st.info("Please configure your data directories in the sidebar to get started.")
            return

        # Load data with progress indication
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

        st.sidebar.markdown("---")
        st.sidebar.title("Dashboard Controls")

        # Main controls
        selected_market = st.sidebar.selectbox(
            "Select Market:",
            options=st.session_state.available_markets,
            index=0,
            help="Choose a market to view crop prices"
        )

        wma_window = st.sidebar.slider("WMA Window (weeks)", min_value=3, max_value=15, value=5, step=1)
        price_type = st.sidebar.selectbox(
            "Price Type:",
            options=['Modal_Price', 'Min_Price', 'Max_Price'],
            index=0,
            format_func=lambda x: x.replace('_', ' ').title(),
        )

        chart_style = st.sidebar.radio("Chart Style", options=["Line", "Candlestick"], index=0)
        forecast_weeks = st.sidebar.slider("Forecast Horizon (weeks)", 4, 26, 12, 1)
        input_cost = st.sidebar.number_input("Input Cost per Quintal (₹)", min_value=0.0, value=0.0, step=50.0)

        if selected_market and selected_market in st.session_state.market_crops:
            available_crops = st.session_state.market_crops[selected_market]
            selected_crop = st.sidebar.selectbox(
                "Select Crop:",
                options=available_crops,
                index=0,
                help="Choose a crop to view price trends"
            )

            market_df = st.session_state.market_data[selected_market]
            crop_df = market_df[market_df['Commodity'] == selected_crop].copy()

            if crop_df.empty:
                st.warning(f"No data available for {selected_crop} in {selected_market}")
                return

            crop_df = crop_df.sort_values('Arrival_Date')
            self.debug_log(f"Crop data shape: {crop_df.shape}")

            # Summary metrics
            st.subheader("📊 Current Market Summary")
            self.create_summary_metrics(crop_df)
            st.markdown("---")

            # Weekly price table
            st.subheader(f"📅 {selected_crop} Weekly Price Table - {selected_market} Market")
            st.markdown("*(all prices per quintal)*")
            
            with st.spinner("Generating weekly price table..."):
                price_table = self.create_weekly_price_table(
                    crop_df, selected_crop, price_type, wma_window=wma_window
                )
                
                if not price_table.empty:
                    styled_table = self.apply_color_coding_to_table(price_table)
                    st.dataframe(styled_table, use_container_width=True, height=400)

                    # Legend
                    st.markdown("**Color Legend:**")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.markdown("🔴 **Very Low** (≤25%)")
                    with col2:
                        st.markdown("🟡 **Mid Range** (25-75%)")
                    with col3:
                        st.markdown("🟢 **High** (75-90%)")
                    with col4:
                        st.markdown("🟢 **Very High** (>90%)")

            st.markdown("---")

            # Price trend charts
            st.subheader("📈 Price Trends")
            
            # Create separate dataframes for different chart types
            if chart_style == "Line":
                # Clean dataframe for line chart - avoid duplicates
                line_df = crop_df[['Arrival_Date', price_type]].copy()
                line_df = line_df.rename(columns={price_type: 'Price'})
                
                fig_line = self.make_line_trend(
                    line_df,
                    y_col='Price',
                    title=f"{selected_crop} - {price_type.replace('_', ' ').title()} Trend"
                )
                st.plotly_chart(fig_line, use_container_width=True)
                
            else:
                # Candlestick chart - needs OHLC data
                candle_df = crop_df[['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']].copy()
                fig_candles = self.make_candles_from_prices(
                    candle_df,
                    title=f"{selected_crop} - Weekly Candlestick Chart"
                )
                st.plotly_chart(fig_candles, use_container_width=True)

            st.markdown("---")

            # Forecast section
            st.subheader("🔮 Price Forecast & Analysis")
            
            forecast_df = crop_df[['Arrival_Date', price_type]].copy()
            forecast_df = forecast_df.rename(columns={price_type: 'Price'})
            
            hist, forecast = self.forecast_prices(
                forecast_df,
                price_col='Price',
                wma_window=max(4, wma_window),
                horizon_weeks=forecast_weeks
            )

            if not hist.empty and not forecast.empty:
                fig_fore = go.Figure()
                
                # Historical prices
                fig_fore.add_trace(go.Scatter(
                    x=hist['Arrival_Date'], 
                    y=hist['Price'], 
                    mode='lines', 
                    name='Historical Price',
                    line=dict(color='blue')
                ))
                
                # WMA trend
                fig_fore.add_trace(go.Scatter(
                    x=hist['Arrival_Date'], 
                    y=hist['WMA'], 
                    mode='lines', 
                    name='WMA Trend',
                    line=dict(dash='dash', color='green')
                ))
                
                # Forecast
                fig_fore.add_trace(go.Scatter(
                    x=forecast['Arrival_Date'], 
                    y=forecast['Forecast'], 
                    mode='lines', 
                    name='Forecast',
                    line=dict(color='orange', dash='dot', width=3)
                ))

                # Input cost baseline
                if input_cost and input_cost > 0:
                    fig_fore.add_hline(
                        y=input_cost, 
                        line=dict(color='red', dash='dash'), 
                        annotation_text=f"Input Cost: ₹{input_cost:.0f}"
                    )

                fig_fore.update_layout(
                    title="Historical Prices, WMA Trend, and Forecast",
                    xaxis_title="Date",
                    yaxis_title="Price (₹/Quintal)",
                    hovermode='x unified'
                )
                fig_fore = self.add_range_selector(fig_fore)
                st.plotly_chart(fig_fore, use_container_width=True)

            st.markdown("---")

            # Best months analysis
            st.subheader("🏆 Best Performing Months by Year")
            
            best_months_df = crop_df[['Arrival_Date', price_type]].copy()
            best_months_df = best_months_df.rename(columns={price_type: 'Price'})
            
            best_months = self.best_months_by_year(
                best_months_df, 
                price_type='Price', 
                top_k=2
            )
            
            if not best_months.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.dataframe(best_months, use_container_width=True, height=300)
                with col2:
                    # Monthly performance summary
                    month_summary = best_months.groupby('MonthName').agg({
                        'AvgPrice': 'mean',
                        'Year': 'count'
                    }).rename(columns={'Year': 'Times_Best'}).round(0)
                    month_summary = month_summary.sort_values('AvgPrice', ascending=False)
                    st.markdown("**Monthly Performance Summary:**")
                    st.dataframe(month_summary, use_container_width=True)

    # ----------------------------
    # Crop Screener Page
    # ----------------------------
    def page_crop_screener(self):
        """Advanced crop screening and market selection"""
        st.markdown('<h1 class="main-header">🔍 Crop Screener & Market Selector</h1>', unsafe_allow_html=True)

        if not self.get_data_paths():
            st.info("Please configure your data directories in the sidebar to get started.")
            return

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

        st.sidebar.markdown("---")
        st.sidebar.title("Screener Controls")

        # Screener parameters
        per_km_cost = st.sidebar.number_input(
            "Transport Cost (₹/km)", 
            min_value=0.0, 
            value=2.0, 
            step=0.5,
            help="Cost per km for transporting produce"
        )
        
        price_col = st.sidebar.selectbox(
            "Price Type for Analysis", 
            options=['Modal_Price', 'Min_Price', 'Max_Price'], 
            index=0,
            format_func=lambda x: x.replace('_', ' ').title()
        )

        # Distance configuration
        st.subheader("🚛 Market Distance Configuration")
        st.markdown("Configure distances from your location to different markets for transport cost calculation:")
        
        if st.session_state.screener_distances.empty:
            st.session_state.screener_distances = pd.DataFrame({
                'Market': st.session_state.available_markets,
                'Distance_km': [np.nan] * len(st.session_state.available_markets)
            })

        # Distance editor
        edited_distances = st.data_editor(
            st.session_state.screener_distances,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Market": st.column_config.TextColumn("Market Name", disabled=True),
                "Distance_km": st.column_config.NumberColumn(
                    "Distance (km)",
                    help="Distance from your location to this market",
                    min_value=0.0,
                    max_value=1000.0,
                    step=5.0
                )
            },
            key="dist_editor"
        )
        
        st.session_state.screener_distances = edited_distances

        # Build screener
        with st.spinner("Analyzing crop performance across markets..."):
            screener_df = self.build_screener(
                st.session_state.market_data,
                per_km_cost=per_km_cost,
                distances_df=st.session_state.screener_distances,
                price_col=price_col
            )

        st.markdown("---")
        st.subheader("📊 Crop Performance Screener")

        if screener_df.empty:
            st.info("No screener results available. Check your data and try again.")
            return

        # Filters
        st.markdown("**Filter Options:**")
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            crop_filter = st.multiselect(
                "Filter by Crops", 
                options=sorted(screener_df['Crop'].unique()), 
                default=[],
                help="Select specific crops to analyze"
            )
            
        with filter_col2:
            market_filter = st.multiselect(
                "Filter by Markets", 
                options=sorted(screener_df['Market'].unique()), 
                default=[],
                help="Select specific markets to compare"
            )
            
        with filter_col3:
            sort_by = st.selectbox(
                "Sort by", 
                options=['NetPrice', 'Return_1Y_%', 'Return_5Y_%', 'Momentum_90d_%', 'Volatility_%'], 
                index=0,
                help="Choose primary sorting criterion"
            )

        # Apply filters
        df_view = screener_df.copy()
        if crop_filter:
            df_view = df_view[df_view['Crop'].isin(crop_filter)]
        if market_filter:
            df_view = df_view[df_view['Market'].isin(market_filter)]
        
        # Sort results
        ascending = (sort_by == 'Volatility_%')  # Lower volatility is better
        df_view = df_view.sort_values(sort_by, ascending=ascending, na_position='last')

        # Display results
        if not df_view.empty:
            st.dataframe(
                df_view.reset_index(drop=True), 
                use_container_width=True, 
                height=500,
                column_config={
                    "LatestPrice": st.column_config.NumberColumn("Latest Price (₹)", format="₹%.0f"),
                    "NetPrice": st.column_config.NumberColumn("Net Price (₹)", format="₹%.0f"),
                    "Return_1Y_%": st.column_config.NumberColumn("1Y Return (%)", format="%.1f%%"),
                    "Return_5Y_%": st.column_config.NumberColumn("5Y Return (%)", format="%.1f%%"),
                    "Volatility_%": st.column_config.NumberColumn("Volatility (%)", format="%.1f%%"),
                    "Momentum_90d_%": st.column_config.NumberColumn("90d Momentum (%)", format="%.1f%%")
                }
            )

            st.markdown("---")
            
            # Top recommendations
            st.subheader("🎯 Top Recommendations")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**🏆 Best Overall Performance:**")
                top_row = df_view.iloc[0]
                st.success(f"""
                **Crop:** {top_row['Crop']}  
                **Market:** {top_row['Market']}  
                **Net Price:** ₹{top_row['NetPrice']:.0f}/quintal  
                **1Y Return:** {top_row['Return_1Y_%']:.1f}%  
                **Volatility:** {top_row['Volatility_%']:.1f}%
                """)
            
            with col2:
                # Best by different criteria
                st.markdown("**📈 Category Leaders:**")
                
                best_return_1y = df_view.loc[df_view['Return_1Y_%'].idxmax()] if not df_view['Return_1Y_%'].isna().all() else None
                best_price = df_view.loc[df_view['NetPrice'].idxmax()] if not df_view['NetPrice'].isna().all() else None
                lowest_vol = df_view.loc[df_view['Volatility_%'].idxmin()] if not df_view['Volatility_%'].isna().all() else None
                
                if best_return_1y is not None:
                    st.info(f"**Best 1Y Return:** {best_return_1y['Crop']} at {best_return_1y['Market']} ({best_return_1y['Return_1Y_%']:.1f}%)")
                if best_price is not None:
                    st.info(f"**Highest Net Price:** {best_price['Crop']} at {best_price['Market']} (₹{best_price['NetPrice']:.0f})")
                if lowest_vol is not None:
                    st.info(f"**Most Stable:** {lowest_vol['Crop']} at {lowest_vol['Market']} ({lowest_vol['Volatility_%']:.1f}% vol)")

            # Summary statistics
            st.markdown("---")
            st.subheader("📊 Market Summary")
            
            summary_col1, summary_col2, summary_col3 = st.columns(3)
            
            with summary_col1:
                avg_net_price = df_view['NetPrice'].mean()
                st.metric("Average Net Price", f"₹{avg_net_price:.0f}")
                
            with summary_col2:
                avg_return = df_view['Return_1Y_%'].mean() if not df_view['Return_1Y_%'].isna().all() else 0
                st.metric("Average 1Y Return", f"{avg_return:.1f}%")
                
            with summary_col3:
                total_opportunities = len(df_view)
                st.metric("Total Opportunities", total_opportunities)

        else:
            st.info("No results match your current filters. Try adjusting the filter criteria.")

    # ----------------------------
    # Main application router
    # ----------------------------
    def run(self):
        """Main application entry point"""
        try:
            # Navigation
            page = st.sidebar.radio(
                "🧭 Navigate", 
                options=["Market Dashboard", "Crop Screener"], 
                index=0
            )
            
            # Route to appropriate page
            if page == "Market Dashboard":
                self.page_market_dashboard()
            elif page == "Crop Screener":
                self.page_crop_screener()
                
        except Exception as e:
            st.error(f"Application error: {e}")
            if st.session_state.debug_mode:
                st.exception(e)


def main():
    """Application entry point"""
    try:
        dashboard = AgriDashboard()
        dashboard.run()
    except Exception as e:
        st.error(f"Fatal error: {e}")
        st.info("Please refresh the page and try again.")


if __name__ == "__main__":
    main()
