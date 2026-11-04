let currentUser = null;
let currentGame = null;
let currentSession = null;
let authHeader = "";
let wickRegenInterval = null;
let secondsUntilNextWick = 0;

document.addEventListener("DOMContentLoaded", async () => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        try { tg.enableClosingConfirmation(); } catch (e) {}
    }

    const urlParams = new URLSearchParams(window.location.search);
    const devTgId = urlParams.get('tg_id') || "123456789";
    const initData = tg?.initData || `dev_user_${devTgId}`;
    authHeader = initData;

    setupTabs();
    setupAudioToggle();
    await authenticateUser(initData);
});

async function authenticateUser(initData) {
    try {
        const resp = await fetch('/api/auth/telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: initData })
        });
        const data = await resp.json();
        if (data.success) {
            currentUser = data.user;
            updateUI(data);
        }
    } catch (e) {
        console.error("Auth error:", e);
    }
}

function updateUI(authData) {
    const u = authData.user;
    
    document.getElementById('user-wicks').innerText = `${u.diya_wicks}/10`;
    document.getElementById('user-name').innerText = u.first_name || u.username || `Player_${u.telegram_id}`;
    document.getElementById('user-tier-label').innerText = `${u.tier_name} (Tier ${u.tier_level})`;
    document.getElementById('user-points').innerText = `${u.points_total} Pts`;
    const emblems = { 1: "☀️ Surya", 2: "🔥 Agni", 3: "🌙 Chandra", 4: "💨 Vayu" };
    const gName = emblems[u.gharana_id] ? `${emblems[u.gharana_id]} Gharana` : (u.gharana_name || u.gharana);
    document.getElementById('user-gharana').innerText = gName;

    const sparks = authData.community_sparks;
    const target = authData.target_sparks;
    const pct = Math.min(100, ((sparks / target) * 100)).toFixed(1);
    
    document.getElementById('sparks-display').innerText = `${sparks.toLocaleString()} Sparks`;
    document.getElementById('flame-progress').style.width = `${pct}%`;
    document.getElementById('progress-pct').innerText = `${pct}%`;

    // Community Milestone Stage Name
    const stageNames = {
        0: "Stage 0: Lighting the Wick",
        1: "Stage 1: Pratham Jyoti (The First Spark)",
        2: "Stage 2: Shubh Rangoli Radiance",
        3: "Stage 3: Deepotsav Halfway Glow",
        4: "Stage 4: Maha Akhand Jyoti (Core Goal)",
        5: "Stage 5: Ananta Utsav (Overdrive)"
    };
    const stageBadge = document.getElementById('stage-badge');
    if (stageBadge) {
        stageBadge.innerText = stageNames[authData.current_stage] || `Stage ${authData.current_stage}`;
    }

    // Shubh Muhurat Refill Banner
    const shubhBtn = document.getElementById('shubh-action-btn');
    const shubhTxt = document.getElementById('shubh-status-txt');
    if (shubhBtn && shubhTxt) {
        if (u.shubh_refill_available) {
            shubhBtn.disabled = false;
            shubhBtn.innerText = "CLAIM +5";
            shubhBtn.style.opacity = "1";
            shubhTxt.innerText = "Daily +5 Diya Wicks Blessing (Available Now!)";
        } else {
            shubhBtn.disabled = true;
            shubhBtn.innerText = "CLAIMED";
            shubhBtn.style.opacity = "0.5";
            shubhTxt.innerText = "Blessing claimed today • Resets tomorrow";
        }
    }

    // Stamina Regeneration Timer
    secondsUntilNextWick = u.seconds_until_next_wick || 0;
    startWickTimer();

    // Diya Companion Card
    const compBox = document.getElementById('companion-container');
    if (u.companion) {
        compBox.innerHTML = `
            <div class="companion-header">
                <div>
                    <div class="user-name">🤝 Diya Companion: ${u.companion.name}</div>
                    <div class="companion-status">${u.companion.tier_name} • Bonded</div>
                </div>
                <button class="gift-wick-btn" id="gift-wick-action-btn" onclick="sendWickGift()">🎁 Send Wick</button>
            </div>
            <p style="font-size:0.75rem; color:#94A3B8;">Exchange 1 free Diya Wick daily with your companion!</p>
        `;
    } else {
        compBox.innerHTML = `
            <div class="companion-header">
                <div>
                    <div class="user-name">🤝 No Diya Companion Yet</div>
                    <div class="companion-status">Invite 1 friend to form your exclusive bond!</div>
                </div>
                <button class="gift-wick-btn" onclick="copyShagunLink()">🔗 Invite</button>
            </div>
            <p style="font-size:0.75rem; color:#94A3B8;">Your 1st active friend becomes your permanent Companion.</p>
        `;
    }

    document.getElementById('ref-points-count').innerText = `${u.referral_points_earned}/15 Pts`;
    document.getElementById('total-refs-count').innerText = `${u.total_referrals_count} Friends`;

    // Highlight user's unlocked tiers in the ladder
    updateTierLadder(u.tier_level);
}

