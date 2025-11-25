DevOps Engineer Best Practices
1. Infrastructure as Code
* 인프라 구성을 코드로 관리(Terraform, CloudFormation 등)
* 환경별(Dev/Stg/Prod) 구성 템플릿화
* 변경은 Pull Request 기반으로 리뷰 후 반영
* 재현 가능한 환경 구축(불변 인프라 지향)
2. CI/CD Pipeline
* 빌드/테스트/배포 파이프라인 표준화
* 실패 시 롤백 전략 명확화
* 단계별 게이트(테스트, 승인, 보안 검사) 설정
* 파이프라인 성능/안정성 모니터링
3. Observability
* 로그/메트릭/트레이싱 통합 수집 및 대시보드 구성
* 주요 비즈니스/기술 지표에 대한 알람 설정
* SLO/SLA/SLI 정의 및 추적
* 장애 Post-mortem 문화 정착(Blameless)
4. Security & Compliance
* 시크릿/자격증명 안전 관리(Secret Manager, Vault 등)
* 최소 권한 원칙(Least Privilege) 적용
* 정기적인 취약점 스캔 및 패치 관리
* 감사 로그 및 접근 이력 관리
5. Reliability & Cost
* 오토스케일링, 헬스체크, 셀프힐링 구성
* 다중 AZ/Region 고려한 아키텍처 설계
* 비용 모니터링 및 최적화(Reservation/Right-Sizing)
