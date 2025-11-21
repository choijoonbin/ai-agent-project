#!/usr/bin/env python3
"""
SQLite 데이터베이스 내용을 확인하는 유틸리티 스크립트
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

DB_PATH = Path(__file__).parent / "interview_history.db"


def view_interviews(limit: int = 10) -> None:
    """면접 이력 목록 조회"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("📋 면접 이력 목록")
    print("=" * 80)

    cursor.execute(
        """
        SELECT id, job_title, candidate_name, status, total_questions, created_at
        FROM interviews
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()
    if not rows:
        print("데이터가 없습니다.")
        return

    for row in rows:
        print(f"\n[ID: {row['id']}]")
        print(f"  포지션: {row['job_title']}")
        print(f"  지원자: {row['candidate_name']}")
        print(f"  상태: {row['status']}")
        print(f"  질문 수: {row['total_questions']}")
        print(f"  생성일: {row['created_at']}")

    conn.close()


def view_interview_detail(interview_id: int) -> None:
    """특정 면접 상세 정보 조회"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM interviews WHERE id = ?
        """,
        (interview_id,),
    )

    row = cursor.fetchone()
    if not row:
        print(f"ID {interview_id}에 해당하는 면접 이력이 없습니다.")
        conn.close()
        return

    print("\n" + "=" * 80)
    print(f"📄 면접 상세 정보 (ID: {interview_id})")
    print("=" * 80)

    print(f"\n기본 정보:")
    print(f"  포지션: {row['job_title']}")
    print(f"  지원자: {row['candidate_name']}")
    print(f"  상태: {row['status']}")
    print(f"  질문 수: {row['total_questions']}")
    print(f"  생성일: {row['created_at']}")

    # state_json 파싱
    try:
        state = json.loads(row['state_json'])
        print(f"\n📊 State 정보:")
        print(f"  - JD 요약: {state.get('jd_summary', 'N/A')[:100]}...")
        print(f"  - 지원자 요약: {state.get('candidate_summary', 'N/A')[:100]}...")
        
        qa_history = state.get('qa_history', [])
        print(f"  - 질문/답변 수: {len(qa_history)}")
        
        evaluation = state.get('evaluation', {})
        if evaluation:
            print(f"  - 평가 요약: {evaluation.get('summary', 'N/A')[:100]}...")
            recommendation = evaluation.get('recommendation', 'N/A')
            print(f"  - 추천 결과: {recommendation}")
    except json.JSONDecodeError:
        print("\n⚠️  state_json 파싱 실패")

    conn.close()


def view_tables() -> None:
    """모든 테이블 목록 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("📊 데이터베이스 테이블 목록")
    print("=" * 80)

    cursor.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
        """
    )

    tables = cursor.fetchall()
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  - {table_name}: {count}개 레코드")

    conn.close()


def view_table_schema(table_name: str) -> None:
    """테이블 스키마 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"\n📋 테이블 '{table_name}' 스키마:")
    print("=" * 80)

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()

    for col in columns:
        print(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULL'}")

    conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "list":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            view_interviews(limit)
        elif command == "detail":
            if len(sys.argv) < 3:
                print("사용법: python view_db.py detail <interview_id>")
                sys.exit(1)
            interview_id = int(sys.argv[2])
            view_interview_detail(interview_id)
        elif command == "tables":
            view_tables()
        elif command == "schema":
            if len(sys.argv) < 3:
                print("사용법: python view_db.py schema <table_name>")
                sys.exit(1)
            table_name = sys.argv[2]
            view_table_schema(table_name)
        else:
            print("알 수 없는 명령어입니다.")
            sys.exit(1)
    else:
        print("""
SQLite 데이터베이스 조회 유틸리티

사용법:
  python view_db.py list [limit]          # 면접 이력 목록 조회 (기본 10개)
  python view_db.py detail <interview_id>  # 특정 면접 상세 정보
  python view_db.py tables                 # 모든 테이블 목록
  python view_db.py schema <table_name>   # 테이블 스키마 조회

예시:
  python view_db.py list 20
  python view_db.py detail 1
  python view_db.py tables
  python view_db.py schema interviews
        """)

