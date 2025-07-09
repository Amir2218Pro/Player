// Global variables
let currentVideo = null;
let currentPlaylist = null;
let currentPlaylistIndex = -1;
let allVideos = [];
let playlists = [];
let currentPath = '';
let searchResults = [];
let isSearching = false;
let controlsTimeout;
let isControlsVisible = true;
let currentSort = { by: 'name', order: 'asc' };

// User permissions (set from template)
const permissions = window.userPermissions || {
    can_use_playlists: true,
    can_download: true,
    can_use_subtitles: true
};

// DOM Elements
const videoPlayer = document.getElementById('videoPlayer');
const videoContainer = document.getElementById('videoContainer');
const videoControls = document.getElementById('videoControls');
const playPauseBtn = document.getElementById('playPauseBtn');
const progressBar = document.getElementById('progressBar');
const progressFilled = document.getElementById('progressFilled');
const progressHandle = document.getElementById('progressHandle');
const volumeSlider = document.getElementById('volumeSlider');
const currentTimeSpan = document.getElementById('currentTime');
const durationSpan = document.getElementById('duration');
const fullscreenBtn = document.getElementById('fullscreenBtn');
const videoTitle = document.getElementById('videoTitle');
const videoPath = document.getElementById('videoPath');
const fileList = document.getElementById('fileList');
const breadcrumb = document.getElementById('breadcrumb');
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initializePlayer();
    initializeControls();
    initializeSearch();
    initializeKeyboardShortcuts();
    loadFiles();
    
    // Initialize playlists if user has permission
    if (permissions.can_use_playlists) {
        loadPlaylists();
    }
});

// Player initialization
function initializePlayer() {
    // Video events
    videoPlayer.addEventListener('loadedmetadata', updateDuration);
    videoPlayer.addEventListener('timeupdate', updateProgress);
    videoPlayer.addEventListener('ended', handleVideoEnd);
    videoPlayer.addEventListener('play', () => updatePlayPauseButton(true));
    videoPlayer.addEventListener('pause', () => updatePlayPauseButton(false));
    videoPlayer.addEventListener('waiting', () => showLoading(true));
    videoPlayer.addEventListener('canplay', () => showLoading(false));
    
    // Container events for controls
    videoContainer.addEventListener('mousemove', showControls);
    videoContainer.addEventListener('mouseleave', () => {
        if (!videoPlayer.paused) {
            hideControlsDelayed();
        }
    });
    
    // Click to play/pause
    videoContainer.addEventListener('click', (e) => {
        if (e.target === videoPlayer || e.target === videoContainer) {
            togglePlayPause();
        }
    });
    
    // Prevent controls from hiding when hovering over them
    videoControls.addEventListener('mouseenter', clearControlsTimeout);
    videoControls.addEventListener('mouseleave', () => {
        if (!videoPlayer.paused) {
            hideControlsDelayed();
        }
    });
}

// Controls initialization
function initializeControls() {
    // Play/Pause button
    playPauseBtn.addEventListener('click', togglePlayPause);
    
    // Progress bar
    progressBar.addEventListener('click', seekVideo);
    progressBar.addEventListener('mousedown', startProgressDrag);
    
    // Volume control
    volumeSlider.addEventListener('input', changeVolume);
    document.getElementById('volumeBtn').addEventListener('click', toggleMute);
    
    // Fullscreen
    fullscreenBtn.addEventListener('click', toggleFullscreen);
    
    // Speed control
    document.querySelectorAll('.speed-option').forEach(option => {
        option.addEventListener('click', () => changeSpeed(parseFloat(option.dataset.speed)));
    });
    
    // Next/Previous buttons
    document.getElementById('nextBtn').addEventListener('click', playNext);
    document.getElementById('prevBtn').addEventListener('click', playPrevious);
    
    // Download button
    const downloadBtn = document.getElementById('downloadBtn');
    if (permissions.can_download) {
        downloadBtn.addEventListener('click', downloadCurrentVideo);
    } else {
        downloadBtn.style.display = 'none';
    }
    
    // Playlist buttons
    if (permissions.can_use_playlists) {
        document.getElementById('playlistBtn').addEventListener('click', showPlaylistModal);
        document.getElementById('playlistAddBtn').addEventListener('click', showAddToPlaylistModal);
    }
}

