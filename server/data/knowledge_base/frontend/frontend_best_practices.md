Frontend Developer Best Practices
1. Code & Architecture
* 컴포넌트 단위 분리(재사용/응집도 중심)
* 상태 관리 전략 명확화(전역/로컬 상태 구분)
* 폴더 구조와 네이밍 일관성 유지
* 프레젠테이션/컨테이너 컴포넌트 분리
* 타입 시스템(TypeScript 등) 적극 활용
2. UI/UX Implementation
* 디자인 시스템 또는 컴포넌트 라이브러리 일관 사용
* 반응형 레이아웃(Grid/Flex + Media Query) 적용
* 사용성 높은 기본 상호작용(Loading, Empty, Error State) 구현
* 접근성(ARIA, 키보드 네비게이션, 대비 등) 고려
* 마이크로 인터랙션(hover, focus 등)으로 피드백 제공
3. Performance
* 코드 스플리팅 및 Lazy Loading 적용
* 불필요한 리렌더링 최소화(Memoization, key 관리)
* 이미지/폰트/리소스 최적화
* Lighthouse/DevTools 기반 성능 측정 및 개선
* 번들 사이즈 관리(트리 쉐이킹, 의존성 최소화)
4. API & 상태 연동
* API 클라이언트 모듈 분리(에러/토큰/로그 공통 처리)
* 로딩/에러 상태 UI 패턴 표준화
* 낙관적 업데이트/비관적 업데이트 기준 정의
* 캐싱 전략(SWR/React Query 등) 수립
5. Testing & Tooling
* 주요 기능에 대한 단위/통합/E2E 테스트 작성
* Storybook 등으로 컴포넌트 카탈로그 관리
* 린트/포맷터(ESLint, Prettier) 강제 적용
* CI에서 테스트/빌드 자동 검증
