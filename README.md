# 🌾 Agricultural Data Processing Toolkit

A comprehensive suite of tools for processing, analyzing, and visualizing agricultural commodity price data across markets and crops.

## 📋 Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Tools Overview](#tools-overview)
- [Directory Structure](#directory-structure)
- [Usage Examples](#usage-examples)
- [Data Requirements](#data-requirements)
- [Contributing](#contributing)
- [License](#license)

## ✨ Features

### 🎛️ Interactive Dashboard
- **Real-time price visualization** with color-coded weekly tables
- **Market and crop selection** via dropdown menus
- **Intelligent data extrapolation** for missing weekly price points
- **Price trend analysis** with summary metrics

### 📊 Data Processing Tools
- **Market CSV Splitter**: Split master CSV files by market
- **Crop Excel Generator**: Create Excel files with crop-specific sheets
- **Price Chart Generator**: Generate professional price trend charts
- **Price Analyzer**: Identify top 25 consistently high-priced crops

### 🔧 Advanced Features
- **Cross-platform compatibility** (Windows, macOS, Linux)
- **Configurable file paths** with sensible defaults
- **Comprehensive error handling** and logging
- **Command-line and interactive modes**
- **Professional chart output** (300 DPI PNG images)

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Install Dependencies

# Clone the repository
git clone <your-repository-url>
cd agricultural-data-toolkit

# Install required packages
pip install -r requirements.txt

# Test the dashboard
streamlit --version

# Test other components
python -c "import pandas, plotly, matplotlib; print('All packages installed successfully!')"

## Quick Start

# 1. Set Up Data Structure
agricultural-data-toolkit/
├── data/
│   ├── raw_data.csv              # Your master CSV file
│   ├── market_csvs/              # Split market files
│   └── crop_excel_files/         # Excel files with crop sheets
├── output/
│   ├── market_csvs/              # Generated market files
│   ├── crop_excel_files/         # Generated Excel files
│   ├── price_charts/             # Generated charts
│   └── analysis/                 # Analysis reports
└── scripts/                      # All Python tools

# 2. Run the Interactive Dashboard
streamlit run agridashboard.py

