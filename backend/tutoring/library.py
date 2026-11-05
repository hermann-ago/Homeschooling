"""Family reading catalog using the existing book, lesson and activity engines.

Cataloguing and uploading are local operations. Only an explicit preparation
request queues the normal checkpointed book indexer. Its source scans are keyed
by checksum and reused across children; learner topics and evidence stay separate.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from storage.files import safe_name

LIBRARY_FOLDER = "Family Library/Books"
STAGES = ["The Gateway", "Case Against the State", "Practical Mechanics", "Money & Banking",
          "Fiction & Sci-Fi", "Deep Philosophy & Ethics", "The Heavyweights"]

# Parent-supplied metadata and links, not verified availability or acquired files.
# title, author, year, style, approximate pages, availability, source, Amazon query
CATALOG = [
    ("The Adventures of Jonathan Gullible", "Ken Schoolland", 1981, "Illustrated Fable", 120, "Paid", None, "The Adventures of Jonathan Gullible Ken Schoolland"),
    ("The Law", "Frederic Bastiat", 1850, "Classic Essay", 60, "100% Free", "https://mises.org/library/book/law", "The Law Frederic Bastiat"),
    ("How an Economy Grows and Why It Crashes", "Peter D. Schiff & Andrew J. Schiff", 2010, "Comic / Parable", 240, "1979 Orig. Free / 2010 Paid", "https://archive.org/details/how-an-economy-grows-and-why-it-doesnt-irwin-schiff", "How an Economy Grows and Why It Crashes Peter Schiff"),
    ("I, Pencil", "Leonard E. Read", 1958, "Short Story", 15, "100% Free", "https://fee.org/resources/i-pencil/", "I Pencil Leonard Read"),
    ("Economics in One Lesson", "Henry Hazlitt", 1946, "Accessible Guide", 220, "100% Free", "https://mises.org/library/book/economics-one-lesson", "Economics in One Lesson Henry Hazlitt"),
    ("Economic Policy: Thoughts for Today and Tomorrow (The Six Lessons)", "Ludwig von Mises", 1979, "Warm Lectures", 100, "100% Free", "https://mises.org/library/book/economic-policy-thoughts-today-and-tomorrow", "Economic Policy Thoughts for Today and Tomorrow Ludwig von Mises"),
    ("Free to Choose: A Personal Statement", "Milton & Rose Friedman", 1980, "Popular Non-Fiction", 330, "TV Series Free / Book Paid", "https://www.youtube.com/playlist?list=PL1B8889063321AB8B", "Free to Choose Milton Friedman"),
    ("Anatomy of the State", "Murray N. Rothbard", 1974, "Punchy Essay", 60, "100% Free", "https://mises.org/library/book/anatomy-state", "Anatomy of the State Murray Rothbard"),
    ("Healing Our World: The Compassion of Libertarianism", "Dr. Mary J. Ruwart", 1992, "Empathetic / Practical", 350, "100% Free (Classic Ed.)", "https://archive.org/details/healing-our-world-the-compassion-of-libertarianism", "Healing Our World Mary Ruwart"),
    ("For a New Liberty: The Libertarian Manifesto", "Murray N. Rothbard", 1973, "Manifesto / Overview", 400, "100% Free", "https://mises.org/library/book/new-liberty-libertarian-manifesto", "For a New Liberty Murray Rothbard"),
    ("A Spontaneous Order: The Capitalist Case for a Stateless Society", "Chase Rachels", 2015, "Modern Primer", 270, "100% Free", "https://mises.org/library/book/spontaneous-order-capitalist-case-stateless-society", "A Spontaneous Order Chase Rachels"),
    ("The Problem of Political Authority", "Michael Huemer", 2013, "Common-Sense Logic", 400, "Paid", None, "The Problem of Political Authority Michael Huemer"),
    ("No Treason: The Constitution of No Authority", "Lysander Spooner", 1870, "Fiery Legal Essay", 60, "100% Free", "https://mises.org/library/book/no-treason-constitution-no-authority", "No Treason The Constitution of No Authority Lysander Spooner"),
    ("The Invisible Hook: The Hidden Economics of Pirates", "Peter T. Leeson", 2009, "Fun Pirate History", 270, "Paid", None, "The Invisible Hook Peter Leeson"),
    ("Anarchy Unbound: Why Self-Governance Works Better Than You Think", "Peter T. Leeson", 2014, "Historical Case Studies", 260, "Paid", None, "Anarchy Unbound Peter Leeson"),
    ("The Machinery of Freedom: Guide to a Radical Capitalism", "David D. Friedman", 1973, "Witty / Game Theory", 380, "100% Free", "http://www.daviddfriedman.com/The_Machinery_of_Freedom_.pdf", "The Machinery of Freedom David Friedman"),
    ("Chaos Theory: Two Essays on Market Anarchy", "Robert P. Murphy", 2002, "Short Thought Exp.", 75, "100% Free", "https://mises.org/library/book/chaos-theory-two-essays-market-anarchy", "Chaos Theory Robert P Murphy"),
    ("The Market for Liberty", "Morris & Linda Tannehill", 1970, "World-Building Guide", 170, "100% Free", "https://mises.org/library/book/market-liberty", "The Market for Liberty Morris Tannehill"),
    ("What Has Government Done to Our Money?", "Murray N. Rothbard", 1963, "Monetary History", 110, "100% Free", "https://mises.org/library/book/what-has-government-done-our-money", "What Has Government Done to Our Money Murray Rothbard"),
    ("End the Fed", "Ron Paul", 2009, "Political Expose", 220, "Paid", None, "End the Fed Ron Paul"),
    ("The Bitcoin Standard", "Saifedean Ammous", 2018, "Modern Money History", 300, "Paid", None, "The Bitcoin Standard Saifedean Ammous"),
    ("The Moon Is a Harsh Mistress", "Robert A. Heinlein", 1966, "Classic Sci-Fi Novel", 380, "Paid", None, "The Moon Is a Harsh Mistress Robert Heinlein"),
    ("Alongside Night", "J. Neil Schulman", 1979, "Agorist Thriller Novel", 280, "100% Free", "https://archive.org/details/alongsidenight00schu", "Alongside Night J Neil Schulman"),
    ("Anthem", "Ayn Rand", 1938, "Dystopian Novella", 100, "100% Free", "https://www.gutenberg.org/ebooks/1250", "Anthem Ayn Rand"),
    ("Defending the Undefendable", "Walter Block", 1976, "Provocative Cases", 250, "100% Free", "https://mises.org/library/book/defending-undefendable", "Defending the Undefendable Walter Block"),
    ("Against Intellectual Property", "N. Stephan Kinsella", 2001, "Crisp Legal Logic", 70, "100% Free", "https://mises.org/library/book/against-intellectual-property", "Against Intellectual Property Stephan Kinsella"),
    ("The Ethics of Liberty", "Murray N. Rothbard", 1982, "Deep Philosophy", 320, "100% Free", "https://mises.org/library/book/ethics-liberty", "The Ethics of Liberty Murray Rothbard"),
    ("Democracy: The God That Failed", "Hans-Hermann Hoppe", 2001, "Political Sociology", 300, "Paid", None, "Democracy The God That Failed Hans Hermann Hoppe"),
    ("Man, Economy, and State (with Power and Market)", "Murray N. Rothbard", 1962, "Full Textbook", 1400, "100% Free", "https://mises.org/library/book/man-economy-and-state-power-and-market", "Man Economy and State with Power and Market Murray Rothbard"),
    ("Human Action: A Treatise on Economics", "Ludwig von Mises", 1949, "Deep Treatise", 900, "100% Free", "https://mises.org/library/book/human-action", "Human Action Ludwig von Mises"),
]


def seed_catalog(db):
    missing = [(n, row) for n, row in enumerate(CATALOG, 1) if not db.get("library_books", f"library-{n:02}")]
    if not missing:
        return
    with db.transaction(kind="library.seed", summary="Saved the family's staged reading list") as tx:
        for n, (title, author, year, style, pages, availability, source, query) in missing:
            stage = next(i for i, last in enumerate((8, 13, 18, 21, 24, 28, 30), 1) if n <= last)
            note = {3: "This link is to How an Economy Grows and Why It Doesn't by Irwin Schiff, a different work from the listed 2010 book. Add it as a separate title if you use it.",
                    7: "The supplied link is a TV playlist, not a copy of the book.",
                    9: "The supplied source refers to a classic edition; check the exact edition before uploading."}.get(n, "")
            tx.insert("library_books", {"id": f"library-{n:02}", "title": title, "author": author, "year": year,
                "style": style, "estimated_pages": pages, "availability": availability, "stage": stage,
                "stage_title": STAGES[stage - 1], "position": n, "source_url": source,
                "source_label": "Different work / edition" if n == 3 else "TV series" if n == 7 else "Provided source",
                "store_url": "https://www.amazon.com/s?k=" + quote_plus(query), "source_note": note})


def reading_view(db, reading):
    subject = db.get("subjects", reading["subject_id"])
    topics = sorted((t for t in db.find("topics", subject_id=subject["id"]) if not t.get("archived")),
                    key=lambda t: (t["chapter_order"] or 0, t["id"]))
    jobs = [j for b in db.find("subject_books", subject_id=subject["id"])
            for j in db.find("book_imports", book_id=b["id"])]
    job = max(jobs, key=lambda j: (j["created_at"], j["id"]), default=None)
    sessions = [s for s in db.find("tutor_sessions", subject_id=subject["id"])
                if s["status"] in ("active", "unfinished")]
    session = max(sessions, key=lambda s: (s["updated_at"], s["id"]), default=None)
    return {**reading, "active": subject.get('purpose') != 'library_paused', "subject": subject, "topics": topics, "completed_topics": sum(bool(t["completed"]) for t in topics),
            "total_topics": len(topics), "job": {k: job.get(k) for k in ("id", "status", "stage", "done", "total", "error", "pending_ranges")} if job else None,
            "resume_session": {"id": session["id"], "topic_id": session["topic_id"]} if session else None}


def book_view(db, book, child_id=None):
    readings = db.find("library_readings", book_id=book["id"])
    if child_id is not None:
        readings = [r for r in readings if r["child_id"] == child_id]
    doc = db.get("documents", book["document_id"]) if book.get("document_id") else None
    materials = db.find("library_materials", book_id=book["id"])
    shared = {kind: len({r["cache_key"] for r in materials if r["kind"] == kind}) for kind in
              ("reading_topics", "source_passage", "guided_lesson", "quiz", "audio", "terms", "explain", "narration")}
    return {**book, "shared_preparation": shared, "document": {k: doc.get(k) for k in ("id", "original_filename", "page_count", "size_bytes", "file_path", "sha256")} if doc else None,
            "readings": [reading_view(db, r) for r in readings]}


def enroll(tx, book, child):
    current = next(iter(tx.find("library_readings", book_id=book["id"], child_id=child["id"])), None)
    if current:
        if tx.get('subjects', current['subject_id']).get('purpose') == 'library_paused':
            tx.update('subjects', current['subject_id'], {'purpose': 'library'})
        return current
    folder = f"{safe_name(child['name'])}/Extra Reading/{safe_name(book['id'] + '-' + book['title'])}"
    subject = tx.insert("subjects", {"name": book["title"], "child_id": child["id"], "purpose": "library",
                         "grade": "N/A", "folder": folder, "weight": 0})
    from tutoring.skills import save
    from .library_materials import skill_packet
    save(tx, subject, skill_packet(tx, book)["content"], 0)
    return tx.insert("library_readings", {"id": f"{book['id']}-child-{child['id']}", "book_id": book["id"],
                                          "child_id": child["id"], "subject_id": subject["id"]})


def teaching_template(book):
    """The family's chosen book teaching (first written for Jonathan Gullible);
    every book starts from it. The app adds the end-of-chapter quiz itself."""
    return f"""# {book['title']} — shared book teaching

