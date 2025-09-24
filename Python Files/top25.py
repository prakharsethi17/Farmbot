import os
import pandas as pd
import sys
import argparse
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

def get_default_paths():
    """Get default paths relative to script location"""
    script_dir = Path(__file__).parent.absolute()
    return {
        'input': script_dir / 'data' / 'crop_excel_files',
        'output': script_dir / 'output' / 'analysis'
    }

def analyze_top_priced_crops_from_excel_directory(input_directory, output_directory=None, output_filename="top25_crops_analysis.txt"):
    """
    Analyze Excel files where each file represents a market and each sheet represents a crop
    to find top 25 consistently high-priced crops across markets and years.
    
    Parameters:
    input_directory (str or Path): Directory containing market Excel files with crop sheets
    output_directory (str or Path): Directory to save output file (optional, defaults to current directory)
    output_filename (str): Name of output text file
    
    Returns:
    bool: True if successful, False otherwise
    """
    
    # Convert to Path objects and resolve
    input_path = Path(input_directory).resolve()
    
    if output_directory:
        output_path = Path(output_directory).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()
    
    output_file_path = output_path / output_filename
    
    # Validate input directory
    if not input_path.exists():
        print(f"Error: Input directory does not exist: {input_path}")
        return False
    
    if not input_path.is_dir():
        print(f"Error: Input path is not a directory: {input_path}")
        return False
    
    print("=" * 80)
    print("ANALYZING CROP PRICES FROM EXCEL FILES")
    print("=" * 80)
    print(f"Input Directory: {input_path}")
    print(f"Output File: {output_file_path}")
    print()
    
    try:
        # Step 1: Load all Excel files and their sheets
        all_crop_data = []
        excel_files = list(input_path.glob('*.xlsx'))
        
        if not excel_files:
            print("No Excel files found in the input directory!")
            print(f"Please ensure Excel files (.xlsx) are present in: {input_path}")
            return False
        
        print(f"Found {len(excel_files)} Excel files to process:")
        
        total_sheets = 0
        processing_errors = []
        
        for excel_file in excel_files:
            try:
                # Extract market name from filename (remove file extension and clean)
                market_name = excel_file.stem.replace('_crops_data', '').replace('_', ' ').title()
                
                # Load Excel file
                excel_data = pd.ExcelFile(excel_file)
                sheet_names = excel_data.sheet_names
                
                print(f"  {excel_file.name}: {len(sheet_names)} crop sheets")
                
                # Read each sheet (crop)
                file_sheets_loaded = 0
                for sheet_name in sheet_names:
                    try:
                        df = pd.read_excel(excel_data, sheet_name=sheet_name)
                        
                        # Check for required columns
                        required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
                        missing_cols = [col for col in required_cols if col not in df.columns]
                        
                        if missing_cols:
                            error_msg = f"Skipping sheet '{sheet_name}' in {excel_file.name}: Missing columns {missing_cols}"
                            print(f"    Warning: {error_msg}")
                            processing_errors.append(error_msg)
                            continue
                        
                        # Check if data is not empty
                        if df.empty:
                            error_msg = f"Skipping sheet '{sheet_name}' in {excel_file.name}: No data"
                            print(f"    Warning: {error_msg}")
                            processing_errors.append(error_msg)
                            continue
                        
                        # Add metadata
                        df['Market'] = market_name
                        df['Commodity'] = sheet_name
                        
                        all_crop_data.append(df)
                        file_sheets_loaded += 1
                        total_sheets += 1
                        
                    except Exception as e:
                        error_msg = f"Error reading sheet '{sheet_name}' in {excel_file.name}: {str(e)}"
                        print(f"    Error: {error_msg}")
                        processing_errors.append(error_msg)
                        continue
                
                print(f"    Successfully loaded {file_sheets_loaded} sheets")
                
            except Exception as e:
                error_msg = f"Error processing {excel_file.name}: {str(e)}"
                print(f"  Error: {error_msg}")
                processing_errors.append(error_msg)
                continue
        
        if not all_crop_data:
            print("No valid crop data found in any Excel files!")
            print("Please check that your Excel files contain the required columns:")
            print("  - Arrival_Date, Min_Price, Max_Price, Modal_Price")
            return False
        
        print(f"\nSuccessfully loaded {total_sheets} crop sheets from {len(excel_files)} files")
        
        # Step 2: Combine all data
        print("Combining and processing data...")
        combined_df = pd.concat(all_crop_data, ignore_index=True)
        print(f"Combined dataset: {len(combined_df):,} total records")
        
        # Step 3: Clean and prepare data
        print("Cleaning data...")
        
        # Convert dates and extract year
        combined_df['Arrival_Date'] = pd.to_datetime(combined_df['Arrival_Date'], errors='coerce')
        combined_df['Year'] = combined_df['Arrival_Date'].dt.year
        
        # Remove invalid data
        before_clean = len(combined_df)
        combined_df = combined_df.dropna(subset=['Commodity', 'Market', 'Year', 'Modal_Price'])
        combined_df = combined_df[combined_df['Modal_Price'] > 0]  # Remove zero/negative prices
        after_clean = len(combined_df)
        
        print(f"Data cleaning: {before_clean:,} → {after_clean:,} records ({before_clean - after_clean:,} removed)")
        
        if after_clean == 0:
            print("Error: No valid data remaining after cleaning")
            return False
        
        # Step 4: Calculate aggregated statistics
        print("Calculating crop price statistics...")
        
        # Group by commodity, market, and year
        market_year_stats = combined_df.groupby(['Commodity', 'Market', 'Year']).agg({
            'Min_Price': 'mean',
            'Max_Price': 'mean', 
            'Modal_Price': 'mean'
        }).round(2).reset_index()
        
        # Calculate overall commodity metrics
        commodity_metrics = combined_df.groupby('Commodity').agg({
            'Modal_Price': ['mean', 'median', 'std', 'count'],
            'Market': 'nunique',
            'Year': 'nunique'
        }).round(2)
        
        # Flatten column names
        commodity_metrics.columns = ['_'.join(col).strip() for col in commodity_metrics.columns.values]
        commodity_metrics = commodity_metrics.reset_index()
        
        # Rename for clarity
        commodity_metrics.rename(columns={
            'Modal_Price_mean': 'Avg_Modal_Price',
            'Modal_Price_median': 'Median_Modal_Price', 
            'Modal_Price_std': 'Price_Std_Dev',
            'Modal_Price_count': 'Total_Records',
            'Market_nunique': 'Markets_Count',
            'Year_nunique': 'Years_Count'
        }, inplace=True)
        
        # Step 5: Apply filtering criteria for "consistently high-priced"
        print("Identifying consistently high-priced crops...")
        
        # Calculate thresholds
        price_75th = commodity_metrics['Avg_Modal_Price'].quantile(0.75)
        price_90th = commodity_metrics['Avg_Modal_Price'].quantile(0.90)
        
        print(f"Price thresholds: 75th percentile = ₹{price_75th:.2f}, 90th percentile = ₹{price_90th:.2f}")
        
        # Filter criteria
        high_priced_crops = commodity_metrics[
            (commodity_metrics['Avg_Modal_Price'] >= price_75th) &  # High price
            (commodity_metrics['Markets_Count'] >= 1) &             # At least 1 market
            (commodity_metrics['Years_Count'] >= 2) &               # At least 2 years for consistency
            (commodity_metrics['Total_Records'] >= 5)               # Minimum data points
        ].copy()
        
        print(f"Found {len(high_priced_crops)} crops meeting criteria")
        
        if high_priced_crops.empty:
            print("No crops meet the filtering criteria")
            return False
        
        # Calculate consistency score
        high_priced_crops['Price_CV'] = (high_priced_crops['Price_Std_Dev'] / high_priced_crops['Avg_Modal_Price']) * 100
        high_priced_crops['Consistency_Score'] = (
            high_priced_crops['Avg_Modal_Price'] * 0.5 +           # 50% weight to average price
            high_priced_crops['Markets_Count'] * 100 +             # Market presence bonus
            high_priced_crops['Years_Count'] * 50 +                # Year presence bonus  
            (100 - high_priced_crops['Price_CV'].fillna(0)) * 0.2  # 20% weight to price stability
        )
        
        # Step 6: Get top 25 crops (or all if fewer than 25)
        num_crops = min(25, len(high_priced_crops))
        top_crops = high_priced_crops.nlargest(num_crops, 'Consistency_Score').reset_index(drop=True)
        
        # Step 7: Generate detailed output
        print("Generating detailed analysis...")
        
        success = generate_analysis_report(
            top_crops, market_year_stats, combined_df, excel_files, 
            total_sheets, price_75th, output_file_path, processing_errors
        )
        
        if success:
            print("\n" + "=" * 80)
            print("ANALYSIS COMPLETE!")
            print("=" * 80)
            print(f"Results saved to: {output_file_path}")
            if not top_crops.empty:
                print(f"Top crop: {top_crops.iloc[0]['Commodity']} (₹{top_crops.iloc[0]['Avg_Modal_Price']:.2f})")
                print(f"Average price of top {len(top_crops)}: ₹{top_crops['Avg_Modal_Price'].mean():.2f}")
            print(f"Markets analyzed: {combined_df['Market'].nunique()}")
            print(f"Total crops analyzed: {combined_df['Commodity'].nunique()}")
            
            if processing_errors:
                print(f"Warnings/Errors: {len(processing_errors)} (see output file for details)")
        
        return success
        
    except Exception as e:
        print(f"Fatal error during analysis: {str(e)}")
        return False

