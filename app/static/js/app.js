// ========================================
// 채널 목록 토글
// ========================================

function toggleChannelList() {
    const content = document.getElementById('channelsContent');
    const toggleBtn = document.getElementById('channelToggleBtn');

    if (content.classList.contains('collapsed')) {
        content.classList.remove('collapsed');
        toggleBtn.textContent = '▼';
    } else {
        content.classList.add('collapsed');
        toggleBtn.textContent = '▶';
    }
}

// ========================================
// 카테고리 관리
// ========================================

function selectCategory(categoryId) {
    currentCategoryId = categoryId;

    // 탭 활성화
    document.querySelectorAll('.category-tab').forEach(tab => {
        tab.classList.remove('active');
        if (parseInt(tab.dataset.categoryId) === categoryId) {
            tab.classList.add('active');
        }
    });

    // 채널 추가 버튼 표시/숨김 ('전체' 탭에서는 숨김)
    const addChannelBtn = document.querySelector('.channels-header .btn-primary');
    if (addChannelBtn) {
        addChannelBtn.style.display = categoryId === 0 ? 'none' : 'block';
    }

    // 채널 목록 다시 로드
    loadChannels();

    // 선택 상태만 초기화 (검색 결과는 유지)
    selectedChannelIds.clear();
    // 검색 결과가 있으면 유지, 없으면 그대로
}

function openCategoryModal() {
    loadCategories();
    document.getElementById('categoryModal').classList.add('active');
}

function closeCategoryModal() {
    document.getElementById('categoryModal').classList.remove('active');
}

async function loadCategories() {
    try {
        const response = await fetch('/api/categories/');
        const data = await response.json();

        const categoryList = document.getElementById('categoryList');
        categoryList.innerHTML = '';

        data.categories.forEach((category, index) => {
            const item = document.createElement('div');
            item.className = 'category-item';
            item.dataset.categoryId = category.id;
            item.dataset.displayOrder = category.display_order;

            // 순서 변경 버튼들
            const orderButtons = document.createElement('div');
            orderButtons.className = 'category-order-buttons';
            orderButtons.style.cssText = 'display: flex; flex-direction: column; gap: 2px; margin-right: 8px;';

            const upBtn = document.createElement('button');
            upBtn.className = 'btn-order-up';
            upBtn.textContent = '▲';
            upBtn.title = '위로 이동';
            upBtn.style.cssText = 'padding: 2px 8px; font-size: 10px; background: #333; border: 1px solid #555; color: #fff; cursor: pointer; border-radius: 3px;';
            upBtn.disabled = index === 0;
            if (index > 0) {
                upBtn.onclick = () => moveCategoryUp(category.id, data.categories);
            } else {
                upBtn.style.opacity = '0.3';
                upBtn.style.cursor = 'not-allowed';
            }

            const downBtn = document.createElement('button');
            downBtn.className = 'btn-order-down';
            downBtn.textContent = '▼';
            downBtn.title = '아래로 이동';
            downBtn.style.cssText = 'padding: 2px 8px; font-size: 10px; background: #333; border: 1px solid #555; color: #fff; cursor: pointer; border-radius: 3px;';
            downBtn.disabled = index === data.categories.length - 1;
            if (index < data.categories.length - 1) {
                downBtn.onclick = () => moveCategoryDown(category.id, data.categories);
            } else {
                downBtn.style.opacity = '0.3';
                downBtn.style.cursor = 'not-allowed';
            }

            orderButtons.appendChild(upBtn);
            orderButtons.appendChild(downBtn);

            // 카테고리 이름
            const nameSpan = document.createElement('span');
            nameSpan.className = 'category-item-name';
            nameSpan.textContent = `${category.name} (${category.channel_count})`;

            // 액션 버튼
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'category-item-actions';

            if (category.id !== 1) {
                const editBtn = document.createElement('button');
                editBtn.className = 'btn-edit';
                editBtn.textContent = '수정';
                editBtn.onclick = () => editCategory(category.id, category.name);

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn-delete';
                deleteBtn.textContent = '삭제';
                deleteBtn.onclick = () => deleteCategory(category.id);

                actionsDiv.appendChild(editBtn);
                actionsDiv.appendChild(deleteBtn);
            }

            item.appendChild(orderButtons);
            item.appendChild(nameSpan);
            item.appendChild(actionsDiv);

            categoryList.appendChild(item);
        });

        // 탭 개수도 업데이트
        updateTabCounts(data.categories, data.total_count);
    } catch (error) {
        console.error('카테고리 로드 실패:', error);
        alert('카테고리를 불러오는데 실패했습니다.');
    }
}

function updateTabCounts(categories, totalCount) {
    // 전체 탭 업데이트
    const allTab = document.querySelector('.category-tab[data-category-id="0"] .tab-count');
    if (allTab) {
        allTab.textContent = totalCount;
    }

    // 각 카테고리 탭 업데이트
    categories.forEach(category => {
        const tab = document.querySelector(`.category-tab[data-category-id="${category.id}"] .tab-count`);
        if (tab) {
            tab.textContent = category.channel_count;
        }
    });
}

async function addCategory() {
    const nameInput = document.getElementById('newCategoryName');
    const name = nameInput.value.trim();

    if (!name) {
        alert('카테고리 이름을 입력하세요.');
        return;
    }

    try {
        const response = await fetch('/api/categories/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        if (response.ok) {
            nameInput.value = '';
            loadCategories();
            location.reload(); // 탭 갱신
        } else {
            const error = await response.json();
            alert(error.detail || '카테고리 추가 실패');
        }
    } catch (error) {
        console.error('카테고리 추가 실패:', error);
        alert('카테고리 추가에 실패했습니다.');
    }
}

