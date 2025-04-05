import streamlit as st
import pyodbc
import pandas as pd
from datetime import datetime, timedelta
import os
from contextlib import contextmanager

# Set page config must be first command
st.set_page_config(
    layout="wide",
    page_title="Roster Management Pro",
    page_icon="📊",
    initial_sidebar_state="expanded"
)

# Load custom CSS
def load_css():
    with open("style.css", "r", encoding="utf-8", errors="ignore") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# Database configuration
DB_SERVER = "0.tcp.in.ngrok.io"  # Use the ngrok public address
DB_PORT = "14927"  # Use the ngrok-generated port

DB_NAME = "RosterManagement"
DB_USERNAME = "my_user"
DB_PASSWORD = "!Mynameisapp"

# Special locations mapping
SPECIAL_LOCATIONS = {
    "thomas street": "Thomas Street, Wollongong",
    "albert street": "Albert Street, Erskinville",
    "cecil street": "Cecil Street, Guildford",
    "charles street": "Charles Street, Liverpool",
    "cope street": "Cope Street, Redfern",
    "copeland street": "Copeland Street, Liverpool",
    "fisher street": "Fisher Street, Petersham",
    "goulburn street": "Goulburn Street, Liverpool",
    "todd street": "Todd Street, Merrylands",
    "vine street": "Vine Street, Darlington",
    "89 old south head road": "89 Old South Head Road, Bondi Junction",
    "united for care": "United For Care",
    "bell lane": "Bell Lane, Randwick",
    "bexley": "Bexley",
    "blacktown": "Blacktown",
    "cared global pty ltd": "Cared Global Pty Ltd",
    "castlereagh st": "Castlereagh St"
}

# Database connection manager
@contextmanager
def db_connection():
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER},{DB_PORT};"  # Use ngrok's TCP tunnel address and port
        f"DATABASE={DB_NAME};"
        f"UID={DB_USERNAME};"
        f"PWD={DB_PASSWORD};"
    )
    try:
        yield conn
    finally:
        conn.close()

# Test connection
try:
    with db_connection() as conn:
        st.sidebar.success("✅ Connected to the database successfully!")
except Exception as e:
    st.sidebar.error(f"❌ Database connection failed: {str(e)}")

# Helper function to normalize location names
def normalize_location(location):
    if not location:
        return None
    loc_lower = location.lower()
    for key, value in SPECIAL_LOCATIONS.items():
        if key in loc_lower:
            return value
    return location

# Cached data functions
@st.cache_data(ttl=3600)
def get_location_participant_mapping():
    with db_connection() as conn:
        query = """
        SELECT DISTINCT 
            maica__Participant_Location__c as location,
            maica__Participants__c as participant
        FROM Appointments
        WHERE maica__Participants__c LIKE '%Roster%'
        AND maica__Participant_Location__c IS NOT NULL
        """
        df = pd.read_sql(query, conn)
    return df.set_index('location')['participant'].to_dict()

@st.cache_data(ttl=3600)
def get_locations_with_participants():
    with db_connection() as conn:
        query = """
        SELECT DISTINCT 
            maica__Participant_Location__c as location,
            maica__Participants__c as participant_name
        FROM Appointments
        WHERE maica__Participants__c LIKE '%Roster%'
        AND maica__Participant_Location__c IS NOT NULL
        ORDER BY maica__Participants__c
        """
        df = pd.read_sql(query, conn)
    
    # Create list of dictionaries with display names and actual locations
    locations = []
    for _, row in df.iterrows():
        locations.append({
            'display_name': row['participant_name'],
            'location': row['location']
        })
    
    return locations

@st.cache_data(ttl=3600)
def get_locations():
    mapping = get_location_participant_mapping()
    
    with db_connection() as conn:
        query = """
        SELECT DISTINCT maica__Participant_Location__c 
        FROM Appointments 
        WHERE maica__Participant_Location__c IS NOT NULL
        AND maica__Participants__c LIKE '%Roster%'
        """
        df = pd.read_sql(query, conn)
    
    # Create list of tuples: (display_name, actual_location)
    locations = []
    for loc in df['maica__Participant_Location__c'].tolist():
        display_name = mapping.get(loc, loc)  # Default to location if no participant found
        locations.append((display_name, loc))
    
    return locations