function updateTierLadder(currentTierLevel) {
    for (let t = 0; t <= 5; t++) {
        const card = document.querySelector(`.tier-item-card[data-tier="${t}"]`);
        const pill = document.getElementById(`tier-pill-${t}`);
        if (!card || !pill) continue;
        if (t <= currentTierLevel) {
            card.classList.add('unlocked');
            pill.innerText = "✅ Unlocked";
            pill.style.color = "#10B981";
            pill.style.fontWeight = "700";
        } else {
            card.classList.remove('unlocked');
            pill.innerText = "🔒 Locked";
            pill.style.color = "#64748B";
        }
    }
}

function startWickTimer() {
    if (wickRegenInterval) clearInterval(wickRegenInterval);
    const timerEl = document.getElementById('wick-regen-timer');
    if (!timerEl) return;

    if (!currentUser || currentUser.diya_wicks >= 10) {
        timerEl.innerText = "";
        return;
    }

    const renderTimer = () => {
        if (!currentUser || currentUser.diya_wicks >= 10) {
            timerEl.innerText = "";
            return;
        }
        if (secondsUntilNextWick <= 0) {
            secondsUntilNextWick = 15 * 60;
            currentUser.diya_wicks = Math.min(10, currentUser.diya_wicks + 1);
            document.getElementById('user-wicks').innerText = `${currentUser.diya_wicks}/10`;
            if (currentUser.diya_wicks >= 10) {
                timerEl.innerText = "";
                return;
            }
        }
        const m = Math.floor(secondsUntilNextWick / 60);
        const s = secondsUntilNextWick % 60;
        timerEl.innerText = `(${m}:${s < 10 ? '0' : ''}${s})`;
        secondsUntilNextWick--;
    };

    renderTimer();
    wickRegenInterval = setInterval(renderTimer, 1000);
}

async function claimShubhRefill() {
    window.festivalAudio?.init();
    try {
        const resp = await fetch('/api/game/shubh_refill', {
            method: 'POST',
            headers: {
                'Authorization': authHeader,
                'x-telegram-id': String(currentUser.telegram_id)
            }
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            currentUser.diya_wicks = data.wicks_total;
            currentUser.shubh_refill_available = false;
            document.getElementById('user-wicks').innerText = `${data.wicks_total}/10`;
            startWickTimer();

            const shubhBtn = document.getElementById('shubh-action-btn');
            const shubhTxt = document.getElementById('shubh-status-txt');
            if (shubhBtn) {
                shubhBtn.disabled = true;
                shubhBtn.innerText = "CLAIMED";
                shubhBtn.style.opacity = "0.5";
            }
            if (shubhTxt) {
                shubhTxt.innerText = "Blessing claimed today • Resets tomorrow";
            }

            window.festivalAudio?.playShubhBlessing();
            showCelebrationModal("SHUBH MUHURAT BLESSING! ✨", data.message);
        } else {
            alert(data.detail || data.message || "Failed to claim refill");
        }
    } catch (e) {
        console.error("Shubh refill error", e);
    }
}

function showCelebrationModal(title, message) {
    document.getElementById('celebration-title').innerText = title;
    document.getElementById('celebration-msg').innerText = message;
    document.getElementById('celebration-modal').classList.add('active');
}

function closeCelebrationModal() {
    document.getElementById('celebration-modal').classList.remove('active');
}

function setupTabs() {
    const tabs = document.querySelectorAll('.nav-item');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            window.festivalAudio?.init();
            window.festivalAudio?.playTap();
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.getAttribute('data-tab');
            document.querySelectorAll('.tab-view').forEach(v => v.style.display = 'none');
            document.getElementById(`tab-${target}`).style.display = 'block';

            if (target === 'community') loadCommunityLeaderboard();
        });
    });
}

