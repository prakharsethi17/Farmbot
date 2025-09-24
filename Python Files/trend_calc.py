import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys
import argparse
from datetime import datetime
from pathlib import Path
import re
import warnings
warnings.filterwarnings('ignore')

def get_default_paths():
    """Get default paths relative to script location"""
    script_dir = Path(__file__).parent.absolute()
    return {
        'input': script_dir / 'data' / 'crop_excel_files',
        'output': script_dir / 'output' / 'price_charts'
    }

def create_price_charts_from_excel_files(input_directory, output_directory):
    """
    Process all Excel files in input directory and create price trend charts
    for each crop sheet, saving them to the output directory.
    
    Parameters:
    input_directory (str or Path): Directory containing Excel files with crop sheets
    output_directory (str or Path): Directory to save chart images
    
    Returns:
    bool: True if successful, False otherwise
    """
    
    # Convert to Path objects and resolve
    input_path = Path(input_directory).resolve()
    output_path = Path(output_directory).resolve()
    
    # Validate input directory
    if not input_path.exists():
        print(f"Error: Input directory does not exist: {input_path}")
        return False
    
    if not input_path.is_dir():
        print(f"Error: Input path is not a directory: {input_path}")
        return False
    
    # Create output directory
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"Output directory ready: {output_path}")
    except Exception as e:
        print(f"Error creating output directory: {e}")
        return False
    
    # Find all Excel files
    excel_files = list(input_path.glob('*.xlsx'))
    
    if not excel_files:
        print(f"No Excel files found in: {input_path}")
        print("Please ensure Excel files (.xlsx) are present in the input directory.")
        return False
    
    print(f"Found {len(excel_files)} Excel files to process.")
    
    total_charts = 0
    processing_errors = []
    
    for excel_file in excel_files:
        print(f"\nProcessing: {excel_file.name}")
        
        try:
            # Load Excel file
            excel_data = pd.ExcelFile(excel_file)
            sheet_names = excel_data.sheet_names
            
            print(f"  Found {len(sheet_names)} sheets")
            
            # Create subdirectory for this Excel file's charts
            excel_name = excel_file.stem
            excel_output_dir = output_path / f"{excel_name}_charts"
            excel_output_dir.mkdir(exist_ok=True)
            
            # Process each sheet (crop)
            file_charts_created = 0
            for sheet_name in sheet_names:
                try:
                    # Read sheet data
                    df = pd.read_excel(excel_data, sheet_name=sheet_name)
                    
                    # Check for required columns
                    required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    
                    if missing_cols:
                        error_msg = f"Skipping sheet '{sheet_name}' in {excel_file.name}: Missing columns {missing_cols}"
                        print(f"    Warning: {error_msg}")
                        processing_errors.append(error_msg)
                        continue
                    
                    # Create chart for this crop
                    chart_path = create_single_crop_chart(df, sheet_name, excel_output_dir, excel_name)
                    
                    if chart_path:
                        print(f"    Created chart: {chart_path.name}")
                        file_charts_created += 1
                        total_charts += 1
                    
                except Exception as e:
                    error_msg = f"Error processing sheet '{sheet_name}' in {excel_file.name}: {str(e)}"
                    print(f"    Error: {error_msg}")
                    processing_errors.append(error_msg)
                    continue
            
            print(f"  Created {file_charts_created} charts for {excel_file.name}")
        
        except Exception as e:
            error_msg = f"Error processing Excel file '{excel_file.name}': {str(e)}"
            print(f"  Error: {error_msg}")
            processing_errors.append(error_msg)
            continue
    
    # Summary
    print(f"\nProcessing complete! Created {total_charts} charts in: {output_path}")
    
    if processing_errors:
        print(f"Encountered {len(processing_errors)} warnings/errors:")
        for error in processing_errors[:5]:  # Show first 5 errors
            print(f"  - {error}")
        if len(processing_errors) > 5:
            print(f"  ... and {len(processing_errors) - 5} more (see log file)")
        
        # Create error log
        create_error_log(output_path, processing_errors)
    
    return total_charts > 0

