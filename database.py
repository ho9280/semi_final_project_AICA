<!-- 상단 헤더 및 버튼 -->
<header style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #000; padding-bottom: 10px;">
    <h2>🏛️ 광주 AI 아카데미 민원 서비스</h2>
    <div>
        <label>👤 현재 사용자: </label>
        <select id="userRole" onchange="switchRole()">
            <option value="1">학생 1 (user_id: 1)</option>
            <option value="admin">관리자 (user_id: 99)</option>
        </select>
        <!-- 새 민원 작성 버튼 -->
        <button id="btnOpenWriteModal" onclick="openWriteModal()" style="margin-left: 15px; padding: 8px 15px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;">
            ✏️ 새 민원 작성
        </button>
    </div>
</header>

<!-- 메인 영역: 민원 목록 피드 (화면 전체 활용) -->
<main class="section">
    <h3>📢 공개 민원 피드</h3>
    <div id="filterGroup" style="margin-bottom: 15px;">
        <button onclick="loadComplaints('')">전체</button>
        <button onclick="loadComplaints('청결')">청결</button>
        <button onclick="loadComplaints('시설/환경')">시설/환경</button>
        <button onclick="loadComplaints('학습 장비')">학습 장비</button>
        <button onclick="loadComplaints('수업/학습')">수업/학습</button>
        <button onclick="loadComplaints('개선 방안')">개선 방안</button>
        <button onclick="loadComplaints('비공개 - 기타')">비공개 - 기타</button>
    </div>
    <div id="feedContainer"></div>
</main>

<!-- 민원 작성/상세 조회용 모달 (기본 숨김) -->
<div id="complaintModal" class="modal hidden">
    <div class="modal-content">
        <span class="close-btn" onclick="closeModal()">&times;</span>
        <h3 id="formTitle">📝 새 민원 작성</h3>
        <input type="hidden" id="currentComplaintId">
        
        <div class="form-group">
            <label>카테고리</label>
            <select id="category">
                <option value="청결">청결</option>
                <option value="시설/환경">시설/환경</option>
                <option value="학습 장비">학습 장비</option>
                <option value="수업/학습">수업/학습</option>
                <option value="개선 방안">개선 방안</option>
                <option value="비공개 - 기타">비공개 - 기타</option>
            </select>
        </div>
        
        <!-- 학생 작성 시 또는 관리자 상세조회 시 노출 -->
        <div class="form-group" id="rawContentGroup">
            <label>원문 작성란</label>
            <textarea id="rawContent" placeholder="민원 내용을 상세히 적어주세요."></textarea>
        </div>

        <button id="btnSummarize" onclick="previewSummary()">✨ AI 요약하기</button>

        <div class="form-group" style="margin-top: 10px;">
            <label>💡 AI 요약 결과</label>
            <textarea id="summary" placeholder="요약 결과가 여기에 표시됩니다."></textarea>
        </div>

        <div class="form-group">
            <label>📎 첨부파일 링크 (선택)</label>
            <input type="url" id="photoUrl" placeholder="https://drive.google.com/...">
        </div>

        <hr>
        <div id="studentActionGroup">
            <button onclick="submitComplaint()" style="width:100%; padding: 10px;">🚀 최종 제출하기</button>
        </div>
        <div id="adminActionGroup" class="hidden">
            <p>⚙️ 관리자 상태 변경:</p>
            <button onclick="updateStatus('접수')">접수</button>
            <button onclick="updateStatus('처리 중')">처리 중</button>
            <button onclick="updateStatus('처리 완료')">처리 완료</button>
            <button onclick="updateStatus('승인 거절')">승인 거절</button>
        </div>
    </div>
</div>


/* 모달 배경 (어둡게 처리) */
.modal {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex; justify-content: center; align-items: center;
    z-index: 1000;
}
.modal.hidden { display: none; }

/* 모달 대화상자 스타일 */
.modal-content {
    background: white; padding: 25px; border-radius: 8px;
    width: 500px; max-width: 90%; position: relative;
    max-height: 90vh; overflow-y: auto;
}
.close-btn {
    position: absolute; top: 10px; right: 15px;
    font-size: 24px; cursor: pointer;
}



// 모달 열기 (작성 모드)
function openWriteModal() {
    resetForm();
    document.getElementById('formTitle').innerText = "📝 새 민원 작성";
    document.getElementById('rawContentGroup').classList.remove('hidden');
    document.getElementById('rawContent').readOnly = false;
    document.getElementById('complaintModal').classList.remove('hidden');
}

// 상세조회 열기 (피드에서 버튼 클릭 시)
async function openDetail(id) {
    try {
        const res = await fetch(`${API_BASE}/complaints?current_user_id=${currentUserData.id}`);
        const data = await res.json();
        const target = data.find(c => c.id === id);
        
        if (!target) return;

        document.getElementById('formTitle').innerText = "🔍 민원 상세 조회";
        document.getElementById('currentComplaintId').value = target.id;
        document.getElementById('category').value = target.category;
        document.getElementById('summary').value = target.summary;
        document.getElementById('photoUrl').value = target.photo_url || '';

        // 권한별 원문(rawContent) 노출 분기 처리
        if (currentUserData.role === 'admin') {
            document.getElementById('rawContentGroup').classList.remove('hidden');
            document.getElementById('rawContent').value = target.raw_content;
            document.getElementById('studentActionGroup').classList.add('hidden');
            document.getElementById('adminActionGroup').classList.remove('hidden');
        } else {
            // 학생은 상세보기 시 원문 작성란 숨김 (필요시 본인 글일 때만 표시 가능)
            document.getElementById('rawContentGroup').classList.add('hidden');
            document.getElementById('studentActionGroup').classList.add('hidden');
            document.getElementById('adminActionGroup').classList.add('hidden');
        }

        document.getElementById('complaintModal').classList.remove('hidden');
    } catch (error) {
        console.error("상세 조회 실패:", error);
    }
}

// 모달 닫기
function closeModal() {
    document.getElementById('complaintModal').classList.add('hidden');
}