## Reusable reading and teaching
Prepare a reusable lesson for this book edition, using the uploaded source and the assigned topic's actual text.
Address the reader as 'you'. Never include a child's name, age, grade, preferences, past answers, progress,
personal circumstances or earlier session in the prepared script. Do not assume prior mastery.
The saved explanations, quiz questions and narration will be used by other children in future years.
Live companion conversation can adapt to the current learner separately.
Read the complete assigned text in order, respecting inclusive start and exclusive stop boundaries.
Add warm explanations and concrete examples. Ask one question at a time and wait for the learner.
Use the app's registered activities. Never include executable UI or invent learner answers or scores.

## Independent book club
This is extracurricular reading the family chose. Use the uploaded edition and the assigned topic's actual text.
Explain unfamiliar vocabulary and ideas with short examples appropriate to this learner's observed understanding.
Teach the book's ideas and arguments faithfully, as the book presents them. Invite reasoned questions;
assess comprehension and reasoning, never agreement with a political or philosophical viewpoint.
Read printed reflection, discussion and brainstorming questions as part of the text: food for thought.
End each chapter with the short comprehension check, one question at a time. Base the questions and expected
answers on the assigned source and keep the answers hidden until the child attempts the question. Explain a
misconception kindly and offer a focused follow-up. Preserve first answers, help and revisions.
Reading order follows the family list, not an inferred age or grade level. Let the parent choose each book.
Reading alone is not mastery.
"""
