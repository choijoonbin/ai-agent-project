ML / AI Engineer Best Practices
1. Problem Framing
* 비즈니스 문제를 ML 문제로 올바르게 매핑
* 규칙 기반/통계/ML 중 적절한 접근 선택
* 베이스라인 모델 먼저 구축 후 고도화
* 성공 기준(metric, threshold) 사전 정의
2. Data & Features
* 데이터 수집/정제/레이블링 프로세스 명확화
* 데이터 리스크(편향, 누락, 누설) 점검
* Feature Store 등 재사용 가능한 구조 설계
* Train/Validation/Test 분리 전략 신중 설계
3. Modeling & Training
* 모델/알고리즘 선택 이유 명시(해석력 vs 성능 등)
* Hyperparameter 튜닝 계획 수립(그리드/베이즈 등)
* 재현 가능한 실험 환경(Seed, 버전, 설정 관리)
* 과적합 방지(Regularization, Dropout, Early Stopping 등)
4. Evaluation & Monitoring
* 문제 유형에 맞는 Metric 선택(Precision/Recall/F1, AUC 등)
* 비즈니스 KPI와 Metric의 관계 설명 가능
* 실서비스 데이터 기반 Offline/Online 평가
* Drift/Degradation 모니터링 및 경보 설정
5. Deployment & Ethics
* 모델 서빙 아키텍처(동기/비동기, 배치/실시간) 명확화
* 롤백/그레이 롤아웃(카나리 테스트) 전략 확보
* 데이터/모델 버전 관리 규칙 수립
* 개인정보/편향/공정성 이슈 점검 프로세스 포함