// Controls visibility management
function showControls() {
    clearControlsTimeout();
    videoControls.classList.add('show');
    isControlsVisible = true;
    
    if (!videoPlayer.paused) {
        hideControlsDelayed();
    }
}

function hideControlsDelayed() {
    clearControlsTimeout();
    controlsTimeout = setTimeout(() => {
        if (!videoPlayer.paused && isControlsVisible) {
            videoControls.classList.remove('show');
            isControlsVisible = false;
        }
    }, 3000);
}

function clearControlsTimeout() {
    if (controlsTimeout) {
        clearTimeout(controlsTimeout);
        controlsTimeout = null;
    }
}

// Player controls
function togglePlayPause() {
    if (videoPlayer.paused) {
        videoPlayer.play();
    } else {
        videoPlayer.pause();
    }
}

function updatePlayPauseButton(isPlaying) {
    const playIcon = document.getElementById('playIcon');
    const pauseIcon = document.getElementById('pauseIcon');
    
    if (isPlaying) {
        playIcon.style.display = 'none';
        pauseIcon.style.display = 'block';
        hideControlsDelayed();
    } else {
        playIcon.style.display = 'block';
        pauseIcon.style.display = 'none';
        showControls();
    }
}

function seekVideo(e) {
    const rect = progressBar.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    videoPlayer.currentTime = percent * videoPlayer.duration;
}

function updateProgress() {
    if (videoPlayer.duration) {
        const percent = (videoPlayer.currentTime / videoPlayer.duration) * 100;
        progressFilled.style.width = percent + '%';
        progressHandle.style.left = percent + '%';
        
        currentTimeSpan.textContent = formatTime(videoPlayer.currentTime);
    }
}

function updateDuration() {
    durationSpan.textContent = formatTime(videoPlayer.duration);
}

function changeVolume() {
    videoPlayer.volume = volumeSlider.value;
    updateVolumeIcon();
}

function toggleMute() {
    videoPlayer.muted = !videoPlayer.muted;
    updateVolumeIcon();
}

function updateVolumeIcon() {
    const volumeIcon = document.getElementById('volumeIcon');
    const volume = videoPlayer.muted ? 0 : videoPlayer.volume;
    
    if (volume === 0) {
        volumeIcon.className = 'fas fa-volume-mute';
    } else if (volume < 0.5) {
        volumeIcon.className = 'fas fa-volume-down';
    } else {
        volumeIcon.className = 'fas fa-volume-up';
    }
}

function changeSpeed(speed) {
    videoPlayer.playbackRate = speed;
    document.getElementById('speedText').textContent = speed === 1 ? '1x' : speed + 'x';
    
    // Update active speed option
    document.querySelectorAll('.speed-option').forEach(option => {
        option.classList.toggle('active', parseFloat(option.dataset.speed) === speed);
    });
}