def generate_analysis_report(top_crops, market_year_stats, combined_df, excel_files, total_sheets, price_75th, output_file_path, errors=None):
    """
    Generate the detailed analysis report
    """
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 100 + "\n")
            f.write(f"TOP {len(top_crops)} CONSISTENTLY HIGH-PRICED CROPS ACROSS MARKETS AND YEARS\n")
            f.write("(Analysis from Excel Files with Market-Crop Structure)\n")
            f.write("=" * 100 + "\n")
            f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Data Source: {len(excel_files)} Excel files ({total_sheets} crop sheets)\n")
            f.write(f"Total Records Analyzed: {len(combined_df):,}\n")
            f.write(f"Unique Markets: {combined_df['Market'].nunique()}\n")
            f.write(f"Unique Crops: {combined_df['Commodity'].nunique()}\n")
            f.write(f"Year Range: {combined_df['Year'].min()} - {combined_df['Year'].max()}\n")
            f.write(f"Price Threshold (75th percentile): ₹{price_75th:.2f}\n\n")
            
            # Criteria
            f.write("SELECTION CRITERIA:\n")
            f.write(f"- Average modal price above 75th percentile (₹{price_75th:.2f})\n")
            f.write("- Present across multiple years (minimum 2 years)\n")
            f.write("- Minimum 5 data points for statistical significance\n")
            f.write("- Ranked by consistency score considering price, market presence, and stability\n\n")
            
            # Top crops list
            f.write(f"TOP {len(top_crops)} HIGH-PRICED CROPS:\n")
            f.write("-" * 100 + "\n")
            
            for idx, row in top_crops.iterrows():
                rank = idx + 1
                commodity = row['Commodity']
                avg_price = row['Avg_Modal_Price']
                median_price = row['Median_Modal_Price']
                markets_count = row['Markets_Count']
                years_count = row['Years_Count']
                total_records = row['Total_Records']
                consistency_score = row['Consistency_Score']
                price_cv = row['Price_CV'] if not pd.isna(row['Price_CV']) else 0
                
                f.write(f"{rank:2d}. {commodity}\n")
                f.write(f"    Average Modal Price: ₹{avg_price:.2f}\n")
                f.write(f"    Median Modal Price:  ₹{median_price:.2f}\n")
                f.write(f"    Market Presence:     {markets_count} market(s)\n")
                f.write(f"    Year Coverage:       {years_count} year(s)\n")
                f.write(f"    Total Data Points:   {total_records}\n")
                f.write(f"    Consistency Score:   {consistency_score:.1f}\n")
                f.write(f"    Price Variability:   {price_cv:.1f}% (CV)\n")
                
                # Show markets where this crop appears
                crop_markets = market_year_stats[market_year_stats['Commodity'] == commodity]['Market'].unique()
                f.write(f"    Markets: {', '.join(sorted(crop_markets))}\n")
                f.write("\n")
            
            # Summary statistics
            f.write("SUMMARY STATISTICS:\n")
            f.write("-" * 50 + "\n")
            f.write(f"Average price of top {len(top_crops)} crops: ₹{top_crops['Avg_Modal_Price'].mean():.2f}\n")
            f.write(f"Highest priced crop: {top_crops.iloc[0]['Commodity']} (₹{top_crops.iloc[0]['Avg_Modal_Price']:.2f})\n")
            
            if not top_crops['Price_CV'].isna().all():
                min_cv_idx = top_crops['Price_CV'].idxmin()
                f.write(f"Most consistent crop (lowest CV): {top_crops.loc[min_cv_idx, 'Commodity']}\n")
            
            max_markets_idx = top_crops['Markets_Count'].idxmax()
            f.write(f"Most widespread crop: {top_crops.loc[max_markets_idx, 'Commodity']}\n")
            
            # Market breakdown
            f.write(f"\nMARKET BREAKDOWN:\n")
            f.write("-" * 50 + "\n")
            market_summary = combined_df.groupby('Market').agg({
                'Commodity': 'nunique',
                'Modal_Price': 'mean'
            }).round(2).sort_values('Modal_Price', ascending=False)
            
            for market, stats in market_summary.iterrows():
                f.write(f"{market}: {stats['Commodity']} crops, avg price ₹{stats['Modal_Price']:.2f}\n")
            
            # Processing errors/warnings
            if errors:
                f.write(f"\nPROCESSING WARNINGS/ERRORS ({len(errors)}):\n")
                f.write("-" * 50 + "\n")
                for i, error in enumerate(errors, 1):
                    f.write(f"{i:2d}. {error}\n")
        
        return True
        
    except Exception as e:
        print(f"Error writing analysis report: {str(e)}")
        return False

