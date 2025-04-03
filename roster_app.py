import streamlit as st
import pyodbc
import pandas as pd
from datetime import datetime, timedelta
from sshtunnel import SSHTunnelForwarder

# Set page config must be first command
st.set_page_config(layout="wide")

# Database connection function using Streamlit secrets
def get_db_connection():
    try:
        # 1. Establish SSH tunnel
        tunnel = SSHTunnelForwarder(
            ('72.14.201.61', 22),           # Your public IP
            ssh_username="faiq",             # From whoami command
            ssh_pkey="C:/Users/Faiq/.ssh/streamlit_key",  # Private key path
            remote_bind_address=('localhost', 1433)  # Forward to local SQL
        )
        tunnel.start()
        
        # 2. Connect through the tunnel
        conn = pyodbc.connect(
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER=127.0.0.1,{tunnel.local_bind_port};"
            "DATABASE=RosterManagement;"
            "UID=my_user;"
            "PWD=1234;"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
            "MARS_Connection=yes;"
        )
        return conn, tunnel  # Return both connection and tunnel object
    except Exception as e:
        st.error(f"🚨 Connection failed: {str(e)}")
        st.stop()

# Function to get all locations
def get_locations():
    conn = get_db_connection()
    query = "SELECT DISTINCT maica__Participant_Location__c FROM Appointments WHERE maica__Participant_Location__c IS NOT NULL"
    df = pd.read_sql(query, conn)
    conn.close()
    return df['maica__Participant_Location__c'].tolist()

# Function to get resources by location, filtered by employment type
def get_resources_by_location(location, employment_type='All'):
    conn = get_db_connection()
    
    # Special locations that should be matched by core part of the address
    special_locations = [
        "Thomas Street, Wollongong",  # Changed from full address to core part
        "Albert Street, Erskinville",
        "Cecil Street, Guildford",
        "Charles Street, Liverpool",
        "Cope Street, Redfern",
        "Copeland Street, Liverpool",
        "Fisher Street, Petersham",
        "Goulburn Street, Liverpool",
        "Todd Street, Merrylands",
        "Vine Street, Darlington",
        "89 Old South Head Road, Bondi Junction",
        "United For Care",
        "Bell Lane, Randwick",
        "Bexley",
        "Blacktown",
        "Cared Global Pty Ltd",
        "Castlereagh St"
    ]
    
    core_location = None
    for special_loc in special_locations:
        if special_loc.lower() in location.lower():
            core_location = special_loc
            break
            
    if core_location:
        if employment_type == 'All':
            query = """
            SELECT DISTINCT r.fullName as resource_name
            FROM Resources r
            WHERE r.primaryLocation LIKE '%' + ? + '%'
            AND r.Status = 'Active'
            AND r.jobTitle LIKE '%Disability Support Worker%'
            ORDER BY r.fullName
            """
            params = [core_location]
        else:
            query = """
            SELECT DISTINCT r.fullName as resource_name
            FROM Resources r
            WHERE r.primaryLocation LIKE '%' + ? + '%'
            AND r.employmentType = ?
            AND r.Status = 'Active'
            AND r.jobTitle LIKE '%Disability Support Worker%'
            ORDER BY r.fullName
            """
            params = [core_location, employment_type]
    else:
        if employment_type == 'All':
            query = """
            SELECT DISTINCT r.fullName as resource_name
            FROM Resources r
            WHERE r.primaryLocation = ?
            AND r.Status = 'Active'
            AND r.jobTitle LIKE '%Disability Support Worker%'
            ORDER BY r.fullName
            """
            params = [location]
        else:
            query = """
            SELECT DISTINCT r.fullName as resource_name
            FROM Resources r
            WHERE r.primaryLocation = ?
            AND r.employmentType = ?
            AND r.Status = 'Active'
            AND r.jobTitle LIKE '%Disability Support Worker%'
            ORDER BY r.fullName
            """
            params = [location, employment_type]
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if not df.empty:
        # Normalize spaces in the returned names
        return [' '.join(name.split()) for name in df['resource_name'].tolist()]
    else:
        return []

