import pandas as pd
import os
from openpyxl import Workbook
import re

def create_crop_sheets_from_market_csvs(input_directory, output_directory=None):
    """
    Process each market CSV file and create Excel files with separate sheets for each crop.
    
    Parameters:
    input_directory (str): Directory containing market CSV files
    output_directory (str): Directory to save Excel files (optional, defaults to input_directory)
    """
    
    # Strip quotes if present
    input_directory = input_directory.strip('"\'')
    if output_directory:
        output_directory = output_directory.strip('"\'')
    else:
        output_directory = input_directory
    
    # Create output directory if different and doesn't exist
    if output_directory != input_directory and not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"Created output directory: {output_directory}")
    
    try:
        # List all CSV files in the directory (excluding summary file)
        all_files = [f for f in os.listdir(input_directory) if f.endswith('.csv')]
        csv_files = [f for f in all_files if f != 'markets_summary.csv']
        
        if not csv_files:
            print("❌ No market CSV files found in the directory.")
            return
        
        print(f"📁 Found {len(csv_files)} market CSV files to process.")
        print("=" * 70)
        
        total_excel_files = 0
        total_crop_sheets = 0
        
        for csv_file in csv_files:
            file_path = os.path.join(input_directory, csv_file)
            print(f"\n🔄 Processing: {csv_file}")
            
            try:
                # Load the CSV file
                df = pd.read_csv(file_path)
                print(f"   📊 Records loaded: {len(df)}")
                
                # Check if 'Commodity' column exists
                if 'Commodity' not in df.columns:
                    print(f"   ⚠️  Skipping {csv_file}: 'Commodity' column not found.")
                    print(f"   Available columns: {list(df.columns)}")
                    continue
                
                # Get unique crops/commodities
                unique_crops = df['Commodity'].unique()
                unique_crops = [crop for crop in unique_crops if pd.notna(crop)]  # Remove NaN values
                
                if not unique_crops:
                    print(f"   ⚠️  Skipping {csv_file}: No valid crops found.")
                    continue
                
                print(f"   🌾 Found {len(unique_crops)} unique crops")
                
                # Create Excel file name
                base_name = csv_file.replace('.csv', '').replace('_market_data', '')
                excel_filename = f"{base_name}_crops_data.xlsx"
                excel_path = os.path.join(output_directory, excel_filename)
                
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
                        
                        # Write crop data to sheet
                        crop_data.to_excel(writer, index=False, sheet_name=sheet_name)
                        sheets_created += 1
                        
                        print(f"     ✓ Sheet '{sheet_name}': {len(crop_data)} records")
                    
                    total_crop_sheets += sheets_created
                
                print(f"   🎉 Created Excel file: {excel_filename}")
                print(f"   📋 Total sheets created: {sheets_created}")
                total_excel_files += 1
                
            except Exception as e:
                print(f"   ❌ Error processing {csv_file}: {str(e)}")
                continue
        
        print("\n" + "=" * 70)
        print("📈 PROCESSING SUMMARY")
        print("=" * 70)
        print(f"✅ Successfully processed: {total_excel_files} market files")
        print(f"📊 Total crop sheets created: {total_crop_sheets}")
        print(f"📁 Excel files saved in: {output_directory}")
        
        # Create overall summary
        create_processing_summary(input_directory, output_directory, total_excel_files, total_crop_sheets)
        
    except Exception as e:
        print(f"❌ Error accessing directory: {str(e)}")

def create_safe_sheet_name(crop_name):
    """
    Create a safe sheet name for Excel (max 31 chars, no special characters)
    """
    # Remove or replace invalid characters for Excel sheet names
    invalid_chars = [':', '\\', '/', '?', '*', '[', ']']
    safe_name = str(crop_name)
    
    for char in invalid_chars:
        safe_name = safe_name.replace(char, '_')
    
    # Truncate to 31 characters (Excel limit)
    safe_name = safe_name[:31]
    
    # Remove trailing spaces or underscores
    safe_name = safe_name.strip(' _')
    
    # Ensure name is not empty
    if not safe_name:
        safe_name = "Unknown_Crop"
    
    return safe_name

def create_processing_summary(input_dir, output_dir, excel_files_count, total_sheets):
    """
    Create a summary file of the processing results
    """
    try:
        summary_data = {
            'Processing_Date': [pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')],
            'Input_Directory': [input_dir],
            'Output_Directory': [output_dir],
            'Excel_Files_Created': [excel_files_count],
            'Total_Crop_Sheets': [total_sheets],
            'Status': ['Completed Successfully']
        }
        
        summary_df = pd.DataFrame(summary_data)
        summary_path = os.path.join(output_dir, 'crop_processing_summary.csv')
        summary_df.to_csv(summary_path, index=False)
        print(f"📋 Processing summary saved: crop_processing_summary.csv")
        
    except Exception as e:
        print(f"⚠️  Could not create processing summary: {str(e)}")

def process_single_market_file(csv_file_path, output_directory=None):
    """
    Process a single market CSV file and create Excel with crop sheets
    
    Parameters:
    csv_file_path (str): Path to the market CSV file
    output_directory (str): Directory to save Excel file (optional)
    """
    
    input_dir = os.path.dirname(csv_file_path)
    if not output_directory:
        output_directory = input_dir
    
    csv_filename = os.path.basename(csv_file_path)
    
    # Temporarily change to process just this file
    temp_dir = os.path.join(input_dir, 'temp_single_file')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Copy file to temp directory
    import shutil
    temp_file_path = os.path.join(temp_dir, csv_filename)
    shutil.copy2(csv_file_path, temp_file_path)
    
    # Process the single file
    create_crop_sheets_from_market_csvs(temp_dir, output_directory)
    
    # Cleanup
    shutil.rmtree(temp_dir)

def main():
    """
    Main function with user interaction
    """
    print("=" * 80)
    print("🌾 CROP DATA EXCEL SHEET GENERATOR")
    print("=" * 80)
    print("This script creates Excel files with separate sheets for each crop")
    print("from your market CSV files.")
    print()
    
    # Get input directory
    input_dir = input("Enter the directory containing market CSV files: ").strip()
    
    # Ask for output directory (optional)
    output_choice = input("\nUse same directory for output? (y/n): ").strip().lower()
    
    if output_choice in ['n', 'no']:
        output_dir = input("Enter output directory for Excel files: ").strip()
    else:
        output_dir = None
    
    print("\n" + "=" * 80)
    print("🔄 PROCESSING MARKET CSV FILES...")
    print("=" * 80)
    
    # Process the files
    create_crop_sheets_from_market_csvs(input_dir, output_dir)

# Direct usage functions
def process_market_csvs(input_directory, output_directory=None):
    """
    Direct function for processing - use this for direct calls
    
    Usage:
    process_market_csvs('C:/path/to/market_csvs', 'C:/path/to/output')
    """
    create_crop_sheets_from_market_csvs(input_directory, output_directory)

if __name__ == "__main__":
    main()