async function editCategory(id, currentName) {
    const newName = prompt('새 카테고리 이름:', currentName);
    if (!newName || newName === currentName) return;

    try {
        const response = await fetch(`/api/categories/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });

        if (response.ok) {
            loadCategories();
            location.reload(); // 탭 갱신
        } else {
            const error = await response.json();
            alert(error.detail || '카테고리 수정 실패');
        }
    } catch (error) {
        console.error('카테고리 수정 실패:', error);
        alert('카테고리 수정에 실패했습니다.');
    }
}

async function deleteCategory(id) {
    if (!confirm('이 카테고리를 삭제하시겠습니까?\n(채널은 기본 카테고리로 이동됩니다)')) {
        return;
    }

    try {
        const response = await fetch(`/api/categories/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadCategories();
            location.reload(); // 탭 갱신
        } else {
            const error = await response.json();
            alert(error.detail || '카테고리 삭제 실패');
        }
    } catch (error) {
        console.error('카테고리 삭제 실패:', error);
        alert('카테고리 삭제에 실패했습니다.');
    }
}

// 카테고리 순서 변경 함수들
async function moveCategoryUp(categoryId, categories) {
    const currentIndex = categories.findIndex(c => c.id === categoryId);
    if (currentIndex <= 0) return;

    const currentCategory = categories[currentIndex];
    const previousCategory = categories[currentIndex - 1];

    await swapCategoryOrder(currentCategory.id, previousCategory.id,
                           currentCategory.display_order, previousCategory.display_order);
}

async function moveCategoryDown(categoryId, categories) {
    const currentIndex = categories.findIndex(c => c.id === categoryId);
    if (currentIndex < 0 || currentIndex >= categories.length - 1) return;

    const currentCategory = categories[currentIndex];
    const nextCategory = categories[currentIndex + 1];

    await swapCategoryOrder(currentCategory.id, nextCategory.id,
                           currentCategory.display_order, nextCategory.display_order);
}

async function swapCategoryOrder(id1, id2, order1, order2) {
    try {
        // 두 카테고리의 display_order 교환
        const response1 = await fetch(`/api/categories/${id1}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_order: order2 })
        });

        const response2 = await fetch(`/api/categories/${id2}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_order: order1 })
        });

        if (response1.ok && response2.ok) {
            // 카테고리 목록 다시 로드
            await loadCategories();
            // 탭도 다시 로드
            await reloadCategoryTabs();
        } else {
            alert('순서 변경에 실패했습니다.');
        }
    } catch (error) {
        console.error('카테고리 순서 변경 실패:', error);
        alert('순서 변경에 실패했습니다: ' + error.message);
    }
}

async function reloadCategoryTabs() {
    try {
        const response = await fetch('/api/categories/');
        const data = await response.json();

        // 탭 컨테이너 찾기
        const tabsContainer = document.querySelector('.category-tabs');
        if (!tabsContainer) return;

        // 전체 탭 제외하고 기존 탭 제거
        const allTab = tabsContainer.querySelector('[data-category-id="0"]');
        tabsContainer.innerHTML = '';

        // 전체 탭 다시 추가
        if (allTab) {
            tabsContainer.appendChild(allTab);
        }

        // 카테고리 탭 다시 생성
        data.categories.forEach(category => {
            const button = document.createElement('button');
            button.className = 'category-tab';
            if (category.id === currentCategoryId) {
                button.classList.add('active');
            }
            button.setAttribute('data-category-id', category.id);
            button.setAttribute('data-channel-count', category.channel_count);
            button.onclick = () => selectCategory(category.id);
            button.innerHTML = `${category.name} (<span class="tab-count">${category.channel_count}</span>)`;
            tabsContainer.appendChild(button);
        });

        // 전체 탭 개수 업데이트
        updateTabCounts(data.categories, data.total_count);
    } catch (error) {
        console.error('탭 리로드 실패:', error);
    }
}

// ========================================
// 채널 관리
// ========================================

async function loadChannels() {
    try {
        const response = await fetch(`/api/channels/?category_id=${currentCategoryId}`);
        const data = await response.json();

        const channelsList = document.getElementById('channelsList');
        channelsList.innerHTML = '';

        if (data.channels.length === 0) {
            channelsList.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">등록된 채널이 없습니다. 채널을 추가하세요.</p>';
            // 탭 개수 업데이트
            await refreshTabCounts();
            return;
        }

        data.channels.forEach(channel => {
            const card = document.createElement('div');
            card.className = `channel-card ${channel.is_active ? '' : 'inactive'}`;

            // 설명 툴팁용 텍스트 (최대 200자)
            const descriptionText = channel.description ?
                (channel.description.length > 200 ? channel.description.substring(0, 200) + '...' : channel.description) :
                '채널 설명 없음';

            card.innerHTML = `
                <div class="channel-checkbox">
                    <input type="checkbox"
                           class="channel-select-checkbox"
                           data-channel-id="${channel.id}"
                           onchange="toggleChannelSelection(${channel.id}, this.checked)">
                </div>
                <div class="channel-info">
                    <div class="channel-title">
                        <a href="https://www.youtube.com/channel/${channel.channel_id}"
                           target="_blank"
                           class="channel-title-link"
                           title="${descriptionText}">
                            ${escapeHtml(channel.title || channel.channel_id)}
                        </a>
                    </div>
                    <div class="channel-meta">
                        구독자 ${formatSubscriberCount(channel.subscriber_count || 0)}
                        ${channel.country ? `· ${channel.country}` : ''}
                        ${currentCategoryId === 0 && channel.category_name ? `· <span class="category-badge">${escapeHtml(channel.category_name)}</span>` : ''}
                    </div>
                </div>
                <div class="channel-actions">
                    <select class="category-move-select" onchange="moveChannelCategory(${channel.id}, this.value)" title="카테고리 이동">
                        <option value="">이동...</option>
                    </select>
                    <button class="btn-refresh-channel" onclick="refreshChannelInfo(${channel.id})" title="채널 정보 새로고침">🔄</button>
                    <label class="toggle-switch">
                        <input type="checkbox"
                               ${channel.is_active ? 'checked' : ''}
                               onchange="toggleChannelActive(${channel.id})">
                        <span class="toggle-slider"></span>
                    </label>
                    <button class="btn-delete-channel" onclick="deleteChannel(${channel.id})">삭제</button>
                </div>
            `;
            channelsList.appendChild(card);

            // 카테고리 옵션 동적 로드
            loadCategoryOptions(card.querySelector('.category-move-select'), channel.category_id);
        });

        // 탭 개수 업데이트
        await refreshTabCounts();

        // 일괄 이동 카테고리 옵션 로드
        await loadBulkMoveCategoryOptions();

        // 전체 선택 체크박스 상태 업데이트
        updateSelectAllCheckbox();
    } catch (error) {
        console.error('채널 로드 실패:', error);
    }
}

