import pandas as pd
import streamlit as st
import re

st.title("CSV Matcher And Payment Calculator For Agent Data")

# File uploaders for the three CSV files
roster_file = st.file_uploader("Upload Agent Roster CSV", type=["csv"])
timers_file = st.file_uploader("Upload Timers CSV", type=["csv"])
rawhs_file = st.file_uploader("Upload Raw hs Export CSV", type=["csv"])

def check_columns(df, required_cols, df_name):
    """Check if required_cols are present in df. If not, display an error and stop execution."""
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        st.error(f"Error: The {df_name} file is missing required columns: {missing}")
        st.stop()

if roster_file and timers_file and rawhs_file:
    try:
        # Use utf-8-sig encoding to handle potential BOM issues
        roster = pd.read_csv(roster_file, encoding="utf-8-sig")
        timers = pd.read_csv(timers_file, encoding="utf-8-sig")
        raw_hs = pd.read_csv(rawhs_file, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"Error reading CSV files: {e}")
        st.stop()

    # Check for required columns (including "Client" and "Date" for Raw hs export)
    check_columns(roster, ["Agent Email", "Rate"], "Agent Roster")
    check_columns(timers, ["Hubstaff Project Names", "Team", "Pay Commodity", "Process Name (App)", "Process ID"], "Timers")
    check_columns(raw_hs, ["Work email", "Project", "Time", "Client", "Date"], "Raw hs export")

    # Normalize email columns for matching
    roster["Agent Email"] = roster["Agent Email"].astype(str).str.strip().str.lower()
    raw_hs["Work email"] = raw_hs["Work email"].astype(str).str.strip().str.lower()

    # Clean up the Rate column: remove non-numeric characters (e.g., '$') and convert to numeric
    roster["Rate"] = roster["Rate"].astype(str).str.replace("[^0-9.]", "", regex=True)
    roster["Rate"] = pd.to_numeric(roster["Rate"], errors="coerce")

    try:
        # Merge Raw hs export with Agent Roster (left join)
        merged = pd.merge(
            raw_hs,
            roster[["Agent Email", "Rate"]],
            left_on="Work email",
            right_on="Agent Email",
            how="left"
        )

        # Merge the Timers data
        merged = pd.merge(
            merged,
            timers[["Hubstaff Project Names", "Team", "Pay Commodity", "Process Name (App)", "Process ID"]],
            left_on="Project",
            right_on="Hubstaff Project Names",
            how="left"
        )

        # Drop the duplicate 'Agent Email' column if present
        if "Agent Email" in merged.columns:
            merged.drop(columns=["Agent Email"], inplace=True)

    except Exception as e:
        st.error(f"Error merging data: {e}")
        st.stop()

    # --- Perform all validations on the final merged DataFrame ---
    warnings_list = []

    # For empty checks, use fillna("") so that NaN values are treated as empty strings
    if merged["Client"].fillna("").str.strip().eq("").any():
        warnings_list.append("Some rows in the final CSV have an empty 'Client' column.")

    if merged["Hubstaff Project Names"].fillna("").str.strip().eq("").any():
        warnings_list.append("Some rows in the final CSV have an empty 'Hubstaff Project Names' column.")

    # Validate that all dates are within the current cycle
    merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    if today.day <= 15:
        start_cycle = pd.Timestamp(year=today.year, month=today.month, day=1)
        end_cycle = pd.Timestamp(year=today.year, month=today.month, day=15)
    else:
        start_cycle = pd.Timestamp(year=today.year, month=today.month, day=16)
        end_cycle = pd.Timestamp(year=today.year, month=today.month, day=1) + pd.offsets.MonthEnd(0)
    if not merged["Date"].between(start_cycle, end_cycle).all():
        warnings_list.append(
            f"Some dates in the final CSV are not within the current cycle: {start_cycle.date()} to {end_cycle.date()}."
        )

    if not merged["Work email"].fillna("").str.strip().str.lower().str.endswith("@invisible.email").all():
        warnings_list.append("Not all 'Work email' values in the final CSV have the domain @invisible.email.")

    if merged["Team"].fillna("").str.strip().eq("").any():
        warnings_list.append("Some rows in the final CSV have an empty 'Team' column.")

    # Validate Pay Commodity: not empty and must include allowed keywords
    allowed = ["operate", "qa", "lead", "incentive", "audit"]
    if merged["Pay Commodity"].fillna("").str.strip().eq("").any():
        warnings_list.append("Some rows in the final CSV have an empty 'Pay Commodity' column.")
    else:
        pattern = re.compile(r'\b(?:' + "|".join(allowed) + r')\b', re.IGNORECASE)
        invalid_pay = merged[~merged["Pay Commodity"].fillna("").str.strip().apply(lambda x: bool(pattern.search(x)))]
        if not invalid_pay.empty:
            warnings_list.append(
                "Some rows in the final CSV have an invalid 'Pay Commodity' value. It must include one of: Operate, QA, Lead, Incentive, or Audit."
            )

    if merged["Process ID"].fillna("").str.strip().eq("").any() or merged["Process Name (App)"].fillna("").str.strip().eq("").any():
        warnings_list.append("Some rows in the final CSV have an empty 'Process ID' or 'Process Name (App)' column.")

    for warning in warnings_list:
        st.warning(warning)

    # --- Compute the "Total" column in the complete merged DataFrame ---
    try:
        merged["Time_in_hours"] = pd.to_timedelta(merged["Time"], errors="coerce").dt.total_seconds() / 3600
        merged["Rate"] = pd.to_numeric(merged["Rate"], errors="coerce")
        merged["Total"] = (merged["Time_in_hours"] * merged["Rate"]).round(2)
        merged.drop(columns=["Time_in_hours"], inplace=True)
    except Exception as e:
        st.error(f"Error computing 'Total': {e}")
        st.stop()

    st.write("### Preview of Complete View:")
    st.dataframe(merged.head())

    # Download button for the complete merged CSV ("Complete view")
    complete_csv = merged.to_csv(index=False).encode('utf-8')
    st.download_button("Download Complete CSV", data=complete_csv, file_name='complete_view.csv', mime='text/csv')

    # --- Create the "Data ready for upload" CSV ---
    try:
        # Compute Hours from the Time column (in hours)
        hours_series = pd.to_timedelta(merged["Time"], errors="coerce").dt.total_seconds() / 3600
        # Build the new DataFrame with the required columns:
        # "Email", "Process ID", "Hours", "Rate" (optional), "Commodity Name"
        upload_df = pd.DataFrame({
            "Email": merged["Work email"],
            "Process ID": merged["Process ID"],
            "Hours": hours_series.round(2),
            "Rate": merged["Rate"],
            "Commodity Name": merged["Pay Commodity"]
        })
    except Exception as e:
        st.error(f"Error creating 'Data ready for upload' CSV: {e}")
        st.stop()

    st.write("### Preview of Data Ready for Upload:")
    st.dataframe(upload_df.head())

    # Download button for the "Data ready for upload" CSV
    upload_csv = upload_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Data Ready for Upload CSV", data=upload_csv, file_name='data_ready_for_upload.csv', mime='text/csv')