# Function to get appointments by resource and location
def get_appointments_by_resource_and_location(resource, location):
    conn = get_db_connection()
    
    # Handle special locations
    special_locations = [
        "Albert Street, Erskinville",
        "Cecil Street, Guildford",
        "Charles Street, Liverpool",
        "Cope Street, Redfern",
        "Copeland Street, Liverpool",
        "Fisher Street, Petersham",
        "Goulburn Street, Liverpool",
        "Thomas Street, Wollongong",
        "Todd Street, Merrylands",
        "Vine Street, Darlington",
        "89 Old South Head Road, Bondi Junction",
        "United For Care",
        "Bell Lane, Randwick",
        "Bexley",
        "Blacktown",
        "Cared Global Pty Ltd",
        "Castlereagh St"
    ]
    
    core_location = None
    for special_loc in special_locations:
        if special_loc in location:
            core_location = special_loc
            break
    
    if core_location:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participant_Location__c AS Location
        FROM Appointments
        WHERE maica__Resources__c = ?
        AND maica__Participant_Location__c LIKE '%' + ? + '%'
        ORDER BY maica__Scheduled_Start__c
        """
        params = [resource, core_location]
    else:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participant_Location__c AS Location
        FROM Appointments
        WHERE maica__Resources__c = ?
        AND maica__Participant_Location__c = ?
        ORDER BY maica__Scheduled_Start__c
        """
        params = [resource, location]
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if not df.empty:
        df['DurationHours'] = df['DurationMinutes'] / 60
        df['StartDate'] = pd.to_datetime(df['StartDateTime']).dt.date
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
    return df

def get_resource_counts_by_location(location):
    conn = get_db_connection()
     # Handle special locations
    special_locations = [
        "Albert Street, Erskinville",
        "Cecil Street, Guildford",
        "Charles Street, Liverpool",
        "Cope Street, Redfern",
        "Copeland Street, Liverpool",
        "Fisher Street, Petersham",
        "Goulburn Street, Liverpool",
        "Thomas Street, Wollongong",
        "Todd Street, Merrylands",
        "Vine Street, Darlington",
        "89 Old South Head Road, Bondi Junction",
        "United For Care",
        "Bell Lane, Randwick",
        "Bexley",
        "Blacktown",
        "Cared Global Pty Ltd",
        "Castlereagh St"
    ]
    
    # Handle special locations (same as before)
    core_location = None
    for special_loc in special_locations:
        if special_loc.lower() in location.lower():
            core_location = special_loc
            break
            
    if core_location:
        query = """
        SELECT 
            employmentType,
            COUNT(*) as resource_count
        FROM Resources
        WHERE primaryLocation LIKE '%' + ? + '%'
        AND Status = 'Active'
        AND jobTitle LIKE '%Disability Support Worker%'
        GROUP BY employmentType
        """
        params = [core_location]
    else:
        query = """
        SELECT 
            employmentType,
            COUNT(*) as resource_count
        FROM Resources
        WHERE primaryLocation = ?
        AND Status = 'Active'
        AND jobTitle LIKE '%Disability Support Worker%'
        GROUP BY employmentType
        """
        params = [location]
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


# Function to get resource details
def get_resource_details(resource_name):
    conn = get_db_connection()
    # Normalize the resource name by replacing multiple spaces with single space
    normalized_name = ' '.join(resource_name.split())
    
    query = """
    SELECT 
        id,
        fullName,
        employmentType,
        hoursPerWeek,
        primaryLocation
    FROM Resources
    WHERE REPLACE(REPLACE(fullName, '  ', ' '), '  ', ' ') = ?
    """
    df = pd.read_sql(query, conn, params=[normalized_name])
    conn.close()
    
    if not df.empty:
        return {
            'id': df.iloc[0]['id'],
            'fullName': df.iloc[0]['fullName'],
            'employmentType': df.iloc[0]['employmentType'] or 'Unknown',
            'hoursPerWeek': df.iloc[0]['hoursPerWeek'] or 38,
            'primaryLocation': df.iloc[0]['primaryLocation'] or 'Unknown'
        }
    else:
        # Return default values if resource not found
        return {
            'id': None,
            'fullName': resource_name,
            'employmentType': 'Unknown',
            'hoursPerWeek': 38,  # Default standard hours
            'primaryLocation': 'Unknown'
        }

