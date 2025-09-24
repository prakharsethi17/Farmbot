import pandas as pd
import os
import sys
import argparse
from pathlib import Path
import re

def get_default_paths():
    """Get default paths relative to script location"""
    script_dir = Path(__file__).parent.absolute()
    return {
        'input': script_dir / 'data' / 'raw_data.csv',
        'output': script_dir / 'output' / 'market_csvs'
    }

def create_market_csv_files(input_file_path, output_directory_path):
    """
    Create separate CSV files for each market from the original CSV file.
    
    Parameters:
    input_file_path (str or Path): Full path to the original CSV file
    output_directory_path (str or Path): Directory where market-specific CSV files will be saved
    
    Returns:
    bool: True if successful, False otherwise
    """
    
    # Convert to Path objects and resolve
    input_path = Path(input_file_path).resolve()
    output_path = Path(output_directory_path).resolve()
    
    # Validate input file
    if not input_path.exists():
        print(f"Error: Input file does not exist: {input_path}")
        return False
    
    if not input_path.is_file():
        print(f"Error: Input path is not a file: {input_path}")
        return False
    
    if input_path.suffix.lower() != '.csv':
        print(f"Warning: Input file doesn't have .csv extension: {input_path}")
    
    # Create output directory
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"Output directory ready: {output_path}")
    except Exception as e:
        print(f"Error creating output directory: {e}")
        return False
    
    try:
        # Read the original CSV file
        print(f"Loading CSV file: {input_path.name}")
        df = pd.read_csv(input_path)
        print(f"Total records loaded: {len(df):,}")
        
        if df.empty:
            print("Error: CSV file is empty")
            return False
        
        # Display basic information about the dataset
        print(f"Columns in the dataset: {list(df.columns)}")
        
        # Check if required columns exist
        required_columns = ['State', 'District', 'Market']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            print("Expected columns: State, District, Market")
            print(f"Available columns: {list(df.columns)}")
            return False
        
        # Display State and District info
        unique_states = df['State'].dropna().unique()
        unique_districts = df['District'].dropna().unique()
        
        print(f"State(s): {list(unique_states)}")
        print(f"District(s): {list(unique_districts)}")
        
        # Get unique markets (remove NaN values)
        unique_markets = df['Market'].dropna().unique()
        print(f"Found {len(unique_markets)} unique markets: {list(unique_markets)}")
        
        if len(unique_markets) == 0:
            print("Error: No valid markets found in the data")
            return False
        
        # Create separate CSV files for each market
        created_files = []
        processing_errors = []
        
        for market in unique_markets:
            try:
                # Filter data for the current market
                market_data = df[df['Market'] == market].copy()
                
                if market_data.empty:
                    print(f"Warning: No data found for market '{market}'")
                    continue
                
                # Create safe filename
                safe_market_name = create_safe_filename(market)
                filename = f"{safe_market_name}_market_data.csv"
                filepath = output_path / filename
                
                # Save the market-specific data to CSV
                market_data.to_csv(filepath, index=False)
                created_files.append(filename)
                
                print(f"Created: {filename} with {len(market_data):,} records")
                
                # Display statistics for this market
                stats = get_market_statistics(market_data)
                for stat_line in stats:
                    print(f"  {stat_line}")
                print("  " + "-" * 50)
                
            except Exception as e:
                error_msg = f"Error processing market '{market}': {str(e)}"
                print(f"  {error_msg}")
                processing_errors.append(error_msg)
        
        # Summary
        print(f"\nSuccessfully created {len(created_files)} market CSV files in: {output_path}")
        
        if processing_errors:
            print(f"Encountered {len(processing_errors)} errors:")
            for error in processing_errors:
                print(f"  - {error}")
        
        # Create summary file
        create_summary_file(df, output_path, created_files, processing_errors)
        
        return len(created_files) > 0
        
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}")
        return False
    except pd.errors.EmptyDataError:
        print(f"Error: The file '{input_path}' is empty or contains no valid data")
        return False
    except pd.errors.ParserError as e:
        print(f"Error parsing CSV file: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return False

def create_safe_filename(name):
    """
    Create a safe filename by removing/replacing invalid characters
    """
    # Remove or replace invalid characters
    safe_name = str(name).strip()
    
    # Replace problematic characters with underscores
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
    
    # Replace spaces and other whitespace with underscores
    safe_name = re.sub(r'\s+', '_', safe_name)
    
    # Remove multiple consecutive underscores
    safe_name = re.sub(r'_+', '_', safe_name)
    
    # Remove leading/trailing underscores
    safe_name = safe_name.strip('_')
    
    # Ensure name is not empty
    if not safe_name:
        safe_name = "Unknown_Market"
    
    # Limit length (most filesystems support 255 chars, but let's be safe)
    safe_name = safe_name[:100]
    
    return safe_name

def get_market_statistics(market_data):
    """
    Get statistics for a market dataset
    """
    stats = []
    
    if 'Arrival_Date' in market_data.columns:
        try:
            # Try to parse dates
            dates = pd.to_datetime(market_data['Arrival_Date'], errors='coerce')
            valid_dates = dates.dropna()
            if not valid_dates.empty:
                stats.append(f"Date range: {valid_dates.min().strftime('%Y-%m-%d')} to {valid_dates.max().strftime('%Y-%m-%d')}")
            else:
                stats.append("Date range: No valid dates found")
        except:
            stats.append("Date range: Unable to parse dates")
    
    if 'Commodity' in market_data.columns:
        unique_commodities = market_data['Commodity'].nunique()
        stats.append(f"Unique commodities: {unique_commodities}")
    
    if 'Variety' in market_data.columns:
        unique_varieties = market_data['Variety'].nunique()
        stats.append(f"Unique varieties: {unique_varieties}")
    
    # Add price statistics if available
    price_columns = ['Min_Price', 'Max_Price', 'Modal_Price']
    for price_col in price_columns:
        if price_col in market_data.columns:
            try:
                prices = pd.to_numeric(market_data[price_col], errors='coerce')
                valid_prices = prices.dropna()
                if not valid_prices.empty:
                    stats.append(f"{price_col} range: ₹{valid_prices.min():.2f} - ₹{valid_prices.max():.2f}")
            except:
                pass
    
    return stats

def create_summary_file(df, output_directory_path, created_files, errors=None):
    """
    Create a comprehensive summary file
    """
    try:
        unique_markets = df['Market'].dropna().unique()
        summary_data = []
        
        for market in unique_markets:
            market_data = df[df['Market'] == market]
            
            if market_data.empty:
                continue
            
            summary_info = {
                'Market': market,
                'Total_Records': len(market_data),
                'State': market_data['State'].iloc[0] if 'State' in market_data.columns else 'N/A',
                'District': market_data['District'].iloc[0] if 'District' in market_data.columns else 'N/A'
            }
            
            # Add optional columns if they exist
            if 'Commodity' in market_data.columns:
                summary_info['Unique_Commodities'] = market_data['Commodity'].nunique()
            
            if 'Arrival_Date' in market_data.columns:
                try:
                    dates = pd.to_datetime(market_data['Arrival_Date'], errors='coerce')
                    valid_dates = dates.dropna()
                    if not valid_dates.empty:
                        summary_info['Date_Range_Start'] = valid_dates.min().strftime('%Y-%m-%d')
                        summary_info['Date_Range_End'] = valid_dates.max().strftime('%Y-%m-%d')
                except:
                    summary_info['Date_Range_Start'] = 'Invalid'
                    summary_info['Date_Range_End'] = 'Invalid'
            
            if 'Variety' in market_data.columns:
                summary_info['Unique_Varieties'] = market_data['Variety'].nunique()
            
            summary_data.append(summary_info)
        
        # Create summary DataFrame
        summary_df = pd.DataFrame(summary_data)
        summary_filepath = output_directory_path / 'markets_summary.csv'
        summary_df.to_csv(summary_filepath, index=False)
        print(f"Created summary file: markets_summary.csv")
        
        # Create processing log
        log_filepath = output_directory_path / 'processing_log.txt'
        with open(log_filepath, 'w') as f:
            f.write(f"Market CSV Generation Log - {pd.Timestamp.now()}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Files created: {len(created_files)}\n")
            f.write(f"Errors encountered: {len(errors) if errors else 0}\n\n")
            
            if created_files:
                f.write("Created Files:\n")
                for file in created_files:
                    f.write(f"  - {file}\n")
                f.write("\n")
            
            if errors:
                f.write("Errors:\n")
                for error in errors:
                    f.write(f"  - {error}\n")
        
        print(f"Created processing log: processing_log.txt")
        
    except Exception as e:
        print(f"Warning: Could not create summary file: {str(e)}")

def interactive_mode():
    """
    Interactive mode for user input
    """
    print("=" * 70)
    print("AGRICULTURAL DATA - MARKET CSV GENERATOR")
    print("=" * 70)
    print("This script splits a master CSV file into separate files for each market.")
    print()
    
    # Show default paths
    defaults = get_default_paths()
    print("Default paths:")
    print(f"  Input:  {defaults['input']}")
    print(f"  Output: {defaults['output']}")
    print()
    
    # Get input file path
    input_choice = input("Use default input file? (y/n): ").strip().lower()
    if input_choice in ['y', 'yes', '']:
        input_file = defaults['input']
    else:
        input_file = input("Enter the input CSV file path: ").strip()
    
    # Get output directory
    output_choice = input("Use default output directory? (y/n): ").strip().lower()
    if output_choice in ['y', 'yes', '']:
        output_dir = defaults['output']
    else:
        output_dir = input("Enter the output directory path: ").strip()
    
    print("\n" + "=" * 70)
    print("PROCESSING...")
    print("=" * 70)
    
    # Process the file
    success = create_market_csv_files(input_file, output_dir)
    
    if success:
        print("\nProcessing completed successfully!")
    else:
        print("\nProcessing failed. Please check the error messages above.")

def command_line_mode():
    """
    Command line argument parsing
    """
    parser = argparse.ArgumentParser(
        description='Split master CSV file into separate market CSV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python market_csv_splitter.py
  python market_csv_splitter.py -i data.csv -o ./output
  python market_csv_splitter.py --input master.csv --output ./markets
        '''
    )
    
    defaults = get_default_paths()
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        default=str(defaults['input']),
        help=f'Input CSV file path (default: {defaults["input"]})'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=str(defaults['output']),
        help=f'Output directory path (default: {defaults["output"]})'
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
        success = create_market_csv_files(args.input, args.output)
        sys.exit(0 if success else 1)

# Convenience functions for direct usage
def split_markets_by_csv(input_path, output_path):
    """
    Direct function for splitting - use this for direct calls
    
    Usage:
    split_markets_by_csv('./master.csv', './output')
    """
    return create_market_csv_files(input_path, output_path)

def split_with_defaults():
    """
    Split using default directory structure
    """
    defaults = get_default_paths()
    return create_market_csv_files(defaults['input'], defaults['output'])

if __name__ == "__main__":
    # Check if command line arguments were provided
    if len(sys.argv) > 1:
        command_line_mode()
    else:
        interactive_mode()
