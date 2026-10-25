import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .source import parse_source


class Materials:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.database = data_dir / "courses.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
                filename TEXT NOT NULL, byte_size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'imported',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(id),
                title TEXT NOT NULL, level INTEGER NOT NULL, parent_id TEXT,
                start_line INTEGER NOT NULL, end_line INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS fragments (
                id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(id),
                chapter_id TEXT, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
                kind TEXT NOT NULL, markdown TEXT NOT NULL, missing_images INTEGER NOT NULL
            )""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def courses(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT courses.*, (SELECT count(*) FROM materials
                WHERE course_id=courses.id) AS material_count
                FROM courses ORDER BY created_at, id"""
            )]

    def create_course(self, name: str):
        course_id = str(uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO courses (id, name) VALUES (?, ?)", (course_id, name))
        return next(course for course in self.courses() if course["id"] == course_id)

    def require_course(self, course_id: str):
        with self.connect() as db:
            if db.execute("SELECT id FROM courses WHERE id=?", (course_id,)).fetchone() is None:
                raise LookupError("课程不存在")

    def list_materials(self, course_id: str):
        self.require_course(course_id)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM materials WHERE course_id=? ORDER BY created_at, id", (course_id,)
            )]

    def material(self, course_id: str, material_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM materials WHERE course_id=? AND id=?",
                             (course_id, material_id)).fetchone()
        if row is None:
            raise LookupError("资料不存在")
        return dict(row)

    def import_material(self, course_id: str, filename: str, content: bytes):
        self.require_course(course_id)
        material_id = str(uuid4())
        chapters, fragments = parse_source(material_id, content.decode("utf-8"))
        originals = self.data_dir / "originals"
        originals.mkdir(exist_ok=True)
        path = originals / f"{material_id}.md"
        path.write_bytes(content)
        try:
            with self.connect() as db:
                db.execute("INSERT INTO materials (id, course_id, filename, byte_size) VALUES (?,?,?,?)",
                           (material_id, course_id, filename, len(content)))
                db.executemany("""INSERT INTO chapters
                    (id,material_id,title,level,parent_id,start_line,end_line)
                    VALUES (:id,:material_id,:title,:level,:parent_id,:start_line,:end_line)""",
                    [chapter | {"material_id": material_id} for chapter in chapters])
                db.executemany("""INSERT INTO fragments
                    (id,material_id,chapter_id,start_line,end_line,kind,markdown,missing_images)
                    VALUES (:id,:material_id,:chapter_id,:start_line,:end_line,:kind,:markdown,:missing_images)""",
                    [fragment | {"material_id": material_id} for fragment in fragments])
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.material(course_id, material_id)

    def raw(self, course_id: str, material_id: str):
        material = self.material(course_id, material_id)
        return (self.data_dir / "originals" / f"{material['id']}.md").read_bytes()

    def detail(self, course_id: str, material_id: str):
        material = self.material(course_id, material_id)
        with self.connect() as db:
            chapters = [dict(row) for row in db.execute(
                "SELECT * FROM chapters WHERE material_id=? ORDER BY start_line", (material_id,))]
            counts = db.execute("SELECT count(*) AS fragment_count, coalesce(sum(missing_images),0) AS missing_image_count FROM fragments WHERE material_id=?", (material_id,)).fetchone()
        return material | {"chapters": chapters} | dict(counts)

    def fragments(self, course_id: str, material_id: str, chapter_id: str | None = None):
        material = self.detail(course_id, material_id)
        with self.connect() as db:
            if chapter_id:
                chapter = next((c for c in material["chapters"] if c["id"] == chapter_id), None)
                if chapter is None:
                    raise LookupError("章节不存在")
                rows = db.execute("""SELECT * FROM fragments WHERE material_id=?
                    AND start_line>=? AND end_line<=? ORDER BY start_line""",
                    (material_id, chapter["start_line"], chapter["end_line"]))
            else:
                rows = db.execute("SELECT * FROM fragments WHERE material_id=? ORDER BY start_line", (material_id,))
            return [dict(row) for row in rows]