async function refreshTabCounts() {
    try {
        const response = await fetch('/api/categories/');
        const data = await response.json();
        updateTabCounts(data.categories, data.total_count);
    } catch (error) {
        console.error('탭 개수 업데이트 실패:', error);
    }
}

async function loadCategoryOptions(selectElement, currentCategoryId) {
    try {
        const response = await fetch('/api/categories/');
        const data = await response.json();

        data.categories.forEach(category => {
            if (category.id !== currentCategoryId) {
                const option = document.createElement('option');
                option.value = category.id;
                option.textContent = category.name;
                selectElement.appendChild(option);
            }
        });
    } catch (error) {
        console.error('카테고리 옵션 로드 실패:', error);
    }
}

async function moveChannelCategory(channelId, newCategoryId) {
    if (!newCategoryId) return;

    try {
        const response = await fetch(`/api/channels/${channelId}/move_category`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_category_id: parseInt(newCategoryId) })
        });

        if (response.ok) {
            loadChannels();
        } else {
            const error = await response.json();
            let errorMsg = '채널 이동 실패';
            if (typeof error.detail === 'string') {
                errorMsg = error.detail;
            } else if (Array.isArray(error.detail)) {
                errorMsg = error.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
            } else if (error.detail) {
                errorMsg = JSON.stringify(error.detail);
            }
            console.error('채널 이동 실패:', error);
            alert('채널 이동 실패: ' + errorMsg);
        }
    } catch (error) {
        console.error('채널 이동 실패:', error);
        alert('채널 이동에 실패했습니다.');
    }
}

function openAddChannelModal() {
    document.getElementById('addChannelModal').classList.add('active');
    // 기본적으로 수동 입력 탭 표시
    switchUploadTab('manual');
}

function closeAddChannelModal() {
    document.getElementById('addChannelModal').classList.remove('active');
    document.getElementById('channelInput').value = '';
    document.getElementById('mdFileInput').value = '';
    document.getElementById('filePreview').style.display = 'none';
}

function switchUploadTab(tabName) {
    // 탭 버튼 활성화
    document.querySelectorAll('.upload-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    event?.target?.classList.add('active') ||
        document.querySelector(`.upload-tab:${tabName === 'manual' ? 'first' : 'last'}-child`)?.classList.add('active');

    // 탭 콘텐츠 표시
    document.getElementById('manualInputTab').classList.remove('active');
    document.getElementById('fileUploadTab').classList.remove('active');

    if (tabName === 'manual') {
        document.getElementById('manualInputTab').classList.add('active');
    } else {
        document.getElementById('fileUploadTab').classList.add('active');
    }
}

async function addChannels() {
    const apiKeyInput = document.getElementById('apiKey');
    apiKey = apiKeyInput.value.trim();

    if (!apiKey) {
        alert('YouTube API Key를 입력하세요.');
        apiKeyInput.focus();
        closeAddChannelModal();
        return;
    }

    saveApiKey(apiKey);

    const channelInput = document.getElementById('channelInput').value.trim();
    const channelInputs = channelInput
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

    if (channelInputs.length === 0) {
        alert('채널을 입력하세요.');
        return;
    }

    showLoading(true, false);

    try {
        const response = await fetch('/api/channels/bulk_upsert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category_id: currentCategoryId,
                channel_inputs: channelInputs,
                api_key: apiKey
            })
        });

        const result = await response.json();

        if (result.success > 0) {
            alert(`${result.success}개 채널이 추가되었습니다.${result.failed > 0 ? `\n실패: ${result.failed}개` : ''}`);
            closeAddChannelModal();
            loadChannels();
        } else {
            alert('채널 추가에 실패했습니다.\n' + (result.errors || []).map(e => e.error).join('\n'));
        }
    } catch (error) {
        console.error('채널 추가 실패:', error);
        alert('채널 추가에 실패했습니다.');
    } finally {
        showLoading(false);
    }
}

async function toggleChannelActive(channelId) {
    try {
        const response = await fetch(`/api/channels/${channelId}/toggle_active`, {
            method: 'PUT'
        });

        if (response.ok) {
            loadChannels();
        } else {
            alert('채널 상태 변경에 실패했습니다.');
        }
    } catch (error) {
        console.error('채널 상태 변경 실패:', error);
        alert('채널 상태 변경에 실패했습니다.');
    }
}

function toggleChannelSelection(channelId, isChecked) {
    const id = parseInt(channelId);
    if (isChecked) {
        selectedChannelIds.add(id);
    } else {
        selectedChannelIds.delete(id);
    }
    updateBulkMoveUI();
    updateSelectAllCheckbox();
}

function toggleSelectAll(isChecked) {
    const checkboxes = document.querySelectorAll('.channel-select-checkbox');

    checkboxes.forEach(checkbox => {
        const channelId = parseInt(checkbox.dataset.channelId);
        checkbox.checked = isChecked;

        if (isChecked) {
            selectedChannelIds.add(channelId);
        } else {
            selectedChannelIds.delete(channelId);
        }
    });

    updateBulkMoveUI();
}

