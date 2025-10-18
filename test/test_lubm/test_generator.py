from krrood.experiments.generator import UniversityDataGenerator


def test_generator():
    generator = UniversityDataGenerator(university_count=1, seed=123)
    universities = generator.generate()

    if universities:
        main_university = universities[0]
        first_dept = main_university.departments[0]

        print("\n--- Detailed Look at First Department ---")
        print(f"Department: {first_dept.name}")
        print(f"Faculty Count: {len(first_dept.all_faculty)}")
        print(f"UG Student Count: {len(first_dept.undergraduate_students)}")
        print(f"Grad Student Count: {len(first_dept.graduate_students)}")

        # Example of an Undergraduate Student
        if first_dept.undergraduate_students:
            ug = first_dept.undergraduate_students[0]
            print(
                f"\nExample UG Student ({ug.person.first_name} {ug.person.last_name}):"
            )
            print(
                f"  - Advisor: {ug.advisor.person.last_name if ug.advisor else 'None'}"
            )
            print(f"  - Takes {len(ug.takes_courses)} courses.")

        # Example of a Full Professor
        if first_dept.full_professors:
            prof = first_dept.full_professors[0]
            print(
                f"\nExample Full Professor ({prof.person.first_name} {prof.person.last_name}):"
            )
            print(f"  - Publications: {len(prof.publications)}")
            print(f"  - Advises UG: {len(prof.advises_undergraduate_students)}")
            print(f"  - Teaches UG Courses: {[c.name for c in prof.teaches_courses]}")
