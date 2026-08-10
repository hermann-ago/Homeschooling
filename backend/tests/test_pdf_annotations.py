import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("POSTGRES_URL", None)

from database import Base  # noqa: E402
from models import Child, Document, FamilyAccount, PdfPageAnnotation  # noqa: E402
from routers.annotations import get_page_annotations, save_page_annotations  # noqa: E402
from schemas.annotations import AnnotationPageUpdate  # noqa: E402


def request_with_size(size: int = 512) -> Request:
    return Request({
        "type": "http",
        "method": "PUT",
        "path": "/api/annotations",
        "headers": [(b"content-length", str(size).encode())],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 123),
        "scheme": "http",
    })


class PdfAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.owner_id = str(uuid4())
        account = FamilyAccount(user_id=self.owner_id)
        child = Child(owner_id=self.owner_id, name="Mila", color="#E986B4")
        document = Document(
            owner_id=self.owner_id,
            blob_path="books/language-arts.pdf",
            original_filename="language-arts.pdf",
            size_bytes=1024,
            page_count=12,
        )
        self.db.add_all([account, child, document])
        self.db.commit()
        self.child_id = child.id
        self.document_id = document.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def payload(self, revision=0, color="#1D4ED8"):
        return AnnotationPageUpdate.model_validate({
            "base_revision": revision,
            "strokes": [{
                "id": str(uuid4()),
                "color": color,
                "width": 0.004,
                "points": [[0.1, 0.2], [0.3, 0.4]],
            }],
        })

    def test_empty_create_update_and_conflict(self):
        empty = get_page_annotations(
            self.child_id, self.document_id, 3, self.owner_id, self.db
        )
        self.assertEqual(empty.revision, 0)
        self.assertEqual(empty.strokes, [])

        created = save_page_annotations(
            self.child_id,
            self.document_id,
            3,
            self.payload(),
            request_with_size(),
            self.owner_id,
            self.db,
        )
        self.assertEqual(created.revision, 1)
        self.assertEqual(created.strokes[0].color, "#1D4ED8")

        updated = save_page_annotations(
            self.child_id,
            self.document_id,
            3,
            self.payload(revision=1, color="#DC2626"),
            request_with_size(),
            self.owner_id,
            self.db,
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.strokes[0].color, "#DC2626")

        with self.assertRaises(HTTPException) as conflict:
            save_page_annotations(
                self.child_id,
                self.document_id,
                3,
                self.payload(revision=1),
                request_with_size(),
                self.owner_id,
                self.db,
            )
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(conflict.exception.detail["current"]["revision"], 2)

    def test_rejects_cross_account_and_out_of_range_pages(self):
        with self.assertRaises(HTTPException) as hidden:
            get_page_annotations(
                self.child_id, self.document_id, 1, str(uuid4()), self.db
            )
        self.assertEqual(hidden.exception.status_code, 404)

        with self.assertRaises(HTTPException) as invalid_page:
            get_page_annotations(
                self.child_id, self.document_id, 13, self.owner_id, self.db
            )
        self.assertEqual(invalid_page.exception.status_code, 422)

    def test_rejects_oversized_requests_and_stroke_lists(self):
        with self.assertRaises(HTTPException) as oversized:
            save_page_annotations(
                self.child_id,
                self.document_id,
                1,
                self.payload(),
                request_with_size(1_048_577),
                self.owner_id,
                self.db,
            )
        self.assertEqual(oversized.exception.status_code, 413)

        stroke = self.payload().strokes[0].model_dump(mode="json")
        with self.assertRaises(ValidationError):
            AnnotationPageUpdate.model_validate({
                "base_revision": 0,
                "strokes": [stroke] * 501,
            })

    def test_annotations_cascade_when_child_is_deleted(self):
        save_page_annotations(
            self.child_id,
            self.document_id,
            2,
            self.payload(),
            request_with_size(),
            self.owner_id,
            self.db,
        )
        child = self.db.query(Child).filter(Child.id == self.child_id).one()
        self.db.delete(child)
        self.db.commit()
        self.assertEqual(self.db.query(PdfPageAnnotation).count(), 0)


if __name__ == "__main__":
    unittest.main()