function toggleFullscreen() {
    if (!document.fullscreenElement) {
        videoContainer.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

// Video loading and playing
function loadVideo(videoInfo, playlistInfo = null, playlistIndex = -1) {
    currentVideo = videoInfo;
    currentPlaylist = playlistInfo;
    currentPlaylistIndex = playlistIndex;
    
    videoPlayer.src = videoInfo.url;
    videoTitle.textContent = videoInfo.name;
    videoPath.textContent = videoInfo.path;
    
    // Update active file in list
    updateActiveFile(videoInfo.path);
    
    // Update playlist UI if playing from playlist
    if (currentPlaylist) {
        updatePlaylistUI();
    }
    
    // Load subtitles if available and user has permission
    if (permissions.can_use_subtitles) {
        loadSubtitles(videoInfo.path);
    }
    
    showLoading(true);
}

function updateActiveFile(filePath) {
    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.remove('active');
    });
    
    const activeItem = document.querySelector(`[data-path="${filePath}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
    }
}

function playNext() {
    if (currentPlaylist && currentPlaylistIndex < currentPlaylist.videos.length - 1) {
        // Play next in playlist
        const nextIndex = currentPlaylistIndex + 1;
        const nextVideo = currentPlaylist.videos[nextIndex];
        loadVideo(nextVideo, currentPlaylist, nextIndex);
    } else if (allVideos.length > 0) {
        // Play next in all videos
        const currentIndex = allVideos.findIndex(v => v.path === currentVideo?.path);
        if (currentIndex < allVideos.length - 1) {
            loadVideo(allVideos[currentIndex + 1]);
        }
    }
}

function playPrevious() {
    if (currentPlaylist && currentPlaylistIndex > 0) {
        // Play previous in playlist
        const prevIndex = currentPlaylistIndex - 1;
        const prevVideo = currentPlaylist.videos[prevIndex];
        loadVideo(prevVideo, currentPlaylist, prevIndex);
    } else if (allVideos.length > 0) {
        // Play previous in all videos
        const currentIndex = allVideos.findIndex(v => v.path === currentVideo?.path);
        if (currentIndex > 0) {
            loadVideo(allVideos[currentIndex - 1]);
        }
    }
}

function handleVideoEnd() {
    // Auto-play next video
    playNext();
}

// File browser
async function loadFiles(path = '', sortBy = null, sortOrder = null) {
    try {
        showLoading(true);
        
        // Use current sort if not specified
        if (sortBy) currentSort.by = sortBy;
        if (sortOrder) currentSort.order = sortOrder;
        
        const params = new URLSearchParams({
            path: path,
            sort: currentSort.by,
            order: currentSort.order
        });
        
        const response = await fetch(`/api/browse?${params}`);
        const data = await response.json();
        
        if (response.ok) {
            currentPath = data.current_path;
            renderFiles(data.items);
            updateBreadcrumb(data.current_path, data.parent_path);
            
            // Update all videos list for navigation
            allVideos = [];
            extractVideos(data.items, allVideos);
        } else {
            showNotification(data.error || 'Failed to load files', 'error');
        }
    } catch (error) {
        showNotification('Network error', 'error');
    } finally {
        showLoading(false);
    }
}

function extractVideos(items, videoList) {
    items.forEach(item => {
        if (item.type === 'video' || item.type === 'audio') {
            videoList.push(item);
        } else if (item.type === 'folder' && item.children) {
            extractVideos(item.children, videoList);
        }
    });
}

function renderFiles(items) {
    if (items.length === 0) {
        fileList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-folder-open"></i>
                <p>No files found</p>
            </div>
        `;
        return;
    }
    
    fileList.innerHTML = items.map(item => {
        const isVideo = item.type === 'video' || item.type === 'audio';
        const thumbnail = item.thumbnail ? 
            `<img src="${item.thumbnail}" class="file-thumbnail" alt="Thumbnail">` : 
            '';
        
        return `
            <div class="file-item ${item.thumbnail ? 'has-thumbnail' : ''}" 
                 data-path="${item.path}" 
                 onclick="${item.type === 'folder' ? `navigateToFolder('${item.path}')` : `playFile('${item.path}')`}">
                <div class="file-icon ${item.type}">
                    ${thumbnail || `<i class="fas fa-${getFileIcon(item.type)}"></i>`}
                </div>
                <div class="file-info">
                    <div class="file-name">${item.name}</div>
                    <div class="file-meta">
                        ${formatFileSize(item.size)}
                        ${item.duration ? ` • ${formatTime(item.duration)}` : ''}
                        ${item.type === 'folder' ? ` • ${item.children?.length || 0} items` : ''}
                    </div>
                </div>
                <div class="file-actions">
                    ${isVideo && permissions.can_download ? `
                        <button class="file-action-btn" onclick="event.stopPropagation(); downloadFile('${item.path}')" title="Download">
                            <i class="fas fa-download"></i>
                        </button>
                    ` : ''}
                    ${isVideo && permissions.can_use_playlists ? `
                        <button class="file-action-btn" onclick="event.stopPropagation(); addToPlaylist('${item.path}')" title="Add to Playlist">
                            <i class="fas fa-plus"></i>
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// File sorting
function addSortControls() {
    const browserHeader = document.querySelector('.file-browser-header');
    const sortControls = document.createElement('div');
    sortControls.className = 'sort-controls';
    sortControls.innerHTML = `
        <select id="sortSelect" class="sort-select">
            <option value="name">Name</option>
            <option value="size">Size</option>
            <option value="modified">Modified</option>
            <option value="duration">Duration</option>
            <option value="type">Type</option>
        </select>
        <button id="sortOrderBtn" class="sort-order-btn" title="Sort Order">
            <i class="fas fa-sort-alpha-down"></i>
        </button>
    `;
    
    browserHeader.appendChild(sortControls);
    
    // Event listeners
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        loadFiles(currentPath, e.target.value);
        updateSortIcon();
    });
    
    document.getElementById('sortOrderBtn').addEventListener('click', () => {
        const newOrder = currentSort.order === 'asc' ? 'desc' : 'asc';
        loadFiles(currentPath, currentSort.by, newOrder);
        updateSortIcon();
    });
    
    updateSortIcon();
}

function updateSortIcon() {
    const sortOrderBtn = document.getElementById('sortOrderBtn');
    const sortSelect = document.getElementById('sortSelect');
    
    if (sortOrderBtn && sortSelect) {
        sortSelect.value = currentSort.by;
        
        const icon = sortOrderBtn.querySelector('i');
        if (currentSort.order === 'asc') {
            icon.className = 'fas fa-sort-alpha-down';
        } else {
            icon.className = 'fas fa-sort-alpha-up';
        }
    }
}

// Search functionality
function initializeSearch() {
    const searchTypeFile = document.getElementById('searchTypeFile');
    const searchTypeFolder = document.getElementById('searchTypeFolder');
    const searchClear = document.getElementById('searchClear');
    
    // Search type toggle
    searchTypeFile.addEventListener('click', () => setSearchType('file'));
    searchTypeFolder.addEventListener('click', () => setSearchType('folder'));
    
    // Search input
    searchInput.addEventListener('input', handleSearch);
    searchInput.addEventListener('focus', () => {
        if (searchInput.value.trim()) {
            document.getElementById('searchResults').style.display = 'block';
        }
    });
    
    // Clear search
    searchClear.addEventListener('click', clearSearch);
    
    // Hide search results when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            document.getElementById('searchResults').style.display = 'none';
        }
    });
}

