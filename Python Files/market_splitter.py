import pandas as pd
import os

def create_market_csv_files(input_file_path, output_directory_path):
    """
    Create separate CSV files for each market from the original CSV file.
    
    Parameters:
    input_file_path (str): Full path to the original CSV file
    output_directory_path (str): Full path to directory where market-specific CSV files will be saved
    """
    
    # Strip surrounding quotes if they exist
    input_file_path = input_file_path.strip('"\'')
    output_directory_path = output_directory_path.strip('"\'')
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_directory_path):
        os.makedirs(output_directory_path)
        print(f"Created directory: {output_directory_path}")
    
    try:
        # Read the original CSV file
        print(f"Loading CSV file from: {input_file_path}")
        df = pd.read_csv(input_file_path)
        print(f"Total records loaded: {len(df)}")
        
        # Display basic information about the dataset
        print(f"Columns in the dataset: {list(df.columns)}")
        
        # Check if required columns exist
        required_columns = ['State', 'District', 'Market']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            return
        
        # Display State and District info (should be same for all records)
        unique_states = df['State'].unique()
        unique_districts = df['District'].unique()
        
        print(f"State(s): {list(unique_states)}")
        print(f"District(s): {list(unique_districts)}")
        
        # Get unique markets
        unique_markets = df['Market'].unique()
        print(f"Found {len(unique_markets)} unique markets: {list(unique_markets)}")
        
        # Create separate CSV files for each market
        for market in unique_markets:
            # Filter data for the current market
            market_data = df[df['Market'] == market].copy()
            
            # Create a safe filename (remove special characters and spaces)
            safe_market_name = "".join(c for c in market if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_market_name = safe_market_name.replace(' ', '_')
            
            # Create filename
            filename = f"{safe_market_name}_market_data.csv"
            filepath = os.path.join(output_directory_path, filename)
            
            # Save the market-specific data to CSV
            market_data.to_csv(filepath, index=False)
            
            print(f"✓ Created: {filename} with {len(market_data)} records")
            
            # Display some statistics for this market
            if 'Arrival_Date' in market_data.columns:
                print(f"  - Date range: {market_data['Arrival_Date'].min()} to {market_data['Arrival_Date'].max()}")
            if 'Commodity' in market_data.columns:
                print(f"  - Unique commodities: {market_data['Commodity'].nunique()}")
            print("  " + "-" * 50)
        
        print(f"\n🎉 Successfully created {len(unique_markets)} market CSV files in: {output_directory_path}")
        
        # Create a summary file
        create_summary_file(df, output_directory_path)
        
    except FileNotFoundError:
        print(f"❌ Error: File '{input_file_path}' not found.")
        print("Please check the file path and try again.")
    except pd.errors.EmptyDataError:
        print(f"❌ Error: The file '{input_file_path}' is empty.")
    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")

def create_summary_file(df, output_directory_path):
    """
    Create a summary CSV file with statistics for each market
    """
    try:
        unique_markets = df['Market'].unique()
        summary_data = []
        
        for market in unique_markets:
            market_data = df[df['Market'] == market]
            
            summary_info = {
                'Market': market,
                'Total_Records': len(market_data),
                'State': market_data['State'].iloc[0],
                'District': market_data['District'].iloc[0]
            }
            
            # Add optional columns if they exist
            if 'Commodity' in market_data.columns:
                summary_info['Unique_Commodities'] = market_data['Commodity'].nunique()
            
            if 'Arrival_Date' in market_data.columns:
                summary_info['Date_Range_Start'] = market_data['Arrival_Date'].min()
                summary_info['Date_Range_End'] = market_data['Arrival_Date'].max()
            
            if 'Variety' in market_data.columns:
                summary_info['Unique_Varieties'] = market_data['Variety'].nunique()
            
            summary_data.append(summary_info)
        
        summary_df = pd.DataFrame(summary_data)
        summary_filepath = os.path.join(output_directory_path, 'markets_summary.csv')
        summary_df.to_csv(summary_filepath, index=False)
        print(f"📊 Created summary file: markets_summary.csv")
        
    except Exception as e:
        print(f"Warning: Could not create summary file: {str(e)}")

def main():
    """
    Main function to get user input and execute the script
    """
    print("=" * 70)
    print("🌾 AGRICULTURAL DATA - MARKET CSV GENERATOR")
    print("=" * 70)
    
    # Get input file path from user
    input_file = input("Enter the input CSV file path (with or without quotes): ").strip()
    
    # Get output directory path from user
    output_dir = input("Enter the output directory path (with or without quotes): ").strip()
    
    print("\n" + "=" * 70)
    print("PROCESSING...")
    print("=" * 70)
    
    # Create market-specific CSV files
    create_market_csv_files(input_file, output_dir)

# Alternative function for direct usage with parameters
def split_markets_by_csv(input_path, output_path):
    """
    Direct function call version - use this if you want to call the function directly
    
    Usage:
    split_markets_by_csv('/path/to/input.csv', '/path/to/output_directory')
    """
    create_market_csv_files(input_path, output_path)

if __name__ == "__main__":
    main()