def create_single_crop_chart(df, crop_name, output_dir, market_name):
    """
    Create a single price trend chart for a crop with legend on the right side
    
    Parameters:
    df (DataFrame): Data for the crop
    crop_name (str): Name of the crop
    output_dir (Path): Directory to save the chart
    market_name (str): Name of the market (for title)
    
    Returns:
    Path: Path to saved chart file or None if failed
    """
    
    try:
        # Clean and prepare data
        df_clean = df.copy()
        
        # Convert date column to datetime
        df_clean['Arrival_Date'] = pd.to_datetime(df_clean['Arrival_Date'], errors='coerce')
        
        # Remove rows with invalid dates
        df_clean = df_clean.dropna(subset=['Arrival_Date'])
        
        if df_clean.empty:
            print(f"      No valid date data found for {crop_name}")
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
        
        # Plot the three price lines with different colors and styles
        plt.plot(df_clean['Arrival_Date'], df_clean['Min_Price'], 
                label='Min Price', marker='o', markersize=4, linewidth=2, alpha=0.8, color='#ff7f0e')
        plt.plot(df_clean['Arrival_Date'], df_clean['Max_Price'], 
                label='Max Price', marker='s', markersize=4, linewidth=2, alpha=0.8, color='#d62728')
        plt.plot(df_clean['Arrival_Date'], df_clean['Modal_Price'], 
                label='Modal Price', marker='^', markersize=4, linewidth=2, alpha=0.8, color='#2ca02c')
        
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
        
        # Calculate additional statistics
        price_range = df_clean['Modal_Price'].max() - df_clean['Modal_Price'].min()
        data_points = len(df_clean)
        
        stats_text = (f'Statistics:\n'
                     f'Avg Min: ₹{min_price_avg:.0f}\n'
                     f'Avg Max: ₹{max_price_avg:.0f}\n'
                     f'Avg Modal: ₹{modal_price_avg:.0f}\n'
                     f'Range: ₹{price_range:.0f}\n'
                     f'Data Points: {data_points}')
        
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8),
                fontsize=9)
        
        # Adjust layout to prevent legend cutoff
        plt.tight_layout()
        plt.subplots_adjust(right=0.85)  # Make room for right-side legend
        
        # Create safe filename
        safe_crop_name = create_safe_filename(crop_name)
        chart_filename = f"{safe_crop_name}_price_trend.png"
        chart_path = output_dir / chart_filename
        
        # Save the chart with bbox_inches='tight' to include the legend
        plt.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
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
    safe_name = str(name)
    
    # Remove or replace problematic characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
    
    # Replace spaces and other whitespace with underscores
    safe_name = re.sub(r'\s+', '_', safe_name)
    
    # Remove multiple consecutive underscores
    safe_name = re.sub(r'_+', '_', safe_name)
    
    # Remove leading/trailing underscores
    safe_name = safe_name.strip('_')
    
    # Limit length and ensure it's not empty
    safe_name = safe_name[:50] if safe_name else "Unknown_Crop"
    
    return safe_name

def create_error_log(output_dir, errors):
    """
    Create an error log file
    """
    try:
        log_path = output_dir / 'chart_generation_errors.log'
        with open(log_path, 'w') as f:
            f.write(f"Chart Generation Error Log - {datetime.now()}\n")
            f.write("=" * 60 + "\n\n")
            for i, error in enumerate(errors, 1):
                f.write(f"{i:3d}. {error}\n")
        print(f"Error log saved: {log_path}")
    except Exception as e:
        print(f"Could not create error log: {e}")

def process_single_excel_file(excel_file_path, output_directory):
    """
    Process a single Excel file and create charts for all its sheets
    
    Parameters:
    excel_file_path (str or Path): Path to the Excel file
    output_directory (str or Path): Directory to save charts
    
    Returns:
    bool: True if successful, False otherwise
    """
    
    excel_path = Path(excel_file_path).resolve()
    output_path = Path(output_directory).resolve()
    
    # Validate input file
    if not excel_path.exists():
        print(f"Error: Excel file not found: {excel_path}")
        return False
    
    if not excel_path.is_file():
        print(f"Error: Path is not a file: {excel_path}")
        return False
    
    # Create output directory
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating output directory: {e}")
        return False
    
    excel_name = excel_path.stem
    
    try:
        excel_data = pd.ExcelFile(excel_path)
        sheet_names = excel_data.sheet_names
        
        print(f"Processing Excel file: {excel_name}")
        print(f"Found {len(sheet_names)} sheets")
        
        charts_created = 0
        processing_errors = []
        
        for sheet_name in sheet_names:
            try:
                df = pd.read_excel(excel_data, sheet_name=sheet_name)
                
                required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    error_msg = f"Skipping sheet '{sheet_name}': Missing columns {missing_cols}"
                    print(f"  Warning: {error_msg}")
                    processing_errors.append(error_msg)
                    continue
                
                chart_path = create_single_crop_chart(df, sheet_name, output_path, excel_name)
                
                if chart_path:
                    print(f"  Created: {chart_path.name}")
                    charts_created += 1
                    
            except Exception as e:
                error_msg = f"Error processing sheet '{sheet_name}': {str(e)}"
                print(f"  Error: {error_msg}")
                processing_errors.append(error_msg)
        
        print(f"\nCreated {charts_created} charts for {excel_name}")
        
        if processing_errors:
            create_error_log(output_path, processing_errors)
        
        return charts_created > 0
        
    except Exception as e:
        print(f"Error processing Excel file: {str(e)}")
        return False