function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('selectAllChannels');
    const checkboxes = document.querySelectorAll('.channel-select-checkbox');

    if (checkboxes.length === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
        return;
    }

    const checkedCount = selectedChannelIds.size;

    if (checkedCount === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    } else if (checkedCount === checkboxes.length) {
        selectAllCheckbox.checked = true;
        selectAllCheckbox.indeterminate = false;
    } else {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = true;
    }
}

function updateBulkMoveUI() {
    const bulkMoveContainer = document.getElementById('bulkMoveContainer');
    const selectedCount = document.getElementById('selectedChannelCount');

    if (bulkMoveContainer && selectedCount) {
        if (selectedChannelIds.size > 0) {
            bulkMoveContainer.style.display = 'flex';
            selectedCount.textContent = selectedChannelIds.size;
        } else {
            bulkMoveContainer.style.display = 'none';
        }
    }
}

async function loadBulkMoveCategoryOptions() {
    try {
        const response = await fetch('/api/categories/');
        const data = await response.json();

        const select = document.getElementById('bulkMoveCategorySelect');
        if (!select) {
            console.error('bulkMoveCategorySelect element not found');
            return;
        }

        // 기존 옵션 제거 (첫 번째 옵션은 유지)
        while (select.options.length > 1) {
            select.remove(1);
        }

        // 카테고리 옵션 추가 (전체 탭(0)이 아닌 경우 현재 카테고리 제외)
        data.categories.forEach(category => {
            // 전체 탭(0)이거나 현재 카테고리가 아닌 경우만 추가
            if (currentCategoryId === 0 || category.id !== currentCategoryId) {
                const option = document.createElement('option');
                option.value = category.id;
                option.textContent = category.name;
                select.appendChild(option);
            }
        });

        console.log(`Bulk move options loaded: ${select.options.length - 1} categories`);
    } catch (error) {
        console.error('카테고리 옵션 로드 실패:', error);
    }
}

async function bulkMoveChannels() {
    console.log('bulkMoveChannels called, selected:', selectedChannelIds.size);

    if (selectedChannelIds.size === 0) {
        alert('이동할 채널을 선택하세요.');
        return;
    }

    const categorySelect = document.getElementById('bulkMoveCategorySelect');
    if (!categorySelect) {
        console.error('bulkMoveCategorySelect not found');
        alert('카테고리 선택 상자를 찾을 수 없습니다.');
        return;
    }

    const newCategoryId = parseInt(categorySelect.value);
    console.log('Selected category ID:', newCategoryId);

    if (!newCategoryId || isNaN(newCategoryId)) {
        alert('이동할 카테고리를 선택하세요.');
        return;
    }

    const channelIdsArray = Array.from(selectedChannelIds);
    console.log('Moving channels:', channelIdsArray, 'to category:', newCategoryId);

    // 디버깅: 전송할 데이터 확인
    const requestData = {
        channel_ids: channelIdsArray,
        new_category_id: newCategoryId
    };
    console.log('Request data:', JSON.stringify(requestData, null, 2));
    console.log('Channel IDs types:', channelIdsArray.map(id => typeof id));
    console.log('Category ID type:', typeof newCategoryId);

    try {
        const response = await fetch('/api/channels/bulk/move_category', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();
        console.log('Bulk move response:', response.status, result);

        if (response.ok) {
            alert(`${result.moved_count}개의 채널이 이동되었습니다.`);
            clearChannelSelection();
            await loadChannels();
            await refreshTabCounts();
        } else {
            // 에러 메시지 추출 개선
            let errorMsg = '채널 이동 실패';
            if (typeof result.detail === 'string') {
                errorMsg = result.detail;
            } else if (typeof result.message === 'string') {
                errorMsg = result.message;
            } else if (result.detail && typeof result.detail === 'object') {
                errorMsg = JSON.stringify(result.detail);
            } else if (typeof result === 'string') {
                errorMsg = result;
            }
            console.error('Bulk move failed:', result);
            alert('채널 이동 실패: ' + errorMsg);
        }
    } catch (error) {
        console.error('채널 일괄 이동 실패:', error);
        alert('채널 이동에 실패했습니다: ' + error.message);
    }
}

function clearChannelSelection() {
    selectedChannelIds.clear();

    // 모든 체크박스 해제
    document.querySelectorAll('.channel-select-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });

    updateBulkMoveUI();
    updateSelectAllCheckbox();
}

async function bulkDeleteChannels() {
    if (selectedChannelIds.size === 0) {
        alert('삭제할 채널을 선택하세요.');
        return;
    }

    const confirmMessage = `선택한 ${selectedChannelIds.size}개의 채널을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`;
    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const response = await fetch('/api/channels/bulk/delete', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                channel_ids: Array.from(selectedChannelIds)
            })
        });

        const result = await response.json();

        if (response.ok) {
            alert(`${result.deleted_count}개의 채널이 삭제되었습니다.`);
            clearChannelSelection();
            await loadChannels();
            await refreshTabCounts();
        } else {
            const errorMsg = result.detail || result.message || JSON.stringify(result) || '채널 삭제 실패';
            alert(errorMsg);
        }
    } catch (error) {
        console.error('채널 일괄 삭제 실패:', error);
        alert('채널 삭제에 실패했습니다: ' + error.message);
    }
}

