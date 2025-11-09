#!/usr/bin/env python3

import sys, os, csv, math
from datetime import datetime, timedelta
import pandas as pd

def load_holidays(holidays_path='holidays.csv'):
    """Load Jewish holidays from a CSV file."""
    holidays = []
    try:
        with open(holidays_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header row
            for row in reader:
                if row and len(row) >= 2:
                    date_str, description = row[0], row[1]
                    try:
                        holiday_date = datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
                        holidays.append(holiday_date)
                    except ValueError:
                        print(f"Warning: Could not parse date '{date_str}' for holiday '{description}'")
    except FileNotFoundError:
        print(f"Warning: Holiday file '{holidays_path}' not found. Using default holidays.")
        return []
    
    return holidays

# Load holidays when module is imported
HOLIDAYS = load_holidays()

# ---------- HELPER FUNCTIONS ----------
def parse_datetime(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str.strip()} {time_str.strip()}", "%d/%m/%Y %H:%M:%S")


def get_overtime_windows(start_dt: datetime) -> list:
    """Generate overtime windows for holidays and Saturdays in the same week/month."""
    overtime_windows = []

    # Add holiday windows
    for holiday in HOLIDAYS:
        eve_start = datetime.combine(holiday - timedelta(days=1), datetime.strptime("18:00:00", "%H:%M:%S").time())
        eve_end = datetime.combine(holiday, datetime.strptime("18:00:00", "%H:%M:%S").time())
        overtime_windows.append((eve_start, eve_end))

    # Add Saturday windows
    current_date = start_dt.date().replace(day=1)  # Start from the first day of the month
    while current_date.month == start_dt.month:
        if current_date.weekday() == 5:  # Saturday
            eve_start = datetime.combine(current_date - timedelta(days=1), datetime.strptime("18:00:00", "%H:%M:%S").time())
            eve_end = datetime.combine(current_date, datetime.strptime("18:00:00", "%H:%M:%S").time())
            overtime_windows.append((eve_start, eve_end))
        current_date += timedelta(days=1)

    return overtime_windows

def calculate_overtime_hours(start: datetime, end: datetime, windows: list) -> float:
    """Calculate total hours overlapping with overtime windows without double-counting."""
    ot_hours = 0.0
    current_start = start

    for win_start, win_end in sorted(windows):
        if current_start >= end:
            break  # No more overlap possible

        if win_end <= current_start:
            continue  # Skip windows that end before the current start

        overlap_start = max(current_start, win_start)
        overlap_end = min(end, win_end)

        if overlap_start < overlap_end:
            ot_hours += (overlap_end - overlap_start).total_seconds() / 3600
            current_start = overlap_end  # Move the start forward to avoid double-counting

    return ot_hours

def calculate_shift_hours(duration: float, ot150: float, start_dt: datetime) -> tuple:
    """Calculate regular, OT125, and OT150 hours based on shift limits."""
    regular_limit = 7 if start_dt.time() >= datetime.strptime("18:00:00", "%H:%M:%S").time() else 8
    remaining = duration - ot150

    regular = max(0.0, min(remaining, regular_limit))
    remaining -= regular
    ot125 = max(0.0, min(remaining, 2))
    remaining -= ot125
    ot150_extra = max(0.0, remaining)
    ot150_total = ot150 + ot150_extra

    return regular, ot125, ot150_total

def apply_deduction(regular: float, ot125: float, ot150: float, duration: float) -> tuple:
    """Apply a 0.5-hour deduction if the shift duration is 6.5 hours or more."""
    if duration < 6.5:
        return regular, ot125, ot150

    deduction = 0.5
    if ot150 >= deduction:
        ot150 -= deduction
    else:
        deduction -= ot150
        ot150 = 0.0
        if ot125 >= deduction:
            ot125 -= deduction
        else:
            deduction -= ot125
            ot125 = 0.0
            regular = max(0.0, regular - deduction)

    return regular, ot125, ot150

# ---------- CORE LOGIC PER SHIFT ----------
def analyze_shift(start_dt: datetime, end_dt: datetime) -> tuple:
    """Analyze a shift and return (regular, ot125, ot150, workday_date)."""
    if end_dt <= start_dt:
        raise ValueError("End time must be after start time.")
        # end_dt += timedelta(days=1)
    duration = (end_dt - start_dt).total_seconds() / 3600  # total hours

    # Get overtime windows
    overtime_windows = get_overtime_windows(start_dt)

    # Calculate hours in overtime windows
    ot150 = calculate_overtime_hours(start_dt, end_dt, overtime_windows)

    # Calculate shift hours
    regular, ot125, ot150_total = calculate_shift_hours(duration, ot150, start_dt)

    # Apply deduction for long shifts
    regular, ot125, ot150_total = apply_deduction(regular, ot125, ot150_total, duration)

    return regular, ot125, ot150_total, start_dt.date()

# ---------- LOAD RAW FILE ----------
def load_raw_new_format(path: str) -> list:
    """
    Parse the new XLS format (October 2025) with chunked employee sections.
    
    Structure per employee:
    - Row: Employee name (col 8) + "עובד:" (col 9)
    - Row: Column headers (סה"כ, 200%, 175%, 150%, 125%, 100%, יום, יציאה, כניסה, משמרת)
    - Rows: Shift data with entry (col 8) and exit (col 7) datetimes
    - Row: Summary row (סה"כ:)
    
    We ignore pre-calculated percentages and only use entry/exit times.
    """
    df = pd.read_excel(path, engine='xlrd', header=None)
    shifts = []
    current_employee = None
    
    for idx, row in df.iterrows():
        row_values = [str(v) if pd.notna(v) else '' for v in row.values]
        
        # Check if this is an employee name row (has 'עובד:' in column 9)
        if len(row_values) > 9 and row_values[9] == 'עובד:':
            # Employee name is in column 8
            emp_name_raw = row_values[8].strip()
            # Keep full name with ID: "11 - איליי", "32 - נור סאסין", "מרינה"
            current_employee = emp_name_raw
            continue
        
        # Check if this is a header row (skip it)
        if 'כניסה' in row_values and 'יציאה' in row_values:
            continue
        
        # Check if this is a summary row (skip it)
        if 'סה"כ:' in row_values or 'כמות משמרות:' in row_values:
            continue
        
        # Try to parse shift data
        # Shift rows have datetime values: exit in col 7, entry in col 8
        if current_employee and len(row_values) > 8:
            try:
                exit_val = row_values[7]
                entry_val = row_values[8]
                
                # Check if both have datetime format (YYYY-MM-DD HH:MM:SS)
                if (exit_val and entry_val and 
                    '-' in exit_val and ':' in exit_val and 
                    '-' in entry_val and ':' in entry_val):
                    
                    # Parse the datetime values
                    entry_dt = pd.to_datetime(entry_val)
                    exit_dt = pd.to_datetime(exit_val)
                    
                    shifts.append({
                        "employee": current_employee,
                        "date_in": entry_dt.strftime("%d/%m/%Y"),
                        "time_in": entry_dt.strftime("%H:%M:%S"),
                        "date_out": exit_dt.strftime("%d/%m/%Y"),
                        "time_out": exit_dt.strftime("%H:%M:%S"),
                    })
            except (ValueError, IndexError):
                # Skip rows that don't have valid datetime values
                pass
    
    return shifts


def load_raw_old_format(rows: list) -> list:
    """
    Parse the old format with 'קוד עובד' sections.
    """
    indices = [i for i, r in enumerate(rows) if r and str(r[0]).startswith("קוד עובד")]
    shifts = []
    for idx_num, emp_idx in enumerate(indices):
        row_emp = rows[emp_idx]
        emp_name = row_emp[2].split(":")[-1].strip() if len(row_emp) >= 3 else "לא ידוע"
        next_idx = indices[idx_num + 1] if idx_num + 1 < len(indices) else len(rows)
        for j in range(emp_idx + 2, next_idx):
            r = rows[j]
            if len(r) < 6 or not str(r[0]).strip():
                continue
            try:
                datetime.strptime(str(r[0]).strip(), "%d/%m/%Y")
            except Exception:
                continue
            if not str(r[3]).strip() or not str(r[5]).strip():
                continue
            shifts.append({
                "employee": emp_name,
                "date_in": str(r[0]).strip(),
                "time_in": str(r[3]).strip(),
                "date_out": str(r[4]).strip(),
                "time_out": str(r[5]).strip(),
            })
    return shifts


def load_raw(path: str) -> list:
    """
    Load raw shift data from file, auto-detecting format.
    Supports both old format (with 'קוד עובד') and new format (October 2025).
    """
    ext = os.path.splitext(path)[1].lower()
    
    # Try new format first for XLS/XLSX files
    if ext in (".xlsx", ".xls"):
        try:
            # Try new format
            shifts = load_raw_new_format(path)
            if shifts:
                return shifts
        except Exception:
            pass
        
        # Fall back to old format
        try:
            df = pd.read_excel(path, header=None, dtype=str, engine='xlrd' if ext == '.xls' else None)
        except Exception:
            # Try with openpyxl engine for .xlsx
            df = pd.read_excel(path, header=None, dtype=str, engine='openpyxl')
        rows = df.values.tolist()
        return load_raw_old_format(rows)
    
    else:  # CSV - use old format
        with open(path, newline='', encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        return load_raw_old_format(rows)


def process_file_to_dataframe(file_path: str) -> pd.DataFrame:
    """
    Complete processing pipeline: load file, analyze shifts, aggregate results.
    Returns a pandas DataFrame ready for display or export.
    
    Args:
        file_path: Path to the shift file (CSV, XLS, or XLSX)
    
    Returns:
        DataFrame with columns: שם עובד, מס שעות רגילות, מס שעות 125 אחוז, 
        מס שעות 150 אחוז, סהכ שעות, מס ימי עבודה
    """
    # Load raw shifts
    shifts = load_raw(file_path)
    
    # Aggregate by employee
    agg = {}
    for s in shifts:
        start_dt = parse_datetime(s["date_in"], s["time_in"])
        end_dt = parse_datetime(s["date_out"], s["time_out"])
        reg, ot125, ot150, day = analyze_shift(start_dt, end_dt)
        emp = s["employee"]
        if emp not in agg:
            agg[emp] = {"regular": 0.0, "ot125": 0.0, "ot150": 0.0, "days": set()}
        agg[emp]["regular"] += reg
        agg[emp]["ot125"] += ot125
        agg[emp]["ot150"] += ot150
        agg[emp]["days"].add(day)
    
    # Create records for DataFrame
    records = [{
        "שם עובד": emp,
        "מס שעות רגילות": round(d["regular"], 2),
        "מס שעות 125 אחוז": round(d["ot125"], 2),
        "מס שעות 150 אחוז": round(d["ot150"], 2),
        "סהכ שעות": round(d["regular"] + d["ot125"] + d["ot150"], 2),
        "מס ימי עבודה": len(d["days"])
    } for emp, d in agg.items()]
    
    return pd.DataFrame(records)

def main():
    if len(sys.argv) < 3:
        print("Usage: python victory_hours.py input_file output_file")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    shifts = load_raw(input_path)

    agg = {}
    for s in shifts:
        start_dt = parse_datetime(s["date_in"], s["time_in"])
        end_dt   = parse_datetime(s["date_out"], s["time_out"])
        reg, ot125, ot150, day = analyze_shift(start_dt, end_dt)
        emp = s["employee"]
        if emp not in agg:
            agg[emp] = {"regular": 0.0, "ot125": 0.0, "ot150": 0.0, "days": set()}
        if emp =='וואליד':
            print(f"DEBUG: {emp} {day} {start_dt} {end_dt} reg={reg} ot125={ot125} ot150={ot150} total={reg + ot125 + ot150}")
        agg[emp]["regular"] += reg
        agg[emp]["ot125"]   += ot125
        agg[emp]["ot150"]   += ot150
        agg[emp]["days"].add(day)

    records = [{
        "שם עובד": emp,
        "מס שעות רגילות": round(d["regular"], 2),
        "מס שעות 125 אחוז": round(d["ot125"], 2),
        "מס שעות 150 אחוז": round(d["ot150"], 2),
        "סהכ שעות": round(d["regular"] + d["ot125"] + d["ot150"], 2),
        "מס ימי עבודה": len(d["days"])
    } for emp, d in agg.items()]

    df = pd.DataFrame(records)
    df.to_excel(output_path, index=False, sheet_name="סיכום")
    print(f"✓ Summary saved to {output_path}")

if __name__ == "__main__":
    main()
