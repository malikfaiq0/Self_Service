import streamlit as st
import pyodbc
import pandas as pd
from datetime import datetime, timedelta
import os
from contextlib import contextmanager

# Set page config must be first command
st.set_page_config(
    layout="wide",
    page_title="Shift Management",
    page_icon="📅",
    initial_sidebar_state="expanded"
)

# Custom CSS
def load_css():
    with open("styles.css", "r", encoding="utf-8", errors="ignore") as f:
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
# try:
#     with db_connection() as conn:
#         st.sidebar.success("✅ Connected to the database successfully!")
# except Exception as e:
#     st.sidebar.error(f"❌ Database connection failed: {str(e)}")

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
        FROM NewAppointments
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
        FROM NewAppointments
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

@st.cache_data(ttl=300)
def get_week_ranges(location):
    """Get the start and end dates for week 1 and week 2 based on actual appointments for this location"""
    norm_location = normalize_location(location)
    
    with db_connection() as conn:
        query = """
        SELECT 
            MIN(maica__Scheduled_Start__c) as first_start,
            MAX(maica__Scheduled_Start__c) as last_start
        FROM NewAppointments
        WHERE maica__Participant_Location__c LIKE '%' + ? + '%'
        AND maica__Participants__c LIKE '%Roster%'
        """
        df = pd.read_sql(query, conn, params=[norm_location])
    
    if df.empty or df.iloc[0]['first_start'] is None:
        # Default to current week if no appointments found
        today = datetime.now().date()
        week1_start = today - timedelta(days=today.weekday())
        week1_end = week1_start + timedelta(days=6)
        week2_start = week1_end + timedelta(days=1)
        week2_end = week2_start + timedelta(days=6)
    else:
        first_start = pd.to_datetime(df.iloc[0]['first_start']).date()
        last_start = pd.to_datetime(df.iloc[0]['last_start']).date()
        
        # Calculate week ranges based on actual appointment dates
        week1_start = first_start
        week1_end = week1_start + timedelta(days=6)
        week2_start = week1_end + timedelta(days=1)
        week2_end = last_start  # Use last appointment date as end of week 2
    
    return {
        'week1_start': week1_start,
        'week1_end': week1_end,
        'week2_start': week2_start,
        'week2_end': week2_end
    }


@st.cache_data(ttl=300)
def get_appointments_by_resource_and_location(resource, location):
    norm_location = normalize_location(location)
    
    # First get the week ranges for this location
    week_ranges = get_week_ranges(location)
    
    with db_connection() as conn:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participants__c AS Participant
        FROM NewAppointments
        WHERE REPLACE(REPLACE(maica__Resources__c, '  ', ' '), '  ', ' ') = ?
        AND maica__Participant_Location__c LIKE '%' + ? + '%'
        AND maica__Participants__c LIKE '%Roster%'
        ORDER BY maica__Scheduled_Start__c
        """
        normalized_resource = ' '.join(resource.split())
        params = [normalized_resource, norm_location]
        
        df = pd.read_sql(query, conn, params=params)
    
    if not df.empty:
        df['DurationHours'] = df['DurationMinutes'] / 60
        df['StartDate'] = pd.to_datetime(df['StartDateTime']).dt.date
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%a, %m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%a, %m/%d/%Y %I:%M %p')
        df['DayOfWeek'] = pd.to_datetime(df['StartDateTime']).dt.day_name()
        
        # Calculate week number based on the location's week ranges
        def calculate_week(start_date):
            if week_ranges['week1_start'] <= start_date <= week_ranges['week1_end']:
                return 1
            elif week_ranges['week2_start'] <= start_date <= week_ranges['week2_end']:
                return 2
            else:
                return 1  # Default to week 1 if outside these ranges
        
        df['Week'] = df['StartDate'].apply(calculate_week)
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
    
    # First get the week ranges for this location
    week_ranges = get_week_ranges(location)
    
    with db_connection() as conn:
        query = """
        SELECT 
            Id AS AppointmentID,
            Name,
            CONVERT(VARCHAR, maica__Scheduled_Start__c, 120) AS StartDateTime,
            CONVERT(VARCHAR, maica__Scheduled_End__c, 120) AS EndDateTime,
            maica__Scheduled_Duration_Minutes__c AS DurationMinutes,
            maica__Participants__c AS Participant
        FROM NewAppointments
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
        df['DisplayStart'] = pd.to_datetime(df['StartDateTime']).dt.strftime('%a, %m/%d/%Y %I:%M %p')
        df['DisplayEnd'] = pd.to_datetime(df['EndDateTime']).dt.strftime('%a, %m/%d/%Y %I:%M %p')
        df['DayOfWeek'] = pd.to_datetime(df['StartDateTime']).dt.day_name()
        
        # Calculate week number based on the location's week ranges
        def calculate_week(start_date):
            if week_ranges['week1_start'] <= start_date <= week_ranges['week1_end']:
                return 1
            elif week_ranges['week2_start'] <= start_date <= week_ranges['week2_end']:
                return 2
            else:
                return 1  # Default to week 1 if outside these ranges
        
        df['Week'] = df['StartDate'].apply(calculate_week)
    return df

