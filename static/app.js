document.addEventListener('DOMContentLoaded', () => {
    const songsInput = document.getElementById('songsInput');
    const songCountBadge = document.getElementById('songCountBadge');
    const bitrateSelect = document.getElementById('bitrateSelect');
    const concurrencySelect = document.getElementById('concurrencySelect');
    const prefixCheckbox = document.getElementById('prefixCheckbox');
    const folderInput = document.getElementById('folderInput');
    const btnOpenFolder = document.getElementById('btnOpenFolder');
    const btnOpenDownloadsFolder = document.getElementById('btnOpenDownloadsFolder');
    const btnStartDownload = document.getElementById('btnStartDownload');
    const btnSample = document.getElementById('btnSample');
    const btnPaste = document.getElementById('btnPaste');
    const btnClear = document.getElementById('btnClear');
    const btnCancelDownload = document.getElementById('btnCancelDownload');

    const progressCard = document.getElementById('progressCard');
    const overallStatusTitle = document.getElementById('overallStatusTitle');
    const overallStatusSub = document.getElementById('overallStatusSub');
    const overallProgressFill = document.getElementById('overallProgressFill');
    const overallProgressStats = document.getElementById('overallProgressStats');
    const overallPercent = document.getElementById('overallPercent');
    const queueList = document.getElementById('queueList');

    // Cloud Banner Elements
    const cloudBanner = document.getElementById('cloudBanner');
    const backendUrlInput = document.getElementById('backendUrlInput');
    const btnSaveBackend = document.getElementById('btnSaveBackend');
    const backendStatusTag = document.getElementById('backendStatusTag');

    let currentJobId = null;
    let eventSource = null;
    let totalSongs = 0;
    let completedSongs = 0;

    // Detect if running on Cloud/Netlify or Localhost
    const isCloudHost = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    let API_BASE = '';

    if (isCloudHost) {
        if (cloudBanner) cloudBanner.style.display = 'flex';
        const savedBackend = localStorage.getItem('mp3_backend_url') || '';
        API_BASE = savedBackend.replace(/\/+$/, '');
        if (backendUrlInput) backendUrlInput.value = API_BASE;
        checkBackendStatus(API_BASE);

        if (btnSaveBackend) {
            btnSaveBackend.addEventListener('click', () => {
                const url = (backendUrlInput.value || '').trim().replace(/\/+$/, '');
                localStorage.setItem('mp3_backend_url', url);
                API_BASE = url;
                checkBackendStatus(API_BASE);
            });
        }
    } else {
        if (cloudBanner) cloudBanner.style.display = 'none';
        API_BASE = '';
        loadConfig();
    }

    async function checkBackendStatus(url) {
        if (!backendStatusTag) return;
        backendStatusTag.className = 'status-tag';
        backendStatusTag.textContent = 'Testing connection...';

        const endpoint = (url ? url : '') + '/api/config';
        try {
            const res = await fetch(endpoint);
            if (res.ok) {
                const data = await res.json();
                backendStatusTag.className = 'status-tag connected';
                backendStatusTag.textContent = '🟢 Connected';
                if (data.default_folder && folderInput) {
                    folderInput.value = data.default_folder;
                }
            } else {
                throw new Error('Not OK');
            }
        } catch (e) {
            backendStatusTag.className = 'status-tag disconnected';
            backendStatusTag.textContent = '🔴 Disconnected (Start backend)';
        }
    }

    const btnResetFolder = document.getElementById('btnResetFolder');
    let defaultFolderValue = '';

    function loadConfig() {
        fetch(`${API_BASE}/api/config`)
            .then(res => res.json())
            .then(data => {
                if (data.default_folder) {
                    defaultFolderValue = data.default_folder;
                    if (folderInput && !folderInput.value) {
                        folderInput.value = data.default_folder;
                    }
                }
            })
            .catch(err => console.warn('Config load notice:', err));
    }

    if (btnResetFolder) {
        btnResetFolder.addEventListener('click', () => {
            if (folderInput) {
                folderInput.value = defaultFolderValue;
            }
        });
    }

    // Song counter
    function updateSongCount() {
        const songs = getCleanedSongsList();
        songCountBadge.textContent = `${songs.length} song${songs.length === 1 ? '' : 's'} detected`;
    }

    function getCleanedSongsList() {
        return songsInput.value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s.length > 0);
    }

    songsInput.addEventListener('input', updateSongCount);

    // Load samples
    btnSample.addEventListener('click', () => {
        songsInput.value = [
            "Imagine Dragons - Believer",
            "Arijit Singh - Kesariya",
            "Alan Walker - Faded",
            "Diljit Dosanjh - Lover"
        ].join('\n');
        updateSongCount();
        songsInput.focus();
    });

    // Paste clipboard
    btnPaste.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                if (songsInput.value.trim().length > 0) {
                    songsInput.value += '\n' + text.trim();
                } else {
                    songsInput.value = text.trim();
                }
                updateSongCount();
            }
        } catch (e) {
            alert('Please allow clipboard access or paste directly into the box.');
        }
    });

    // Clear box
    btnClear.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear the songs list?')) {
            songsInput.value = '';
            updateSongCount();
        }
    });

    // Open folder in Windows explorer
    async function triggerOpenFolder() {
        const folder = folderInput.value.trim();
        try {
            await fetch(`${API_BASE}/api/open-folder`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder: folder })
            });
        } catch (e) {
            console.error('Failed to open folder:', e);
        }
    }

    const btnBrowseFolder = document.getElementById('btnBrowseFolder');
    if (btnBrowseFolder) {
        btnBrowseFolder.addEventListener('click', async () => {
            btnBrowseFolder.disabled = true;
            btnBrowseFolder.textContent = '⏳ Picking...';
            try {
                const res = await fetch(`${API_BASE}/api/browse-folder`, { method: 'POST' });
                const data = await res.json();
                if (data.folder && folderInput) {
                    folderInput.value = data.folder;
                }
            } catch (e) {
                console.warn('Browse folder failed:', e);
            } finally {
                btnBrowseFolder.disabled = false;
                btnBrowseFolder.innerHTML = '📁 Browse';
            }
        });
    }

    btnOpenFolder.addEventListener('click', triggerOpenFolder);
    btnOpenDownloadsFolder.addEventListener('click', triggerOpenFolder);

    // Cancel download
    btnCancelDownload.addEventListener('click', async () => {
        if (!currentJobId) return;
        if (confirm('Cancel remaining downloads?')) {
            btnCancelDownload.disabled = true;
            btnCancelDownload.textContent = 'Cancelling...';
            try {
                await fetch(`${API_BASE}/api/cancel/${currentJobId}`, { method: 'POST' });
            } catch (e) {
                console.error('Failed to cancel:', e);
            }
        }
    });

    // Start download process
    btnStartDownload.addEventListener('click', async () => {
        const songs = getCleanedSongsList();
        if (songs.length === 0) {
            alert('Please add at least one song name or YouTube URL in the box.');
            songsInput.focus();
            return;
        }

        const targetFolder = (folderInput.value || '').trim();
        if (targetFolder.startsWith('http://') || targetFolder.startsWith('https://')) {
            alert('Kripya valid local folder path dalein (jaise C:\\Downloads ya E:\\Music). Web links folder path ke roop me valid nahi hain.');
            folderInput.focus();
            return;
        }

        totalSongs = songs.length;
        completedSongs = 0;

        // UI Reset
        btnStartDownload.disabled = true;
        btnStartDownload.innerHTML = `<span class="spinner"></span> <span>Preparing Downloads...</span>`;
        btnCancelDownload.disabled = false;
        btnCancelDownload.innerHTML = `<span>🛑</span> Cancel`;

        progressCard.style.display = 'block';
        progressCard.scrollIntoView({ behavior: 'smooth' });

        overallStatusTitle.textContent = `Downloading ${totalSongs} Songs...`;
        overallStatusSub.textContent = `Processing queue in high quality ${bitrateSelect.value} kbps`;
        updateOverallProgress(0);

        // Populate initial queue list
        queueList.innerHTML = '';
        songs.forEach((song, idx) => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            itemDiv.id = `queue-item-${idx + 1}`;
            itemDiv.innerHTML = `
                <div class="queue-idx">${idx + 1}</div>
                <div class="queue-thumb" id="thumb-${idx + 1}">🎵</div>
                <div class="queue-info">
                    <div class="queue-title" id="title-${idx + 1}">${escapeHtml(song)}</div>
                    <div class="queue-meta" id="meta-${idx + 1}">
                        <span class="status-msg">Waiting in queue...</span>
                    </div>
                    <div class="item-progress-bar-wrap" id="bar-wrap-${idx + 1}" style="display: none;">
                        <div class="item-progress-bar-fill" id="bar-${idx + 1}" style="width: 0%;"></div>
                    </div>
                </div>
                <div class="queue-status-badge status-queued" id="badge-${idx + 1}">Queued</div>
            `;
            queueList.appendChild(itemDiv);
        });

        // Submit API request
        try {
            const concurrencyVal = parseInt(concurrencySelect ? concurrencySelect.value : '5') || 5;
            const addPrefixVal = prefixCheckbox ? prefixCheckbox.checked : true;

            const response = await fetch(`${API_BASE}/api/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    songs: songs,
                    bitrate: bitrateSelect.value,
                    concurrency: concurrencyVal,
                    add_prefix: addPrefixVal,
                    folder: folderInput.value.trim()
                })
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Backend server is not responding. Please check your backend connection.' }));
                throw new Error(err.detail || 'Download request failed');
            }

            const data = await response.json();
            currentJobId = data.job_id;
            listenToProgress(currentJobId);

        } catch (err) {
            alert('Backend Error: ' + err.message + '\n\nNote: If using Netlify, make sure your Python backend is running locally (start_downloader.bat) or deployed to Render.');
            resetDownloadButton();
        }
    });

    function listenToProgress(jobId) {
        if (eventSource) {
            eventSource.close();
        }

        eventSource = new EventSource(`${API_BASE}/api/progress/${jobId}`);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleProgressEvent(data);
        };

        eventSource.onerror = (err) => {
            console.warn('SSE disconnected or complete:', err);
            eventSource.close();
        };
    }

    function handleProgressEvent(data) {
        const idx = data.index;
        const badge = document.getElementById(`badge-${idx}`);
        const meta = document.getElementById(`meta-${idx}`);
        const title = document.getElementById(`title-${idx}`);
        const thumb = document.getElementById(`thumb-${idx}`);
        const barWrap = document.getElementById(`bar-wrap-${idx}`);
        const bar = document.getElementById(`bar-${idx}`);

        switch (data.type) {
            case 'song_start':
                if (badge) {
                    badge.className = 'queue-status-badge status-searching';
                    badge.textContent = 'Searching';
                }
                if (meta) meta.innerHTML = `<span class="status-msg">🔍 Searching on YouTube...</span>`;
                break;

            case 'song_progress':
                if (badge) {
                    badge.className = 'queue-status-badge status-downloading';
                    badge.textContent = `${Math.round(data.percent)}%`;
                }
                if (barWrap) barWrap.style.display = 'block';
                if (bar) bar.style.width = `${data.percent}%`;
                if (meta) {
                    meta.innerHTML = `
                        <span>⬇️ ${data.speed || 'Downloading'}</span>
                        ${data.eta ? `<span>&bull; ETA: ${data.eta}</span>` : ''}
                    `;
                }
                break;

            case 'song_converting':
                if (badge) {
                    badge.className = 'queue-status-badge status-converting';
                    badge.textContent = 'Converting';
                }
                if (barWrap) barWrap.style.display = 'none';
                if (meta) meta.innerHTML = `<span>🎵 Extracting audio to 320kbps MP3...</span>`;
                break;

            case 'song_completed':
                completedSongs++;
                updateOverallProgress((completedSongs / totalSongs) * 100);

                if (badge) {
                    badge.className = 'queue-status-badge status-completed';
                    badge.textContent = 'Saved MP3';
                }
                if (title && (data.filename || data.title)) {
                    title.textContent = data.filename ? data.filename.replace(/\.mp3$/i, '') : data.title;
                }
                if (thumb && data.thumbnail) {
                    thumb.innerHTML = `<img src="${data.thumbnail}" alt="art" onerror="this.parentElement.textContent='🎵'">`;
                }
                if (barWrap) barWrap.style.display = 'none';
                if (meta) {
                    meta.innerHTML = `
                        <span style="color: #34d399;">✅ ${data.filename}</span>
                        ${data.duration ? `<span>&bull; ${data.duration}</span>` : ''}
                    `;
                }
                break;

            case 'song_error':
                completedSongs++;
                updateOverallProgress((completedSongs / totalSongs) * 100);

                if (badge) {
                    badge.className = 'queue-status-badge status-error';
                    badge.textContent = 'Failed';
                }
                if (barWrap) barWrap.style.display = 'none';
                if (meta) {
                    meta.innerHTML = `<span class="text-danger">❌ ${escapeHtml(data.error || 'Failed')}</span>`;
                }
                break;

            case 'job_completed':
                overallStatusTitle.textContent = `🎉 All Downloads Completed!`;
                overallStatusSub.textContent = data.message;
                updateOverallProgress(100);
                resetDownloadButton();
                if (eventSource) eventSource.close();
                break;

            case 'job_cancelled':
                overallStatusTitle.textContent = `⚠️ Download Process Stopped`;
                overallStatusSub.textContent = data.message;
                resetDownloadButton();
                if (eventSource) eventSource.close();
                break;
        }
    }

    function updateOverallProgress(percent) {
        percent = Math.min(100, Math.max(0, percent));
        overallProgressFill.style.width = `${percent}%`;
        overallPercent.textContent = `${Math.round(percent)}%`;
        overallProgressStats.textContent = `${completedSongs} / ${totalSongs} Completed`;
    }

    function resetDownloadButton() {
        btnStartDownload.disabled = false;
        btnStartDownload.innerHTML = `<span class="btn-icon">⚡</span> <span class="btn-text">Download All MP3s</span>`;
        btnCancelDownload.disabled = true;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
});