async function deleteChannel(channelId) {
    if (!confirm('이 채널을 삭제하시겠습니까?')) {
        return;
    }

    try {
        const response = await fetch(`/api/channels/${channelId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadChannels();
        } else {
            alert('채널 삭제에 실패했습니다.');
        }
    } catch (error) {
        console.error('채널 삭제 실패:', error);
        alert('채널 삭제에 실패했습니다.');
    }
}

async function refreshChannelInfo(channelId) {
    const apiKeyInput = document.getElementById('apiKey');
    const apiKey = apiKeyInput.value.trim();

    if (!apiKey) {
        alert('YouTube API Key를 입력하세요.');
        apiKeyInput.focus();
        return;
    }

    try {
        const response = await fetch(`/api/channels/${channelId}/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });

        if (response.ok) {
            const result = await response.json();
            alert(`채널 정보가 업데이트되었습니다.\n\n제목: ${result.title}\n구독자: ${formatSubscriberCount(result.subscriber_count)}`);
            loadChannels();
        } else {
            const error = await response.json();
            alert(error.detail || '채널 정보 업데이트 실패');
        }
    } catch (error) {
        console.error('채널 정보 업데이트 실패:', error);
        alert('채널 정보 업데이트에 실패했습니다.');
    }
}

async function uploadMdFile() {
    const apiKeyInput = document.getElementById('apiKey');
    apiKey = apiKeyInput.value.trim();

    if (!apiKey) {
        alert('YouTube API Key를 입력하세요.');
        apiKeyInput.focus();
        return;
    }

    const fileInput = document.getElementById('mdFileInput');
    const file = fileInput.files[0];

    if (!file) {
        alert('파일을 선택하세요.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('category_id', currentCategoryId);
    formData.append('api_key', apiKey);

    showLoading(true, false);

    try {
        const response = await fetch('/api/channels/upload_md', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success > 0) {
            alert(`${result.success}개 채널이 추가되었습니다.${result.failed > 0 ? `\n실패: ${result.failed}개` : ''}\n\n발견된 채널: ${result.identifiers_found}개`);
            closeAddChannelModal();
            loadChannels();
        } else {
            alert('채널 추가에 실패했습니다.\n' + (result.errors || []).map(e => e.error).join('\n'));
        }
    } catch (error) {
        console.error('파일 업로드 실패:', error);
        alert('파일 업로드에 실패했습니다.');
    } finally {
        showLoading(false);
    }
}

// 파일 선택 시 미리보기
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('mdFileInput');
    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const identifiers = extractYouTubeIdentifiers(text);

                const preview = document.getElementById('filePreview');
                const urlList = document.getElementById('urlList');
                const urlCountHeader = document.getElementById('urlCountHeader');

                if (identifiers.length > 0) {
                    // 식별자 개수 헤더 업데이트
                    urlCountHeader.textContent = `감지된 YouTube 채널: ${identifiers.length}개`;
                    urlCountHeader.style.color = '#4caf50';

                    // 식별자 목록 표시
                    urlList.innerHTML = identifiers.map(id =>
                        `<div style="font-size: 11px; color: #2196f3; padding: 4px 0; border-bottom: 1px solid #1a1a1a;">${escapeHtml(id)}</div>`
                    ).join('');
                    preview.style.display = 'block';
                } else {
                    preview.style.display = 'none';
                    alert('파일에서 YouTube URL, 채널ID, 핸들을 찾을 수 없습니다.');
                }
            } catch (error) {
                console.error('파일 읽기 오류:', error);
                alert('파일을 읽을 수 없습니다. 지원되는 형식: MD, TXT, CSV, Excel');
            }
        });
    }
});

function extractYouTubeIdentifiers(text) {
    // URL 패턴
    const urlPatterns = [
        /https?:\/\/(?:www\.)?youtube\.com\/channel\/([a-zA-Z0-9_-]+)/g,
        /https?:\/\/(?:www\.)?youtube\.com\/@([a-zA-Z0-9_-]+)/g,
        /https?:\/\/(?:www\.)?youtube\.com\/c\/([a-zA-Z0-9_-]+)/g,
        /https?:\/\/(?:www\.)?youtube\.com\/user\/([a-zA-Z0-9_-]+)/g,
    ];

    // 채널 ID 패턴 (UC로 시작하는 24자)
    const channelIdPattern = /\b(UC[a-zA-Z0-9_-]{22})\b/g;

    // 핸들 패턴 (@로 시작)
    const handlePattern = /@([a-zA-Z0-9_-]+)/g;

    const identifiers = new Set();

    // URL 매칭
    urlPatterns.forEach(pattern => {
        const matches = text.matchAll(pattern);
        for (const match of matches) {
            identifiers.add(match[0]);
        }
    });

    // 채널 ID 매칭
    const channelIdMatches = text.matchAll(channelIdPattern);
    for (const match of channelIdMatches) {
        identifiers.add(match[1]);
    }

    // 핸들 매칭 (URL에 포함되지 않은 경우만)
    const handleMatches = text.matchAll(handlePattern);
    for (const match of handleMatches) {
        const fullMatch = match[0];
        // URL에 이미 포함되지 않은 경우만 추가
        let isInUrl = false;
        for (const id of identifiers) {
            if (id.includes(fullMatch)) {
                isInUrl = true;
                break;
            }
        }
        if (!isInUrl) {
            identifiers.add(fullMatch);
        }
    }

    return Array.from(identifiers);
}

// ========================================
// 검색 및 영상 수집
// ========================================

let searchAbortController = null;

