"""Sample workspace used only by --demo and screenshot generation."""
from datetime import datetime, timedelta, timezone

from . import storage


def populate():
    repo = storage.Repository()
    today = datetime.now().date()
    studio = repo.save('projects', {'name': 'Studio launch', 'color': '#a6a1ff'})
    learning = repo.save('projects', {'name': 'Learning lab', 'color': '#75b9a5'})
    personal = repo.save('projects', {'name': 'A little better', 'color': '#e6a08b'})
    items = [
        ('Sketch the first chapter', 'Collect references and explore a few directions. Start with a rough sketch, then follow the idea.', studio, 'todo', 'high', today),
        ('Build the welcome experience', 'Make the first five minutes feel effortless. Keep the essentials close.', studio, 'doing', 'high', today+timedelta(days=2)),
        ('Find our visual rhythm', 'A calm palette, clear type, and a little room to breathe.', studio, 'done', 'medium', None),
        ('Make something with Python', 'Try a small idea from start to finish. Write down what you learn.', learning, 'doing', 'medium', today+timedelta(days=3)),
        ('Read a chapter & take notes', 'Twenty minutes with a good book. Capture one idea to try tomorrow.', learning, 'todo', 'low', today+timedelta(days=1)),
        ('Plan a screen-free afternoon', 'A walk, a new recipe, and a little space for the unexpected.', personal, 'todo', 'low', None),
        ('Clear the desk, clear the mind', 'Keep only the things that help you make good work.', personal, 'done', 'medium', None),
    ]
    ids = []
    for title, description, project, status, priority, due in items:
        ids.append(repo.save('tasks', {'title': title, 'description': description, 'project_id': project,
                                      'status': status, 'priority': priority, 'due': due.isoformat() if due else ''}))
    repo.save('notes', {'title': 'A few good principles', 'body': 'Start small.\nMake room for the important things.\nLet the work be a little imperfect at first.\n\nProgress is a practice, not a destination.'})
    repo.save('notes', {'title': 'Ideas for a quieter workspace', 'body': 'A warm lamp. A good playlist. A notebook within reach.\n\nLess friction between an idea and the first step.'})
    repo.save('notes', {'title': 'This week’s little wins', 'body': 'Finished the first draft.\nMade time to learn something new.\nWent outside before checking my phone.\n\nSmall things count.'})
    with storage.connect() as con:
        for offset, minutes in [(0, 25), (0, 25), (1, 45), (2, 25), (3, 50), (5, 25), (6, 35)]:
            timestamp = datetime.now(timezone.utc)-timedelta(days=offset, hours=1)
            con.execute('INSERT INTO sessions(task_id,minutes,created) VALUES(?,?,?)', (ids[1], minutes, timestamp.isoformat()))