def get_unassigned_appointments(location):
    conn = get_db_connection()
    
    # Handle special locations
    special_locations = [
        "Albert Street, Erskinville",
        "Cecil Street, Guildford",
        "Charles Street, Liverpool",
        "Cope Street, Redfern",
        "Copeland Street, Liverpool",
        "Fisher Street, Petersham",
        "Goulburn Street, Liverpool",
        "Thomas Street, Wollongong",
        "Todd Street, Merrylands",
        "Vine Street, Darlington",
        "89 Old South Head Road, Bondi Junction",
        "United For Care",
        "Bell Lane, Randwick",
        "Bexley",
        "Blacktown",
        "Cared Global Pty Ltd",
        "Castlereagh St"
    ]
    
    core_location = None
    for special_loc in special_locations:
        if special_loc in location:
            core_location = special_loc
            break
    
    if core_location:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participant_Location__c AS Location
        FROM Appointments
        WHERE (maica__Resources__c IS NULL OR maica__Resources__c = 'NULL')
        AND maica__Participant_Location__c LIKE '%' + ? + '%'
        ORDER BY maica__Scheduled_Start__c
        """
        params = [core_location]
    else:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participant_Location__c AS Location
        FROM Appointments
        WHERE (maica__Resources__c IS NULL OR maica__Resources__c = 'NULL')
        AND maica__Participant_Location__c = ?
        ORDER BY maica__Scheduled_Start__c
        """
        params = [location]
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if not df.empty:
        df['DurationHours'] = df['DurationMinutes'] / 60
        df['StartDate'] = pd.to_datetime(df['StartDateTime']).dt.date
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
    return df

