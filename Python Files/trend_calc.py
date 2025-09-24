import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def create_price_charts_from_excel_files(input_directory, output_directory):
    """
    Process all Excel files in input directory and create price trend charts
    for each crop sheet, saving them to the output directory.
    
    Parameters:
    input_directory (str): Directory containing Excel files with crop sheets
    output_directory (str): Directory to save chart images
    """
    
    # Strip quotes if present
    input_directory = input_directory.strip('"\'')
    output_directory = output_directory.strip('"\'')
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"Created output directory: {output_directory}")
    
    # Find all Excel files in input directory
    excel_files = [f for f in os.listdir(input_directory) if f.endswith('.xlsx')]
    
    if not excel_files:
        print("No Excel files found in the input directory.")
        return
    
    print(f"Found {len(excel_files)} Excel files to process.")
    
    total_charts = 0
    
    for excel_file in excel_files:
        excel_path = os.path.join(input_directory, excel_file)
        print(f"\nProcessing: {excel_file}")
        
        try:
            # Load Excel file
            excel_data = pd.ExcelFile(excel_path)
            sheet_names = excel_data.sheet_names
            
            print(f"  Found {len(sheet_names)} sheets: {sheet_names}")
            
            # Create subdirectory for this Excel file's charts
            excel_name = excel_file.replace('.xlsx', '')
            excel_output_dir = os.path.join(output_directory, f"{excel_name}_charts")
            if not os.path.exists(excel_output_dir):
                os.makedirs(excel_output_dir)
            
            # Process each sheet (crop)
            for sheet_name in sheet_names:
                try:
                    # Read sheet data
                    df = pd.read_excel(excel_data, sheet_name=sheet_name)
                    
                    # Check for required columns
                    required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    
                    if missing_cols:
                        print(f"    Skipping sheet '{sheet_name}': Missing columns {missing_cols}")
                        continue
                    
                    # Create chart for this crop
                    chart_path = create_single_crop_chart(df, sheet_name, excel_output_dir, excel_name)
                    
                    if chart_path:
                        print(f"    ✓ Created chart: {os.path.basename(chart_path)}")
                        total_charts += 1
                    
                except Exception as e:
                    print(f"    ❌ Error processing sheet '{sheet_name}': {str(e)}")
                    continue
        
        except Exception as e:
            print(f"  ❌ Error processing Excel file '{excel_file}': {str(e)}")
            continue
    
    print(f"\n🎉 Processing complete! Created {total_charts} charts in: {output_directory}")

def create_single_crop_chart(df, crop_name, output_dir, market_name):
    """
    Create a single price trend chart for a crop with legend on the right side
    
    Parameters:
    df (DataFrame): Data for the crop
    crop_name (str): Name of the crop
    output_dir (str): Directory to save the chart
    market_name (str): Name of the market (for title)
    
    Returns:
    str: Path to saved chart file
    """
    
    try:
        # Clean and prepare data
        df_clean = df.copy()
        
        # Convert date column to datetime
        df_clean['Arrival_Date'] = pd.to_datetime(df_clean['Arrival_Date'], errors='coerce')
        
        # Remove rows with invalid dates
        df_clean = df_clean.dropna(subset=['Arrival_Date'])
        
        if df_clean.empty:
            print(f"      No valid data found for {crop_name}")
            return None
        
        # Sort by date
        df_clean = df_clean.sort_values('Arrival_Date')
        
        # Remove rows with missing price data
        price_cols = ['Min_Price', 'Max_Price', 'Modal_Price']
        df_clean = df_clean.dropna(subset=price_cols)
        
        if df_clean.empty:
            print(f"      No valid price data found for {crop_name}")
            return None
        
        # Create the plot with extra width to accommodate right-side legend
        plt.figure(figsize=(16, 8))
        
        # Plot the three price lines
        plt.plot(df_clean['Arrival_Date'], df_clean['Min_Price'], 
                label='Min Price', marker='o', markersize=4, linewidth=2, alpha=0.8)
        plt.plot(df_clean['Arrival_Date'], df_clean['Max_Price'], 
                label='Max Price', marker='s', markersize=4, linewidth=2, alpha=0.8)
        plt.plot(df_clean['Arrival_Date'], df_clean['Modal_Price'], 
                label='Modal Price', marker='^', markersize=4, linewidth=2, alpha=0.8)
        
        # Customize the plot
        plt.title(f'Price Trend for {crop_name} - {market_name} Market', fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Price (₹)', fontsize=12)
        
        # Format x-axis dates
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)
        
        # Add grid
        plt.grid(True, alpha=0.3)
        
        # Place legend on the right side (outside the plot area)
        plt.legend(fontsize=12, loc='center left', bbox_to_anchor=(1.02, 0.5))
        
        # Add statistics text box on the top left (inside plot area)
        min_price_avg = df_clean['Min_Price'].mean()
        max_price_avg = df_clean['Max_Price'].mean()
        modal_price_avg = df_clean['Modal_Price'].mean()
        
        stats_text = f'Average Prices:\nMin: ₹{min_price_avg:.0f}\nMax: ₹{max_price_avg:.0f}\nModal: ₹{modal_price_avg:.0f}'
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8),
                fontsize=10)
        
        # Adjust layout to prevent legend cutoff
        plt.tight_layout()
        plt.subplots_adjust(right=0.85)  # Make room for right-side legend
        
        # Create safe filename
        safe_crop_name = create_safe_filename(crop_name)
        chart_filename = f"{safe_crop_name}_price_trend.png"
        chart_path = os.path.join(output_dir, chart_filename)
        
        # Save the chart with bbox_inches='tight' to include the legend
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()  # Close to free memory
        
        return chart_path
        
    except Exception as e:
        print(f"      Error creating chart for {crop_name}: {str(e)}")
        plt.close()  # Make sure to close the figure even if there's an error
        return None

