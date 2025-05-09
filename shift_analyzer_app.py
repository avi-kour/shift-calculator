import streamlit as st
import pandas as pd
from io import BytesIO
# import xlsxwriter
from victory_hours import load_raw, analyze_shift, parse_datetime

def process_shifts(file):
    """Process the uploaded file and return the analysis results."""
    # Save the uploaded file to a temporary location
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file.read())
        temp_file_path = temp_file.name

    # Load raw data using the logic from victory_hours.py
    shifts = load_raw(temp_file_path)

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

    records = [{
        "שם עובד": emp,
        "מס שעות רגילות": round(d["regular"], 2),
        "מס שעות 125 אחוז": round(d["ot125"], 2),
        "מס שעות 150 אחוז": round(d["ot150"], 2),
        "סהכ שעות": round(d["regular"] + d["ot125"] + d["ot150"], 2),
        "מס ימי עבודה": len(d["days"])
    } for emp, d in agg.items()]

    return pd.DataFrame(records)

# Streamlit app
st.title("Shift Analyzer")

uploaded_file = st.file_uploader("Upload a shift file (CSV or Excel):", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    with st.spinner("Processing..."):
        result_df = process_shifts(uploaded_file)

    st.success("Analysis complete!")
    st.dataframe(result_df)

    # Create an Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        result_df.to_excel(writer, index=False, sheet_name="סיכום")
    excel_data = output.getvalue()

    # Download button
    st.download_button(
        label="Download Results as Excel",
        data=excel_data,
        file_name="shift_analysis_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
