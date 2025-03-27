import pandas as pd
import streamlit as st
import re

st.title("CSV Combiner for Agent Data")

# Display template links as clickable markdown
st.markdown("""
### Template Files
- [Agent Roster Template](https://docs.google.com/spreadsheets/d/1s12fMHdchSNLQ47XKuUri_36XxVw1pmJiY93xWtw8mQ/edit?gid=0#gid=0)
- [Project Timers Template](https://docs.google.com/spreadsheets/d/1JALcudxvxBBJyDGQ9ZiLgJeL-D8RTISrqHVyqULwXcg/edit?gid=0#gid=0)
- [Hubstaff Export Template](https://docs.google.com/spreadsheets/d/1eH4uR63F35XOv7C80zj7Yd1UtmGVSQILpGh2KRlrMUw/edit?gid=0#gid=0)
""")

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

        # Drop rows that are completely empty in each file
        roster.dropna(how="all", inplace=True)
        timers.dropna(how="all", inplace=True)
        raw_hs.dropna(how="all", inplace=True)
    except Exception as e:
        st.error(f"Error reading CSV files: {e}")
        st.stop()

    # Check required columns for each file.
    check_columns(roster, ["Agent Email", "Rate", "Team"], "Roster")
    check_columns(timers, ["Team", "Hubstaff Project Names", "Pay Commodity", "Process Name (App)", "Process ID"], "Timers")
    check_columns(raw_hs, ["Client", "Project", "Date", "Member", "Work email", "Time"], "Raw hs export")

    # Create lists to store warnings (each as a tuple: (summary, details))
    warnings_roster = []
    warnings_timers = []
    warnings_rawhs = []

    # ---- Pre-Merge Validations ----
    ## Roster Validations
    # (a) Check that "Agent Email" is not empty.
    empty_agent_email_idx = roster[roster["Agent Email"].fillna("").str.strip().eq("")].index
    if not empty_agent_email_idx.empty:
        warnings_roster.append(("Empty 'Agent Email'", list(empty_agent_email_idx)))
    # (b) Check that "Rate" is not empty.
    empty_rate_idx = roster[roster["Rate"].fillna("").str.strip().eq("")].index
    if not empty_rate_idx.empty:
        warnings_roster.append(("Empty 'Rate'", list(empty_rate_idx)))
    # (c) Check that "Team" is not empty.
    empty_team_roster_idx = roster[roster["Team"].fillna("").str.strip().eq("")].index
    if not empty_team_roster_idx.empty:
        warnings_roster.append(("Empty 'Team'", list(empty_team_roster_idx)))
    # (d) Validate that "Agent Email" ends with "@invisible.email"
    bad_domain_idx = roster[~roster["Agent Email"].fillna("").str.strip().str.lower().str.endswith("@invisible.email")].index
    if not bad_domain_idx.empty:
        warnings_roster.append(("Invalid Email Domain", list(bad_domain_idx)))
    # (e) Check for duplicate rates for the same user.
    dup_rate = roster.groupby("Agent Email")["Rate"].nunique()
    multi_rate_agents = dup_rate[dup_rate > 1].index
    if len(multi_rate_agents) > 0:
        agent_rows = {}
        for agent in multi_rate_agents:
            agent_rows[agent] = list(roster[roster["Agent Email"] == agent].index)
        warnings_roster.append(("Multiple Rates for Agent", agent_rows))

    ## Timers Validations
    # (a) "Team" should not be empty.
    empty_team_idx = timers[timers["Team"].fillna("").str.strip().eq("")].index
    if not empty_team_idx.empty:
        warnings_timers.append(("Empty 'Team'", list(empty_team_idx)))
    # (b) "Hubstaff Project Names" should not be empty.
    empty_proj_idx = timers[timers["Hubstaff Project Names"].fillna("").str.strip().eq("")].index
    if not empty_proj_idx.empty:
        warnings_timers.append(("Empty 'Hubstaff Project Names'", list(empty_proj_idx)))
    # (c) "Pay Commodity" should not be empty.
    empty_commodity_idx = timers[timers["Pay Commodity"].fillna("").str.strip().eq("")].index
    if not empty_commodity_idx.empty:
        warnings_timers.append(("Empty 'Pay Commodity'", list(empty_commodity_idx)))
    else:
        allowed = ["operate", "qa", "lead", "incentive", "audit"]
        pattern = re.compile(r'\b(?:' + "|".join(allowed) + r')\b', re.IGNORECASE)
        invalid_commodity_idx = timers[~timers["Pay Commodity"].fillna("").str.strip().apply(lambda x: bool(pattern.search(x)))].index
        if not invalid_commodity_idx.empty:
            warnings_timers.append(("Invalid 'Pay Commodity'", list(invalid_commodity_idx)))
    # (d) "Process ID" and "Process Name (App)" should not be empty.
    empty_process_idx = timers[
        timers["Process ID"].fillna("").str.strip().eq("") |
        timers["Process Name (App)"].fillna("").str.strip().eq("")
    ].index
    if not empty_process_idx.empty:
        warnings_timers.append(("Empty Process Details", list(empty_process_idx)))

    ## Raw hs export Validations
    # (a) "Client" should not be empty.
    empty_client_idx = raw_hs[raw_hs["Client"].fillna("").str.strip().eq("")].index
    if not empty_client_idx.empty:
        warnings_rawhs.append(("Empty 'Client'", list(empty_client_idx)))
    # (b) "Project" should not be empty.
    empty_project_idx = raw_hs[raw_hs["Project"].fillna("").str.strip().eq("")].index
    if not empty_project_idx.empty:
        warnings_rawhs.append(("Empty 'Project'", list(empty_project_idx)))
    # (c) "Date" should not be empty and must be within the current cycle.
    empty_date_idx = raw_hs[raw_hs["Date"].fillna("").str.strip().eq("")].index
    if not empty_date_idx.empty:
        warnings_rawhs.append(("Empty 'Date'", list(empty_date_idx)))
    raw_hs["Date"] = pd.to_datetime(raw_hs["Date"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    if today.day <= 15:
        start_cycle = pd.Timestamp(year=today.year, month=today.month, day=1)
        end_cycle = pd.Timestamp(year=today.year, month=today.month, day=15)
    else:
        start_cycle = pd.Timestamp(year=today.year, month=today.month, day=16)
        end_cycle = pd.Timestamp(year=today.year, month=today.month, day=1) + pd.offsets.MonthEnd(0)
    out_of_cycle_idx = raw_hs[~raw_hs["Date"].between(start_cycle, end_cycle)].index
    if not out_of_cycle_idx.empty:
        warnings_rawhs.append(("Date Outside Cycle", list(out_of_cycle_idx)))
    # (d) "Member" should not be empty.
    empty_member_idx = raw_hs[raw_hs["Member"].fillna("").str.strip().eq("")].index
    if not empty_member_idx.empty:
        warnings_rawhs.append(("Empty 'Member'", list(empty_member_idx)))
    # (e) "Work email" should not be empty and must end with "@invisible.email"
    empty_work_email_idx = raw_hs[raw_hs["Work email"].fillna("").str.strip().eq("")].index
    if not empty_work_email_idx.empty:
        warnings_rawhs.append(("Empty 'Work email'", list(empty_work_email_idx)))
    invalid_work_email_idx = raw_hs[~raw_hs["Work email"].fillna("").str.strip().str.lower().str.endswith("@invisible.email")].index
    if not invalid_work_email_idx.empty:
        warnings_rawhs.append(("Invalid 'Work email' Domain", list(invalid_work_email_idx)))
    # (f) "Time" should not be empty.
    empty_time_idx = raw_hs[raw_hs["Time"].fillna("").str.strip().eq("")].index
    if not empty_time_idx.empty:
        warnings_rawhs.append(("Empty 'Time'", list(empty_time_idx)))

    # Function to display warnings using expanders.
    def display_warnings(file_name, warnings_list):
        for summary, details in warnings_list:
            with st.expander(f"{file_name}: {summary}"):
                st.write("Rows:", details)

    display_warnings("Roster", warnings_roster)
    display_warnings("Timers", warnings_timers)
    display_warnings("Raw hs export", warnings_rawhs)

    # ---- End Pre-Merge Validations ----

    # Normalize email columns for merging.
    roster["Agent Email"] = roster["Agent Email"].astype(str).str.strip().str.lower()
    raw_hs["Work email"] = raw_hs["Work email"].astype(str).str.strip().str.lower()

    # Clean up the Rate column in Roster.
    roster["Rate"] = roster["Rate"].astype(str).str.replace("[^0-9.]", "", regex=True)
    roster["Rate"] = pd.to_numeric(roster["Rate"], errors="coerce")

    try:
        # Merge Raw hs export with Roster using a left join on email.
        merged = pd.merge(
            raw_hs,
            roster[["Agent Email", "Rate"]],
            left_on="Work email",
            right_on="Agent Email",
            how="left"
        )
        # Merge Timers data on Project and Hubstaff Project Names.
        merged = pd.merge(
            merged,
            timers[["Hubstaff Project Names", "Team", "Pay Commodity", "Process Name (App)", "Process ID"]],
            left_on="Project",
            right_on="Hubstaff Project Names",
            how="left"
        )
        # Drop duplicate 'Agent Email' column if present.
        if "Agent Email" in merged.columns:
            merged.drop(columns=["Agent Email"], inplace=True)
    except Exception as e:
        st.error(f"Error merging data: {e}")
        st.stop()

    # Normalize the "Time" column: convert "HH:MM" to "HH:MM:SS"
    def normalize_time_format(t):
        t_str = str(t).strip()
        if t_str == "":
            return t_str
        if t_str.count(":") == 1:
            return t_str + ":00"
        return t_str

    merged["Time"] = merged["Time"].apply(normalize_time_format)

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

    complete_csv = merged.to_csv(index=False).encode('utf-8')
    st.download_button("Download Complete CSV", data=complete_csv, file_name='complete_view.csv', mime='text/csv')

    try:
        upload_df = pd.DataFrame({
            "Email": merged["Work email"],
            "Process ID": merged["Process ID"],
            "Hours": merged["Time"],
            "Rate": merged["Rate"],
            "Commodity Name": merged["Pay Commodity"]
        })
    except Exception as e:
        st.error(f"Error creating 'Data ready for upload' CSV: {e}")
        st.stop()

    st.write("### Preview of Data Ready for Upload:")
    st.dataframe(upload_df.head())

    upload_csv = upload_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Data Ready for Upload CSV", data=upload_csv, file_name='data_ready_for_upload.csv', mime='text/csv')