@st.cache_data(ttl=3600)
def get_all_resources():
    """Get all active resources with caching"""
    with db_connection() as conn:
        query = """
        SELECT DISTINCT 
            r.fullName as resource_name, 
            r.primaryLocation,
            r.employmentType
        FROM Resources r
        WHERE r.Status = 'Active'
        AND r.jobTitle LIKE '%Disability Support Worker%'
        ORDER BY r.fullName
        """
        df = pd.read_sql(query, conn)
    
    if not df.empty:
        df['resource_name'] = df['resource_name'].apply(lambda x: ' '.join(x.split()))
    return df

@st.cache_data(ttl=600)  # Cache for 10 minutes since this changes more frequently
def get_resources_by_location(location, employment_type='All'):
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
        if employment_type == 'All':
            query = """
            SELECT DISTINCT r.fullName as resource_name
            FROM Resources r
            WHERE r.primaryLocation LIKE '%' + ? + '%'
            AND r.Status = 'Active'
            AND r.jobTitle LIKE '%Disability Support Worker%'
            ORDER BY r.fullName
            """
            params = [norm_location]
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
            params = [norm_location, employment_type]
        
        df = pd.read_sql(query, conn, params=params)
    
    if not df.empty:
        return [' '.join(name.split()) for name in df['resource_name'].tolist()]
    return []

@st.cache_data(ttl=300)  # Short cache since appointments change frequently
def get_appointments_by_resource_and_location(resource, location):
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participants__c AS Participant
        FROM Appointments
        WHERE maica__Resources__c = ?
        AND maica__Participant_Location__c LIKE '%' + ? + '%'
        AND maica__Participants__c LIKE '%Roster%'
        ORDER BY maica__Scheduled_Start__c
        """
        params = [resource, norm_location]
        
        df = pd.read_sql(query, conn, params=params)
    
    if not df.empty:
        df['DurationHours'] = df['DurationMinutes'] / 60
        df['StartDate'] = pd.to_datetime(df['StartDateTime']).dt.date
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
    return df

@st.cache_data(ttl=600)
def get_resource_counts_by_location(location):
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
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
        params = [norm_location]
        
        df = pd.read_sql(query, conn, params=params)
    return df

@st.cache_data(ttl=600)
def get_resource_details(resource_name):
    normalized_name = ' '.join(resource_name.split())
    
    with db_connection() as conn:
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
    
    if not df.empty:
        employment_type = df.iloc[0]['employmentType'] or 'Unknown'
        hours_per_week = df.iloc[0]['hoursPerWeek'] if employment_type != 'Casual' else 0
        
        return {
            'id': df.iloc[0]['id'],
            'fullName': df.iloc[0]['fullName'],
            'employmentType': employment_type,
            'hoursPerWeek': hours_per_week,
            'primaryLocation': df.iloc[0]['primaryLocation'] or 'Unknown'
        }
    else:
        return {
            'id': None,
            'fullName': resource_name,
            'employmentType': 'Unknown',
            'hoursPerWeek': 0,
            'primaryLocation': 'Unknown'
        }

@st.cache_data(ttl=300)
def get_unassigned_appointments(location):
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participants__c AS Participant
        FROM Appointments
        WHERE (maica__Resources__c IS NULL OR maica__Resources__c = 'NULL')
        AND maica__Participant_Location__c LIKE '%' + ? + '%'
        AND maica__Participants__c LIKE '%Roster%'
        ORDER BY maica__Scheduled_Start__c
        """
        params = [norm_location]
        
        df = pd.read_sql(query, conn, params=params)
    
    if not df.empty:
        df['DurationHours'] = df['DurationMinutes'] / 60
        df['StartDate'] = pd.to_datetime(df['StartDateTime']).dt.date
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%m/%d/%Y %I:%M %p')
    return df

