/**
 * @fileoverview 출결 에이전트 프론트엔드 모듈 (Vanilla JS)
 * @description 백엔드 신호(OPEN_CALCULATOR_POPUP) 수신 시 동적 DOM 마운트 및 V8 GC를 활용한 상태 초기화를 수행합니다.
 * 시연 환경에 맞추어 타이핑을 배제하고 증감 버튼(+/-) 이벤트를 통해 백엔드(FastAPI)와 통신합니다.
 */

/**
 * @typedef {Object} AttendanceState
 * @property {number} absence - 결석 일수
 * @property {number} lateness - 지각 횟수
 * @property {number} early_leave - 조퇴 횟수
 * @property {number} outing - 외출 횟수
 * @property {number} official_leave - 공가 일수
 */

const MONTH_TOTAL_DAYS = {
    5: 17, 6: 21, 7: 22, 8: 20,
    9: 20, 10: 20, 11: 21, 12: 9
};

function getGuideValues(month) {
    const totalDays = MONTH_TOTAL_DAYS[month] || 20;
    return {
        target_50_days: Math.ceil(totalDays * 0.5),
        target_80_days: Math.ceil(totalDays * 0.8),
        max_official_leave: Math.floor(totalDays * 0.2)
    };
}

class AttendanceCalculatorUI {
    /**
     * 출결 계산기 모달 객체를 초기화합니다.
     */
    constructor() {
        /** @type {AttendanceState} */
        this.state = {
            absence: 0,
            lateness: 0,
            early_leave: 0,
            outing: 0,
            official_leave: 0
        };
        
        /** @type {HTMLElement | null} */
        this.modalElement = null;
        
        // 통신할 백엔드 출결 연산 라우터 주소 (포트 및 IP는 환경에 맞게 수정)
        this.apiUrl = "http://localhost:8000/attendance/calculate";
    }

