#!/usr/bin/env python3
"""
LangGraph 워크플로우 시각화 스크립트

이 스크립트는 면접 워크플로우 그래프를 시각화합니다.
- ASCII 아트로 콘솔에 출력
- Mermaid 다이어그램 코드 생성
- PNG 이미지로 저장 (옵션)

사용법:
    cd server
    python workflow/visualize_graph.py
"""

import sys
from pathlib import Path

# server 디렉토리를 Python 경로에 추가
SERVER_DIR = Path(__file__).parent.parent.resolve()
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from workflow.graph import create_interview_graph


def main():
    """워크플로우 그래프를 시각화합니다."""
    print("=" * 80)
    print("AI Interview Agent - LangGraph 워크플로우 시각화")
    print("=" * 80)
    print()

    # 그래프 생성
    print("📊 워크플로우 그래프 생성 중...")
    graph = create_interview_graph(enable_rag=True, use_mini=True)
    print("✅ 그래프 생성 완료!\n")

    # 1. ASCII 아트로 출력
    print("-" * 80)
    print("1️⃣ ASCII 아트 시각화:")
    print("-" * 80)
    try:
        ascii_diagram = graph.get_graph().draw_ascii()
        print(ascii_diagram)
    except Exception as e:
        print(f"⚠️ ASCII 시각화 실패: {e}")
        print("대신 print_ascii()를 시도합니다...")
        try:
            graph.get_graph().print_ascii()
        except Exception as e2:
            print(f"⚠️ print_ascii()도 실패: {e2}")

    print("\n")

    # 2. Mermaid 다이어그램 코드 생성
    print("-" * 80)
    print("2️⃣ Mermaid 다이어그램 코드:")
    print("-" * 80)
    try:
        mermaid_code = graph.get_graph().draw_mermaid()
        print(mermaid_code)
        print("\n💡 위 Mermaid 코드를 https://mermaid.live/ 에 붙여넣으면 시각화할 수 있습니다.")
    except Exception as e:
        print(f"⚠️ Mermaid 시각화 실패: {e}")

    print("\n")

    # 3. 그래프 정보 출력
    print("-" * 80)
    print("3️⃣ 그래프 구조 정보:")
    print("-" * 80)
    try:
        graph_info = graph.get_graph()
        print(f"노드 수: {len(graph_info.nodes)}")
        print(f"엣지 수: {len(graph_info.edges)}")
        print(f"\n노드 목록:")
        for node_id in graph_info.nodes:
            print(f"  - {node_id}")
        print(f"\n엣지 목록:")
        for edge in graph_info.edges:
            print(f"  - {edge.source} → {edge.target}")
    except Exception as e:
        print(f"⚠️ 그래프 정보 조회 실패: {e}")

    print("\n" + "=" * 80)
    print("시각화 완료!")
    print("=" * 80)


if __name__ == "__main__":
    main()

