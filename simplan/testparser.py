from simplan.parser import Kind, parse_task
 
 
def test_kind_ignores_case():
    task = parse_task("QUIZ, Q1, 10:00, hours=2, on=2027-01-11")
    assert task.kind == Kind.QUIZ