function setSearchType(type) {
    const fileBtn = document.getElementById('searchTypeFile');
    const folderBtn = document.getElementById('searchTypeFolder');
    
    if (type === 'file') {
        fileBtn.classList.add('active');
        folderBtn.classList.remove('active');
        searchInput.placeholder = 'Search by filename...';
    } else {
        folderBtn.classList.add('active');
        fileBtn.classList.remove('active');
        searchInput.placeholder = 'Search by folder name...';
    }
    
    // Re-search if there's a query
    if (searchInput.value.trim()) {
        handleSearch();
    }
}

async function handleSearch() {
    const query = searchInput.value.trim();
    const searchType = document.querySelector('.search-type-btn.active').id === 'searchTypeFile' ? 'file' : 'folder';
    const searchClear = document.getElementById('searchClear');
    const searchResultsDiv = document.getElementById('searchResults');
    
    // Show/hide clear button
    searchClear.style.display = query ? 'block' : 'none';
    
    if (!query) {
        searchResultsDiv.style.display = 'none';
        isSearching = false;
        return;
    }
    
    try {
        isSearching = true;
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&type=${searchType}`);
        const data = await response.json();
        
        if (response.ok) {
            renderSearchResults(data.results);
            searchResultsDiv.style.display = 'block';
        } else {
            showNotification(data.error || 'Search failed', 'error');
        }
    } catch (error) {
        showNotification('Search error', 'error');
    }
}

function renderSearchResults(results) {
    const searchResultsDiv = document.getElementById('searchResults');
    
    if (results.length === 0) {
        searchResultsDiv.innerHTML = `
            <div class="search-no-results">
                <i class="fas fa-search"></i>
                <p>No results found</p>
            </div>
        `;
        return;
    }
    
    searchResultsDiv.innerHTML = results.map(item => `
        <div class="search-result-item" onclick="${item.type === 'folder' ? `navigateToFolder('${item.path}')` : `playFile('${item.path}')`}">
            <div class="search-result-icon">
                <i class="fas fa-${getFileIcon(item.type)}"></i>
            </div>
            <div class="search-result-content">
                <div class="search-result-name">${item.name}</div>
                <div class="search-result-meta">
                    <span class="search-result-type">${item.type}</span>
                    <span class="search-result-path">${item.folder}</span>
                </div>
            </div>
        </div>
    `).join('');
}

function clearSearch() {
    searchInput.value = '';
    document.getElementById('searchClear').style.display = 'none';
    document.getElementById('searchResults').style.display = 'none';
    isSearching = false;
}

// Playlist functionality
async function loadPlaylists() {
    if (!permissions.can_use_playlists) return;
    
    try {
        const response = await fetch('/api/playlists');
        const data = await response.json();
        
        if (response.ok) {
            playlists = data.playlists;
        } else {
            showNotification(data.error || 'Failed to load playlists', 'error');
        }
    } catch (error) {
        showNotification('Network error', 'error');
    }
}

function showPlaylistModal() {
    document.getElementById('playlistModal').style.display = 'flex';
    renderPlaylists();
}

function renderPlaylists() {
    const playlistList = document.getElementById('playlistList');
    
    if (playlists.length === 0) {
        playlistList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-list"></i>
                <p>No playlists found</p>
            </div>
        `;
        return;
    }
    
    playlistList.innerHTML = playlists.map(playlist => `
        <div class="playlist-item">
            <div class="playlist-item-header">
                <h4 class="playlist-name">${playlist.name}</h4>
                <div class="playlist-actions-btn">
                    <button class="playlist-action" onclick="playPlaylist(${playlist.id})" title="Play">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="playlist-action" onclick="editPlaylist(${playlist.id})" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="playlist-action" onclick="deletePlaylist(${playlist.id})" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="playlist-meta">${playlist.videos.length} videos</div>
            ${playlist.description ? `<div class="playlist-description">${playlist.description}</div>` : ''}
        </div>
    `).join('');
}

