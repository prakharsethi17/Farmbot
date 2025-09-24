import os
import pandas as pd
from datetime import datetime

def analyze_top_priced_crops_from_excel_directory(input_directory, output_filename="top25_crops_analysis.txt"):
    """
    Analyze Excel files where each file represents a market and each sheet represents a crop
    to find top 25 consistently high-priced crops across markets and years.
    
    Parameters:
    input_directory (str): Directory containing market Excel files with crop sheets
    output_filename (str): Name of output text file (saved in current directory)
    """
    
    # Strip quotes if present
    input_directory = input_directory.strip('"\'')
    
    # Output file will be saved in current working directory
    output_file_path = os.path.join(os.getcwd(), output_filename)
    
    print("=" * 80)
    print("🌾 ANALYZING CROP PRICES FROM EXCEL FILES")
    print("=" * 80)
    print(f"Input Directory: {input_directory}")
    print(f"Output File: {output_file_path}")
    print()
    
    # Step 1: Load all Excel files and their sheets
    all_crop_data = []
    excel_files = [f for f in os.listdir(input_directory) if f.endswith('.xlsx')]
    
    if not excel_files:
        print("❌ No Excel files found in the input directory!")
        return
    
    print(f"📁 Found {len(excel_files)} Excel files to process:")
    
    total_sheets = 0
    
    for excel_file in excel_files:
        file_path = os.path.join(input_directory, excel_file)
        
        try:
            # Extract market name from filename (remove file extension and clean)
            market_name = excel_file.replace('.xlsx', '').replace('_crops_data', '').replace('_', ' ')
            
            # Load Excel file
            excel_data = pd.ExcelFile(file_path)
            sheet_names = excel_data.sheet_names
            
            print(f"  📊 {excel_file}: {len(sheet_names)} crop sheets")
            
            # Read each sheet (crop)
            for sheet_name in sheet_names:
                try:
                    df = pd.read_excel(excel_data, sheet_name=sheet_name)
                    
                    # Check for required columns
                    required_cols = ['Arrival_Date', 'Min_Price', 'Max_Price', 'Modal_Price']
                    if not all(col in df.columns for col in required_cols):
                        print(f"    ⚠ Skipping sheet '{sheet_name}': Missing required columns")
                        continue
                    
                    # Add metadata
                    df['Market'] = market_name
                    df['Commodity'] = sheet_name
                    
                    all_crop_data.append(df)
                    total_sheets += 1
                    
                except Exception as e:
                    print(f"    ❌ Error reading sheet '{sheet_name}': {str(e)}")
                    continue
        
        except Exception as e:
            print(f"  ❌ Error processing {excel_file}: {str(e)}")
            continue
    
    if not all_crop_data:
        print("❌ No valid crop data found in any Excel files!")
        return
    
    print(f"\n📈 Successfully loaded {total_sheets} crop sheets from {len(excel_files)} markets")
    
    # Step 2: Combine all data
    print("🔄 Combining and processing data...")
    combined_df = pd.concat(all_crop_data, ignore_index=True)
    print(f"Combined dataset: {len(combined_df):,} total records")
    
    # Step 3: Clean and prepare data
    # Convert dates and extract year
    combined_df['Arrival_Date'] = pd.to_datetime(combined_df['Arrival_Date'], errors='coerce')
    combined_df['Year'] = combined_df['Arrival_Date'].dt.year
    
    # Remove invalid data
    before_clean = len(combined_df)
    combined_df = combined_df.dropna(subset=['Commodity', 'Market', 'Year', 'Modal_Price'])
    combined_df = combined_df[combined_df['Modal_Price'] > 0]  # Remove zero/negative prices
    after_clean = len(combined_df)
    
    print(f"Data cleaning: {before_clean:,} → {after_clean:,} records")
    
    # Step 4: Calculate aggregated statistics
    print("📊 Calculating crop price statistics...")
    
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
    print("🎯 Identifying consistently high-priced crops...")
    
    # Calculate thresholds
    price_75th = commodity_metrics['Avg_Modal_Price'].quantile(0.75)
    price_90th = commodity_metrics['Avg_Modal_Price'].quantile(0.90)
    
    print(f"Price thresholds: 75th percentile = ₹{price_75th:.2f}, 90th percentile = ₹{price_90th:.2f}")
    
    # Filter criteria
    high_priced_crops = commodity_metrics[
        (commodity_metrics['Avg_Modal_Price'] >= price_75th) &  # High price
        (commodity_metrics['Markets_Count'] >= 1) &             # At least 1 market (since we may have few markets)
        (commodity_metrics['Years_Count'] >= 2) &               # At least 2 years for consistency
        (commodity_metrics['Total_Records'] >= 5)               # Minimum data points
    ].copy()
    
    print(f"Found {len(high_priced_crops)} crops meeting criteria")
    
    # Calculate consistency score
    high_priced_crops['Price_CV'] = (high_priced_crops['Price_Std_Dev'] / high_priced_crops['Avg_Modal_Price']) * 100
    high_priced_crops['Consistency_Score'] = (
        high_priced_crops['Avg_Modal_Price'] * 0.5 +           # 50% weight to average price
        high_priced_crops['Markets_Count'] * 100 +             # Market presence bonus
        high_priced_crops['Years_Count'] * 50 +                # Year presence bonus  
        (100 - high_priced_crops['Price_CV'].fillna(0)) * 0.2  # 20% weight to price stability
    )
    
    # Step 6: Get top 25 crops
    top_25_crops = high_priced_crops.nlargest(25, 'Consistency_Score').reset_index(drop=True)
    
    # Step 7: Generate detailed output
    print("📝 Generating detailed analysis...")
    
    with open(output_file_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("=" * 100 + "\n")
        f.write("TOP 25 CONSISTENTLY HIGH-PRICED CROPS ACROSS MARKETS AND YEARS\n")
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
        f.write("- Average modal price above 75th percentile (₹{:.2f})\n".format(price_75th))
        f.write("- Present across multiple years (minimum 2 years)\n")
        f.write("- Minimum 5 data points for statistical significance\n")
        f.write("- Ranked by consistency score considering price, market presence, and stability\n\n")
        
        # Top 25 List
        f.write("TOP 25 HIGH-PRICED CROPS:\n")
        f.write("-" * 100 + "\n")
        
        for idx, row in top_25_crops.iterrows():
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
        f.write(f"Average price of top 25 crops: ₹{top_25_crops['Avg_Modal_Price'].mean():.2f}\n")
        f.write(f"Highest priced crop: {top_25_crops.iloc[0]['Commodity']} (₹{top_25_crops.iloc[0]['Avg_Modal_Price']:.2f})\n")
        f.write(f"Most consistent crop (lowest CV): {top_25_crops.loc[top_25_crops['Price_CV'].idxmin(), 'Commodity']}\n")
        f.write(f"Most widespread crop: {top_25_crops.loc[top_25_crops['Markets_Count'].idxmax(), 'Commodity']}\n")
        
        # Market breakdown
        f.write(f"\nMARKET BREAKDOWN:\n")
        f.write("-" * 50 + "\n")
        market_summary = combined_df.groupby('Market').agg({
            'Commodity': 'nunique',
            'Modal_Price': 'mean'
        }).round(2).sort_values('Modal_Price', ascending=False)
        
        for market, stats in market_summary.iterrows():
            f.write(f"{market}: {stats['Commodity']} crops, avg price ₹{stats['Modal_Price']:.2f}\n")
    
    # Final summary
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE!")
    print("=" * 80)
    print(f"📋 Results saved to: {output_file_path}")
    print(f"🏆 Top crop: {top_25_crops.iloc[0]['Commodity']} (₹{top_25_crops.iloc[0]['Avg_Modal_Price']:.2f})")
    print(f"📊 Average price of top 25: ₹{top_25_crops['Avg_Modal_Price'].mean():.2f}")
    print(f"🏪 Markets analyzed: {combined_df['Market'].nunique()}")
    print(f"🌾 Total crops analyzed: {combined_df['Commodity'].nunique()}")

def main():
    """
    Main function for interactive usage
    """
    print("=" * 80)
    print("🌾 TOP 25 HIGH-PRICED CROPS ANALYZER (Excel Version)")
    print("=" * 80)
    
    input_dir = input("Enter directory containing crop Excel files: ").strip()
    
    # Optional: custom output filename
    custom_output = input("Enter output filename (press Enter for default 'top25_crops_analysis.txt'): ").strip()
    output_file = custom_output if custom_output else "top25_crops_analysis.txt"
    
    analyze_top_priced_crops_from_excel_directory(input_dir, output_file)

# Direct usage function
def analyze_excel_crops(input_directory, output_filename="top25_crops_analysis.txt"):
    """
    Direct function call for analysis
    
    Usage:
    analyze_excel_crops('./crop_excel_files', 'my_results.txt')
    """
    analyze_top_priced_crops_from_excel_directory(input_directory, output_filename)

if __name__ == "__main__":
    main()