def assign_resource_to_appointment(appointment_id, resource_name):
    normalized_name = ' '.join(resource_name.split())
    
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            update_query = """
            UPDATE Appointments
            SET maica__Resources__c = ?
            WHERE Id = ?
            """
            cursor.execute(update_query, (normalized_name, appointment_id))
            conn.commit()
            
            # Clear relevant caches after update
            st.cache_data.clear()
            return True
        except Exception as e:
            conn.rollback()
            st.error(f"Error assigning resource: {str(e)}")
            return False

@st.cache_data(ttl=300)
def calculate_constraints(resource_name, location):
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
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
        params = [resource_name, norm_location]
        
        df = pd.read_sql(query, conn, params=params)
    
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
    # Sidebar with filters
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-header">
            <h2>🔍 Filters</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # Initialize session state
        if 'expanded_appointment' not in st.session_state:
            st.session_state.expanded_appointment = None
        if 'selected_location' not in st.session_state:
            st.session_state.selected_location = None
        if 'selected_resource' not in st.session_state:
            st.session_state.selected_resource = None
        if 'selected_employment_type' not in st.session_state:
            st.session_state.selected_employment_type = 'All'

        # Get locations with participant names for display
        location_options = get_locations_with_participants()
        
        # Create options for selectbox
        options = [loc['display_name'] for loc in location_options]
        
        # Show participant names in dropdown
        selected_display = st.selectbox(
            "Select Roster:", 
            options=options,
            key="main_unique_location_selectbox"
        )
        
        # Find the corresponding actual location
        selected_location = None
        for loc in location_options:
            if loc['display_name'] == selected_display:
                selected_location = loc['location']
                break
        
        # Update session state when location changes
        if selected_location and selected_location != st.session_state.selected_location:
            st.session_state.selected_location = selected_location
            st.session_state.selected_resource = None  # Reset resource selection
            st.rerun()

    # Main content
    st.markdown("""
    <div class="main-header">
        <h1>📊 Roster Management Pro</h1>
        <p class="subtitle">Optimize your workforce scheduling with powerful analytics</p>
    </div>
    """, unsafe_allow_html=True)

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
        
        # Show selectbox with counts in sidebar
        with st.sidebar:
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

        # Get resources for selected location and employment type
        resources = get_resources_by_location(
            st.session_state.selected_location, 
            st.session_state.selected_employment_type
        )

        if resources:
            # Use tabs to separate assigned and unassigned appointments
            tab_assigned, tab_unassigned = st.tabs(["📅 Assigned Appointments", "🆔 Unassigned Appointments"])

            with tab_assigned:
                # Resource selection with unique key
                col1, col2 = st.columns([3, 1])
                with col1:
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
                    # Get appointments for selected resource
                    appointments = get_appointments_by_resource_and_location(
                        st.session_state.selected_resource, 
                        st.session_state.selected_location
                    )
                    
                    if not appointments.empty:
                        st.markdown(f"""
                        <div class="resource-header">
                            <h2>👤 {st.session_state.selected_resource}</h2>
                            <p class="resource-subheader">at {st.session_state.selected_location} • {len(appointments)} Appointments</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Get constraints
                        constraints = calculate_constraints(
                            st.session_state.selected_resource, 
                            st.session_state.selected_location
                        )
                        
                        # Display resource details
                        resource_details = get_resource_details(st.session_state.selected_resource)
                        
                        st.markdown("""
                        <div class="resource-card">
                            <div class="resource-card-header">
                                <h3>Resource Details</h3>
                            </div>
                            <div class="resource-card-body">
                                <div class="resource-detail">
                                    <span class="detail-icon">🧑‍💼</span>
                                    <span class="detail-label">Name:</span>
                                    <span class="detail-value">{fullName}</span>
                                </div>
                                <div class="resource-detail">
                                    <span class="detail-icon">📝</span>
                                    <span class="detail-label">Type:</span>
                                    <span class="detail-value">{employmentType}</span>
                                </div>
                                <div class="resource-detail">
                                    <span class="detail-icon">⏰</span>
                                    <span class="detail-label">Contracted Hours:</span>
                                    <span class="detail-value">{hoursPerWeek}/week</span>
                                </div>
                                <div class="resource-detail">
                                    <span class="detail-icon">📍</span>
                                    <span class="detail-label">Primary Location:</span>
                                    <span class="detail-value">{primaryLocation}</span>
                                </div>
                            </div>
                        </div>
                        """.format(
                            fullName=resource_details['fullName'],
                            employmentType=resource_details['employmentType'],
                            hoursPerWeek=resource_details.get('hoursPerWeek', 38),
                            primaryLocation=resource_details.get('primaryLocation', 'Unknown')
                        ), unsafe_allow_html=True)
                        
                        # Display constraints in metrics cards
                        st.markdown("""
                        <div class="metrics-container">
                            <div class="metric-card {consecutive_class}">
                                <div class="metric-value">{max_consecutive_days}/5</div>
                                <div class="metric-label">Consecutive Days {consecutive_icon}</div>
                            </div>
                            <div class="metric-card {hours_class}">
                                <div class="metric-value">{min_hours_between_shifts}h</div>
                                <div class="metric-label">Min Between Shifts {hours_icon}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-value">{week1_hours:.1f}h</div>
                                <div class="metric-label">Week 1 Hours</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-value">{week2_hours:.1f}h</div>
                                <div class="metric-label">Week 2 Hours</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-value">{total_hours:.1f}h</div>
                                <div class="metric-label">Total Hours</div>
                            </div>
                        </div>
                        """.format(
                            max_consecutive_days=constraints['max_consecutive_days'],
                            consecutive_icon="✅" if constraints['max_consecutive_days'] <= 5 else "❌",
                            consecutive_class="metric-success" if constraints['max_consecutive_days'] <= 5 else "metric-danger",
                            min_hours_between_shifts=constraints['min_hours_between_shifts'],
                            hours_icon="✅" if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) >= 10 else "❌",
                            hours_class="metric-success" if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) >= 10 else "metric-danger",
                            week1_hours=constraints['week1_hours'],
                            week2_hours=constraints['week2_hours'],
                            total_hours=constraints['total_hours']
                        ), unsafe_allow_html=True)

                        # Validate constraints
                        constraint_errors = []
                        if constraints['max_consecutive_days'] > 5:
                            constraint_errors.append(f"❌ This resource has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
                        
                        if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
                            constraint_errors.append(f"❌ Only {constraints['min_hours_between_shifts']} hours between shifts (min 10 required)")
                        
                        if constraint_errors:
                            st.markdown("""
                            <div class="constraint-alert">
                                <div class="constraint-alert-header">
                                    ⚠️ Constraint Violations Detected
                                </div>
                                <div class="constraint-alert-body">
                            """, unsafe_allow_html=True)
                            for error in constraint_errors:
                                st.markdown(f'<div class="constraint-error">{error}</div>', unsafe_allow_html=True)
                            st.markdown("</div></div>", unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        # Display all appointments
                        st.markdown("""
                        <div class="section-header">
                            <h3>📋 Appointment Schedule</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        for idx, row in appointments.iterrows():
                            appt_id = row['AppointmentID']
                            
                            # Create appointment card
                            st.markdown(f"""
                            <div class="appointment-card {'expanded' if st.session_state.expanded_appointment == appt_id else ''}">
                                <div class="appointment-card-header">
                                    <div class="appointment-title">
                                        <strong>{row['Name']}</strong>
                                    </div>
                                    <div class="appointment-time">
                                        {row['DisplayStart']} to {row['DisplayEnd']} • {row['DurationHours']:.2f}h
                                    </div>
                                    <div class="appointment-actions">
                            """, unsafe_allow_html=True)
                            
                            # Toggle button for expand/collapse
                            if st.button("📝 Details", key=f"expand_assigned_{appt_id}"):
                                if st.session_state.expanded_appointment == appt_id:
                                    st.session_state.expanded_appointment = None
                                else:
                                    st.session_state.expanded_appointment = appt_id
                                st.rerun()
                            
                            st.markdown("""
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            # Expanded details section
                            if st.session_state.expanded_appointment == appt_id:
                                with st.container():
                                    st.markdown("""
                                    <div class='appointment-card-body'>
                                        <div class="appointment-detail">
                                            <span class="detail-icon">👤</span>
                                            <span class="detail-label">Participant:</span>
                                            <span class="detail-value">{participant}</span>
                                        </div>
                                        <div class="appointment-detail">
                                            <span class="detail-icon">⏰</span>
                                            <span class="detail-label">Start:</span>
                                            <span class="detail-value">{displayStart}</span>
                                        </div>
                                        <div class="appointment-detail">
                                            <span class="detail-icon">🕒</span>
                                            <span class="detail-label">End:</span>
                                            <span class="detail-value">{displayEnd}</span>
                                        </div>
                                        <div class="appointment-detail">
                                            <span class="detail-icon">⏱️</span>
                                            <span class="detail-label">Duration:</span>
                                            <span class="detail-value">{durationHours:.2f} hours</span>
                                        </div>
                                    </div>
                                    """.format(
                                        participant=row['Participant'],
                                        displayStart=row['DisplayStart'],
                                        displayEnd=row['DisplayEnd'],
                                        durationHours=row['DurationHours']
                                    ), unsafe_allow_html=True)
                            
                            st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("""
                        <div class="empty-state">
                            <div class="empty-state-icon">⚠️</div>
                            <div class="empty-state-text">
                                No appointments found for {resource} at {location}
                            </div>
                        </div>
                        """.format(
                            resource=st.session_state.selected_resource,
                            location=st.session_state.selected_location
                        ), unsafe_allow_html=True)
            
            with tab_unassigned:
                # Show unassigned appointments
                unassigned_appointments = get_unassigned_appointments(st.session_state.selected_location)
                
                if not unassigned_appointments.empty:
                    st.markdown(f"""
                    <div class="section-header">
                        <h3>🚨 Unassigned Appointments at {st.session_state.selected_location}</h3>
                        <p class="section-subheader">{len(unassigned_appointments)} unassigned shifts</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Get all resources (not filtered by location)
                    all_resources_df = get_all_resources()
                    # Get local resources
                    local_resources = get_resources_by_location(
                        st.session_state.selected_location, 
                        st.session_state.selected_employment_type
                    )
                    
                    for idx, row in unassigned_appointments.iterrows():
                        appt_id = row['AppointmentID']
                        start_datetime = pd.to_datetime(row['StartDateTime'])
                        end_datetime = pd.to_datetime(row['EndDateTime'])
                        
                        # Initialize session state for this appointment
                        if f"assigned_{appt_id}" not in st.session_state:
                            st.session_state[f"assigned_{appt_id}"] = False
                            st.session_state[f"selected_resource_{appt_id}"] = None
                        
                        # Check if appointment is already assigned
                        with db_connection() as conn:
                            check_query = "SELECT maica__Resources__c FROM Appointments WHERE Id = ?"
                            assigned_to = pd.read_sql(check_query, conn, params=[appt_id]).iloc[0,0]
                        
                        if assigned_to and not st.session_state[f"assigned_{appt_id}"]:
                            st.session_state[f"assigned_{appt_id}"] = True
                            st.session_state[f"selected_resource_{appt_id}"] = assigned_to
                        
                        with st.expander(f"{row['Name']} - {row['DisplayStart']} to {row['DisplayEnd']} ({row['DurationHours']:.2f}h)", expanded=True):
                            # Show days and times in detail view
                            st.markdown("""
                            <div class="unassigned-details">
                                <div class="appointment-detail">
                                    <span class="detail-icon">📅</span>
                                    <span class="detail-label">Day:</span>
                                    <span class="detail-value">{day_of_week}, {date}</span>
                                </div>
                                <div class="appointment-detail">
                                    <span class="detail-icon">⏰</span>
                                    <span class="detail-label">Time:</span>
                                    <span class="detail-value">{start_time} to {end_time}</span>
                                </div>
                                <div class="appointment-detail">
                                    <span class="detail-icon">👤</span>
                                    <span class="detail-label">Participant:</span>
                                    <span class="detail-value">{participant}</span>
                                </div>
                                <div class="appointment-detail">
                                    <span class="detail-icon">⏱️</span>
                                    <span class="detail-label">Duration:</span>
                                    <span class="detail-value">{durationHours:.2f} hours</span>
                                </div>
                            </div>
                            """.format(
                                day_of_week=start_datetime.strftime('%A'),
                                date=start_datetime.strftime('%m/%d/%Y'),
                                start_time=start_datetime.strftime('%I:%M %p'),
                                end_time=end_datetime.strftime('%I:%M %p'),
                                participant=row['Participant'],
                                durationHours=row['DurationHours']
                            ), unsafe_allow_html=True)
                            
                            if st.session_state[f"assigned_{appt_id}"]:
                                st.warning(f"⚠️ This appointment is already assigned to {st.session_state[f'selected_resource_{appt_id}']}. Please select another appointment.")
                                continue
                            
                            # Create two columns for the dropdowns
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Local resources dropdown
                                local_selected = st.selectbox(
                                    "Assign Local Resource:",
                                    [""] + local_resources,
                                    key=f"local_select_{appt_id}"
                                )
                            
                            with col2:
                                # All resources dropdown
                                all_selected = st.selectbox(
                                    "Or select from ALL Resources:",
                                    [""] + all_resources_df['resource_name'].unique().tolist(),
                                    format_func=lambda x: f"{x} ({all_resources_df[all_resources_df['resource_name'] == x]['primaryLocation'].values[0]})" if x else "Select...",
                                    key=f"all_select_{appt_id}"
                                )
                            
                            # Determine which resource is selected
                            selected_resource = all_selected if all_selected else local_selected
                            
                            # Update session state when a new resource is selected
                            if selected_resource:
                                st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                            
                            # Get the resource to display
                            display_resource = st.session_state[f"selected_resource_{appt_id}"]
                            
                            # Show resource details if one is selected or after assignment
                            if display_resource:
                                resource_details = get_resource_details(display_resource)
                                constraints = calculate_constraints(display_resource, st.session_state.selected_location)
                                
                                # Display resource details in a card
                                st.markdown("""
                                <div class="resource-card">
                                    <div class="resource-card-header">
                                        <h3>Resource Details</h3>
                                    </div>
                                    <div class="resource-card-body">
                                        <div class="resource-detail">
                                            <span class="detail-icon">🧑‍💼</span>
                                            <span class="detail-label">Name:</span>
                                            <span class="detail-value">{fullName}</span>
                                        </div>
                                        <div class="resource-detail">
                                            <span class="detail-icon">📝</span>
                                            <span class="detail-label">Type:</span>
                                            <span class="detail-value">{employmentType}</span>
                                        </div>
                                        <div class="resource-detail">
                                            <span class="detail-icon">⏰</span>
                                            <span class="detail-label">Contracted Hours:</span>
                                            <span class="detail-value">{hoursPerWeek}/week</span>
                                        </div>
                                        <div class="resource-detail">
                                            <span class="detail-icon">📍</span>
                                            <span class="detail-label">Primary Location:</span>
                                            <span class="detail-value">{primaryLocation}</span>
                                        </div>
                                    </div>
                                </div>
                                """.format(
                                    fullName=resource_details['fullName'],
                                    employmentType=resource_details['employmentType'],
                                    hoursPerWeek=resource_details.get('hoursPerWeek', 38),
                                    primaryLocation=resource_details.get('primaryLocation', 'Unknown')
                                ), unsafe_allow_html=True)
                                
                                # Calculate week numbers (1 or 2) based on rotation start
                                rotation_start = constraints.get('rotation_start', datetime.now().date())
                                week_num = 1 if (start_datetime.date() - rotation_start).days < 7 else 2
                                
                                # Calculate new hours if this appointment were assigned
                                new_week1 = constraints['week1_hours']
                                new_week2 = constraints['week2_hours']
                                if week_num == 1:
                                    new_week1 += row['DurationHours']
                                else:
                                    new_week2 += row['DurationHours']
                                new_total = new_week1 + new_week2
                                
                                # Check contracted hours constraints
                                contracted_hours = resource_details.get('hoursPerWeek', 38)
                                employment_type = resource_details['employmentType']
                                
                                # Initialize error flags and messages
                                week1_class = ""
                                week2_class = ""
                                total_class = ""
                                hours_error = False
                                error_messages = []

                                if resource_details['employmentType'] == 'Full Time':
                                    if new_week1 > 38:
                                        week1_class = "metric-danger"
                                        hours_error = True
                                        error_messages.append(f"❌ Week 1 hours would be {new_week1:.1f} (must not exceed 38)")
                                    elif new_week1 < 38:
                                        week1_class = "metric-warning"
                                        error_messages.append(f"⚠️ Week 1 has {new_week1:.1f} hours (should reach 38)")
                                    
                                    if new_week2 > 38:
                                        week2_class = "metric-danger"
                                        hours_error = True
                                        error_messages.append(f"❌ Week 2 hours would be {new_week2:.1f} (must not exceed 38)")
                                    elif new_week2 < 38:
                                        week2_class = "metric-warning"
                                        error_messages.append(f"⚠️ Week 2 has {new_week2:.1f} hours (should reach 38)")
                                    
                                    if new_total > 76:
                                        total_class = "metric-danger"
                                        hours_error = True
                                        error_messages.append(f"❌ Total hours would be {new_total:.1f} (must not exceed 76)")

                                elif resource_details['employmentType'] == 'Part Time':
                                    if contracted_hours <= 0 or contracted_hours >= 38:
                                        hours_error = True
                                        error_messages.append(f"❌ Invalid contracted hours ({contracted_hours}) for Part-Time (must be 1-37)")
                                    if new_total > (contracted_hours * 2):
                                        total_class = "metric-danger"
                                        hours_error = True
                                        error_messages.append(f"❌ Total hours would be {new_total:.1f} (must not exceed {contracted_hours*2})")
                                
                                # Display constraints in metrics cards
                                st.markdown(f"""
                                    <div class="metrics-container">
                                        <div class="metric-card {week1_class}">
                                            <div class="metric-value">{new_week1:.1f}h</div>
                                            <div class="metric-label">Week 1 Hours {'❌' if week1_class == 'metric-danger' else '⚠️' if week1_class == 'metric-warning' else ''}</div>
                                        </div>
                                        <div class="metric-card {week2_class}">
                                            <div class="metric-value">{new_week2:.1f}h</div>
                                            <div class="metric-label">Week 2 Hours {'❌' if week2_class == 'metric-danger' else '⚠️' if week2_class == 'metric-warning' else ''}</div>
                                        </div>
                                        <div class="metric-card {total_class}">
                                            <div class="metric-value">{new_total:.1f}h</div>
                                            <div class="metric-label">Total Hours {'❌' if total_class == 'metric-danger' else ''}</div>
                                        </div>
                                        <div class="metric-card">
                                            <div class="metric-value">{constraints['max_consecutive_days']}/5</div>
                                            <div class="metric-label">Consecutive Days {'✅' if constraints['max_consecutive_days'] <= 5 else '❌'}</div>
                                        </div>
                                        <div class="metric-card">
                                            <div class="metric-value">{constraints['min_hours_between_shifts']}h</div>
                                            <div class="metric-label">Min Between Shifts {'✅' if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) >= 10 else '❌'}</div>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                                # For the warning message
                                if hours_error:
                                    st.markdown(f"""
                                    <div class="hours-warning">
                                        <p class="hours-warning-text">⚠️ WARNING: {error_messages[0]}</p>
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Validate other constraints
                                constraint_errors = []
                                if constraints['max_consecutive_days'] > 5:
                                    constraint_errors.append(f"❌ This resource has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
                                
                                if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
                                    constraint_errors.append(f"❌ Only {constraints['min_hours_between_shifts']} hours between shifts (min 10 required)")
                                
                                if constraint_errors:
                                    st.markdown("""
                                    <div class="constraint-alert">
                                        <div class="constraint-alert-header">
                                            ⚠️ Constraint Violations Detected
                                        </div>
                                        <div class="constraint-alert-body">
                                    """, unsafe_allow_html=True)
                                    for error in constraint_errors:
                                        st.markdown(f'<div class="constraint-error">{error}</div>', unsafe_allow_html=True)
                                    st.markdown("</div></div>", unsafe_allow_html=True)
                            
                            # Assign button (only show if not already assigned)
                            if not st.session_state[f"assigned_{appt_id}"]:
                                if st.button("✨ Assign Resource", key=f"assign_btn_{appt_id}"):
                                    if not selected_resource:
                                        st.error("Please select a resource to assign")
                                    else:
                                        # Check constraints before assignment
                                        constraints = calculate_constraints(selected_resource, st.session_state.selected_location)
                                        
                                        # Get existing appointments for this resource
                                        existing_appointments = get_appointments_by_resource_and_location(
                                            selected_resource, 
                                            st.session_state.selected_location
                                        )
                                        
                                        # Check consecutive days constraint (max 5)
                                        if constraints['max_consecutive_days'] >= 5:
                                            st.error(f"❌ Cannot assign - {selected_resource} already has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
                                        
                                        # Check minimum hours between shifts (min 10 hours)
                                        elif constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
                                            st.error(f"❌ Cannot assign - Only {constraints['min_hours_between_shifts']} hours between shifts (min 10 required)")
                                        
                                        # Additional check for the new appointment's timing
                                        else:
                                            # Check if this new appointment would violate the 10-hour gap rule
                                            violation_found = False
                                            for _, existing_row in existing_appointments.iterrows():
                                                existing_start = pd.to_datetime(existing_row['StartDateTime'])
                                                existing_end = pd.to_datetime(existing_row['EndDateTime'])
                                                
                                                # Check gap before new appointment
                                                gap_before = (start_datetime - existing_end).total_seconds() / 3600
                                                if 0 < gap_before < 10:
                                                    st.error(f"❌ Cannot assign - Only {gap_before:.1f} hours between new shift and existing shift ending at {existing_row['DisplayEnd']}")
                                                    violation_found = True
                                                    break
                                                
                                                # Check gap after new appointment
                                                gap_after = (existing_start - end_datetime).total_seconds() / 3600
                                                if 0 < gap_after < 10:
                                                    st.error(f"❌ Cannot assign - Only {gap_after:.1f} hours between new shift and existing shift starting at {existing_row['DisplayStart']}")
                                                    violation_found = True
                                                    break
                                            
                                            if not violation_found and not hours_error:
                                                if assign_resource_to_appointment(appt_id, selected_resource):
                                                    st.session_state[f"assigned_{appt_id}"] = True
                                                    st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                                                    st.success(f"✅ Successfully assigned {selected_resource} to this appointment!")
                                                    # Force update by rerunning but keeping expander open
                                                    st.rerun()
                                                else:
                                                    st.error("Failed to assign resource")
                                            elif hours_error:
                                                st.error("Cannot assign due to contracted hours violation")
                else:
                    st.markdown("""
                    <div class="empty-state success">
                        <div class="empty-state-icon">🎉</div>
                        <div class="empty-state-text">
                            All appointments at {location} have resources assigned!
                        </div>
                    </div>
                    """.format(
                        location=st.session_state.selected_location
                    ), unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <div class="empty-state-text">
                    No resources found for {location}
                </div>
            </div>
            """.format(
                location=st.session_state.selected_location
            ), unsafe_allow_html=True)

if __name__ == "__main__":
    main()