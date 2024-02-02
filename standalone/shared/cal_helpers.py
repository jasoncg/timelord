# import shared.gitlab_helpers as gitlab_helpers
# import shared.constants as constants
import datetime
import dateutil.rrule
import pytz

# local_tz = pytz.timezone('US/Eastern')


def getWeekDateRange(days=30):
    '''
    Returns a start and end date. Start is the Sunday of the current week, and end is the Saturday about 30 days later
    '''
    # Get the current date
    current_date = datetime.datetime.now(pytz.utc)

    # Find the most recent Sunday
    start_date = current_date - datetime.timedelta(days=current_date.weekday() + 1)

    # Find the Saturday of the week about 30 days out from the start date

    end_date = start_date + datetime.timedelta(days=days)
    end_date = end_date - datetime.timedelta(days=end_date.weekday() + 2) + datetime.timedelta(days=6)

    return {'start': start_date, 'end': end_date}


def getEvents(cal, start, end):
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get('dtstart').dt if component.get('dtstart') else None
            dtend = component.get('dtend').dt if component.get('dtend') else None

            if dtstart and dtend and start <= dtstart <= end:
                summary = component.get('summary')
                sender = component.get('organizer')
                attendees = [attendee for attendee in component.get('attendee', [])]
                events.append((summary, sender, attendees, dtstart, dtend))
    return events


def getRecurrenceDetails(cal):
    recurrence_details = []
    for component in cal.walk():
        if component.name == "VEVENT":
            rrule = component.get('rrule')
            if rrule:
                freq = f"Frequency: {rrule.get('freq', [])[0]} " if rrule.get('freq') else ""
                interval = f"Interval: {rrule.get('interval', [])[0]} " if rrule.get('interval') else ""
                until = (
                    f"Until: {rrule.get('until', [])[0].strftime('%Y-%m-%d %H:%M:%S')} "
                    if rrule.get('until')
                    else "No End Date "
                )
                count = f"Count: {rrule.get('count', [])[0]} " if rrule.get('count') else ""
                byday = f"Days: {','.join(rrule.get('byday', []))}" if rrule.get('byday') else ""

                description = f"{freq}{interval}{until}{count}{byday}"

                recurrence_details.append(description)
    return recurrence_details


def parse_ics(cal):
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            summary = component.get('summary')
            sender = component.get('organizer')
            attendee_data = component.get('attendee', [])
            if not isinstance(attendee_data, list):
                attendee_data = [attendee_data]
            attendees = [attendee for attendee in attendee_data]
            dtstart = component.get('dtstart').dt if component.get('dtstart') else None
            dtend = component.get('dtend').dt if component.get('dtend') else None
            events.append((summary, sender, attendees, dtstart, dtend))
    return events


def parse_ics_to_events(cal, start=None, until_date=None):
    events = []

    for component in cal.walk():
        if component.name == "VEVENT":
            start_dt = component.get('dtstart').dt if component.get('dtstart') else None
            end_dt = component.get('dtend').dt if component.get('dtend') else None
            rrule = component.get('rrule')

            duration = component.get('duration')
            # Normalize to UTC if timezone aware
            # if start_dt is not None and start_dt.tzinfo is not None
            #    and start_dt.tzinfo.utcoffset(start_dt) is not None:
            #    start_dt = start_dt.astimezone(pytz.utc)
            # if end_dt is not None and end_dt.tzinfo is not None and end_dt.tzinfo.utcoffset(end_dt) is not None:
            #    end_dt = end_dt.astimezone(pytz.utc)
            current_date = datetime.datetime.now(pytz.utc)
            # if start isn't given, start with the most recent Sunday
            if start is None:
                start = current_date - datetime.timedelta(days=current_date.weekday() + 1)

            # If until_date isn't given, then go 21 days out from today
            if until_date is None:
                until_date = current_date + datetime.timedelta(days=21)

            if rrule:  # Recurring event
                rrule_str = rrule.to_ical().decode('utf-8')
                rule = dateutil.rrule.rrulestr(rrule_str, dtstart=start_dt)

                occurrences = rule.between(start_dt, until_date)

                for occurrence in occurrences:
                    start_time = occurrence.time()
                    end_time = (occurrence + (end_dt - start_dt)).time()
                    day_of_week = occurrence.weekday()
                    duration = (end_dt - start_dt).seconds
                    events.append({
                        'date': occurrence.date(),
                        'start_time': start_time,
                        'end_time': end_time,
                        'day_of_week': day_of_week,
                        'duration': duration
                    })

            else:  # Non-recurring event
                if end_dt and start_dt:
                    duration = (end_dt - start_dt)
                events.append({
                    'date': start_dt.date(),
                    'start_time': start_dt.time(),
                    'end_time': end_dt.time(),
                    'day_of_week': start_dt.weekday(),
                    'duration': duration
                })
    return events


def is_event_over(cal) -> bool:
    '''
    Returns True if there are no future events
    '''
    now = datetime.datetime.now(pytz.utc)

    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get('dtstart').dt
            dtend = component.get('dtend').dt if component.get('dtend') else dtstart
            rrule = component.get('rrule')

            # If it's a recurring event, check the recurrence rules
            if rrule:
                # freq = rrule.get('freq', [])[0]
                until = rrule.get('until', [])[0] if rrule.get('until') else None
                count = rrule.get('count', [])[0] if rrule.get('count') else None

                # If there is an 'until' date, check if it's in the past
                if isinstance(dtend, datetime.datetime):
                    if until and until < now:
                        continue
                else:
                    if until and until < now.date():
                        continue

                # If there is no 'until' date or 'count', then the event is not over
                if not until and not count:
                    return False

            # If it's not recurring or if it's a single past event, check the end date
            if not rrule:
                if isinstance(dtend, datetime.datetime):
                    if not rrule and dtend < now:
                        continue
                else:
                    if not rrule and dtend < now.date():
                        continue

            # If any instance of the event is in the future, the event is not over
            return False

    # If all instances of the event are in the past, the event is over
    return True
