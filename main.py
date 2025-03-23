from Process import run_tests
from CreateExcel import create_excels

# Define your parent folders here (e.g., Q1, Q2, Q3)
questions = ["Q1", "Q2", "Q3"]

# Weight in percentage for each question
folder_weights = {questions[0]: 25, questions[1]: 45, questions[2]: 30}

run_tests(questions)
# Slim makes a final excel with only final grades, or with details per question
create_excels(questions, slim=False)
print("\n\nDONE, HAPPY GRADING!")