function setupAudioToggle() {
    const btn = document.getElementById('audio-toggle-btn');
    const saved = localStorage.getItem('festival_audio_muted');
    if (saved !== null) {
        window.festivalAudio.muted = (saved === 'true');
        btn.innerText = window.festivalAudio.muted ? '🔇' : '🔊';
    }
    btn.addEventListener('click', () => {
        window.festivalAudio.muted = !window.festivalAudio.muted;
        localStorage.setItem('festival_audio_muted', String(window.festivalAudio.muted));
        btn.innerText = window.festivalAudio.muted ? '🔇' : '🔊';
        if (!window.festivalAudio.muted) {
            window.festivalAudio?.init();
            window.festivalAudio?.playTap();
        }
    });
}

async function launchMiniGame(gameType) {
    if (!currentUser || currentUser.diya_wicks < 1) {
        alert("Out of Diya Wicks! Wait for stamina regeneration (1 wick every 15 mins).");
        return;
    }

    window.festivalAudio?.init();

    try {
        const resp = await fetch('/api/game/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
                'x-telegram-id': String(currentUser.telegram_id)
            },
            body: JSON.stringify({ game_type: gameType })
        });
        const sessionData = await resp.json();
        if (!resp.ok) {
            alert(sessionData.detail || "Failed to start game");
            return;
        }

        currentSession = sessionData;
        currentUser.diya_wicks = sessionData.wicks_remaining;
        document.getElementById('user-wicks').innerText = `${currentUser.diya_wicks}/10`;

        const overlay = document.getElementById('game-overlay');
        overlay.classList.add('active');
        const canvas = document.getElementById('game-canvas');
        canvas.width = Math.min(window.innerWidth, 450);
        canvas.height = Math.min(window.innerHeight - 120, 550);

        if (gameType === 1) {
            document.getElementById('game-modal-title').innerText = "Chakri Whirl & Rocket";
            document.getElementById('game-action-btn').style.display = 'block';
            document.getElementById('game-action-btn').innerText = "🚀 IGNITE!";
            currentGame = new window.ChakriGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 2) {
            document.getElementById('game-modal-title').innerText = "Rangoli Color Symphony";
            document.getElementById('game-action-btn').style.display = 'none';
            currentGame = new window.RangoliGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 3) {
            document.getElementById('game-modal-title').innerText = "Mithai Drop Catcher";
            document.getElementById('game-action-btn').style.display = 'none';
            currentGame = new window.MithaiGame(canvas, onGameFinished);
            currentGame.start();
        }
    } catch (e) {
        console.error("Game launch error", e);
    }
}

function handleGameActionButton() {
    if (currentGame && currentGame.handleTap) currentGame.handleTap();
}