async function searchVideos() {
    // API Key 확인
    const apiKeyInput = document.getElementById('apiKey');
    apiKey = apiKeyInput.value.trim();

    if (!apiKey) {
        alert('YouTube API Key를 입력하세요.');
        apiKeyInput.focus();
        return;
    }

    // API Key 저장
    saveApiKey(apiKey);

    const maxVideos = parseInt(document.getElementById('maxVideos').value) || 50;

    // 이전 검색이 진행 중이면 중지
    if (searchAbortController) {
        searchAbortController.abort();
    }

    // 새로운 AbortController 생성
    searchAbortController = new AbortController();

    // 로딩 시작
    showLoading(true, true); // 중지 버튼 표시

    try {
        // DB에 저장된 활성 채널들로부터 영상 검색
        const searchResponse = await fetch('/api/search/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category_id: currentCategoryId,
                api_key: apiKey,
                max_videos: maxVideos,
                min_views_man: parseInt(document.getElementById('minViews').value) || 0,
                sort: document.getElementById('sortBy').value
            }),
            signal: searchAbortController.signal
        });

        const searchResult = await searchResponse.json();

        if (!searchResponse.ok) {
            throw new Error(searchResult.detail || '검색 실패');
        }

        currentVideos = searchResult.videos || [];

        // 결과 표시
        renderVideoGrid();
        updateResultInfo();

        // 결과 옵션 표시
        document.getElementById('resultOptions').style.display = 'flex';

        // 에러가 있으면 로딩 화면에 표시
        if (searchResult.errors && searchResult.errors.length > 0) {
            console.warn('일부 채널에서 오류 발생:', searchResult.errors);
            displayLoadingErrors(searchResult.errors);
        }

        if (currentVideos.length === 0 && (!searchResult.errors || searchResult.errors.length === 0)) {
            alert('검색 결과가 없습니다.\n활성화된 채널이 있는지 확인하세요.');
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('검색이 사용자에 의해 중지되었습니다.');
            updateLoadingMessage('검색이 중지되었습니다.');
        } else {
            console.error('검색 실패:', error);
            displayLoadingErrors([{ channel_title: '시스템', error: error.message }]);
            alert('검색에 실패했습니다.\n' + error.message);
        }
    } finally {
        searchAbortController = null;
        showLoading(false);
    }
}

function abortSearch() {
    if (searchAbortController) {
        searchAbortController.abort();
        updateLoadingMessage('검색 중지 중...');
    }
}

async function applyFilters() {
    showLoading(true, false);

    try {
        const response = await fetch(
            `/api/search/videos?category_id=${currentCategoryId}` +
            `&min_views_man=${parseInt(document.getElementById('minViews').value) || 0}` +
            `&sort=${document.getElementById('sortBy').value}`
        );

        const data = await response.json();
        currentVideos = data.videos || [];

        renderVideoGrid();
        updateResultInfo();

    } catch (error) {
        console.error('필터 적용 실패:', error);
    } finally {
        showLoading(false);
    }
}

function clearSearchResults() {
    currentVideos = [];
    selectedVideoIds.clear();
    renderVideoGrid();
    updateResultInfo();

    // 결과 옵션 숨김
    document.getElementById('resultOptions').style.display = 'none';
}

// ========================================
// 비디오 그리드 렌더링
// ========================================

function renderVideoGrid() {
    const grid = document.getElementById('videoGrid');

    if (currentVideos.length === 0) {
        grid.innerHTML = '<p class="text-center" style="grid-column: 1 / -1; color: #999;">검색 결과가 없습니다.</p>';
        return;
    }

    grid.innerHTML = '';

    currentVideos.forEach(video => {
        const card = createVideoCard(video);
        grid.appendChild(card);
    });
}

function createVideoCard(video) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.dataset.videoId = video.video_id;

    if (selectedVideoIds.has(video.video_id)) {
        card.classList.add('selected');
    }

    // 조회수 포맷팅
    const viewCount = formatViewCount(video.view_count);

    // 날짜 포맷팅
    const publishedDate = formatDate(video.published_at);

    // 썸네일 div 생성
    const thumbnailDiv = document.createElement('div');
    thumbnailDiv.className = 'video-thumbnail';
    thumbnailDiv.style.position = 'relative';
    thumbnailDiv.style.cursor = 'pointer';

    const thumbnailImg = document.createElement('img');
    thumbnailImg.src = video.thumbnail_url;
    thumbnailImg.alt = video.title;
    thumbnailImg.loading = 'lazy';

    // 재생 버튼 오버레이
    const playButton = document.createElement('div');
    playButton.style.cssText = `
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 48px;
        height: 48px;
        background: rgba(0, 0, 0, 0.7);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
    `;
    playButton.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
            <path d="M8 5v14l11-7z"/>
        </svg>
    `;

    thumbnailDiv.appendChild(thumbnailImg);
    thumbnailDiv.appendChild(playButton);
    thumbnailDiv.onclick = () => openVideoPlayer(video.video_id, video.title);

    // 비디오 정보
    const videoInfo = document.createElement('div');
    videoInfo.className = 'video-info';
    videoInfo.innerHTML = `
        <div class="video-title">${escapeHtml(video.title)}</div>
        <div class="video-meta">
            <span>조회수 ${viewCount}</span>
            <span>${escapeHtml(video.channel_title || '')}</span>
            <span>${publishedDate}</span>
        </div>
    `;

    // YouTube 링크 버튼 추가
    const videoActions = document.createElement('div');
    videoActions.style.cssText = 'padding: 8px; display: flex; gap: 8px; align-items: center;';

    const youtubeLink = document.createElement('a');
    youtubeLink.href = `https://www.youtube.com/watch?v=${video.video_id}`;
    youtubeLink.target = '_blank';
    youtubeLink.style.cssText = 'color: #2196f3; font-size: 12px; text-decoration: none;';
    youtubeLink.textContent = 'YouTube에서 열기 ↗';
    videoActions.appendChild(youtubeLink);

    // 체크박스
    const videoToggle = document.createElement('div');
    videoToggle.className = 'video-toggle';
    videoToggle.innerHTML = `
        <div class="toggle-checkbox">
            <input type="checkbox" id="toggle-${video.video_id}"
                   ${selectedVideoIds.has(video.video_id) ? 'checked' : ''}
                   onchange="toggleVideoSelection('${video.video_id}')">
            <label for="toggle-${video.video_id}">영상추출</label>
        </div>
    `;

    card.appendChild(thumbnailDiv);
    card.appendChild(videoInfo);
    card.appendChild(videoActions);
    card.appendChild(videoToggle);

    return card;
}

