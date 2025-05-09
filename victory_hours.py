#!/usr/bin/env python3
"""
victory_hours.py  -  Monthly shift summarizer for "ויקטורי"

USAGE:
    python victory_hours.py input_file output_file

The script reads a shift report (CSV or Excel), applies the business
rules below, and writes an Excel summary ready for payroll.

Business rules implemented
--------------------------
1. Each row describes one shift with columns:
       A: Date-In   (DD/MM/YYYY)
       D: Time-In   (HH:MM:SS)
       E: Date-Out
       F: Time-Out
   The script auto-detects the header/delimiter pattern used in the
   reports you export.

2. If a shift crosses midnight, it is *not* split; total hours are
   counted in the day of Time-In.

3. Pay rates:
       • Regular hours: up to 8 h.
       • If shift starts ≥ 18:00 → limit is 7 h.
       • First   2 h  beyond limit → OT 125 %.
       • Remaining hours       → OT 150 %.
       • All time between Friday 18:00 ↔ Saturday 18:00 → 150 %.
       • Jewish holidays (array inside this script) treated as saturday
         (from 18:00) → 150 %.

4. If total shift ≥ 6.5 h → deduct 0.5 h from *most expensive* bucket:
       first 150 %, then 125 %, finally regular.

5. Final summary per employee:
       • Regular hours
       • OT 125 %
       • OT 150 %
       • Distinct workdays

You can adapt the HOLIDAYS set near the top for future months.
"""

import sys, os, csv, math
from datetime import datetime, timedelta
import pandas as pd

HOLIDAYS = [
    datetime(2025, 4, 13).date(),  #'Pesach I'
    datetime(2025, 4, 19).date(),  #'Pesach VII'
    datetime(2025, 5, 1).date(),   #'Atzmaut'
    datetime(2025, 6, 2).date(),   #'Shavuot'
    datetime(2025, 9, 23).date(),  #'Rosh Hashana 5786'
    datetime(2025, 9, 24).date(),  #'Rosh Hashana II'
    datetime(2025, 10, 2).date(),  #'Yom Kippur'
    datetime(2025, 10, 7).date(),  #'Sukkot I'
    datetime(2025, 10, 14).date()  #'Shmini Atzeret'
]

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
def load_raw(path: str) -> list:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=None, dtype=str)
        rows = df.values.tolist()
    else:  # assume CSV
        with open(path, newline='', encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    # Detect employee sections
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
