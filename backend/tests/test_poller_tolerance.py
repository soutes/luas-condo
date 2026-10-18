"""
Regression test: the email sync must tolerate a single unparseable document
(one bad attachment must not abort the whole batch).
No emojis used.
"""

from pathlib import Path
import sys
import pytest

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services import email_worker, poller


def test_sync_continues_when_one_document_fails(monkeypatch):
    """Documents are synced one per call: the failing one is logged and skipped,
    the remaining ones still produce cycles."""
    attempted = []

    def fake_fetch(**kwargs):
        return [
            email_worker.IngestedDocument(
                doc_type=email_worker.DocumentType.CONDO_BILL,
                filename="boleto_quebrado.pdf",
                content=b"%PDF-1.4 bad",
            ),
            email_worker.IngestedDocument(
                doc_type=email_worker.DocumentType.CONDO_BILL,
                filename="boleto_bom.pdf",
                content=b"%PDF-1.4 good",
            ),
        ]

    def fake_sync(db_session_arg, docs, storage_dir="/data/storage"):
        for d in docs:
            attempted.append(d.filename)
            if "quebrado" in d.filename:
                raise ValueError("Unable to parse condo bill: data_vencimento not found")
        return [object()]

    monkeypatch.setattr(poller, "fetch_new_condo_emails", fake_fetch)
    monkeypatch.setattr(poller, "sync_condo_cycle", fake_sync)

    import asyncio

    res = asyncio.run(poller.execute_email_sync(db=None, imap_client=object()))

    assert res["status"] == "ok"
    assert res["synced_cycles"] == 1
    assert attempted == ["boleto_quebrado.pdf", "boleto_bom.pdf"]