def assign_resource_to_appointment(appointment_id, resource_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Normalize the resource name
        normalized_name = ' '.join(resource_name.split())
        
        update_query = """
        UPDATE Appointments
        SET maica__Resources__c = ?
        WHERE Id = ?
        """
        cursor.execute(update_query, (normalized_name, appointment_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error assigning resource: {str(e)}")
        return False
    finally:
        conn.close()
    
# Function to calculate constraints for a resource at a location
def calculate_constraints(resource_name, location):
    conn = get_db_connection()
    
    # Handle special locations
    special_locations = [
        "Albert Street, Erskinville",
        "Cecil Street, Guildford",
        "Charles Street, Liverpool",
        "Cope Street, Redfern",
        "Copeland Street, Liverpool",
        "Fisher Street, Petersham",
        "Goulburn Street, Liverpool",
        "Thomas Street, Wollongong",
        "Todd Street, Merrylands",
        "Vine Street, Darlington",
        "89 Old South Head Road, Bondi Junction",
        "United For Care",
        "Bell Lane, Randwick",
        "Bexley",
        "Blacktown",
        "Cared Global Pty Ltd",
        "Castlereagh St"
    ]
    
    core_location = None
    for special_loc in special_locations:
        if special_loc in location:
            core_location = special_loc
            break
    
    if core_location:
        query = """
        SELECT 
            a.Id AS AppointmentID,
            a.maica__Scheduled_Start__c AS StartDateTime,
            a.maica__Scheduled_End__c AS EndDateTime,
            a.maica__Scheduled_Duration_Minutes__c AS DurationMinutes
        FROM Appointments a
        WHERE a.maica__Resources__c = ?
        AND a.maica__Participant_Location__c LIKE '%' + ? + '%'
        ORDER BY a.maica__Scheduled_Start__c
        """
        params = [resource_name, core_location]
    else:
        query = """
        SELECT 
            a.Id AS AppointmentID,
            a.maica__Scheduled_Start__c AS StartDateTime,
            a.maica__Scheduled_End__c AS EndDateTime,
            a.maica__Scheduled_Duration_Minutes__c AS DurationMinutes
        FROM Appointments a
        WHERE a.maica__Resources__c = ?
        AND a.maica__Participant_Location__c = ?
        ORDER BY a.maica__Scheduled_Start__c
        """
        params = [resource_name, location]
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if df.empty:
        return {
            'max_consecutive_days': 0,
            'min_hours_between_shifts': 'N/A',
            'week1_hours': 0,
            'week2_hours': 0,
            'total_hours': 0,
            'shift_details': []
        }
    
    df['StartDateTime'] = pd.to_datetime(df['StartDateTime'])
    df['EndDateTime'] = pd.to_datetime(df['EndDateTime'])
    
    shift_details = []
    for _, row in df.iterrows():
        shift_details.append({
            'date': row['StartDateTime'].date(),
            'start': row['StartDateTime'].time(),
            'end': row['EndDateTime'].time(),
            'duration': row['DurationMinutes']/60
        })
    
    # Calculate consecutive days
    df['Date'] = df['StartDateTime'].dt.date
    unique_dates = df.drop_duplicates('Date')
    
    if len(unique_dates) > 1:
        unique_dates = unique_dates.sort_values('Date')
        unique_dates['DayDiff'] = unique_dates['Date'].diff().dt.days.fillna(1)
        unique_dates['ConsecutiveGroup'] = (unique_dates['DayDiff'] != 1).cumsum()
        consecutive_counts = unique_dates.groupby('ConsecutiveGroup').size()
        max_consecutive_days = consecutive_counts.max()
    else:
        max_consecutive_days = 1
    
    # Calculate hours between shifts
    df_sorted = df.sort_values('StartDateTime')
    if len(df_sorted) > 1:
        df_sorted['NextStart'] = df_sorted['StartDateTime'].shift(-1)
        df_sorted['HoursBetween'] = (df_sorted['NextStart'] - df_sorted['EndDateTime']).dt.total_seconds() / 3600
        min_hours_between = df_sorted['HoursBetween'].min()
    else:
        min_hours_between = None
    
    # Calculate weekly hours
    rotation_start = df['StartDateTime'].min().date()
    df['Week'] = df['StartDateTime'].apply(
        lambda x: 1 if (x.date() - rotation_start).days < 7 else 2
    )
    
    weekly_hours = df.groupby('Week')['DurationMinutes'].sum() / 60
    week1_hours = weekly_hours.get(1, 0)
    week2_hours = weekly_hours.get(2, 0)
    total_hours = weekly_hours.sum()
    
    return {
        'max_consecutive_days': max_consecutive_days,
        'min_hours_between_shifts': f"{min_hours_between:.1f}" if min_hours_between is not None else 'N/A',
        'week1_hours': week1_hours,
        'week2_hours': week2_hours,
        'total_hours': total_hours,
        'shift_details': shift_details
    }

def main():
    # Custom CSS
    st.markdown("""
    <style>
    .appointment-header {
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #e1e4e8;
        margin-bottom: 5px;
        background-color: #f9f9f9;
        color: #333333 !important;
    }
    .appointment-details {
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #e1e4e8;
        margin-bottom: 15px;
        background-color: #f0f7ff;
    }
    .selected-tick {
        color: #2e7d32;
        font-weight: bold;
    }
    .unselected-cross {
        color: #ff4b4b;
        font-weight: bold;
    }
    .compact-resource {
        margin-bottom: 5px;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        margin-left: 10px;
    }
    .assigned {
        background-color: #e6f7e6;
        color: #2e7d32;
    }
    .unassigned {
        background-color: #ffebee;
        color: #ff4b4b;
    }
    .constraint-error {
        color: #ff4b4b;
        font-weight: bold;
        margin: 5px 0;
    }
    .count-badge {
        display: inline-block;
        padding: 0.15em 0.4em;
        font-size: 0.75em;
        font-weight: bold;
        line-height: 1;
        color: #fff;
        background-color: #6c757d;
        border-radius: 0.25rem;
        margin-left: 0.5em;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("📅 Roster Management System")
    
    # Initialize session state
    if 'expanded_appointment' not in st.session_state:
        st.session_state.expanded_appointment = None
    if 'selected_location' not in st.session_state:
        st.session_state.selected_location = None
    if 'selected_resource' not in st.session_state:
        st.session_state.selected_resource = None
    if 'selected_employment_type' not in st.session_state:
        st.session_state.selected_employment_type = 'All'

    # Step 1: Select location with unique key
    locations = get_locations()
    new_location = st.selectbox(
        "Select Location:", 
        locations,
        key="main_unique_location_selectbox"
    )
    
    # Update session state when location changes
    if new_location != st.session_state.selected_location:
        st.session_state.selected_location = new_location
        st.session_state.selected_resource = None  # Reset resource selection
        st.rerun()

    if st.session_state.selected_location:
        # Get resource counts by type
        resource_counts = get_resource_counts_by_location(st.session_state.selected_location)
        
        # Convert to dictionary for easy access
        counts_dict = dict(zip(resource_counts['employmentType'], resource_counts['resource_count']))
        total_resources = sum(counts_dict.values())
        
        # Create labels with counts
        employment_types = ['All', 'Full Time', 'Part Time', 'Casual']
        labels_with_counts = [
            f"All ({total_resources})",
            f"Full Time ({counts_dict.get('Full Time', 0)})",
            f"Part Time ({counts_dict.get('Part Time', 0)})",
            f"Casual ({counts_dict.get('Casual', 0)})"
        ]
        
        # Create mapping between display labels and actual values
        type_mapping = dict(zip(labels_with_counts, employment_types))
        
        # Show selectbox with counts
        selected_label = st.selectbox(
            "Filter by Employment Type:", 
            labels_with_counts,
            index=0,  # Default to 'All'
            key="employment_type_filter"
        )
        
        # Get the actual employment type value
        employment_type = type_mapping[selected_label]
        
        if employment_type != st.session_state.selected_employment_type:
            st.session_state.selected_employment_type = employment_type
            st.session_state.selected_resource = None
            st.rerun()

        # Step 2: Get resources for selected location
        resources = get_resources_by_location(st.session_state.selected_location, st.session_state.selected_employment_type)

        if resources:
            # Use tabs to separate assigned and unassigned appointments
            tab_assigned, tab_unassigned = st.tabs(["Assigned Appointments", "Unassigned Appointments"])

            with tab_assigned:
                # Resource selection with unique key
                new_resource = st.selectbox(
                    "Select Resource:",
                    resources,
                    key="main_assigned_resource_selectbox"
                )
                
                # Update resource selection
                if new_resource != st.session_state.selected_resource:
                    st.session_state.selected_resource = new_resource
                    st.rerun()
                
                if st.session_state.selected_resource:
                    # Get appointments for selected resource at selected location
                    appointments = get_appointments_by_resource_and_location(
                        st.session_state.selected_resource, 
                        st.session_state.selected_location
                    )
                    
                    if not appointments.empty:
                        st.subheader(f"👤 {st.session_state.selected_resource} at {st.session_state.selected_location} - {len(appointments)} Appointments")
                        
                        # Initialize constraints with default values
                        constraints = {
                            'max_consecutive_days': 0,
                            'min_hours_between_shifts': 'N/A',
                            'week1_hours': 0,
                            'week2_hours': 0,
                            'total_hours': 0,
                            'shift_details': []
                        }
                        
                        # Calculate constraints if we have appointments
                        if len(appointments) > 0:
                            constraints = calculate_constraints(
                                st.session_state.selected_resource, 
                                st.session_state.selected_location
                            )
                        
                        # Display resource details
                        resource_details = get_resource_details(st.session_state.selected_resource)
                        st.markdown(f"""
                        <div class="compact-resource">
                            <p><strong>🧑‍💼 Name:</strong> {resource_details['fullName']}</p>
                            <p><strong>📝 Type:</strong> {resource_details['employmentType']}</p>
                            <p><strong>⏰ Contracted Hours:</strong> {resource_details.get('hoursPerWeek', 38)}/week</p>
                            <p><strong>📍 Primary Location:</strong> {resource_details.get('primaryLocation', 'Unknown')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Display constraints
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            consecutive_status = "✅" if constraints['max_consecutive_days'] <= 5 else "❌"
                            st.markdown(f"""
                            <div class="compact-resource">
                                <p><strong>{consecutive_status} Consecutive Days:</strong> {constraints['max_consecutive_days']}/5</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if constraints['min_hours_between_shifts'] != 'N/A':
                                hours_status = "✅" if float(constraints['min_hours_between_shifts']) >= 10 else "❌"
                                st.markdown(f"""
                                <div class="compact-resource">
                                    <p><strong>{hours_status} Hours Between:</strong> {constraints['min_hours_between_shifts']}h (min 10h)</p>
                                </div>
                                """, unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown(f"""
                            <div class="compact-resource">
                                <p><strong>📅 Week 1:</strong> {constraints['week1_hours']:.2f}h/{resource_details.get('hoursPerWeek', 38)}h</p>
                                <p><strong>📅 Week 2:</strong> {constraints['week2_hours']:.2f}h/{resource_details.get('hoursPerWeek', 38)}h</p>
                                <p><strong>📊 Total:</strong> {constraints['total_hours']:.2f}h</p>
                            </div>
                            """, unsafe_allow_html=True)

                        # Show shift details
                        with st.expander("📝 Show All Shifts"):
                            st.dataframe(
                                pd.DataFrame(constraints['shift_details']),
                                column_config={
                                    "date": "📅 Date",
                                    "start": "⏰ Start",
                                    "end": "🕒 End", 
                                    "duration": "⏱️ Hours"
                                },
                                use_container_width=True,
                                hide_index=True
                            )
                        
                        # Validate constraints
                        constraint_errors = []
                        if constraints['max_consecutive_days'] > 5:
                            constraint_errors.append(f"❌ This resource has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
                        
                        if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
                            constraint_errors.append(f"❌ Only {constraints['min_hours_between_shifts']} hours between shifts (min 10 required)")
                        
                        if constraint_errors:
                            st.error("Constraint violations detected:")
                            for error in constraint_errors:
                                st.markdown(f'<div class="constraint-error">{error}</div>', unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        # Display all appointments
                        for idx, row in appointments.iterrows():
                            appt_id = row['AppointmentID']
                            
                            # Create columns for the appointment header
                            col1, col2 = st.columns([0.9, 0.1])
                            
                            with col1:
                                # Appointment header
                                st.markdown(f"""
                                <div class="appointment-header">
                                    <strong>{row['Name']}</strong> - {row['DisplayStart']} to {row['DisplayEnd']} ({row['DurationHours']:.2f}h)
                                </div>
                                """, unsafe_allow_html=True)
                            
                            with col2:
                                # Toggle button for expand/collapse with unique key
                                if st.button("📝", key=f"expand_assigned_{appt_id}"):
                                    if st.session_state.expanded_appointment == appt_id:
                                        st.session_state.expanded_appointment = None
                                    else:
                                        st.session_state.expanded_appointment = appt_id
                            
                            # Expanded details section
                            if st.session_state.expanded_appointment == appt_id:
                                with st.container():
                                    st.markdown("<div class='appointment-details'>", unsafe_allow_html=True)
                                    
                                    st.write(f"Location: {row['Location']}")
                                    st.write(f"Start: {row['DisplayStart']}")
                                    st.write(f"End: {row['DisplayEnd']}")
                                    st.write(f"Duration: {row['DurationHours']:.2f} hours")
                                    
                                    st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.warning(f"⚠️ No appointments found for {st.session_state.selected_resource} at {st.session_state.selected_location}")
            
            with tab_unassigned:
                # Show unassigned appointments
                unassigned_appointments = get_unassigned_appointments(st.session_state.selected_location)
                
                if not unassigned_appointments.empty:
                    st.subheader(f"🚨 Unassigned Appointments at {st.session_state.selected_location} - {len(unassigned_appointments)}")
                    
                    for idx, row in unassigned_appointments.iterrows():
                        appt_id = row['AppointmentID']
                        
                        with st.expander(f"{row['Name']} - {row['DisplayStart']} to {row['DisplayEnd']} ({row['DurationHours']:.2f}h)"):
                            st.write(f"**Location:** {row['Location']}")
                            st.write(f"**Start:** {row['DisplayStart']}")
                            st.write(f"**End:** {row['DisplayEnd']}")
                            st.write(f"**Duration:** {row['DurationHours']:.2f} hours")
                            
                            # Resource assignment form with unique key
                            with st.form(key=f"assign_form_{appt_id}"):
                                selected_assign_resource = st.selectbox(
                                    "Assign Resource:",
                                    resources,
                                    key=f"assign_select_{appt_id}"
                                )
                                
                                if st.form_submit_button("Assign Resource"):
                                    if assign_resource_to_appointment(appt_id, selected_assign_resource):
                                        st.success(f"Successfully assigned {selected_assign_resource} to this appointment!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to assign resource")
                else:
                    st.success(f"🎉 All appointments at {st.session_state.selected_location} have resources assigned!")
        else:
            st.warning(f"⚠️ No resources found for {st.session_state.selected_location}")

if __name__ == "__main__":
    main()