function toggleVideoSelection(videoId) {
    if (selectedVideoIds.has(videoId)) {
        selectedVideoIds.delete(videoId);
    } else {
        selectedVideoIds.add(videoId);
    }

    // 카드 스타일 업데이트
    const card = document.querySelector(`[data-video-id="${videoId}"]`);
    if (card) {
        card.classList.toggle('selected');
    }

    updateResultInfo();
}

function updateResultInfo() {
    document.getElementById('resultCount').textContent = `${currentVideos.length}개 영상`;

    const selectedCountEl = document.getElementById('selectedCount');
    const downloadBtn = document.getElementById('btnDownload');

    if (selectedVideoIds.size > 0) {
        selectedCountEl.textContent = `${selectedVideoIds.size}개 선택`;
        selectedCountEl.style.display = 'block';
        downloadBtn.style.display = 'block';
    } else {
        selectedCountEl.style.display = 'none';
        downloadBtn.style.display = 'none';
    }
}

// ========================================
// 다운로드
// ========================================

async function downloadSelected() {
    if (selectedVideoIds.size === 0) {
        alert('다운로드할 영상을 선택하세요.');
        return;
    }

    const videoIds = Array.from(selectedVideoIds);
    const modal = document.getElementById('downloadModal');
    const statusEl = document.getElementById('downloadStatus');
    const progressFill = document.getElementById('progressFill');
    const resultsEl = document.getElementById('downloadResults');

    // 모달 열기
    modal.classList.add('active');
    statusEl.textContent = '다운로드 시작 중...';
    progressFill.style.width = '0%';
    resultsEl.innerHTML = '';

    try {
        const response = await fetch('/api/downloads/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_ids: videoIds })
        });

        const result = await response.json();

        // 진행률 업데이트
        const successRate = (result.success / result.total) * 100;
        progressFill.style.width = '100%';
        statusEl.textContent = `완료: ${result.success}개 / 실패: ${result.failed}개`;

        // 결과 표시
        result.results.forEach(item => {
            const resultItem = document.createElement('div');
            resultItem.className = `download-result-item ${item.status}`;
            resultItem.innerHTML = `
                <strong>${escapeHtml(item.video_title || item.video_id)}</strong><br>
                ${item.status === 'done' ? '✓ 다운로드 완료' : `✗ 실패: ${item.error}`}
            `;
            resultsEl.appendChild(resultItem);
        });

        // 3초 후 자동 닫기 (성공 시)
        if (result.failed === 0) {
            setTimeout(() => {
                modal.classList.remove('active');
            }, 3000);
        }

    } catch (error) {
        console.error('다운로드 실패:', error);
        statusEl.textContent = '다운로드 중 오류가 발생했습니다.';
        alert('다운로드에 실패했습니다.');
    }
}

function closeDownloadModal() {
    const modal = document.getElementById('downloadModal');
    modal.classList.remove('active');
}

// ========================================
// API Key 관리
// ========================================

function openApiKeyModal() {
    loadApiKeys();
    document.getElementById('apiKeyModal').classList.add('active');
}

function closeApiKeyModal() {
    document.getElementById('apiKeyModal').classList.remove('active');
}

async function loadApiKeys() {
    try {
        const response = await fetch('/api/api_keys/');
        const data = await response.json();

        const apiKeyList = document.getElementById('apiKeyList');
        apiKeyList.innerHTML = '';

        if (data.api_keys.length === 0) {
            apiKeyList.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">등록된 API 키가 없습니다.</p>';
            return;
        }

        data.api_keys.forEach(apiKey => {
            const item = document.createElement('div');
            item.className = 'category-item';

            // 날짜 포맷팅
            const createdDate = new Date(apiKey.created_at).toLocaleDateString('ko-KR');

            // 상태 표시
            let statusBadge = '';
            if (apiKey.quota_exceeded) {
                statusBadge = '<span style="color: #f44336; font-size: 12px; margin-left: 8px;">⚠ 쿼터 초과</span>';
            } else if (!apiKey.is_active) {
                statusBadge = '<span style="color: #999; font-size: 12px; margin-left: 8px;">비활성</span>';
            } else {
                statusBadge = '<span style="color: #4caf50; font-size: 12px; margin-left: 8px;">✓ 활성</span>';
            }

            item.innerHTML = `
                <div>
                    <div class="category-item-name">
                        ${apiKey.api_key}
                        ${statusBadge}
                    </div>
                    <div style="font-size: 11px; color: #666; margin-top: 4px;">
                        ${apiKey.name ? apiKey.name + ' · ' : ''}${createdDate}
                        ${apiKey.last_used_at ? ' · 마지막 사용: ' + formatDate(apiKey.last_used_at) : ''}
                    </div>
                </div>
                <div class="category-item-actions">
                    ${apiKey.quota_exceeded ? `
                        <button class="btn-edit" onclick="resetQuota(${apiKey.id})">쿼터 초기화</button>
                    ` : ''}
                    <button class="btn-delete" onclick="deleteApiKey(${apiKey.id})">삭제</button>
                </div>
            `;
            apiKeyList.appendChild(item);
        });
    } catch (error) {
        console.error('API 키 로드 실패:', error);
        alert('API 키를 불러오는데 실패했습니다.');
    }
}

async function addApiKey() {
    const keyInput = document.getElementById('newApiKey');
    const nameInput = document.getElementById('newApiKeyName');
    const key = keyInput.value.trim();
    const name = nameInput.value.trim();

    if (!key) {
        alert('API 키를 입력하세요.');
        return;
    }

    try {
        const response = await fetch('/api/api_keys/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: key,
                name: name || null,
                priority: 0
            })
        });

        if (response.ok) {
            keyInput.value = '';
            nameInput.value = '';
            loadApiKeys();

            // 첫 번째 API 키라면 자동으로 입력란에 설정
            const data = await response.json();
            if (!apiKey) {
                document.getElementById('apiKey').value = key;
                apiKey = key;
            }
        } else {
            const error = await response.json();
            alert(error.detail || 'API 키 추가 실패');
        }
    } catch (error) {
        console.error('API 키 추가 실패:', error);
        alert('API 키 추가에 실패했습니다.');
    }
}

