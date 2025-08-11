# Backtest Folder Structure Enhancement

## Overview
This enhancement changes freqtrade's backtest output from creating zip files to creating organized folder structures that contain all backtest artifacts.

## Before (Zip Structure)
```
user_data/backtest_results/
├── backtest-result-2025-08-08_17-10-34.zip          # JSON + config + strategy + market data
├── backtest-result-2025-08-08_17-10-34.meta.json   # Metadata (separate)
├── console-Strategy001-5m-2025-08-08_17-10-34.md   # Console output (separate)
├── visual_analysis/                                  # Visual files (separate directory)
│   ├── dashboard-Strategy001-5m-2025-08-08_17-10-34.html
│   ├── pair-BTC_USDT-Strategy001-5m-2025-08-08_17-10-34.html
│   ├── pair-ETH_USDT-Strategy001-5m-2025-08-08_17-10-34.html
│   └── pair-XRP_USDT-Strategy001-5m-2025-08-08_17-10-34.html
└── .last_result.json
```

## After (Folder Structure)
```
user_data/backtest_results/
├── backtest-result-2025-08-08_17-10-34/             # 📁 All files organized in one folder
│   ├── backtest-result-2025-08-08_17-10-34.json         # 📊 Backtest results
│   ├── backtest-result-2025-08-08_17-10-34.meta.json   # 📋 Metadata
│   ├── backtest-result-2025-08-08_17-10-34_config.json  # ⚙️ Configuration used
│   ├── backtest-result-2025-08-08_17-10-34_Strategy001.py # 🤖 Strategy file
│   ├── backtest-result-2025-08-08_17-10-34_market_change.feather # 📈 Market data
│   ├── console-Strategy001-5m-2025-08-08_17-10-34.md    # 📝 Console report
│   └── visual_analysis/                                  # 🎨 Visual analysis files
│       ├── dashboard-Strategy001-5m-2025-08-08_17-10-34.html
│       ├── pair-BTC_USDT-Strategy001-5m-2025-08-08_17-10-34.html
│       ├── pair-ETH_USDT-Strategy001-5m-2025-08-08_17-10-34.html
│       └── pair-XRP_USDT-Strategy001-5m-2025-08-08_17-10-34.html
└── .last_result.json
```

## Benefits

✅ **Organized**: All related files for a backtest are in one folder  
✅ **No Zip Files**: Direct access to all files without extraction  
✅ **Easy Navigation**: Clear folder structure for each backtest run  
✅ **Better Version Control**: Individual files can be tracked separately  
✅ **Simplified Sharing**: Copy entire folder to share complete backtest  
✅ **Enhanced Visual Analysis**: All reports and visualizations in context  

## What Changed

### Core Files Modified:
1. `freqtrade/optimize/optimize_reports/bt_storage.py` - Creates folder instead of zip
2. `freqtrade/optimize/optimize_reports/bt_output.py` - Console markdown uses folder
3. `freqtrade/optimize/backtesting.py` - Captures results folder path
4. `freqtrade/rpc/api_server/api_backtest.py` - Updated for folder structure

### Key Features:
- **Automatic Integration**: Console markdown and visual analysis are automatically included
- **Error Handling**: Robust error handling ensures backtest storage succeeds even if reports fail
- **Backward Compatibility**: Existing code continues to work
- **Same Structure**: All the same files are created, just better organized

## Testing

The changes have been tested and verified to:
- ✅ Create organized folder structure
- ✅ Include all necessary backtest files
- ✅ Generate console markdown in the folder
- ✅ Place visual analysis files in the folder  
- ✅ Maintain existing functionality
- ✅ Handle errors gracefully
- ✅ **Fix duplication issue** - Visual analysis files are no longer created in both locations

## Usage

No changes needed to existing commands:
```bash
freqtrade backtesting --strategy YourStrategy --export trades
```

This will now create an organized folder with all backtest outputs instead of a zip file.