def interactive_mode():
    """
    Interactive mode for user input
    """
    print("=" * 80)
    print("TOP 25 HIGH-PRICED CROPS ANALYZER (Excel Version)")
    print("=" * 80)
    print("This script analyzes Excel files with crop sheets to find high-priced crops.")
    print()
    
    # Show default paths
    defaults = get_default_paths()
    print("Default paths:")
    print(f"  Input:  {defaults['input']}")
    print(f"  Output: {defaults['output']}")
    print()
    
    # Get input directory
    input_choice = input("Use default input directory? (y/n): ").strip().lower()
    if input_choice in ['y', 'yes', '']:
        input_dir = defaults['input']
    else:
        input_dir = input("Enter directory containing crop Excel files: ").strip()
    
    # Get output directory
    output_choice = input("Use default output directory? (y/n): ").strip().lower()
    if output_choice in ['y', 'yes', '']:
        output_dir = defaults['output']
    else:
        custom_output = input("Enter output directory (press Enter for current directory): ").strip()
        output_dir = custom_output if custom_output else None
    
    # Get output filename
    output_filename = input("Enter output filename (press Enter for 'top25_crops_analysis.txt'): ").strip()
    if not output_filename:
        output_filename = "top25_crops_analysis.txt"
    
    print("\n" + "=" * 80)
    print("PROCESSING...")
    print("=" * 80)
    
    # Run analysis
    success = analyze_top_priced_crops_from_excel_directory(input_dir, output_dir, output_filename)
    
    if success:
        print("\nAnalysis completed successfully!")
    else:
        print("\nAnalysis failed. Please check the error messages above.")

