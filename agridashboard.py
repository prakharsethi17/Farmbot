import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Safe SciPy import (not required for WMA, but kept for environment validation)
try:
    from scipy import interpolate  # not used after WMA-only change
    SCIPY_AVAILABLE = True
except ImportError as e:
    SCIPY_AVAILABLE = False
    st.error(f"SciPy import failed: {e}")
    st.stop()

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
            st.session_state.market_meta = None  # optional market metadata (lat/lon)
        if 'screener_distances' not in st.session_state:
            st.session_state.screener_distances = pd.DataFrame()

    def get_data_paths(self):
        """Get data paths from user input or use defaults"""
        if not st.session_state.data_paths:
            st.sidebar.title("Data Configuration")
            st.sidebar.markdown("Set data directories:")

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
            st.sidebar.markdown("Current Paths:")
            if st.session_state.data_paths:
                for key, path in st.session_state.data_paths.items():
                    exists = "✅" if os.path.exists(path) else "❌"
                    st.sidebar.write(f"{exists} {key}: `{path}`")
            return False

        return True

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

    # ----------------------------
    # Weighted Moving Average utils
    # ----------------------------
    def _fill_missing_with_wma(self, s: pd.Series, window: int = 5) -> pd.Series:
        """
        Fill NaNs using a backward-looking weighted moving average (WMA).
        - Linear weights 1..window (highest weight to most recent point).
        - Ignores NaNs inside window, renormalizes weights to available values.
        - Only fills NaNs; observed values are preserved.
        """
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

    def compute_wma_series(self, s: pd.Series, window: int = 5) -> pd.Series:
        """
        Compute a full WMA (no filling logic), returning WMA for each point where at least one value exists in window.
        """
        arr = s.astype(float).values
        base_w = np.arange(1, window + 1, dtype=float)

        def wma_window(x):
            w = base_w[-len(x):]
            mask = ~np.isnan(x)
            if mask.sum() == 0:
                return np.nan
            return float(np.dot(w[mask], x[mask]) / w[mask].sum())

        return pd.Series(arr).rolling(window=window, min_periods=1).apply(
            lambda x: wma_window(x.values), raw=False
        ).set_axis(s.index)

    # ----------------------------
    # Weekly price table with WMA
    # ----------------------------
    def create_weekly_price_table(self, df, crop_name, price_type='Modal_Price', wma_window=5):
        """Create a weekly price table and fill missing with WMA only"""
        df_work = df.copy()
        df_work['Year'] = df_work['Arrival_Date'].dt.year
        df_work['Month'] = df_work['Arrival_Date'].dt.month
        df_work['Week_of_Year'] = df_work['Arrival_Date'].dt.isocalendar().week.astype(int)

        years = sorted(df_work['Year'].unique())

        weeks_per_month = {
            1: list(range(1, 6)),
            2: list(range(5, 10)),
            3: list(range(9, 14)),
            4: list(range(13, 18)),
            5: list(range(17, 22)),
            6: list(range(21, 27)),
            7: list(range(26, 31)),
            8: list(range(30, 35)),
            9: list(range(34, 40)),
            10: list(range(39, 44)),
            11: list(range(43, 48)),
            12: list(range(47, 53))
        }

        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        columns = []
        for month_idx, month_name in enumerate(month_names, 1):
            month_weeks = weeks_per_month[month_idx]
            for week_idx, _ in enumerate(month_weeks[:4]):
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

        # WMA-only imputation
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

        return price_table

    # ----------------------------
    # Color coding (merged low+medium)
    # ----------------------------
    def apply_color_coding_to_table(self, df):
        """
        Apply color coding with merged low+medium into a single 'Mid' band.
        Bands: Very Low (<=25%), Mid (25-75%), High (75-90%), Very High (>90%)
        """
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

    # ----------------------------
    # Summary metrics
    # ----------------------------
    def create_summary_metrics(self, df):
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
            price_volatility = df['Modal_Price'].std() / df['Modal_Price'].mean() * 100 if df['Modal_Price'].mean() else 0
            st.metric(
                label="Price Volatility",
                value=f"{price_volatility:.1f}%",
                help="Coefficient of variation (std/mean)"
            )

    # ----------------------------
    # Trend graphs and stock-style views
    # ----------------------------
    def add_range_selector(self, fig: go.Figure):
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

    def make_line_trend(self, df, y_col, title):
        fig = px.line(df, x='Arrival_Date', y=y_col, title=title)
        fig = self.add_range_selector(fig)
        return fig

    def make_candles_from_prices(self, df, title):
        """
        Create weekly OHLC candlesticks using:
        open=first Modal, high=max Max, low=min Min, close=last Modal.
        """
        work = df[['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']].copy()
        work = work.set_index('Arrival_Date').sort_index()

        o = work['Modal_Price'].resample('W').first()
        h = work['Max_Price'].resample('W').max()
        l = work['Min_Price'].resample('W').min()
        c = work['Modal_Price'].resample('W').last()
        ohlc = pd.DataFrame({'Open': o, 'High': h, 'Low': l, 'Close': c}).dropna(how='all')

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

    # ----------------------------
    # Best months per year
    # ----------------------------
    def best_months_by_year(self, df, price_type='Modal_Price', top_k=1):
        work = df[['Arrival_Date', price_type]].copy()
        work['Year'] = work['Arrival_Date'].dt.year
        work['Month'] = work['Arrival_Date'].dt.month
        monthly = work.groupby(['Year', 'Month'])[price_type].mean().reset_index()
        # For each year, get top_k months by average price
        monthly['Rank'] = monthly.groupby('Year')[price_type].rank(method='first', ascending=False)
        top = monthly[monthly['Rank'] <= top_k].copy()
        month_names = {i: m for i, m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], start=1)}
        top['MonthName'] = top['Month'].map(month_names)
        top = top.sort_values(['Year', 'Rank'])
        top['AvgPrice'] = top[price_type].round(0).astype(int)
        return top[['Year', 'MonthName', 'AvgPrice']]

    # ----------------------------
    # Simple forecast using WMA + seasonality
    # ----------------------------
    def forecast_prices(self, df, price_col='Modal_Price', wma_window=8, horizon_weeks=12):
        """
        Forecast next N weeks using:
        - Recent WMA as trend level
        - Add seasonal monthly adjustment (avg by month - overall avg)
        """
        work = df[['Arrival_Date', price_col]].sort_values('Arrival_Date').copy()
        work['WMA'] = self.compute_wma_series(work[price_col], window=wma_window)

        # Monthly seasonality (additive)
        work['Month'] = work['Arrival_Date'].dt.month
        overall = work[price_col].mean()
        season = work.groupby('Month')[price_col].mean() - overall
        season = season.reindex(range(1, 13), fill_value=0.0)

        last_date = work['Arrival_Date'].max()
        future_dates = pd.date_range(last_date + timedelta(days=7), periods=horizon_weeks, freq='W')
        last_wma = work['WMA'].iloc[-1] if not work['WMA'].dropna().empty else work[price_col].iloc[-1]
        future = []
        for d in future_dates:
            m = d.month
            fut = max(0.0, last_wma + float(season.get(m, 0.0)))
            future.append((d, fut))
        forecast_df = pd.DataFrame(future, columns=['Arrival_Date', 'Forecast'])
        return work, forecast_df

    # ----------------------------
    # Crop Screener
    # ----------------------------
    def compute_returns(self, s: pd.Series, periods_back: int):
        if s.empty:
            return np.nan
        current_date = s.index.max()
        past_date = current_date - pd.DateOffset(days=periods_back)
        past_val = s.loc[s.index.get_indexer([past_date], method='nearest')]
        if len(past_val) == 0:
            return np.nan
        past_val = float(past_val.values[0])
        curr_val = float(s.iloc[-1])
        if past_val == 0:
            return np.nan
        return (curr_val / past_val - 1.0) * 100.0

    def build_screener(self, market_data, per_km_cost=0.0, distances_df=None, price_col='Modal_Price'):
        """
        Aggregate metrics by Crop and Market:
        - 1Y return, 5Y return, Volatility, Momentum (90d)
        - Net price adjustment = latest price - per_km_cost * distance (if provided)
        """
        rows = []
        for market, df in market_data.items():
            d = df[['Arrival_Date', 'Commodity', price_col]].copy().dropna()
            if d.empty:
                continue
            d['Arrival_Date'] = pd.to_datetime(d['Arrival_Date'])
            for crop, g in d.groupby('Commodity'):
                g = g.sort_values('Arrival_Date').set_index('Arrival_Date')
                ser = g[price_col].asfreq('D').interpolate()  # smooth for return calc
                r1y = self.compute_returns(ser, 365)
                r5y = self.compute_returns(ser, 365*5)
                vol = g[price_col].pct_change().std() * np.sqrt(252) * 100 if len(g) > 2 else np.nan
                mom = (ser.iloc[-1] / ser.iloc[-90] - 1) * 100 if len(ser) > 90 else np.nan
                latest = float(g[price_col].iloc[-1])

                # distance-based net price
                net_price = latest
                if distances_df is not None and not distances_df.empty and market in distances_df['Market'].values:
                    dist_row = distances_df[distances_df['Market'] == market].iloc[0]
                    if pd.notna(dist_row.get('Distance_km', np.nan)):
                        net_price = latest - per_km_cost * float(dist_row['Distance_km'])

                rows.append({
                    'Market': market,
                    'Crop': crop,
                    'LatestPrice': latest,
                    'NetPrice': net_price,
                    'Return_1Y_%': r1y,
                    'Return_5Y_%': r5y,
                    'Volatility_%': vol,
                    'Momentum_90d_%': mom
                })
        if not rows:
            return pd.DataFrame()
        out = pd.DataFrame(rows)
        return out.sort_values(['NetPrice', 'Return_1Y_%'], ascending=[False, False])

    # ----------------------------
    # Pages
    # ----------------------------
    def page_market_dashboard(self):
        st.markdown('<h1 class="main-header">Agricultural Weekly Price Dashboard</h1>', unsafe_allow_html=True)

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
        st.sidebar.title("Dashboard Controls")

        selected_market = st.sidebar.selectbox(
            "Select Market:",
            options=st.session_state.available_markets,
            index=0,
            help="Choose a market to view crop prices"
        )

        wma_window = st.sidebar.slider("WMA Window (weeks)", min_value=3, max_value=12, value=5, step=1)
        price_type = st.sidebar.selectbox(
            "Price Type:",
            options=['Modal_Price', 'Min_Price', 'Max_Price'],
            index=0,
            format_func=lambda x: x.replace('_', ' ').title(),
        )

        chart_style = st.sidebar.radio("Chart Style", options=["Line", "Candlestick"], index=0)
        forecast_weeks = st.sidebar.slider("Forecast Horizon (weeks)", 4, 26, 12, 1)
        input_cost = st.sidebar.number_input("Input Cost per Quintal (₹)", min_value=0.0, value=0.0, step=10.0)

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
                st.warning("No data for the selected crop/market.")
                return

            crop_df = crop_df.sort_values('Arrival_Date')

            # Summary
            st.subheader("Current Market Summary")
            self.create_summary_metrics(crop_df)
            st.markdown("---")

            # Weekly table
            st.subheader(f"{selected_crop} Weekly Price Table - {selected_market} Market")
            st.markdown("*(all prices per quintal)*")
            with st.spinner("Generating weekly price table..."):
                price_table = self.create_weekly_price_table(crop_df, selected_crop, price_type, wma_window=wma_window)
                if not price_table.empty:
                    styled_table = self.apply_color_coding_to_table(price_table)
                    st.dataframe(styled_table, use_container_width=True, height=500)

                    st.markdown("Legend:")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.markdown("Very Low (≤25%)")
                    with col2:
                        st.markdown("Mid (25–75%)")
                    with col3:
                        st.markdown("High (75–90%)")
                    with col4:
                        st.markdown("Very High (>90%)")

            st.markdown("---")

            # Trend graphs
            st.subheader("Price Trends")
            trend_df = crop_df[['Arrival_Date', price_type, 'Min_Price', 'Max_Price', 'Modal_Price']].copy()

            if chart_style == "Line":
                fig_line = self.make_line_trend(
                    trend_df.rename(columns={price_type: 'Price'}),
                    y_col='Price',
                    title=f"{selected_crop} - {price_type.replace('_', ' ').title()} Trend"
                )
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                fig_candles = self.make_candles_from_prices(
                    trend_df,
                    title=f"{selected_crop} - Weekly Candlestick (derived)"
                )
                st.plotly_chart(fig_candles, use_container_width=True)

            # Forecast and profit overlay
            st.subheader("Forecast and Profit")
            hist, forecast = self.forecast_prices(crop_df[['Arrival_Date', price_type]].rename(columns={price_type: 'Price'}),
                                                 price_col='Price', wma_window=max(4, wma_window), horizon_weeks=forecast_weeks)

            fig_fore = go.Figure()
            fig_fore.add_trace(go.Scatter(
                x=hist['Arrival_Date'], y=hist['Price'], mode='lines', name='Price'
            ))
            fig_fore.add_trace(go.Scatter(
                x=hist['Arrival_Date'], y=hist['WMA'], mode='lines', name='WMA', line=dict(dash='dash')
            ))
            fig_fore.add_trace(go.Scatter(
                x=forecast['Arrival_Date'], y=forecast['Forecast'], mode='lines', name='Forecast', line=dict(color='orange', dash='dot')
            ))

            # Profit baseline from input cost
            if input_cost and input_cost > 0:
                fig_fore.add_hline(y=input_cost, line=dict(color='red', dash='dash'), annotation_text="Input Cost")

            fig_fore.update_layout(
                title="Historical, WMA, and Forecast",
                xaxis_title="Date",
                yaxis_title="Price"
            )
            fig_fore = self.add_range_selector(fig_fore)
            st.plotly_chart(fig_fore, use_container_width=True)

            # Best months by year
            st.subheader("Best Months by Year")
            best_months = self.best_months_by_year(crop_df[['Arrival_Date', price_type]].rename(columns={price_type: 'Price'}),
                                                   price_type='Price', top_k=1)
            st.dataframe(best_months, use_container_width=True)

    def page_crop_screener(self):
        st.markdown('<h1 class="main-header">Crop Screener and Market Selector</h1>', unsafe_allow_html=True)

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

        per_km_cost = st.sidebar.number_input("Transport Cost (₹/km)", min_value=0.0, value=0.0, step=1.0)
        price_col = st.sidebar.selectbox("Screener Price Type", options=['Modal_Price', 'Min_Price', 'Max_Price'], index=0)

        # Distance editor
        st.subheader("Market Distances (optional)")
        if st.session_state.screener_distances.empty:
            st.session_state.screener_distances = pd.DataFrame({
                'Market': st.session_state.available_markets,
                'Distance_km': np.nan
            })
        st.session_state.screener_distances = st.data_editor(
            st.session_state.screener_distances,
            use_container_width=True,
            num_rows="dynamic",
            key="dist_editor"
        )

        screener_df = self.build_screener(
            st.session_state.market_data,
            per_km_cost=per_km_cost,
            distances_df=st.session_state.screener_distances,
            price_col=price_col
        )

        st.subheader("Screener Results")
        if screener_df.empty:
            st.info("No screener results available.")
            return

        # Filters
        cols = st.columns(3)
        with cols[0]:
            crop_filter = st.multiselect("Filter Crops", options=sorted(screener_df['Crop'].unique()), default=[])
        with cols[1]:
            market_filter = st.multiselect("Filter Markets", options=sorted(screener_df['Market'].unique()), default=[])
        with cols[2]:
            sort_by = st.selectbox("Sort By", options=['NetPrice', 'Return_1Y_%', 'Return_5Y_%', 'Momentum_90d_%', 'Volatility_%'], index=0)

        df_view = screener_df.copy()
        if crop_filter:
            df_view = df_view[df_view['Crop'].isin(crop_filter)]
        if market_filter:
            df_view = df_view[df_view['Market'].isin(market_filter)]
        df_view = df_view.sort_values(sort_by, ascending=(sort_by == 'Volatility_%'))

        st.dataframe(df_view.reset_index(drop=True), use_container_width=True, height=500)

        # Best performing crop and suggested market
        st.subheader("Top Picks")
        if not df_view.empty:
            top_row = df_view.iloc[0]
            st.markdown(f"- Best Crop: {top_row['Crop']} at {top_row['Market']} (NetPrice ₹{top_row['NetPrice']:.0f})")
            st.markdown(f"- Returns: 1Y {top_row['Return_1Y_%']:.1f}% | 5Y {np.nan_to_num(top_row['Return_5Y_%'], nan=0.0):.1f}% | Vol {np.nan_to_num(top_row['Volatility_%'], nan=0.0):.1f}% | Mom90d {np.nan_to_num(top_row['Momentum_90d_%'], nan=0.0):.1f}%")

    # ----------------------------
    # Main router
    # ----------------------------
    def run(self):
        page = st.sidebar.radio("Navigate", options=["Market Dashboard", "Crop Screener"], index=0)
        if page == "Market Dashboard":
            self.page_market_dashboard()
        else:
            self.page_crop_screener()


def main():
    dashboard = AgriDashboard()
    dashboard.run()


if __name__ == "__main__":
    main()