def interactive_mode():
    """
    Interactive mode for user input
    """
    print("=" * 80)
    print("CROP PRICE TREND CHART GENERATOR")
    print("=" * 80)
    print("This script creates price trend charts from Excel files containing crop data.")
    print()
    
    # Show default paths
    defaults = get_default_paths()
    print("Default paths:")
    print(f"  Input:  {defaults['input']}")
    print(f"  Output: {defaults['output']}")
    print()
    
    mode = input("Process (1) Directory of Excel files or (2) Single Excel file? Enter 1 or 2: ").strip()
    
    if mode == "1":
        # Directory mode
        input_choice = input("Use default input directory? (y/n): ").strip().lower()
        if input_choice in ['y', 'yes', '']:
            input_dir = defaults['input']
        else:
            input_dir = input("Enter directory containing Excel files: ").strip()
        
        output_choice = input("Use default output directory? (y/n): ").strip().lower()
        if output_choice in ['y', 'yes', '']:
            output_dir = defaults['output']
        else:
            output_dir = input("Enter output directory for charts: ").strip()
        
        print("\n" + "=" * 80)
        print("PROCESSING DIRECTORY...")
        print("=" * 80)
        
        success = create_price_charts_from_excel_files(input_dir, output_dir)
        
    elif mode == "2":
        # Single file mode
        excel_file = input("Enter path to Excel file: ").strip()
        
        output_choice = input("Use default output directory? (y/n): ").strip().lower()
        if output_choice in ['y', 'yes', '']:
            output_dir = defaults['output']
        else:
            output_dir = input("Enter output directory for charts: ").strip()
        
        print("\n" + "=" * 80)
        print("PROCESSING SINGLE FILE...")
        print("=" * 80)
        
        success = process_single_excel_file(excel_file, output_dir)
        
    else:
        print("Invalid option. Please run again and choose 1 or 2.")
        return
    
    if success:
        print("\nChart generation completed successfully!")
    else:
        print("\nChart generation failed. Please check the error messages above.")

def command_line_mode():
    """
    Command line argument parsing
    """
    parser = argparse.ArgumentParser(
        description='Generate price trend charts from Excel crop data files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python price_chart_generator.py
  python price_chart_generator.py -i ./excel_files -o ./charts
  python price_chart_generator.py --file single_market.xlsx --output ./charts
        '''
    )
    
    defaults = get_default_paths()
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        default=str(defaults['input']),
        help=f'Input directory containing Excel files (default: {defaults["input"]})'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=str(defaults['output']),
        help=f'Output directory for charts (default: {defaults["output"]})'
    )
    
    parser.add_argument(
        '-f', '--file',
        type=str,
        help='Process single Excel file instead of directory'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Run in interactive mode'
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
    elif args.file:
        print("Processing single Excel file...")
        success = process_single_excel_file(args.file, args.output)
        sys.exit(0 if success else 1)
    else:
        print("Processing directory of Excel files...")
        success = create_price_charts_from_excel_files(args.input, args.output)
        sys.exit(0 if success else 1)

# Convenience functions for direct usage
def generate_charts_from_directory(input_directory, output_directory):
    """
    Direct function call for processing directory of Excel files
    
    Usage:
    generate_charts_from_directory('./excel_files', './charts')
    """
    return create_price_charts_from_excel_files(input_directory, output_directory)

def generate_charts_from_file(excel_file_path, output_directory):
    """
    Direct function call for processing single Excel file
    
    Usage:
    generate_charts_from_file('./market.xlsx', './charts')
    """
    return process_single_excel_file(excel_file_path, output_directory)

def generate_charts_with_defaults():
    """
    Generate charts using default directory structure
    """
    defaults = get_default_paths()
    return create_price_charts_from_excel_files(defaults['input'], defaults['output'])

if __name__ == "__main__":
    # Check if command line arguments were provided
    if len(sys.argv) > 1:
        command_line_mode()
    else:
        interactive_mode()