def assign_resource_to_appointment(appointment_id, resource_name):
    normalized_name = ' '.join(resource_name.split())
    
    # First check if appointment is already assigned
    with db_connection() as conn:
        check_query = "SELECT maica__Resources__c FROM NewAppointments WHERE Id = ?"
        current_assignment = pd.read_sql(check_query, conn, params=[appointment_id]).iloc[0,0]
        
        if current_assignment and current_assignment != 'NULL':
            st.error(f"This appointment is already assigned to {current_assignment}")
            return False
    
    # Get appointment details
    with db_connection() as conn:
        appt_query = """
        SELECT 
            maica__Scheduled_Start__c,
            maica__Scheduled_End__c,
            maica__Scheduled_Duration_Minutes__c
        FROM NewAppointments
        WHERE Id = ?
        """
        appt_details = pd.read_sql(appt_query, conn, params=[appointment_id]).iloc[0]
    
    # Get current constraints for the resource
    resource_details = get_resource_details(resource_name)
    constraints = calculate_constraints(resource_name, resource_details['primaryLocation'])
    
    # Check minimum hours between shifts
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        st.error(f"Cannot assign - Minimum 10 hours required between shifts (currently {constraints['min_hours_between_shifts']}h)")
        return False
    
    # Check consecutive days
    if constraints['max_consecutive_days'] > 5:
        st.error(f"Cannot assign - Exceeds maximum 5 consecutive days (currently {constraints['max_consecutive_days']} days)")
        return False
    
    # Check weekly hours (using week-specific validation)
    appt_hours = appt_details['maica__Scheduled_Duration_Minutes__c'] / 60
    start_date = pd.to_datetime(appt_details['maica__Scheduled_Start__c']).date()
    
    # Get week ranges for the location
    week_ranges = get_week_ranges(resource_details['primaryLocation'])
    
    # Determine which week this appointment belongs to
    if week_ranges['week1_start'] <= start_date <= week_ranges['week1_end']:
        week_num = 1
    else:
        week_num = 2
    
    if resource_details['employmentType'] == 'Full Time':
        if week_num == 1 and (constraints['week1_hours'] + appt_hours) > 38:
            st.error(f"Cannot assign - Week 1 hours would exceed 38 (would be {constraints['week1_hours'] + appt_hours:.1f}h)")
            return False
        if week_num == 2 and (constraints['week2_hours'] + appt_hours) > 38:
            st.error(f"Cannot assign - Week 2 hours would exceed 38 (would be {constraints['week2_hours'] + appt_hours:.1f}h)")
            return False
        if (constraints['total_hours'] + appt_hours) > 76:
            st.error(f"Cannot assign - Total hours would exceed 76 (would be {constraints['total_hours'] + appt_hours:.1f}h)")
            return False
    elif resource_details['employmentType'] == 'Part Time':
        if week_num == 1 and (constraints['week1_hours'] + appt_hours) > resource_details['hoursPerWeek']:
            st.error(f"Cannot assign - Week 1 hours would exceed contracted {resource_details['hoursPerWeek']}h (would be {constraints['week1_hours'] + appt_hours:.1f}h)")
            return False
        if week_num == 2 and (constraints['week2_hours'] + appt_hours) > resource_details['hoursPerWeek']:
            st.error(f"Cannot assign - Week 2 hours would exceed contracted {resource_details['hoursPerWeek']}h (would be {constraints['week2_hours'] + appt_hours:.1f}h)")
            return False
        if (constraints['total_hours'] + appt_hours) > (resource_details['hoursPerWeek'] * 2):
            st.error(f"Cannot assign - Total hours would exceed contracted {resource_details['hoursPerWeek']*2}h (would be {constraints['total_hours'] + appt_hours:.1f}h)")
            return False
    
    # If all checks pass, proceed with assignment
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            update_query = """
            UPDATE NewAppointments
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
@st.cache_data(ttl=300)
def calculate_constraints(resource_name, location):
    norm_location = normalize_location(location)
    normalized_name = ' '.join(resource_name.split())
    
    with db_connection() as conn:
        # Get resource details
        resource_query = """
        SELECT employmentType, hoursPerWeek 
        FROM Resources 
        WHERE REPLACE(REPLACE(fullName, '  ', ' '), '  ', ' ') = ?
        """
        resource_df = pd.read_sql(resource_query, conn, params=[normalized_name])
        
        if resource_df.empty:
            return {
                'max_consecutive_days': 0,
                'min_hours_between_shifts': 'N/A',
                'same_day_min_gap': 'N/A',
                'week1_hours': 0,
                'week2_hours': 0,
                'total_hours': 0,
                'shift_details': [],
                'employmentType': 'Unknown',
                'contractedHours': 0,
                'gap_violation': False,
                'same_day_gap_violation': False,
                'week1_violation': False,
                'week2_violation': False,
                'total_violation': False
            }
            
        resource_details = resource_df.iloc[0]
        
        # Get appointments sorted by start time
        query = """
        SELECT 
            a.Id AS AppointmentID,
            a.maica__Scheduled_Start__c AS StartDateTime,
            a.maica__Scheduled_End__c AS EndDateTime,
            a.maica__Scheduled_Duration_Minutes__c AS DurationMinutes
        FROM NewAppointments a
        WHERE REPLACE(REPLACE(a.maica__Resources__c, '  ', ' '), '  ', ' ') = ?
        AND a.maica__Participant_Location__c LIKE '%' + ? + '%'
        ORDER BY a.maica__Scheduled_Start__c
        """
        params = [normalized_name, norm_location]
        df = pd.read_sql(query, conn, params=params)
    
    if df.empty:
        return {
            'max_consecutive_days': 0,
            'min_hours_between_shifts': 'N/A',
            'same_day_min_gap': 'N/A',
            'week1_hours': 0,
            'week2_hours': 0,
            'total_hours': 0,
            'shift_details': [],
            'employmentType': resource_details['employmentType'],
            'contractedHours': resource_details['hoursPerWeek'],
            'gap_violation': False,
            'same_day_gap_violation': False,
            'week1_violation': False,
            'week2_violation': False,
            'total_violation': False
        }
    
    df['StartDateTime'] = pd.to_datetime(df['StartDateTime'])
    df['EndDateTime'] = pd.to_datetime(df['EndDateTime'])
    df = df.sort_values('StartDateTime')
    df['Date'] = df['StartDateTime'].dt.date
    df['Week'] = df['StartDateTime'].apply(lambda x: 1 if (x.date() - df['StartDateTime'].min().date()).days < 7 else 2)
    
    # Calculate consecutive days PER WEEK
    max_consecutive_days = 0
    for week_num in [1, 2]:
        week_df = df[df['Week'] == week_num]
        if not week_df.empty:
            unique_dates = week_df.drop_duplicates('Date').sort_values('Date')
            if len(unique_dates) > 1:
                unique_dates['DayDiff'] = unique_dates['Date'].diff().dt.days.fillna(1)
                unique_dates['ConsecutiveGroup'] = (unique_dates['DayDiff'] != 1).cumsum()
                consecutive_counts = unique_dates.groupby('ConsecutiveGroup').size()
                week_max = consecutive_counts.max()
                if week_max > max_consecutive_days:
                    max_consecutive_days = week_max
    
    # Calculate minimum hours between ALL consecutive shifts
    min_hours_between = None
    gap_violation = False
    
    # Calculate same-day minimum gap
    same_day_min_gap = None
    same_day_gap_violation = False
    
    # Check gaps between all consecutive shifts
    for i in range(len(df)-1):
        current_end = df.iloc[i]['EndDateTime']
        next_start = df.iloc[i+1]['StartDateTime']
        gap = (next_start - current_end).total_seconds() / 3600
        
        # Update overall minimum gap
        if min_hours_between is None or gap < min_hours_between:
            min_hours_between = gap
            if gap < 10:
                gap_violation = True
        
        # Update same-day gap if applicable
        if current_end.date() == next_start.date():
            if same_day_min_gap is None or gap < same_day_min_gap:
                same_day_min_gap = gap
                if gap < 10:
                    same_day_gap_violation = True
    
    # Calculate weekly hours
    weekly_hours = df.groupby('Week')['DurationMinutes'].sum() / 60
    week1_hours = weekly_hours.get(1, 0)
    week2_hours = weekly_hours.get(2, 0)
    total_hours = weekly_hours.sum()
    
    # Check for violations
    week1_violation = False
    week2_violation = False
    total_violation = False
    
    if resource_details['employmentType'] == 'Full Time':
        if week1_hours > 38:
            week1_violation = True
        if week2_hours > 38:
            week2_violation = True
        if total_hours > 76:
            total_violation = True
    elif resource_details['employmentType'] == 'Part Time':
        contracted_hours = resource_details['hoursPerWeek']
        if week1_hours > contracted_hours:
            week1_violation = True
        if week2_hours > contracted_hours:
            week2_violation = True
        if total_hours > (contracted_hours * 2):
            total_violation = True
    
    return {
        'max_consecutive_days': max_consecutive_days,
        'min_hours_between_shifts': f"{min_hours_between:.1f}" if min_hours_between is not None else 'N/A',
        'same_day_min_gap': f"{same_day_min_gap:.1f}" if same_day_min_gap is not None else 'N/A',
        'week1_hours': week1_hours,
        'week2_hours': week2_hours,
        'total_hours': total_hours,
        'shift_details': df.to_dict('records'),
        'employmentType': resource_details['employmentType'],
        'contractedHours': resource_details['hoursPerWeek'],
        'gap_violation': gap_violation,
        'same_day_gap_violation': same_day_gap_violation,
        'week1_violation': week1_violation,
        'week2_violation': week2_violation,
        'total_violation': total_violation
    }

def validate_assignment(resource_name, location, new_appt_start, new_appt_end, week_num=None):
    """Validate if new assignment would violate constraints"""
    constraints = calculate_constraints(resource_name, location)
    new_start = pd.to_datetime(new_appt_start)
    new_end = pd.to_datetime(new_appt_end)
    
    # Check for gap violations with existing shifts in same week
    min_gap = None
    for appt in constraints['shift_details']:
        if appt['Week'] == week_num:
            existing_start = pd.to_datetime(appt['StartDateTime'])
            existing_end = pd.to_datetime(appt['EndDateTime'])
            
            gap_before = (existing_start - new_end).total_seconds() / 3600
            gap_after = (new_start - existing_end).total_seconds() / 3600
            
            if gap_before > 0 and gap_after > 0:
                gap = min(gap_before, gap_after)
            else:
                gap = max(gap_before, gap_after)
            
            if min_gap is None or gap < min_gap:
                min_gap = gap
    
    if min_gap is not None and min_gap < 10:
        return False, f"Would have only {min_gap:.1f}h gap with existing shift (min 10h required)"
    
    # Check consecutive days only for current week
    current_week_dates = [pd.to_datetime(appt['StartDateTime']).date() 
                         for appt in constraints['shift_details'] 
                         if appt['Week'] == week_num]
    current_week_dates = list(set(current_week_dates))  # Get unique dates
    new_date = new_start.date()
    
    if current_week_dates:
        all_dates = sorted(current_week_dates + [new_date])
        consecutive_count = 1
        max_consecutive = 1
        for i in range(1, len(all_dates)):
            if (all_dates[i] - all_dates[i-1]).days == 1:
                consecutive_count += 1
                max_consecutive = max(max_consecutive, consecutive_count)
            else:
                consecutive_count = 1
        
        if max_consecutive > 5:
            return False, f"Would have {max_consecutive} consecutive days in this week (max 5 allowed)"
    
    # Only check the weekly hours for the relevant week
    resource_details = get_resource_details(resource_name)
    appt_hours = (new_end - new_start).total_seconds() / 3600
    
    if week_num == 1:
        if resource_details['employmentType'] == 'Full Time' and (constraints['week1_hours'] + appt_hours) > 38:
            return False, f"Would exceed Week 1 limit (38h)"
        elif resource_details['employmentType'] == 'Part Time' and (constraints['week1_hours'] + appt_hours) > resource_details['hoursPerWeek']:
            return False, f"Would exceed Week 1 contracted hours ({resource_details['hoursPerWeek']}h)"
    
    elif week_num == 2:
        if resource_details['employmentType'] == 'Full Time' and (constraints['week2_hours'] + appt_hours) > 38:
            return False, f"Would exceed Week 2 limit (38h)"
        elif resource_details['employmentType'] == 'Part Time' and (constraints['week2_hours'] + appt_hours) > resource_details['hoursPerWeek']:
            return False, f"Would exceed Week 2 contracted hours ({resource_details['hoursPerWeek']}h)"
    
    # Check total hours constraint for both weeks
    if (constraints['total_hours'] + appt_hours) > (38 * 2 if resource_details['employmentType'] == 'Full Time' else resource_details['hoursPerWeek'] * 2):
        return False, f"Would exceed total hours limit"
    
    return True, "Valid assignment"


def calculate_constraints_with_potential_assignment(resource_name, location, new_appt_start, new_appt_end):
    """Calculate constraints including a potential new assignment"""
    constraints = calculate_constraints(resource_name, location)
    
    if constraints['shift_details']:
        # Check if new appointment overlaps or has insufficient gap with existing ones
        new_start = pd.to_datetime(new_appt_start)
        new_end = pd.to_datetime(new_appt_end)
        
        # Find closest appointments before and after
        min_gap = None
        for appt in constraints['shift_details']:
            existing_start = pd.to_datetime(appt['StartDateTime'])
            existing_end = pd.to_datetime(appt['EndDateTime'])
            
            # Only check gaps for same-day appointments
            if existing_start.date() == new_start.date():
                if new_start < existing_end:  # Overlapping
                    gap = (existing_start - new_end).total_seconds() / 3600
                else:
                    gap = (new_start - existing_end).total_seconds() / 3600
                
                if min_gap is None or gap < min_gap:
                    min_gap = gap
        
        if min_gap is not None and min_gap < 10:
            constraints['min_hours_between_shifts'] = f"{min_gap:.1f}"
            constraints['gap_violation'] = True
        else:
            constraints['gap_violation'] = False
    
    return constraints

def display_constraints(constraints):
    consecutive_class = "metric-card"
    if constraints['max_consecutive_days'] >= 5:
        consecutive_class = "metric-card alert-danger"
    
    hours_class = "metric-card"
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        hours_class = "metric-card alert-danger"
    
    week1_class = "metric-card"
    if constraints['week1_violation']:
        week1_class = "metric-card alert-danger"
    
    week2_class = "metric-card"
    if constraints['week2_violation']:
        week2_class = "metric-card alert-danger"
    
    total_class = "metric-card"
    if constraints['total_violation']:
        total_class = "metric-card alert-danger"
    
    st.markdown("""
    <div class="metric-container">
        <div class="{consecutive_class}">
            <div class="metric-value">{max_consecutive_days}/5</div>
            <div class="metric-label">Consecutive Days</div>
        </div>
        <div class="{hours_class}">
            <div class="metric-value">{min_hours_between_shifts}h</div>
            <div class="metric-label">Min Between Shifts</div>
        </div>
        <div class="{week1_class}">
            <div class="metric-value">{week1_hours:.1f}h</div>
            <div class="metric-label">Week 1 Hours</div>
        </div>
        <div class="{week2_class}">
            <div class="metric-value">{week2_hours:.1f}h</div>
            <div class="metric-label">Week 2 Hours</div>
        </div>
        <div class="{total_class}">
            <div class="metric-value">{total_hours:.1f}h</div>
            <div class="metric-label">Total Hours</div>
        </div>
    </div>
    """.format(
        max_consecutive_days=constraints['max_consecutive_days'],
        min_hours_between_shifts=constraints['min_hours_between_shifts'],
        week1_hours=constraints['week1_hours'],
        week2_hours=constraints['week2_hours'],
        total_hours=constraints['total_hours'],
        consecutive_class=consecutive_class,
        hours_class=hours_class,
        week1_class=week1_class,
        week2_class=week2_class,
        total_class=total_class
    ), unsafe_allow_html=True)

    # Validate constraints
    constraint_errors = []
    if constraints['max_consecutive_days'] > 5:
        constraint_errors.append(f"❌ This resource has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
    
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        constraint_errors.append(f"❌ Only {constraints['min_hours_between_shifts']} hours between shifts on the same day (min 10 required)")
    
    if constraints['employmentType'] == 'Full Time':
        if constraints['week1_violation']:
            constraint_errors.append(f"❌ Week 1 hours exceed 38 (currently {constraints['week1_hours']:.1f}h)")
        if constraints['week2_violation']:
            constraint_errors.append(f"❌ Week 2 hours exceed 38 (currently {constraints['week2_hours']:.1f}h)")
        if constraints['total_violation']:
            constraint_errors.append(f"❌ Total hours exceed 76 (currently {constraints['total_hours']:.1f}h)")
    elif constraints['employmentType'] == 'Part Time':
        if constraints['week1_violation']:
            constraint_errors.append(f"❌ Week 1 hours exceed contracted {constraints['contractedHours']}h (currently {constraints['week1_hours']:.1f}h)")
        if constraints['week2_violation']:
            constraint_errors.append(f"❌ Week 2 hours exceed contracted {constraints['contractedHours']}h (currently {constraints['week2_hours']:.1f}h)")
        if constraints['total_violation']:
            constraint_errors.append(f"❌ Total hours exceed contracted {constraints['contractedHours']*2}h (currently {constraints['total_hours']:.1f}h)")
    
    if constraint_errors:
        st.markdown("""
        <div class="alert alert-danger">
            <strong>⚠️ Constraint Violations Detected</strong>
            <ul>
        """, unsafe_allow_html=True)
        for error in constraint_errors:
            st.markdown(f'<li>{error}</li>', unsafe_allow_html=True)
        st.markdown("</ul></div>", unsafe_allow_html=True)
        
def display_resource_details(resource_details):
    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="icon">👤</span> Resource Details
        </div>
        <div class="resource-details">
            <div class="resource-detail">
                <span class="detail-label">Name</span>
                <span class="detail-value">{fullName}</span>
            </div>
            <div class="resource-detail">
                <span class="detail-label">Employment Type</span>
                <span class="detail-value">{employmentType}</span>
            </div>
            <div class="resource-detail">
                <span class="detail-label">Contracted Hours</span>
                <span class="detail-value">{hoursPerWeek}/week</span>
            </div>
            <div class="resource-detail">
                <span class="detail-label">Primary Location</span>
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

def display_constraints(constraints):
    consecutive_class = "metric-card"
    if constraints['max_consecutive_days'] >= 5:
        consecutive_class = "metric-card alert-danger"
    
    hours_class = "metric-card"
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        hours_class = "metric-card alert-danger"
    
    st.markdown("""
    <div class="metric-container">
        <div class="{consecutive_class}">
            <div class="metric-value">{max_consecutive_days}/5</div>
            <div class="metric-label">Consecutive Days</div>
        </div>
        <div class="{hours_class}">
            <div class="metric-value">{min_hours_between_shifts}h</div>
            <div class="metric-label">Min Between Shifts</div>
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
        min_hours_between_shifts=constraints['min_hours_between_shifts'],
        week1_hours=constraints['week1_hours'],
        week2_hours=constraints['week2_hours'],
        total_hours=constraints['total_hours'],
        consecutive_class=consecutive_class,
        hours_class=hours_class
    ), unsafe_allow_html=True)

