# Shift Calculator for Victory Supermarkets

A payroll calculation tool designed for Victory Supermarkets (ויקטורי) to automate the complex process of computing employee work hours and overtime according to Israeli labor laws.

## Overview

This application processes employee shift data and calculates regular hours and overtime according to specific business rules. It handles special cases like overnight shifts, weekend work, and holiday pay rates automatically.

## Features

- **CSV/Excel Import**: Process data directly from your time-tracking system
- **Automatic Overtime Calculation**: Handles the complexity of different overtime rates
- **Weekend & Holiday Detection**: Automatically applies premium rates for weekends and Jewish holidays
- **Break Deduction**: Automatically handles required break times
- **Employee Summaries**: Generates per-employee totals for payroll processing
- **Excel Export**: Creates a ready-to-use report for payroll systems

## Technical Details

### Core Script: `victory_hours.py`

#### Usage
```
python victory_hours.py input_file output_file
```

#### Business Rules Implemented

1. **Input Format:** Each row describes one shift with columns:
   - A: Date-In (DD/MM/YYYY)
   - D: Time-In (HH:MM:SS)
   - E: Date-Out
   - F: Time-Out
   
   The script auto-detects the header/delimiter pattern used in the reports you export.

2. **Overnight Shifts:** If a shift crosses midnight, it is *not* split; total hours are counted in the day of Time-In.

3. **Pay Rates:**
   - Regular hours: up to 8 hours
   - If shift starts ≥ 18:00 → limit is 7 hours
   - First 2 hours beyond limit → OT 125%
   - Remaining hours → OT 150%
   - All time between Friday 18:00 ↔ Saturday 18:00 → 150%
   - Jewish holidays (defined in the script) treated as Saturday (from 18:00) → 150%

4. **Break Deduction:** If total shift ≥ 6.5 hours → deduct 0.5 hour from *most expensive* bucket:
   - First 150%, then 125%, finally regular

5. **Final Summary:** Per employee:
   - Regular hours
   - OT 125%
   - OT 150%
   - Distinct workdays

## Configuration

### Jewish Holidays

The application uses a configurable list of Jewish holidays stored in `holidays.csv`. This file contains dates and descriptions of holidays when premium pay rates apply.

#### Holiday CSV Format:
```
Date,Description
13/04/2025,Pesach I
19/04/2025,Pesach VII
```

To update holidays:
1. Edit `holidays.csv` in any text editor or spreadsheet program
2. Enter dates in DD/MM/YYYY format
3. Add a description for each holiday

The web interface allows viewing all configured holidays in the sidebar.

## Requirements

- Python 3.6+
- pandas
- openpyxl

## Installation

1. Clone this repository
2. Install required packages:
   ```
   pip install pandas openpyxl
   ```

## Example

```
python victory_hours.py March2025_TimeReport.xlsx March2025_PayrollSummary.xlsx
```

## License

This software is proprietary and intended for use by Victory Supermarkets.