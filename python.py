"""Console planner. Run `streamlit run app.py` for the full dashboard."""
from planner.validation import allocate_minutes, integer, number, score, text


def ask(prompt, validate):
    while True:
        try:
            return validate(input(prompt))
        except ValueError as exc:
            print(f"Please try again: {exc}")


def main():
    print("Study Planner · console edition")
    count = ask("Enter number of subjects: ", lambda x: integer(x, "Subject count", 1, 100))
    maximum = ask("Maximum marks (for example 10 or 100): ", lambda x: number(x, "Maximum marks", 0.000001))
    subjects, names = [], set()
    for _ in range(count):
        while True:
            name = ask("Subject name: ", lambda x: text(x, "Subject name"))
            if name.casefold() not in names:
                names.add(name.casefold())
                break
            print("That subject already exists. Enter a different name.")
        earned = ask("Marks: ", lambda x: number(x, "Marks", 0, maximum))
        subjects.append((name, earned, maximum))
    hours = ask("Enter daily study hours: ", lambda x: number(x, "Hours", 0, 24))
    allocations = allocate_minutes(subjects, round(hours * 60))
    print("\nSmart Study Plan:\n")
    for name, minutes in allocations.items():
        print(f"{name}: {minutes // 60}h {minutes % 60:02d}m ({minutes / 60:.2f} hours)")
    lowest = min(score(earned, maximum) for _, earned, maximum in subjects)
    weak = [name for name, earned, maximum in subjects if score(earned, maximum) == lowest]
    print("\nFocus more on: " + ", ".join(weak))


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nPlanner closed.")