def display_appointment_card(row):
    # Format the date and time display to include days
    start_datetime = pd.to_datetime(row['StartDateTime'])
    end_datetime = pd.to_datetime(row['EndDateTime'])
    
    display_start = start_datetime.strftime('%a, %m/%d/%Y %I:%M %p')
    display_end = end_datetime.strftime('%a, %m/%d/%Y %I:%M %p')
    
    st.markdown(f"""
    <div class="appointment-card">
        <div class="appointment-header">
            <div class="appointment-title">{row['Name']}</div>
            <div class="appointment-time">{row['DurationHours']:.2f}h</div>
        </div>
        <div class="appointment-time">{display_start} to {display_end}</div>
        <div style="margin-top: 0.5rem;">
            <span class="badge badge-primary">{row['Participant']}</span>
            <span class="badge badge-secondary">{row['DayOfWeek']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def display_day_tabs(days, selected_day, week_num=None):
    # Define all possible days in order
    all_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Create columns for each day
    cols = st.columns(len(all_days))
    
    for i, day in enumerate(all_days):
        with cols[i]:
            # Include week_num in the key if provided
            key = f"day_{day}_{week_num}" if week_num is not None else f"day_{day}"
            if st.button(day, key=key, disabled=(day not in days)):
                selected_day = day
    
    # Show which day is currently selected
    st.markdown(f"**Showing appointments for:** {selected_day}")
    return selected_day

def display_resource_constraints(resource_name, location):
    """Show current constraints without adding potential assignment hours"""
    constraints = calculate_constraints(resource_name, location)
    
    # Display constraints in metrics cards
    consecutive_class = "metric-card"
    if constraints['max_consecutive_days'] > 5:
        consecutive_class = "metric-card alert-danger"
    
    hours_class = "metric-card"
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        hours_class = "metric-card alert-danger"
    
    week1_class = "metric-card"
    if constraints['week1_violation']:
        week1_class = "metric-card alert-danger"
    
    week2_class = "metric-card"
    if constraints['week2_violation']:
        week2_class = "metric-card alert-danger"
    
    total_class = "metric-card"
    if constraints['total_violation']:
        total_class = "metric-card alert-danger"
    
    st.markdown("""
    <div class="metric-container">
        <div class="{consecutive_class}">
            <div class="metric-value">{max_consecutive_days}/5</div>
            <div class="metric-label">Consecutive Days</div>
        </div>
        <div class="{hours_class}">
            <div class="metric-value">{min_hours_between_shifts}h</div>
            <div class="metric-label">Min Between Shifts</div>
        </div>
        <div class="{week1_class}">
            <div class="metric-value">{week1_hours:.1f}h</div>
            <div class="metric-label">Week 1 Hours</div>
        </div>
        <div class="{week2_class}">
            <div class="metric-value">{week2_hours:.1f}h</div>
            <div class="metric-label">Week 2 Hours</div>
        </div>
        <div class="{total_class}">
            <div class="metric-value">{total_hours:.1f}h</div>
            <div class="metric-label">Total Hours</div>
        </div>
    </div>
    """.format(
        max_consecutive_days=constraints['max_consecutive_days'],
        min_hours_between_shifts=constraints['min_hours_between_shifts'],
        week1_hours=constraints['week1_hours'],
        week2_hours=constraints['week2_hours'],
        total_hours=constraints['total_hours'],
        consecutive_class=consecutive_class,
        hours_class=hours_class,
        week1_class=week1_class,
        week2_class=week2_class,
        total_class=total_class
    ), unsafe_allow_html=True)

    # Validate constraints
    constraint_errors = []
    if constraints['max_consecutive_days'] > 5:
        constraint_errors.append(f"❌ This resource has {constraints['max_consecutive_days']} consecutive days (max 5 allowed)")
    
    if constraints['min_hours_between_shifts'] != 'N/A' and float(constraints['min_hours_between_shifts']) < 10:
        constraint_errors.append(f"❌ Only {constraints['min_hours_between_shifts']} hours between shifts (min 10 required)")
    
    if constraints['employmentType'] == 'Full Time':
        if constraints['week1_hours'] > 38:
            constraint_errors.append(f"❌ Week 1 hours exceed 38 (currently {constraints['week1_hours']:.1f}h)")
        if constraints['week2_hours'] > 38:
            constraint_errors.append(f"❌ Week 2 hours exceed 38 (currently {constraints['week2_hours']:.1f}h)")
        if constraints['total_hours'] > 76:
            constraint_errors.append(f"❌ Total hours exceed 76 (currently {constraints['total_hours']:.1f}h)")
    elif constraints['employmentType'] == 'Part Time':
        if constraints['week1_hours'] > constraints['contractedHours']:
            constraint_errors.append(f"❌ Week 1 hours exceed contracted {constraints['contractedHours']}h (currently {constraints['week1_hours']:.1f}h)")
        if constraints['week2_hours'] > constraints['contractedHours']:
            constraint_errors.append(f"❌ Week 2 hours exceed contracted {constraints['contractedHours']}h (currently {constraints['week2_hours']:.1f}h)")
        if constraints['total_hours'] > (constraints['contractedHours'] * 2):
            constraint_errors.append(f"❌ Total hours exceed contracted {constraints['contractedHours']*2}h (currently {constraints['total_hours']:.1f}h)")
    
    if constraint_errors:
        st.markdown("""
        <div class="alert alert-danger">
            <strong>⚠️ Constraint Violations Detected</strong>
            <ul>
        """, unsafe_allow_html=True)
        for error in constraint_errors:
            st.markdown(f'<li>{error}</li>', unsafe_allow_html=True)
        st.markdown("</ul></div>", unsafe_allow_html=True)

def display_assigned_tab(selected_location, selected_employment_type, selected_resource):
    resources = get_resources_by_location(
        selected_location,
        selected_employment_type
    )

    if resources:
        new_resource = st.selectbox(
            "Select Resource:",
            resources,
            key="assigned_resource_selectbox"
        )

        if new_resource != selected_resource:
            st.session_state.selected_resource = new_resource
            st.rerun()

        if selected_resource:
            appointments = get_appointments_by_resource_and_location(
                selected_resource,
                selected_location
            )

            if not appointments.empty:
                if not pd.api.types.is_datetime64_any_dtype(appointments['StartDateTime']):
                    appointments['StartDateTime'] = pd.to_datetime(appointments['StartDateTime'])
                if not pd.api.types.is_datetime64_any_dtype(appointments['EndDateTime']):
                    appointments['EndDateTime'] = pd.to_datetime(appointments['EndDateTime'])

                st.markdown(f"""
                <div class="card">
                    <div class="card-header">
                        <span class="icon">📅</span> {selected_resource}'s Schedule at {selected_location}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                resource_details = get_resource_details(selected_resource)
                display_resource_details(resource_details)
                display_resource_constraints(selected_resource, selected_location)

                all_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

                appointments['Date'] = appointments['StartDateTime'].dt.date
                appointments['DayOfWeek'] = appointments['StartDateTime'].dt.day_name()

                week1_appointments = appointments[appointments['Week'] == 1]
                week2_appointments = appointments[appointments['Week'] == 2]

                week1_dates = week1_appointments['StartDateTime'].dt.date.unique()
                week2_dates = week2_appointments['StartDateTime'].dt.date.unique()

                week_tab1, week_tab2 = st.tabs([
                    f"📅 Week 1 ({min(week1_dates).strftime('%b %d')} - {max(week1_dates).strftime('%b %d')})" if len(week1_dates) > 0 else "📅 Week 1",
                    f"📅 Week 2 ({min(week2_dates).strftime('%b %d')} - {max(week2_dates).strftime('%b %d')})" if len(week2_dates) > 0 else "📅 Week 2"
                ])

                def render_week(week_appointments, label):
                    if not week_appointments.empty:
                        unique_days = [
                            f"{day} ({week_appointments[week_appointments['DayOfWeek'] == day]['StartDateTime'].dt.strftime('%b %d').iloc[0]})"
                            if not week_appointments[week_appointments['DayOfWeek'] == day].empty else f"{day}"
                            for day in all_days
                        ]

                        st.subheader(f"{label} - {selected_resource}")
                        cols = st.columns(7)

                        for i, day in enumerate(unique_days):
                            with cols[i]:
                                st.markdown(f"""
                                <div class="weekly-header" style="text-align:center; font-weight:bold;">
                                    {day.split()[0][:3]}<br>{day.split('(')[1][:-1] if '(' in day else ''}
                                </div>
                                <div class="weekly-day-column">
                                """, unsafe_allow_html=True)

                        appointments_by_day = {day: [] for day in all_days}
                        for _, row in week_appointments.iterrows():
                            day = row['DayOfWeek']
                            start_time = row['StartDateTime'].strftime('%I:%M %p')
                            end_time = row['EndDateTime'].strftime('%I:%M %p')
                            duration = f"{row['DurationHours']:.1f}h"
                            appointments_by_day[day].append(
                                f"<span class='time-range'>{start_time} - {end_time}</span><br>"
                                f"<span class='duration'>({duration})</span>"
                            )

                        max_appointments = max(len(appts) for appts in appointments_by_day.values())
                        for i in range(max_appointments):
                            cols = st.columns(7)
                            for j, day in enumerate(all_days):
                                with cols[j]:
                                    if i < len(appointments_by_day[day]):
                                        st.markdown(f"""
                                        <div class="weekly-appointment">
                                            {appointments_by_day[day][i]}
                                        </div>
                                        """, unsafe_allow_html=True)

                        cols = st.columns(7)
                        for col in cols:
                            with col:
                                st.markdown("</div>", unsafe_allow_html=True)

                        total_hours = week_appointments['DurationHours'].sum()
                        st.markdown(f"""
                        <div class="total-hours">
                            Total Hours: {total_hours:.2f} hours
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown("""
                        <div class="empty-state">
                            <div class="empty-state-icon">📅</div>
                            <div class="empty-state-text">No appointments</div>
                        </div>
                        """, unsafe_allow_html=True)

                with week_tab1:
                    render_week(week1_appointments, "Week 1 Schedule")

                with week_tab2:
                    render_week(week2_appointments, "Week 2 Schedule")

            else:
                st.markdown("""
                    <div class="empty-state">
                        <div class="empty-state-icon">⚠️</div>
                        <div class="empty-state-text">
                            No appointments found for {resource} at {location}
                        </div>
                    </div>
                    """.format(
                    resource=selected_resource,
                    location=selected_location
                ), unsafe_allow_html=True)

                
def display_unassigned_tab(selected_location, selected_employment_type):
    # Show unassigned appointments
    unassigned_appointments = get_unassigned_appointments(selected_location)
    
    if not unassigned_appointments.empty:
        st.markdown(f"""
        <div class="card">
            <div class="card-header">
                <span class="icon">🚨</span> Unassigned Appointments at {selected_location}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Get all resources (not filtered by location)
        all_resources_df = get_all_resources()
        # Get local resources
        local_resources = get_resources_by_location(
            selected_location, 
            selected_employment_type
        )
        
        # Week selection tabs
        week_tab1, week_tab2 = st.tabs(["Week 1", "Week 2"])
        
        with week_tab1:
            week1_appointments = unassigned_appointments[unassigned_appointments['Week'] == 1]
            if not week1_appointments.empty:
                # Get unique days in week 1
                days = week1_appointments['DayOfWeek'].unique().tolist()
                selected_day = st.session_state.get('selected_day_unassigned_week1', 'Monday')
                
                # Display day tabs (all days shown, disabled if no appointments)
                selected_day = display_day_tabs(days, selected_day, week_num="unassigned_1")
                st.session_state.selected_day_unassigned_week1 = selected_day
                
                # Filter appointments for selected day
                day_appointments = week1_appointments[week1_appointments['DayOfWeek'] == selected_day]
                
                if not day_appointments.empty:
                    # Display appointments
                    for _, row in day_appointments.iterrows():
                        appt_id = row['AppointmentID']
                        start_datetime = pd.to_datetime(row['StartDateTime'])
                        end_datetime = pd.to_datetime(row['EndDateTime'])
                        
                        # Initialize session state for this appointment
                        if f"assigned_{appt_id}" not in st.session_state:
                            st.session_state[f"assigned_{appt_id}"] = False
                            st.session_state[f"selected_resource_{appt_id}"] = None
                        
                        # Check if appointment is already assigned
                        with db_connection() as conn:
                            check_query = "SELECT maica__Resources__c FROM NewAppointments WHERE Id = ?"
                            assigned_to = pd.read_sql(check_query, conn, params=[appt_id]).iloc[0,0]
                        
                        if assigned_to and not st.session_state[f"assigned_{appt_id}"]:
                            st.session_state[f"assigned_{appt_id}"] = True
                            st.session_state[f"selected_resource_{appt_id}"] = assigned_to
                        
                        with st.expander(f"{row['Name']} - {row['DisplayStart']} to {row['DisplayEnd']} ({row['DurationHours']:.2f}h)", expanded=True):
                            if st.session_state[f"assigned_{appt_id}"]:
                                st.warning(f"⚠️ This appointment is already assigned to {st.session_state[f'selected_resource_{appt_id}']}")
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
                                display_resource_details(resource_details)
                                
                                # Show CURRENT constraints (without adding potential assignment)
                                st.markdown("**Current Constraints:**")
                                current_constraints = calculate_constraints(display_resource, selected_location)
                                display_constraints(current_constraints)
                                
                                # Assign button with comprehensive validation
                                if st.button("✨ Assign Resource", key=f"assign_btn_{appt_id}"):
                                    if not selected_resource:
                                        st.error("Please select a resource to assign")
                                    else:
                                        # Validate the potential assignment
                                        is_valid, message = validate_assignment(
                                            selected_resource,
                                            selected_location,
                                            row['StartDateTime'],
                                            row['EndDateTime'],
                                            week_num=1
                                        )
                                        
                                        if not is_valid:
                                            st.error(f"Cannot assign: {message}")
                                        else:
                                            # Check weekly hours constraints
                                            appt_hours = row['DurationHours']
                                            week_num = row['Week']
                                            
                                            if resource_details['employmentType'] == 'Full Time':
                                                if week_num == 1 and (current_constraints['week1_hours'] + appt_hours) > 38:
                                                    st.error(f"Cannot assign - Would exceed Week 1 limit (38h)")
                                                elif week_num == 2 and (current_constraints['week2_hours'] + appt_hours) > 38:
                                                    st.error(f"Cannot assign - Would exceed Week 2 limit (38h)")
                                                elif (current_constraints['total_hours'] + appt_hours) > 76:
                                                    st.error(f"Cannot assign - Would exceed total limit (76h)")
                                                else:
                                                    if assign_resource_to_appointment(appt_id, selected_resource):
                                                        st.session_state[f"assigned_{appt_id}"] = True
                                                        st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                                                        st.success(f"✅ Successfully assigned {selected_resource} to this appointment!")
                                                        st.rerun()
                                            elif resource_details['employmentType'] == 'Part Time':
                                                if week_num == 1 and (current_constraints['week1_hours'] + appt_hours) > resource_details['hoursPerWeek']:
                                                    st.error(f"Cannot assign - Would exceed Week 1 contracted hours ({resource_details['hoursPerWeek']}h)")
                                                elif week_num == 2 and (current_constraints['week2_hours'] + appt_hours) > resource_details['hoursPerWeek']:
                                                    st.error(f"Cannot assign - Would exceed Week 2 contracted hours ({resource_details['hoursPerWeek']}h)")
                                                elif (current_constraints['total_hours'] + appt_hours) > (resource_details['hoursPerWeek'] * 2):
                                                    st.error(f"Cannot assign - Would exceed total contracted hours ({resource_details['hoursPerWeek']*2}h)")
                                                else:
                                                    if assign_resource_to_appointment(appt_id, selected_resource):
                                                        st.session_state[f"assigned_{appt_id}"] = True
                                                        st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                                                        st.success(f"✅ Successfully assigned {selected_resource} to this appointment!")
                                                        st.rerun()
                else:
                    st.markdown(f"""
                    <div class="empty-state">
                        <div class="empty-state-icon">📅</div>
                        <div class="empty-state-text">No unassigned appointments on {selected_day}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="empty-state">
                    <div class="empty-state-icon">📅</div>
                    <div class="empty-state-text">No unassigned appointments in Week 1</div>
                </div>
                """, unsafe_allow_html=True)
        
        with week_tab2:
            week2_appointments = unassigned_appointments[unassigned_appointments['Week'] == 2]
            if not week2_appointments.empty:
                # Get unique days in week 2
                days = week2_appointments['DayOfWeek'].unique().tolist()
                selected_day = st.session_state.get('selected_day_unassigned_week2', 'Monday')
                
                # Display day tabs (all days shown, disabled if no appointments)
                selected_day = display_day_tabs(days, selected_day, week_num="unassigned_2")
                st.session_state.selected_day_unassigned_week2 = selected_day
                
                # Filter appointments for selected day
                day_appointments = week2_appointments[week2_appointments['DayOfWeek'] == selected_day]
                
                if not day_appointments.empty:
                    # Display appointments
                    for _, row in day_appointments.iterrows():
                        appt_id = row['AppointmentID']
                        start_datetime = pd.to_datetime(row['StartDateTime'])
                        end_datetime = pd.to_datetime(row['EndDateTime'])
                        
                        # Initialize session state for this appointment
                        if f"assigned_{appt_id}" not in st.session_state:
                            st.session_state[f"assigned_{appt_id}"] = False
                            st.session_state[f"selected_resource_{appt_id}"] = None
                        
                        # Check if appointment is already assigned
                        with db_connection() as conn:
                            check_query = "SELECT maica__Resources__c FROM NewAppointments WHERE Id = ?"
                            assigned_to = pd.read_sql(check_query, conn, params=[appt_id]).iloc[0,0]
                        
                        if assigned_to and not st.session_state[f"assigned_{appt_id}"]:
                            st.session_state[f"assigned_{appt_id}"] = True
                            st.session_state[f"selected_resource_{appt_id}"] = assigned_to
                        
                        with st.expander(f"{row['Name']} - {row['DisplayStart']} to {row['DisplayEnd']} ({row['DurationHours']:.2f}h)", expanded=True):
                            if st.session_state[f"assigned_{appt_id}"]:
                                st.warning(f"⚠️ This appointment is already assigned to {st.session_state[f'selected_resource_{appt_id}']}")
                                continue
                            
                            # Create two columns for the dropdowns
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Local resources dropdown
                                local_selected = st.selectbox(
                                    "Assign Local Resource:",
                                    [""] + local_resources,
                                    key=f"local_select_{appt_id}_week2"
                                )
                            
                            with col2:
                                # All resources dropdown
                                all_selected = st.selectbox(
                                    "Or select from ALL Resources:",
                                    [""] + all_resources_df['resource_name'].unique().tolist(),
                                    format_func=lambda x: f"{x} ({all_resources_df[all_resources_df['resource_name'] == x]['primaryLocation'].values[0]})" if x else "Select...",
                                    key=f"all_select_{appt_id}_week2"
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
                                display_resource_details(resource_details)
                                
                                # Show CURRENT constraints (without adding potential assignment)
                                st.markdown("**Current Constraints:**")
                                current_constraints = calculate_constraints(display_resource, selected_location)
                                display_constraints(current_constraints)
                                
                                # Assign button with comprehensive validation
                                if st.button("✨ Assign Resource", key=f"assign_btn_{appt_id}_week2"):
                                    if not selected_resource:
                                        st.error("Please select a resource to assign")
                                    else:
                                        # Validate the potential assignment
                                        is_valid, message = validate_assignment(
                                            selected_resource,
                                            selected_location,
                                            row['StartDateTime'],
                                            row['EndDateTime'],
                                            week_num=2
                                        )
                                        
                                        if not is_valid:
                                            st.error(f"Cannot assign: {message}")
                                        else:
                                            # Check weekly hours constraints
                                            appt_hours = row['DurationHours']
                                            week_num = row['Week']
                                            
                                            if resource_details['employmentType'] == 'Full Time':
                                                if week_num == 1 and (current_constraints['week1_hours'] + appt_hours) > 38:
                                                    st.error(f"Cannot assign - Would exceed Week 1 limit (38h)")
                                                elif week_num == 2 and (current_constraints['week2_hours'] + appt_hours) > 38:
                                                    st.error(f"Cannot assign - Would exceed Week 2 limit (38h)")
                                                elif (current_constraints['total_hours'] + appt_hours) > 76:
                                                    st.error(f"Cannot assign - Would exceed total limit (76h)")
                                                else:
                                                    if assign_resource_to_appointment(appt_id, selected_resource):
                                                        st.session_state[f"assigned_{appt_id}"] = True
                                                        st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                                                        st.success(f"✅ Successfully assigned {selected_resource} to this appointment!")
                                                        st.rerun()
                                            elif resource_details['employmentType'] == 'Part Time':
                                                if week_num == 1 and (current_constraints['week1_hours'] + appt_hours) > resource_details['hoursPerWeek']:
                                                    st.error(f"Cannot assign - Would exceed Week 1 contracted hours ({resource_details['hoursPerWeek']}h)")
                                                elif week_num == 2 and (current_constraints['week2_hours'] + appt_hours) > resource_details['hoursPerWeek']:
                                                    st.error(f"Cannot assign - Would exceed Week 2 contracted hours ({resource_details['hoursPerWeek']}h)")
                                                elif (current_constraints['total_hours'] + appt_hours) > (resource_details['hoursPerWeek'] * 2):
                                                    st.error(f"Cannot assign - Would exceed total contracted hours ({resource_details['hoursPerWeek']*2}h)")
                                                else:
                                                    if assign_resource_to_appointment(appt_id, selected_resource):
                                                        st.session_state[f"assigned_{appt_id}"] = True
                                                        st.session_state[f"selected_resource_{appt_id}"] = selected_resource
                                                        st.success(f"✅ Successfully assigned {selected_resource} to this appointment!")
                                                        st.rerun()
                else:
                    st.markdown(f"""
                    <div class="empty-state">
                        <div class="empty-state-icon">📅</div>
                        <div class="empty-state-text">No unassigned appointments on {selected_day}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="empty-state">
                    <div class="empty-state-icon">📅</div>
                    <div class="empty-state-text">No unassigned appointments in Week 2</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-state success">
            <div class="empty-state-icon">🎉</div>
            <div class="empty-state-text">
                All appointments at {location} have resources assigned!
            </div>
        </div>
        """.format(
            location=selected_location
        ), unsafe_allow_html=True)

def main():
    # Initialize session state
    if 'selected_location' not in st.session_state:
        st.session_state.selected_location = None
    if 'selected_resource' not in st.session_state:
        st.session_state.selected_resource = None
    if 'selected_employment_type' not in st.session_state:
        st.session_state.selected_employment_type = 'All'

    # Sidebar with filters
    with st.sidebar:
        # Logo at the very top (smaller size)
        st.image("image.png", width=100)
    
        # Container for proper spacing
        st.markdown('<div class="sidebar-header-container">', unsafe_allow_html=True)
        
        # Filters section
        st.markdown('<div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;">FILTERS</div>', unsafe_allow_html=True)
        
        
        # Get locations with participant names for display
        location_options = get_locations_with_participants()
        
        # Create options for selectbox
        options = [loc['display_name'] for loc in location_options]
        
        # Show participant names in dropdown
        selected_display = st.selectbox(
            "Select Roster:", 
            options=options,
            key="location_selectbox"
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
            
            st.markdown('</div>', unsafe_allow_html=True)  # Close spacing container
            
            st.markdown("""
                    <div class="sidebar-footer">
                        Project Nahl - Powered by Data Science Team
                    </div>
                    """, unsafe_allow_html=True)

    # Main content
    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="icon">📅</span> Shift Management
        </div>
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

        # Main tabs
        tab_assigned, tab_unassigned = st.tabs(["Assigned Shifts", "Unassigned Shifts"])
        
        with tab_assigned:
            display_assigned_tab(
                st.session_state.selected_location,
                st.session_state.selected_employment_type,
                st.session_state.selected_resource
            )
        
        with tab_unassigned:
            display_unassigned_tab(
                st.session_state.selected_location,
                st.session_state.selected_employment_type
            )

if __name__ == "__main__":
    main()