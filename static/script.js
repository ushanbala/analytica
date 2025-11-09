let channels = [];
let allVideos = [];
let progressInterval;

async function loadChannels() {
  const res = await fetch("/api/channels");
  channels = await res.json();
  renderChannels();
}

function displayAnalytics(data) {
    let html = `
      <p><strong>Average Views:</strong> ${data.average_views.toLocaleString()}</p>
      <p><strong>Average Likes:</strong> ${data.average_likes.toLocaleString()}</p>
      <p><strong>Average Duration:</strong> ${Math.floor(data.average_duration_seconds / 60)} min ${data.average_duration_seconds % 60} sec</p>
      <p><strong>Average Engagement Ratio (Likes/Views):</strong> ${data.average_engagement_ratio}</p>
      <p><strong>Average Upload Frequency:</strong> ${data.average_upload_frequency_days ? data.average_upload_frequency_days.toFixed(1) + " days" : "N/A"}</p>
      <p><strong>Top Keywords in Titles:</strong> ${data.top_keywords.map(([word, count]) => `${word} (${count})`).join(", ")}</p>
    `;
  
    document.getElementById("analytics-content").innerHTML = html;
  }
  

  async function loadSavedAnalytics(encodedUrl) {
    const url = decodeURIComponent(encodedUrl);
    const res = await fetch(`/api/analytics/${encodedUrl}`);
    if (res.ok) {
      const data = await res.json();
      displayAnalytics(data);
    } else {
      alert("No saved analytics found for this channel.");
    }
  }

async function fetchAndDisplayAnalytics(videos, channelUrl) {
    if (!videos.length) {
      document.getElementById("analytics-content").innerHTML = "No videos to analyze.";
      return;
    }
  
    const res = await fetch("/api/videos/analytics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ videos, channel_url: channelUrl }),
    });
  
    const data = await res.json();
  
    displayAnalytics(data);
  }
  

async function addChannel() {
  const url = document.getElementById("channel-url").value.trim();
  if (!url) return alert("Enter a valid URL");
  await fetch("/api/channels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  document.getElementById("channel-url").value = "";
  loadChannels();
}

async function removeChannel(url) {
  await fetch("/api/channels", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  loadChannels();
}

function renderChannels() {
    const div = document.getElementById("channels");
    div.innerHTML = "";
    channels.forEach((c) => {
      const safeUrl = encodeURIComponent(c.url);
      const el = document.createElement("div");
      el.innerHTML = `
        <span>${c.name}</span>
        <button onclick="fetchVideos('${c.url}')">Load Videos</button>
        <button onclick="loadSavedAnalytics('${safeUrl}')">Load Saved Analytics</button>
        <button onclick="removeChannel('${c.url}')">❌</button>
      `;
      div.appendChild(el);
    });
  }


async function fetchVideos(url) {
    document.getElementById("progress-container").style.display = "block";
    document.getElementById("progress-bar").style.width = "0%";
    document.getElementById("progress-text").textContent = "Starting...";
  
    await fetch("/api/videos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  
    progressInterval = setInterval(() => checkProgress(url), 1000);
  }
  

  async function checkProgress(channelUrl) {
    const res = await fetch("/api/progress");
    const data = await res.json();
  
    document.getElementById("progress-bar").style.width = data.percent + "%";
    document.getElementById("progress-text").textContent = data.message;
  
    if (data.status === "done") {
      clearInterval(progressInterval);
      await loadVideosAfterCompletion(channelUrl);
    } else if (data.status === "error") {
      clearInterval(progressInterval);
      document.getElementById("progress-text").textContent = "❌ " + data.message;
    }
  }
  
  async function loadVideosAfterCompletion(channelUrl) {
    const res = await fetch("/api/videos/latest");
    const vids = await res.json();
    if (Array.isArray(vids)) {
      allVideos = vids;
      renderVideos();
      await fetchAndDisplayAnalytics(vids, channelUrl);
    }
    document.getElementById("progress-container").style.display = "none";
  }
  
function renderVideos(videos = allVideos) {
  const div = document.getElementById("videos");
  div.innerHTML = "";

  videos.forEach((v) => {
    const el = document.createElement("div");
    el.className = "video";
    el.innerHTML = `
      <img src="${v.thumbnail || ''}" alt="thumbnail" class="thumb" />
      <h3><a href="${v.url}" target="_blank">${v.title}</a></h3>
      <p class="meta">
        👁️ ${v.views?.toLocaleString() || 0} views <br>
        👍 ${v.like_count?.toLocaleString() || 0} likes
      </p>
      <small>${v.published}</small>
      <p class="desc">${v.description || ""}</p>
    `;
    div.appendChild(el);
  });
}

function sortVideos() {
  const val = document.getElementById("sort").value;
  let vids = [...allVideos];
  if (val === "views") vids.sort((a, b) => (b.views || 0) - (a.views || 0));
  else if (val === "likes") vids.sort((a, b) => (b.like_count || 0) - (a.like_count || 0));
  else if (val === "duration") vids.sort((a, b) => (b.duration || 0) - (a.duration || 0));
  renderVideos(vids);
}

function filterVideos() {
  const q = document.getElementById("search").value.toLowerCase();
  const filtered = allVideos.filter(v => v.title.toLowerCase().includes(q));
  renderVideos(filtered);
}



loadChannels();