def command_line_mode():
    """
    Command line argument parsing
    """
    parser = argparse.ArgumentParser(
        description='Analyze Excel crop files to find top high-priced crops',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python crop_price_analyzer.py
  python crop_price_analyzer.py -i ./excel_files -o ./results
  python crop_price_analyzer.py --input ./data --output ./analysis --filename top_crops.txt
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
        help=f'Output directory (default: {defaults["output"]})'
    )
    
    parser.add_argument(
        '-f', '--filename',
        type=str,
        default='top25_crops_analysis.txt',
        help='Output filename (default: top25_crops_analysis.txt)'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Run in interactive mode'
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
    else:
        print("Running in command line mode...")
        success = analyze_top_priced_crops_from_excel_directory(args.input, args.output, args.filename)
        sys.exit(0 if success else 1)

# Convenience functions for direct usage
def analyze_excel_crops(input_directory, output_directory=None, output_filename="top25_crops_analysis.txt"):
    """
    Direct function call for analysis
    
    Usage:
    analyze_excel_crops('./crop_excel_files', './output', 'my_results.txt')
    """
    return analyze_top_priced_crops_from_excel_directory(input_directory, output_directory, output_filename)

def analyze_with_defaults():
    """
    Analyze using default directory structure
    """
    defaults = get_default_paths()
    return analyze_top_priced_crops_from_excel_directory(defaults['input'], defaults['output'])

if __name__ == "__main__":
    # Check if command line arguments were provided
    if len(sys.argv) > 1:
        command_line_mode()
    else:
        interactive_mode()
