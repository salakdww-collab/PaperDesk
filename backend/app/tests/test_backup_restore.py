from pathlib import Path

import app.database as database
from app.config import settings
from app.models import Attachment, Paper
from app.services.backup_service import restore_backup, run_backup


def test_backup_restore_roundtrip(temp_env):
    db = database.SessionLocal()
    paper = Paper(status='confirmed', title='Backup Target')
    db.add(paper)
    db.flush()

    file_path = settings.attachments_dir / f'{paper.id}.pdf'
    file_path.write_bytes(b'%PDF-1.4 fake')

    attachment = Attachment(
        paper_id=paper.id,
        original_filename='x.pdf',
        stored_path=str(file_path),
        sha256='a' * 64,
        file_size=file_path.stat().st_size,
        page_count=1,
        extracted_text='backup text',
    )
    db.add(attachment)
    db.commit()

    backup_name = run_backup(db, kind='weekly')
    db.close()

    db2 = database.SessionLocal()
    db2.query(Attachment).delete()
    db2.query(Paper).delete()
    db2.commit()
    db2.close()

    restore_backup(backup_name)
    database.reset_engine(settings.db_path)

    db3 = database.SessionLocal()
    restored = db3.query(Paper).all()
    db3.close()

    assert len(restored) == 1
    assert restored[0].title == 'Backup Target'
    assert Path(settings.attachments_dir / f'{restored[0].id}.pdf').exists()
