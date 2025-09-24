import pandas as pd
import os
import sys
from openpyxl import Workbook
import re
import argparse
from pathlib import Path

def get_default_paths():
    """Get default paths relative to script location"""
    script_dir = Path(__file__).parent.absolute()
    return {
        'input': script_dir / 'data' / 'market_csvs',
        'output': script_dir / 'output' / 'crop_excel_files'
    }

def create_crop_sheets_from_market_csvs(input_directory, output_directory=None):
    """
    Process each market CSV file and create Excel files with separate sheets for each crop.
    
    Parameters:
    input_directory (str or Path): Directory containing market CSV files
    output_directory (str or Path): Directory to save Excel files (optional, defaults to ./output)
    """
    
    # Convert to Path objects and resolve
    input_path = Path(input_directory).resolve()
    
    if output_directory:
        output_path = Path(output_directory).resolve()
    else:
        output_path = get_default_paths()['output']
    
    # Validate input directory
    if not input_path.exists():
        print(f"Error: Input directory does not exist: {input_path}")
        return False
    
    if not input_path.is_dir():
        print(f"Error: Input path is not a directory: {input_path}")
        return False
    
    # Create output directory if it doesn't exist
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"Output directory ready: {output_path}")
    except Exception as e:
        print(f"Error creating output directory: {e}")
        return False
    
    try:
        # List all CSV files in the directory (excluding summary file)
        csv_files = [f for f in input_path.glob('*.csv') if f.name != 'markets_summary.csv']
        
        if not csv_files:
            print(f"No market CSV files found in: {input_path}")
            print("Please ensure your CSV files are in the correct directory.")
            return False
        
        print(f"Found {len(csv_files)} market CSV files to process.")
        print("=" * 70)
        
        total_excel_files = 0
        total_crop_sheets = 0
        processing_errors = []
        
        for csv_file in csv_files:
            print(f"\nProcessing: {csv_file.name}")
            
            try:
                # Load the CSV file
                df = pd.read_csv(csv_file)
                print(f"   Records loaded: {len(df)}")
                
                # Check if 'Commodity' column exists
                if 'Commodity' not in df.columns:
                    error_msg = f"Skipping {csv_file.name}: 'Commodity' column not found."
                    print(f"   {error_msg}")
                    print(f"   Available columns: {list(df.columns)}")
                    processing_errors.append(error_msg)
                    continue
                
                # Get unique crops/commodities
                unique_crops = df['Commodity'].dropna().unique()
                
                if len(unique_crops) == 0:
                    error_msg = f"Skipping {csv_file.name}: No valid crops found."
                    print(f"   {error_msg}")
                    processing_errors.append(error_msg)
                    continue
                
                print(f"   Found {len(unique_crops)} unique crops")
                
                # Create Excel file name
                base_name = csv_file.stem.replace('_market_data', '')
                excel_filename = f"{base_name}_crops_data.xlsx"
                excel_path = output_path / excel_filename
                
                # Create Excel file with multiple sheets
                with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                    sheets_created = 0
                    
                    for crop in unique_crops:
                        # Filter data for current crop
                        crop_data = df[df['Commodity'] == crop].copy()
                        
                        if crop_data.empty:
                            continue
                        
                        # Create safe sheet name (Excel sheet names have restrictions)
                        sheet_name = create_safe_sheet_name(crop)
                        
                        try:
                            # Write crop data to sheet
                            crop_data.to_excel(writer, index=False, sheet_name=sheet_name)
                            sheets_created += 1
                            print(f"     Sheet '{sheet_name}': {len(crop_data)} records")
                        except Exception as e:
                            print(f"     Error creating sheet for '{crop}': {e}")
                    
                    total_crop_sheets += sheets_created
                
                print(f"   Created Excel file: {excel_filename}")
                print(f"   Total sheets created: {sheets_created}")
                total_excel_files += 1
                
            except Exception as e:
                error_msg = f"Error processing {csv_file.name}: {str(e)}"
                print(f"   {error_msg}")
                processing_errors.append(error_msg)
                continue
        
        # Print summary
        print("\n" + "=" * 70)
        print("PROCESSING SUMMARY")
        print("=" * 70)
        print(f"Successfully processed: {total_excel_files} market files")
        print(f"Total crop sheets created: {total_crop_sheets}")
        print(f"Excel files saved in: {output_path}")
        
        if processing_errors:
            print(f"\nWarnings/Errors encountered: {len(processing_errors)}")
            for error in processing_errors:
                print(f"  - {error}")
        
        # Create overall summary
        create_processing_summary(input_path, output_path, total_excel_files, total_crop_sheets, processing_errors)
        
        return True
        
    except Exception as e:
        print(f"Fatal error accessing directory: {str(e)}")
        return False

