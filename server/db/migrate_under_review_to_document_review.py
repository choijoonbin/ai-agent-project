# server/db/migrate_under_review_to_document_review.py
"""
마이그레이션 스크립트: 
1. UNDER_REVIEW → DOCUMENT_REVIEW (applications 테이블)
2. interviews 테이블에 application_id 컬럼 추가

실행 방법:
    python -m server.db.migrate_under_review_to_document_review
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import sessionmaker

# 프로젝트 루트를 Python 경로에 추가
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# server 디렉토리를 Python 경로에 추가
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from db.database import engine


def migrate():
    """마이그레이션 실행"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # 1. applications 테이블의 status 컬럼 업데이트 (테이블이 있는 경우만)
        if 'applications' in tables:
            print("1️⃣ applications 테이블: UNDER_REVIEW → DOCUMENT_REVIEW")
            try:
                result = db.execute(
                    text("UPDATE applications SET status = 'DOCUMENT_REVIEW' WHERE status = 'UNDER_REVIEW'")
                )
                db.commit()
                updated_count = result.rowcount
                print(f"   ✅ {updated_count}개의 레코드가 업데이트되었습니다.")
            except Exception as e:
                print(f"   ⚠️ applications 테이블 업데이트 중 오류 (무시): {e}")
                db.rollback()
        else:
            print("1️⃣ applications 테이블이 존재하지 않습니다. 건너뜁니다.")
        
        # 2. interviews 테이블에 application_id 컬럼 추가 (없는 경우만)
        if 'interviews' not in tables:
            print("\n❌ interviews 테이블이 존재하지 않습니다. 마이그레이션을 중단합니다.")
            return
        
        print("\n2️⃣ interviews 테이블: application_id 컬럼 추가")
        columns = [col['name'] for col in inspector.get_columns('interviews')]
        
        if 'application_id' not in columns:
            # SQLite는 ALTER TABLE ADD COLUMN 지원
            db.execute(
                text("ALTER TABLE interviews ADD COLUMN application_id INTEGER")
            )
            db.commit()
            print("   ✅ application_id 컬럼이 추가되었습니다.")
            
            # 인덱스 추가 (선택적, 성능 향상)
            try:
                db.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_interviews_application_id ON interviews(application_id)")
                )
                db.commit()
                print("   ✅ application_id 인덱스가 생성되었습니다.")
            except Exception as idx_error:
                print(f"   ⚠️ 인덱스 생성 중 오류 (무시 가능): {idx_error}")
        else:
            print("   ℹ️ application_id 컬럼이 이미 존재합니다.")
        
        # 변경 사항 확인
        print("\n📊 마이그레이션 결과:")
        if 'applications' in tables:
            try:
                count = db.execute(
                    text("SELECT COUNT(*) FROM applications WHERE status = 'DOCUMENT_REVIEW'")
                ).scalar()
                print(f"   - DOCUMENT_REVIEW 상태의 지원서: {count}개")
            except:
                pass
        
        try:
            interview_count = db.execute(
                text("SELECT COUNT(*) FROM interviews WHERE application_id IS NOT NULL")
            ).scalar()
            print(f"   - application_id가 연결된 면접 이력: {interview_count}개")
        except:
            pass
        
        print("\n✅ 모든 마이그레이션이 완료되었습니다!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 마이그레이션 실패: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