async function playPlaylist(playlistId) {
    try {
        const response = await fetch(`/api/playlists/${playlistId}/play`);
        const data = await response.json();
        
        if (response.ok && data.playlist.videos.length > 0) {
            currentPlaylist = data.playlist;
            currentPlaylistIndex = 0;
            
            // Load first video
            loadVideo(data.playlist.videos[0], data.playlist, 0);
            
            // Show playlist viewer
            showPlaylistViewer(data.playlist);
            
            // Close modal
            document.getElementById('playlistModal').style.display = 'none';
        } else {
            showNotification('Playlist is empty or not found', 'error');
        }
    } catch (error) {
        showNotification('Failed to load playlist', 'error');
    }
}

function showPlaylistViewer(playlist) {
    // Remove existing playlist viewer
    const existingViewer = document.querySelector('.playlist-viewer');
    if (existingViewer) {
        existingViewer.remove();
    }
    
    // Create playlist viewer
    const playlistViewer = document.createElement('div');
    playlistViewer.className = 'playlist-viewer';
    playlistViewer.innerHTML = `
        <div class="playlist-header">
            <h3 class="playlist-title">
                <i class="fas fa-list"></i>
                ${playlist.name}
            </h3>
            <div class="playlist-controls">
                <button class="btn btn-secondary" onclick="hidePlaylistViewer()">
                    <i class="fas fa-times"></i>
                    Close
                </button>
            </div>
        </div>
        <div class="playlist-video-list" id="playlistVideoList">
            ${renderPlaylistVideos(playlist.videos)}
        </div>
    `;
    
    // Insert after video section
    const videoSection = document.querySelector('.video-section');
    videoSection.parentNode.insertBefore(playlistViewer, videoSection.nextSibling);
    
    updatePlaylistUI();
}