def create_safe_sheet_name(crop_name):
    """
    Create a safe sheet name for Excel (max 31 chars, no special characters)
    """
    # Remove or replace invalid characters for Excel sheet names
    invalid_chars = [':', '\\', '/', '?', '*', '[', ']']
    safe_name = str(crop_name)
    
    for char in invalid_chars:
        safe_name = safe_name.replace(char, '_')
    
    # Remove any other problematic characters
    safe_name = re.sub(r'[^\w\s-]', '_', safe_name)
    
    # Truncate to 31 characters (Excel limit)
    safe_name = safe_name[:31]
    
    # Remove trailing spaces or underscores
    safe_name = safe_name.strip(' _')
    
    # Ensure name is not empty
    if not safe_name:
        safe_name = "Unknown_Crop"
    
    return safe_name

def create_processing_summary(input_dir, output_dir, excel_files_count, total_sheets, errors=None):
    """
    Create a summary file of the processing results
    """
    try:
        summary_data = {
            'Processing_Date': [pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')],
            'Input_Directory': [str(input_dir)],
            'Output_Directory': [str(output_dir)],
            'Excel_Files_Created': [excel_files_count],
            'Total_Crop_Sheets': [total_sheets],
            'Errors_Count': [len(errors) if errors else 0],
            'Status': ['Completed Successfully' if not errors else 'Completed with Warnings']
        }
        
        summary_df = pd.DataFrame(summary_data)
        summary_path = output_dir / 'crop_processing_summary.csv'
        summary_df.to_csv(summary_path, index=False)
        print(f"Processing summary saved: {summary_path}")
        
        # Also create error log if there were errors
        if errors:
            error_path = output_dir / 'processing_errors.log'
            with open(error_path, 'w') as f:
                f.write(f"Processing Errors - {pd.Timestamp.now()}\n")
                f.write("=" * 50 + "\n\n")
                for i, error in enumerate(errors, 1):
                    f.write(f"{i}. {error}\n")
            print(f"Error log saved: {error_path}")
        
    except Exception as e:
        print(f"Could not create processing summary: {str(e)}")

def interactive_mode():
    """
    Interactive mode for user input
    """
    print("=" * 80)
    print("CROP DATA EXCEL SHEET GENERATOR")
    print("=" * 80)
    print("This script creates Excel files with separate sheets for each crop")
    print("from your market CSV files.")
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
        input_dir = input("Enter the directory containing market CSV files: ").strip()
    
    # Get output directory
    output_choice = input("Use default output directory? (y/n): ").strip().lower()
    if output_choice in ['y', 'yes', '']:
        output_dir = defaults['output']
    else:
        output_dir = input("Enter output directory for Excel files: ").strip()
    
    print("\n" + "=" * 80)
    print("PROCESSING MARKET CSV FILES...")
    print("=" * 80)
    
    # Process the files
    success = create_crop_sheets_from_market_csvs(input_dir, output_dir)
    
    if success:
        print("\nProcessing completed successfully!")
    else:
        print("\nProcessing failed. Please check the error messages above.")

def command_line_mode():
    """
    Command line argument parsing
    """
    parser = argparse.ArgumentParser(
        description='Convert market CSV files to Excel files with crop sheets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python crop_excel_generator.py
  python crop_excel_generator.py -i ./data/market_csvs -o ./output
  python crop_excel_generator.py --input /path/to/csvs --output /path/to/excel
        '''
    )
    
    defaults = get_default_paths()
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        default=str(defaults['input']),
        help=f'Input directory containing CSV files (default: {defaults["input"]})'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str, 
        default=str(defaults['output']),
        help=f'Output directory for Excel files (default: {defaults["output"]})'
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
        success = create_crop_sheets_from_market_csvs(args.input, args.output)
        sys.exit(0 if success else 1)

# Convenience functions for direct usage
def process_market_csvs(input_directory, output_directory=None):
    """
    Direct function for processing - use this for direct calls
    
    Usage:
    process_market_csvs('./data/market_csvs', './output')
    """
    return create_crop_sheets_from_market_csvs(input_directory, output_directory)

def process_with_defaults():
    """
    Process using default directory structure
    """
    defaults = get_default_paths()
    return create_crop_sheets_from_market_csvs(defaults['input'], defaults['output'])

if __name__ == "__main__":
    # Check if command line arguments were provided
    if len(sys.argv) > 1:
        command_line_mode()
    else:
        interactive_mode()