def create_safe_filename(name):
    """
    Create a safe filename by removing invalid characters
    """
    # Replace invalid characters with underscores
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', ' ']
    safe_name = str(name)
    
    for char in invalid_chars:
        safe_name = safe_name.replace(char, '_')
    
    # Remove multiple underscores and limit length
    safe_name = '_'.join(filter(None, safe_name.split('_')))
    safe_name = safe_name[:50]  # Limit to 50 characters
    
    return safe_name

def process_single_excel_file(excel_file_path, output_directory):
    """
    Process a single Excel file and create charts for all its sheets
    
    Parameters:
    excel_file_path (str): Path to the Excel file
    output_directory (str): Directory to save charts
    """
    
    excel_file_path = excel_file_path.strip('"\'')
    output_directory = output_directory.strip('"\'')
    
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    if not os.path.exists(excel_file_path):
        print(f"Excel file not found: {excel_file_path}")
        return
    
    excel_name = os.path.basename(excel_file_path).replace('.xlsx', '')
    
    try:
        excel_data = pd.ExcelFile(excel_file_path)
        sheet_names = excel_data.sheet_names
        
        print(f"Processing Excel file: {excel_name}")
        print(f"Found {len(sheet_names)} sheets")
        
        charts_created = 0
        
        for sheet_name in sheet_names:
            df = pd.read_excel(excel_data, sheet_name=sheet_name)
            
            required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
            if not all(col in df.columns for col in required_cols):
                print(f"  Skipping sheet '{sheet_name}': Missing required columns")
                continue
            
            chart_path = create_single_crop_chart(df, sheet_name, output_directory, excel_name)
            
            if chart_path:
                print(f"  ✓ Created: {os.path.basename(chart_path)}")
                charts_created += 1
        
        print(f"Created {charts_created} charts for {excel_name}")
        
    except Exception as e:
        print(f"Error processing Excel file: {str(e)}")

def main():
    """
    Main function for interactive usage
    """
    print("=" * 80)
    print("📈 CROP PRICE TREND CHART GENERATOR (Legend on Right)")
    print("=" * 80)
    
    mode = input("Process (1) Directory of Excel files or (2) Single Excel file? Enter 1 or 2: ").strip()
    
    if mode == "1":
        input_dir = input("Enter directory containing Excel files: ").strip()
        output_dir = input("Enter output directory for charts: ").strip()
        create_price_charts_from_excel_files(input_dir, output_dir)
    
    elif mode == "2":
        excel_file = input("Enter path to Excel file: ").strip()
        output_dir = input("Enter output directory for charts: ").strip()
        process_single_excel_file(excel_file, output_dir)
    
    else:
        print("Invalid option. Please run again and choose 1 or 2.")

# Direct usage functions
def generate_charts_from_directory(input_directory, output_directory):
    """
    Direct function call for processing directory of Excel files
    """
    create_price_charts_from_excel_files(input_directory, output_directory)

def generate_charts_from_file(excel_file_path, output_directory):
    """
    Direct function call for processing single Excel file
    """
    process_single_excel_file(excel_file_path, output_directory)

if __name__ == "__main__":
    main()