function renderPlaylistVideos(videos) {
    if (videos.length === 0) {
        return `
            <div class="playlist-empty">
                <i class="fas fa-list"></i>
                <p>No videos in this playlist</p>
            </div>
        `;
    }
    
    return videos.map((video, index) => `
        <div class="playlist-video-item ${index === currentPlaylistIndex ? 'playing' : ''}" 
             onclick="playPlaylistVideo(${index})">
            <img src="${video.thumbnail || '/static/placeholder.svg'}" 
                 class="playlist-video-thumbnail" 
                 alt="Thumbnail">
            <div class="playlist-video-info">
                <div class="playlist-video-name">${video.name}</div>
                <div class="playlist-video-meta">
                    <span>${formatFileSize(video.size)}</span>
                    ${video.duration ? `<span class="playlist-video-duration">${formatTime(video.duration)}</span>` : ''}
                </div>
            </div>
            <div class="playlist-video-actions">
                <button class="playlist-video-action remove" 
                        onclick="event.stopPropagation(); removeFromPlaylist(${index})" 
                        title="Remove">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function playPlaylistVideo(index) {
    if (currentPlaylist && currentPlaylist.videos[index]) {
        currentPlaylistIndex = index;
        loadVideo(currentPlaylist.videos[index], currentPlaylist, index);
    }
}

function updatePlaylistUI() {
    const playlistVideoList = document.getElementById('playlistVideoList');
    if (playlistVideoList && currentPlaylist) {
        playlistVideoList.innerHTML = renderPlaylistVideos(currentPlaylist.videos);
    }
}

function hidePlaylistViewer() {
    const viewer = document.querySelector('.playlist-viewer');
    if (viewer) {
        viewer.remove();
    }
    currentPlaylist = null;
    currentPlaylistIndex = -1;
}

// Utility functions
function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

function getFileIcon(type) {
    switch (type) {
        case 'folder': return 'folder';
        case 'video': return 'video';
        case 'audio': return 'music';
        default: return 'file';
    }
}

function showLoading(show) {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (show) {
        loadingOverlay.classList.add('show');
    } else {
        loadingOverlay.classList.remove('show');
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 4000);
}

// Navigation
function navigateToFolder(path) {
    document.getElementById('searchResults').style.display = 'none';
    loadFiles(path);
}

function playFile(path) {
    document.getElementById('searchResults').style.display = 'none';
    
    // Find video info
    const videoInfo = allVideos.find(v => v.path === path);
    if (videoInfo) {
        loadVideo(videoInfo);
    }
}

function updateBreadcrumb(currentPath, parentPath) {
    const pathParts = currentPath ? currentPath.split('/').filter(p => p) : [];
    
    let breadcrumbHTML = `
        <span class="breadcrumb-item ${!currentPath ? 'active' : ''}" 
              onclick="navigateToFolder('')">
            <i class="fas fa-home"></i> Home
        </span>
    `;
    
    let buildPath = '';
    pathParts.forEach((part, index) => {
        buildPath += (buildPath ? '/' : '') + part;
        const isLast = index === pathParts.length - 1;
        
        breadcrumbHTML += `
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item ${isLast ? 'active' : ''}" 
                  onclick="navigateToFolder('${buildPath}')">
                ${part}
            </span>
        `;
    });
    
    breadcrumb.innerHTML = breadcrumbHTML;
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        switch (e.key.toLowerCase()) {
            case ' ':
                e.preventDefault();
                togglePlayPause();
                break;
            case 'arrowleft':
                e.preventDefault();
                videoPlayer.currentTime -= 10;
                break;
            case 'arrowright':
                e.preventDefault();
                videoPlayer.currentTime += 10;
                break;
            case 'arrowup':
                e.preventDefault();
                videoPlayer.volume = Math.min(1, videoPlayer.volume + 0.1);
                volumeSlider.value = videoPlayer.volume;
                updateVolumeIcon();
                break;
            case 'arrowdown':
                e.preventDefault();
                videoPlayer.volume = Math.max(0, videoPlayer.volume - 0.1);
                volumeSlider.value = videoPlayer.volume;
                updateVolumeIcon();
                break;
            case 'f':
                e.preventDefault();
                toggleFullscreen();
                break;
            case 'n':
                e.preventDefault();
                playNext();
                break;
            case 'p':
                e.preventDefault();
                playPrevious();
                break;
            case 't':
                e.preventDefault();
                document.getElementById('themeToggle').click();
                break;
            case 'l':
                if (permissions.can_use_playlists) {
                    e.preventDefault();
                    showPlaylistModal();
                }
                break;
        }
        
        // Ctrl+F for search
        if (e.ctrlKey && e.key === 'f') {
            e.preventDefault();
            searchInput.focus();
        }
    });
}

// Theme management
const theme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', theme);
updateThemeIcon();

function updateThemeIcon() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const lightIcon = document.getElementById('lightIcon');
    const darkIcon = document.getElementById('darkIcon');
    
    if (currentTheme === 'dark') {
        lightIcon.style.display = 'block';
        darkIcon.style.display = 'none';
    } else {
        lightIcon.style.display = 'none';
        darkIcon.style.display = 'block';
    }
}

document.getElementById('themeToggle').addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon();
});

// Logout
document.getElementById('logoutBtn').addEventListener('click', async () => {
    try {
        const response = await fetch('/api/logout', { method: 'POST' });
        if (response.ok) {
            window.location.href = '/login';
        }
    } catch (error) {
        window.location.href = '/login';
    }
});

// Initialize sort controls when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(addSortControls, 100);
});