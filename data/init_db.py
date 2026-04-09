import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "retrieval.db")

TEST_DATA = [
    # General knowledge
    ("What is the capital of France?", "The capital of France is Paris."),
    ("How far is the Moon from Earth?", "The Moon is approximately 384,400 kilometers (238,855 miles) from Earth on average."),
    ("What year did World War II end?", "World War II ended in 1945."),
    ("Who wrote Romeo and Juliet?", "Romeo and Juliet was written by William Shakespeare."),
    ("What is the speed of light?", "The speed of light in a vacuum is approximately 299,792,458 meters per second (about 186,282 miles per second)."),

    # Science & tech
    ("What does CPU stand for?", "CPU stands for Central Processing Unit — the primary component of a computer that executes instructions."),
    ("What is photosynthesis?", "Photosynthesis is the process by which plants use sunlight, water, and carbon dioxide to produce oxygen and energy in the form of glucose."),
    ("How does Wi-Fi work?", "Wi-Fi transmits data wirelessly using radio waves. A router connects to the internet and broadcasts a signal that devices can connect to."),
    ("What is machine learning?", "Machine learning is a type of artificial intelligence where systems learn from data to improve their performance on tasks without being explicitly programmed."),
    ("Whats the difference between RAM and storage?", "RAM (Random Access Memory) is fast temporary memory used while your computer is running. Storage (like an SSD or HDD) holds data permanently, even when powered off."),

    # Health & everyday life
    ("How much water should I drink per day?", "Most adults should drink about 8 cups (2 liters) of water per day, though needs vary by activity level, climate, and body size."),
    ("What foods are high in protein?", "High-protein foods include chicken, beef, fish, eggs, Greek yogurt, lentils, beans, tofu, and nuts."),
    ("Is coffee bad for you?", "Moderate coffee consumption (3–4 cups per day) is generally considered safe for most adults and may even have health benefits, but too much can cause anxiety and sleep issues."),
    ("How do I get better sleep?", "Stick to a consistent sleep schedule, avoid screens before bed, keep your room cool and dark, and limit caffeine in the afternoon."),

    # Casual / conversational
    ("hey whats up", "Hey! Not much — just here and ready to help. What do you need?"),
    ("can you help me", "Of course! What do you need help with?"),
    ("what can you do", "I can answer questions, look things up, and help you find information. Just ask!"),
    ("thanks", "You're welcome! Let me know if there's anything else I can help with."),

    # Programming
    ("What is a REST API?", "A REST API is a way for applications to communicate over HTTP using standard methods like GET, POST, PUT, and DELETE to create, read, update, and delete resources."),
    ("Whats the difference between Python 2 and Python 3?", "Python 3 is the current version and introduced many improvements over Python 2, including better Unicode support, print as a function, and improved integer division. Python 2 reached end-of-life in 2020."),
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS qa_pairs (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer   TEXT NOT NULL
        )
    """)

    cur.execute("SELECT COUNT(*) FROM qa_pairs")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO qa_pairs (question, answer) VALUES (?, ?)",
            TEST_DATA,
        )
        print(f"Inserted {len(TEST_DATA)} rows.")
    else:
        print("Database already populated — skipping seed.")

    conn.commit()
    conn.close()
    print(f"Database ready at: {DB_PATH}")


if __name__ == "__main__":
    init_db()