async function deleteApiKey(id) {
    if (!confirm('이 API 키를 삭제하시겠습니까?')) {
        return;
    }

    try {
        const response = await fetch(`/api/api_keys/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadApiKeys();
        } else {
            const error = await response.json();
            alert(error.detail || 'API 키 삭제 실패');
        }
    } catch (error) {
        console.error('API 키 삭제 실패:', error);
        alert('API 키 삭제에 실패했습니다.');
    }
}

async function resetQuota(id) {
    try {
        const response = await fetch(`/api/api_keys/${id}/reset_quota`, {
            method: 'POST'
        });

        if (response.ok) {
            loadApiKeys();
            alert('쿼터가 초기화되었습니다.');
        } else {
            const error = await response.json();
            alert(error.detail || '쿼터 초기화 실패');
        }
    } catch (error) {
        console.error('쿼터 초기화 실패:', error);
        alert('쿼터 초기화에 실패했습니다.');
    }
}

async function loadApiKey() {
    try {
        const response = await fetch('/api/api_keys/active');
        const data = await response.json();

        if (data.api_key && data.api_key.api_key) {
            document.getElementById('apiKey').value = data.api_key.api_key;
            apiKey = data.api_key.api_key;
        }
    } catch (error) {
        console.error('API Key 로드 실패:', error);
        // 사용 가능한 API 키가 없어도 무시
    }
}

async function saveApiKey(key) {
    // 이 함수는 더 이상 사용되지 않음 (DB에 직접 저장하므로)
    // 하지만 기존 코드와의 호환성을 위해 남겨둠
}

// ========================================
// 유틸리티
// ========================================

function showLoading(show, showAbortButton = false) {
    const loading = document.getElementById('loading');
    const abortBtn = document.getElementById('btnAbort');
    const loadingErrors = document.getElementById('loadingErrors');
    const loadingMessage = document.getElementById('loadingMessage');

    if (show) {
        loading.style.display = 'block';
        abortBtn.style.display = showAbortButton ? 'inline-block' : 'none';
        loadingErrors.innerHTML = '';
        loadingMessage.textContent = '로딩 중...';
    } else {
        loading.style.display = 'none';
        abortBtn.style.display = 'none';
    }
}

function updateLoadingMessage(message) {
    const loadingMessage = document.getElementById('loadingMessage');
    if (loadingMessage) {
        loadingMessage.textContent = message;
    }
}

function displayLoadingErrors(errors) {
    const loadingErrors = document.getElementById('loadingErrors');
    if (!loadingErrors || !errors || errors.length === 0) return;

    loadingErrors.innerHTML = '';

    errors.forEach(error => {
        const errorItem = document.createElement('div');
        errorItem.className = 'loading-error-item';
        errorItem.innerHTML = `
            <div class="error-channel">${escapeHtml(error.channel_title || '알 수 없는 채널')}</div>
            <div class="error-message">${escapeHtml(error.error)}</div>
        `;
        loadingErrors.appendChild(errorItem);
    });

    // 에러가 있으면 3초 후 자동으로 닫지 않고 사용자가 확인할 수 있도록 유지
    updateLoadingMessage(`검색 완료 (${errors.length}개 오류 발생)`);
}

function openYouTube(videoId) {
    window.open(`https://www.youtube.com/watch?v=${videoId}`, '_blank');
}

function openVideoPlayer(videoId, videoTitle) {
    const modal = document.getElementById('videoPlayerModal');
    const iframe = document.getElementById('videoPlayerIframe');
    const title = document.getElementById('videoPlayerTitle');

    // YouTube Shorts는 일반 embed URL 사용
    iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
    title.textContent = videoTitle || '영상 재생';

    modal.classList.add('active');
}

function closeVideoPlayer() {
    const modal = document.getElementById('videoPlayerModal');
    const iframe = document.getElementById('videoPlayerIframe');

    // iframe 소스를 비워서 재생 중지
    iframe.src = '';
    modal.classList.remove('active');
}

function formatViewCount(count) {
    if (count >= 100000000) {
        return `${(count / 100000000).toFixed(1)}억`;
    } else if (count >= 10000) {
        return `${(count / 10000).toFixed(1)}만`;
    } else if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}천`;
    } else {
        return count.toString();
    }
}

function formatSubscriberCount(count) {
    if (count >= 10000000) {
        return `${(count / 10000000).toFixed(0)}천만`;
    } else if (count >= 10000) {
        return `${(count / 10000).toFixed(1)}만`;
    } else if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}천`;
    } else {
        return count.toString();
    }
}

function formatDate(dateString) {
    if (!dateString) return '';

    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(days / 365);

    if (years > 0) return `${years}년 전`;
    if (months > 0) return `${months}개월 전`;
    if (days > 0) return `${days}일 전`;
    if (hours > 0) return `${hours}시간 전`;
    if (minutes > 0) return `${minutes}분 전`;
    return '방금 전';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 모달 외부 클릭 시 닫기
window.addEventListener('click', function(event) {
    const categoryModal = document.getElementById('categoryModal');
    const apiKeyModal = document.getElementById('apiKeyModal');
    const downloadModal = document.getElementById('downloadModal');
    const videoPlayerModal = document.getElementById('videoPlayerModal');

    if (event.target === categoryModal) {
        closeCategoryModal();
    }

    if (event.target === apiKeyModal) {
        closeApiKeyModal();
    }

    if (event.target === videoPlayerModal) {
        closeVideoPlayer();
    }

    // 다운로드 모달은 외부 클릭으로 안 닫히게
});
