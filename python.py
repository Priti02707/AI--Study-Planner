subjects = {}

n = int(input("Enter number of subjects: "))

for i in range(n):
    name = input("Subject name: ")
    marks = float(input("Marks: "))
    subjects[name] = marks

total_time = float(input("Enter daily study hours: "))

total_inverse = sum(10 - m for m in subjects.values())

print("\n Smart Study Plan:\n")

for sub, marks in subjects.items():
    weight = (10 - marks) / total_inverse
    time_alloc = weight * total_time
    print(f"{sub}: {round(time_alloc,2)} hours")

weak = min(subjects, key=subjects.get)
print(f"\n Focus more on: {weak}")