async function onGameFinished(rawScore, durationMs) {
    if (!currentSession) return;
    try {
        const resp = await fetch('/api/game/finish', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
                'x-telegram-id': String(currentUser.telegram_id)
            },
            body: JSON.stringify({
                session_id: currentSession.session_id,
                nonce: currentSession.nonce,
                raw_score: rawScore,
                duration_ms: durationMs
            })
        });
        const resData = await resp.json();
        if (resData.success) {
            currentUser.points_total = resData.new_user_total;
            currentUser.tier_level = resData.new_tier_level;
            currentUser.tier_name = resData.tier_name;
            
            document.getElementById('user-points').innerText = `${resData.new_user_total} Pts`;
            document.getElementById('user-tier-label').innerText = `${resData.tier_name} (Tier ${resData.new_tier_level})`;
            document.getElementById('sparks-display').innerText = `${resData.community_total.toLocaleString()} Sparks`;
            
            updateTierLadder(resData.new_tier_level);

            if (resData.tier_unlocked) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal("TIER UNLOCKED! 🏆", `Congratulations! You have ascended to ${resData.tier_name} (Tier ${resData.new_tier_level})! Your Diwali blessings and reward shares have increased.`);
            } else if (resData.community_total >= 200000) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal("MAHA AKHAND JYOTI IGNITED! 🪔🎆", "Sacred Victory! The community has achieved 200,000 Sparks! The Akhand Diya burns eternally, unlocking treasury distributions!");
            }
        }
    } catch (e) {
        console.error("Score submit error", e);
    }
}

function closeGameModal() {
    if (currentGame) {
        currentGame.stop();
        currentGame = null;
    }
    currentSession = null;
    document.getElementById('game-overlay').classList.remove('active');
}

async function sendWickGift() {
    window.festivalAudio?.init();
    try {
        const resp = await fetch('/api/referral/gift_wick', {
            method: 'POST',
            headers: {
                'Authorization': authHeader,
                'x-telegram-id': String(currentUser.telegram_id)
            }
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            window.festivalAudio?.playSuccessChime();
            const btn = document.getElementById('gift-wick-action-btn');
            if (btn) {
                btn.disabled = true;
                btn.innerText = "✅ Sent";
                btn.style.opacity = "0.6";
            }
            alert(data.message);
        } else {
            alert(data.message || data.detail || "Failed to send gift.");
        }
    } catch (e) {
        alert("Failed to send gift.");
    }
}

function copyShagunLink() {
    const link = `https://t.me/OrdinalLegacyEventBot?start=shagun_${currentUser.telegram_id}`;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(link);
        alert(`🎁 Shagun Invite Link Copied!\n\n${link}`);
    } else {
        prompt("Copy your Diwali Shagun Link:", link);
    }
}

function shareShagunOnTelegram() {
    const link = `https://t.me/OrdinalLegacyEventBot?start=shagun_${currentUser.telegram_id}`;
    const text = encodeURIComponent("🪔 Join me in the Ordinal Legacy Diwali Maha Deepotsav! Awaken the 200,000 Sparks of Akhand Jyoti with me as my bonded Diya Companion!");
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${text}`;
    if (window.Telegram?.WebApp?.openTelegramLink) {
        window.Telegram.WebApp.openTelegramLink(shareUrl);
    } else {
        window.open(shareUrl, '_blank');
    }
}

async function loadCommunityLeaderboard() {
    try {
        const resp = await fetch('/api/community/state');
        const data = await resp.json();
        const listEl = document.getElementById('gharana-list');
        const medals = ["🥇", "🥈", "🥉", "✨"];
        const emblems = { 1: "☀️", 2: "🔥", 3: "🌙", 4: "💨" };
        listEl.innerHTML = data.top_gharanas.map((g, idx) => `
            <div class="user-profile-strip" style="margin: 0 0 10px 0; border-left: 3px solid ${idx === 0 ? '#F59E0B' : '#64748B'};">
                <div class="user-tag">
                    <span class="user-name">${medals[idx] || "•"} ${emblems[g.gharana_id] || ""} ${g.name}</span>
                    <span style="font-size:0.75rem; color:#94A3B8;">${g.members} Members • ${g.total_points.toLocaleString()} Total Sparks</span>
                </div>
                <div class="user-score-box">
                    <span class="user-score-val" style="color:#F59E0B;">${g.avg_points}</span>
                    <span style="font-size:0.7rem; color:#94A3B8;">avg pts</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Failed to load community state", e);
    }
}
