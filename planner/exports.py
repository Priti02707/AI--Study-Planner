import csv
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from planner.clock import timezone_name


def csv_export(sessions):
    buffer = io.StringIO(newline="")
    fields = ["subject", "topic", "kind", "start", "end", "status", "planned_minutes", "done_minutes", "actual_minutes", "reason"]
    writer = csv.DictWriter(buffer, fields, extrasaction="ignore")
    writer.writeheader()
    for session in sessions:
        row = {key: ("'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
               for key, value in session.items()}
        writer.writerow(row)
    return buffer.getvalue()


def escape(value):
    return str(value).replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold(line):
    result, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            result.append(current)
            current = " "
        current += char
    result.append(current)
    return "\r\n".join(result)


def calendar_export(sessions):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Priti Kumari//Study Planner//EN", "CALSCALE:GREGORIAN"]
    zone = ZoneInfo(timezone_name())
    def stamp(value):
        return datetime.fromisoformat(value).replace(tzinfo=zone).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    created = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for session in sessions:
        if session["status"] != "planned":
            continue
        lines.extend(["BEGIN:VEVENT", f"UID:study-{session['id']}@ai-study-planner.local", f"DTSTAMP:{created}",
                      f"DTSTART:{stamp(session['start'])}", f"DTEND:{stamp(session['end'])}",
                      "SUMMARY:" + escape(f"{session['subject']}: {session['topic']}"),
                      "DESCRIPTION:" + escape(session["reason"]), "END:VEVENT"])
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
