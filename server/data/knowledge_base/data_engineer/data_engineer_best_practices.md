Data Engineer Best Practices
1. Data Modeling
* 비즈니스 도메인을 반영한 데이터 모델 설계
* OLTP/OLAP 목적에 따른 스키마 차별화
* 파티셔닝/클러스터링 전략 수립
* 변경 이력(SCD, Audit Log) 관리
2. ETL/ELT & Pipelines
* 파이프라인는 코드로 관리(템플릿/모듈화)
* 실패/재시도/알람 로직 내장
* 스케줄링/의존성 관리(Airflow 등) 체계화
* Batch/Streaming 아키텍처 구분 및 혼합 전략 설계
3. Data Quality
* 스키마 검증, Null/Outlier 체크 등 DQ 룰 정의
* 중요 테이블에 대한 품질 모니터링 대시보드 구축
* 데이터 혈통(Lineage) 관리
* 로그 기반 파이프라인 헬스체크
4. Performance & Cost
* 적절한 파일 포맷(Parquet/ORC 등)과 압축 사용
* 조인/집계 최적화를 위한 파티션 키/정렬 전략
* 캐시/머티리얼라이즈드 뷰 활용
* 저장/쿼리 비용 모니터링 및 최적화
5. Governance & Security
* 데이터 등급 분류(PII, 민감 정보 등)
* 권한/마스킹/암호화 정책 수립
* 카탈로그/메타데이터 관리 도구 활용