    /**
     * 모달을 최상위 DOM에 마운트합니다 (새 창 띄우기 방식).
     * 함수 호출 시 무조건 상태를 0으로 초기화하여 이전 흔적을 소멸시킵니다.
     * @returns {void}
     */
    mount() {
        // [구조적 증명] 기존 요소가 마운트 되어 있다면 예외 처리 (assert 단언)
        console.assert(this.modalElement === null, "Modal is already mounted. Must be unmounted first.");
        
        // 메모리 상의 이전 상태 완전 초기화
        this.state = { absence: 0, lateness: 0, early_leave: 0, outing: 0, official_leave: 0 };

        // 1. 최상위 Backdrop 레이어 생성 (화면 중앙 고정, z-index 9999)
        this.modalElement = document.createElement('div');
        this.modalElement.id = 'attendance-calculator-root';
        this.modalElement.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0, 0, 0, 0.4);
            display: flex; justify-content: center; align-items: center;
            z-index: 9999; backdrop-filter: blur(2px);
        `;

        // 2. 모달 컨테이너 생성
        const modalContent = document.createElement('div');
        modalContent.style.cssText = `
            background: #ffffff; padding: 24px; border-radius: 12px;
            width: 320px; box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            position: relative;
        `;

        // 3. 상단 헤더 행: 타이틀 + 닫기 버튼 (같은 줄, 별도 클릭 여백 확보)
        const headerRow = document.createElement('div');
        headerRow.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;';

        const title = document.createElement('h3');
        title.innerText = '🧮 7기 출결 계산기';
        title.style.cssText = 'margin: 0; color: #212529; font-size: 1.1rem;';

        const closeBtn = document.createElement('button');
        closeBtn.innerText = '✕';
        closeBtn.setAttribute('aria-label', '닫기');
        closeBtn.style.cssText = `
            cursor: pointer; border: none; background: #f1f3f5;
            width: 28px; height: 28px; border-radius: 6px;
            font-weight: 600; color: #495057; flex-shrink: 0;
        `;
        closeBtn.onclick = () => this.unmount();

        headerRow.appendChild(title);
        headerRow.appendChild(closeBtn);
        modalContent.appendChild(headerRow);

        // 4. 가이드 3항목 (50% / 80% / 공가 한도) - 이번 달 기준 고정
        const currentMonth = new Date().getMonth() + 1;
        const guide = getGuideValues(currentMonth);
        const guideBox = document.createElement('div');
        guideBox.style.cssText = 'display:flex; justify-content:space-around; text-align:center; padding:8px 0 12px; border-bottom:1px solid #e9ecef; margin-bottom:12px;';
        guideBox.innerHTML = `
            <div>
                <div style="font-size:11px; color:#868e96;">50% 기준</div>
                <div style="font-size:13px; font-weight:700;">${guide.target_50_days}일</div>
            </div>
            <div>
                <div style="font-size:11px; color:#868e96;">80% 기준</div>
                <div style="font-size:13px; font-weight:700;">${guide.target_80_days}일</div>
            </div>
            <div>
                <div style="font-size:11px; color:#868e96;">공가 한도</div>
                <div style="font-size:13px; font-weight:700;">${guide.max_official_leave}일</div>
            </div>
        `;
        modalContent.appendChild(guideBox);

        // 5. 항목별 입력 폼 렌더링 (map을 활용한 벡터화 유사 구조)
        const fields = [
            { key: 'absence', label: '결석 (일)' },
            { key: 'lateness', label: '지각 (회)' },
            { key: 'early_leave', label: '조퇴 (회)' },
            { key: 'outing', label: '외출 (회)' },
            { key: 'official_leave', label: '공가 (일)' }
        ];

        fields.forEach(field => {
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;';
            
            const label = document.createElement('span');
            label.innerText = field.label;
            label.style.fontWeight = '500';
            
            const controlBox = document.createElement('div');
            controlBox.style.cssText = 'display: flex; align-items: center; gap: 12px;';

            // 감산 버튼 (-)
            const minusBtn = document.createElement('button');
            minusBtn.innerText = '-';
            minusBtn.style.cssText = 'width: 32px; height: 32px; cursor: pointer; border: 1px solid #ced4da; background: #fff; border-radius: 4px; font-size: 1.1rem;';
            minusBtn.onclick = () => this.updateValue(field.key, -1);

            // 현재 수치 텍스트 노출 (타이핑 방지를 위해 span 요소 사용)
            const valDisplay = document.createElement('span');
            valDisplay.id = `display-${field.key}`;
            valDisplay.innerText = this.state[field.key].toString();
            valDisplay.style.cssText = 'width: 24px; text-align: center; font-weight: 700; color: #1c7ed6;';

            // 가산 버튼 (+)
            const plusBtn = document.createElement('button');
            plusBtn.innerText = '+';
            plusBtn.style.cssText = 'width: 32px; height: 32px; cursor: pointer; border: 1px solid #ced4da; background: #fff; border-radius: 4px; font-size: 1.1rem;';
            plusBtn.onclick = () => this.updateValue(field.key, 1);

            controlBox.appendChild(minusBtn);
            controlBox.appendChild(valDisplay);
            controlBox.appendChild(plusBtn);

            row.appendChild(label);
            row.appendChild(controlBox);
            modalContent.appendChild(row);
        });

        // 6. 결과 출력 패널
        const resultBox = document.createElement('div');
        resultBox.id = 'attendance-result-box';
        resultBox.style.cssText = 'margin-top: 24px; padding: 16px; background: #f8f9fa; border-radius: 8px; font-size: 14px; border: 1px solid #e9ecef;';
        resultBox.innerHTML = '<span style="color:#868e96;">초기 데이터를 로드 중입니다...</span>';
        modalContent.appendChild(resultBox);

        // 조립 완료 및 문서(DOM) 삽입
        this.modalElement.appendChild(modalContent);
        document.body.appendChild(this.modalElement);

        // 마운트 시 최초 상태(All 0)를 기준으로 API 즉시 호출
        this.fetchCalculation();
    }

    /**
     * 상태 값을 안전하게 갱신하고 연산 API를 호출합니다.
     * @param {keyof AttendanceState} key - 변경 대상 객체 키
     * @param {number} delta - 적용할 가감 연산 값
     * @returns {void}
     */
    updateValue(key, delta) {
        const newValue = this.state[key] + delta;
        // 음수 출결 횟수는 도메인 논리 상 불가하므로 return 처리
        if (newValue < 0) return; 

        this.state[key] = newValue;
        
        // DOM 리페인팅(Repainting)
        const display = document.getElementById(`display-${key}`);
        console.assert(display !== null, `[Fatal] DOM element display-${key} has been detached.`);
        display.innerText = this.state[key].toString();

        // 실시간 백엔드 연동
        this.fetchCalculation();
    }

    /**
     * 백엔드(FastAPI)와 통신하여 출결 연산 결과를 패치합니다.
     * @async
     * @returns {Promise<void>}
     */
    async fetchCalculation() {
        const resultBox = document.getElementById('attendance-result-box');
        if (!resultBox) return;

        // 시연 안정성을 위한 로딩 상태 렌더링
        resultBox.innerHTML = '<strong>계산 중... ⏳</strong>';

        try {
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // JSON 직렬화를 통해 백엔드의 Pydantic 모델과 타입 안전성 보장
                body: JSON.stringify(this.state)
            });

            if (!response.ok) {
                throw new Error(`[Network Error] API Endpoint returned HTTP ${response.status}`);
            }

            /** 
             * @type {{ attendance_rate: number, recognized_days: number, remaining_leave: number }} 
             */
            const data = await response.json();

            // [구조적 증명] API 응답 스키마 정합성 검증 (assert 단언)
            console.assert(typeof data.attendance_rate === "number", "Response schema mismatch: attendance_rate is missing");

            // 결과 바인딩
            resultBox.innerHTML = `
                <div style="text-align:center; font-size:11px; color:#868e96; margin-bottom:4px;">현재 출석일수 / 단위 출석일수</div>
                <div style="text-align:center; font-size:19px; font-weight:700;">
                    ${data.recognized_days}일
                    <span style="color:#1c7ed6;"> (${data.attendance_rate}%)</span>
                </div>
                <div style="text-align:center; font-size:12px; color:#868e96; margin-top:6px;">잔여 공가 ${data.remaining_leave}일</div>
            `;
        } catch (error) {
            console.error('[AttendanceUI] API Request Exception:', error);
            resultBox.innerHTML = '<span style="color: #e03131; font-weight:bold;">서버 통신 오류가 발생했습니다.</span>';
        }
    }

    /**
     * 모달 요소를 DOM 트리에서 제거하여 V8 엔진의 Garbage Collection을 트리거합니다.
     * @returns {void}
     */
    unmount() {
        if (this.modalElement && this.modalElement.parentNode) {
            this.modalElement.parentNode.removeChild(this.modalElement);
            this.modalElement = null;
        }
    }
}

// =====================================================================
// [챗봇 라우터 및 메인 UI와의 연동부 가이드 (복사하여 사용)]
// =====================================================================

// 싱글톤(Singleton) 패턴 형태로 전역 객체 1개 생성
const attendanceUI = new AttendanceCalculatorUI();

/**
 * 챗봇 라우터 측에서 응답을 수신했을 때 실행되는 핸들러 (예시)
 * @param {Object} botResponse - 백엔드(LangChain)에서 넘어온 JSON
 */
function handleAttendanceAction(botResponse) {
    if (botResponse.action === 'OPEN_CALCULATOR_POPUP') {
        // 버튼 동적 렌더링 후 이벤트 리스너 할당
        // const actionBtn = document.createElement('button');
        // actionBtn.innerText = '🧮 7기 출결 계산기 열기';
        // actionBtn.addEventListener('click', () => { attendanceUI.mount(); });
        // chatBubble.appendChild(actionBtn);
    }
}