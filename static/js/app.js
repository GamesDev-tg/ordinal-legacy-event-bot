let currentUser = null;
let currentGame = null;
let currentSession = null;
let authHeader = "";
let wickRegenInterval = null;
let secondsUntilNextWick = 0;
let boostCountdownInterval = null;
let secondsUntilBoostEnds = 0;

function getCurrentUserId() {
    if (currentUser && currentUser.telegram_id) return currentUser.telegram_id;
    const urlParams = new URLSearchParams(window.location.search);
    const paramId = urlParams.get('tg_id');
    if (paramId && /^\d+$/.test(paramId)) return parseInt(paramId, 10);
    const tgId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    if (tgId) return parseInt(tgId, 10);
    return null;
}

document.addEventListener("DOMContentLoaded", async () => {
    const tg = window.Telegram?.WebApp;
    const isTelegramWebApp = !!(tg && tg.initData && tg.initData.length > 5);

    if (tg) {
        tg.ready();
        tg.expand();
        // Keep normal menu navigation smooth without scary data loss confirmation
        try { tg.disableClosingConfirmation(); } catch (e) {}
    }

    setupTabs();
    setupAudioToggle();
    setupStaminaRefreshButton();

    if (isTelegramWebApp) {
        authHeader = tg.initData;
        await authenticateUser(authHeader);
    } else {
        // Web browser environment
        const savedWebUser = localStorage.getItem('ordinal_web_user');
        if (savedWebUser) {
            try {
                const userObj = JSON.parse(savedWebUser);
                const success = await authenticateViaWidget(userObj);
                if (success) {
                    showWebUserChip(userObj);
                } else {
                    localStorage.removeItem('ordinal_web_user');
                    showWebLoginModal();
                }
            } catch (e) {
                localStorage.removeItem('ordinal_web_user');
                showWebLoginModal();
            }
        } else {
            const urlParams = new URLSearchParams(window.location.search);
            const devTgId = urlParams.get('tg_id');
            if (devTgId) {
                authHeader = `dev_user_${devTgId}`;
                await authenticateUser(authHeader);
            } else {
                showWebLoginModal();
            }
        }
    }

    // Auto-refresh when user returns to mini-app or switches focus from bot chat
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            refreshUserData();
        }
    });
    window.addEventListener("focus", () => {
        refreshUserData();
    });

    // Periodic live stamina & community sparks sync every 5 seconds when tab is active
    setInterval(() => {
        if (!document.hidden && document.visibilityState === "visible") {
            refreshUserData();
        }
    }, 5000);
});

async function refreshUserData() {
    try {
        if (authHeader) {
            if (authHeader.trim().startsWith('{')) {
                const resp = await fetch('/api/auth/widget', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: authHeader
                });
                const data = await resp.json();
                if (resp.ok && data.success) {
                    currentUser = data.user;
                    updateUI(data);
                    return data;
                }
            } else {
                const resp = await fetch('/api/auth/telegram', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ init_data: authHeader })
                });
                const data = await resp.json();
                if (resp.ok && data.success) {
                    currentUser = data.user;
                    updateUI(data);
                    return data;
                }
            }
        }
    } catch (e) {
        console.warn("Background user refresh warning:", e);
    }

    // Fallback if authHeader was invalid / dev user / missing
    const urlParams = new URLSearchParams(window.location.search);
    const tgId = urlParams.get('tg_id') || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || (currentUser ? currentUser.telegram_id : null);
    if (tgId) {
        try {
            const fallbackResp = await fetch('/api/auth/telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: `dev_user_${tgId}` })
            });
            const fallbackData = await fallbackResp.json();
            if (fallbackData.success) {
                currentUser = fallbackData.user;
                if (!authHeader) authHeader = `dev_user_${tgId}`;
                updateUI(fallbackData);
                return fallbackData;
            }
        } catch (e2) {
            console.warn("Fallback user refresh error:", e2);
        }
    }
}

async function authenticateUser(initData) {
    try {
        const resp = await fetch('/api/auth/telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: initData })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            currentUser = data.user;
            await checkAndClaimReferral();
            updateUI(data);
            return;
        }
    } catch (e) {
        console.warn("Primary Telegram auth error, falling back...", e);
    }

    // Resilient fallback for direct browser launch / tg_id parameter
    const urlParams = new URLSearchParams(window.location.search);
    const tgId = urlParams.get('tg_id') || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "123456789";
    try {
        const fallbackResp = await fetch('/api/auth/telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: `dev_user_${tgId}` })
        });
        const fallbackData = await fallbackResp.json();
        if (fallbackData.success) {
            currentUser = fallbackData.user;
            authHeader = `dev_user_${tgId}`;
            await checkAndClaimReferral();
            updateUI(fallbackData);
        }
    } catch (e2) {
        console.error("Fallback auth error:", e2);
    }
}

async function checkAndClaimReferral() {
    try {
        const tg = window.Telegram?.WebApp;
        const urlParams = new URLSearchParams(window.location.search);
        let startParam = tg?.initDataUnsafe?.start_param || urlParams.get('startapp') || urlParams.get('start') || urlParams.get('ref');
        if (!startParam) return;

        let referrerId = null;
        if (typeof startParam === 'string') {
            if (startParam.startsWith('shagun_')) {
                referrerId = parseInt(startParam.replace('shagun_', ''), 10);
            } else if (startParam.startsWith('ref_')) {
                referrerId = parseInt(startParam.replace('ref_', ''), 10);
            } else if (/^\d+$/.test(startParam)) {
                referrerId = parseInt(startParam, 10);
            }
        }

        const myUid = getCurrentUserId();
        if (referrerId && myUid && referrerId !== myUid) {
            const claimResp = await fetch('/api/referral/claim', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': authHeader,
                    'x-telegram-id': String(myUid)
                },
                body: JSON.stringify({ referrer_telegram_id: referrerId })
            });
            const claimData = await claimResp.json();
            if (claimResp.ok && claimData.success) {
                console.log("Mini-App referral claimed successfully:", claimData);
                const refreshResp = await fetch('/api/auth/telegram', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ init_data: authHeader })
                });
                const refreshData = await refreshResp.json();
                if (refreshResp.ok && refreshData.success) {
                    currentUser = refreshData.user;
                }
            }
        }
    } catch (e) {
        console.warn("Could not auto-claim referral via start_param:", e);
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

    // Community Milestone 5 Segments of 200k Sparks
    let stageDesc = authData.stage_description;
    if (!stageDesc) {
        if (sparks >= 200000) {
            stageDesc = `Stage 5: Maha Akhand Jyoti (${sparks.toLocaleString()} Sparks • All Cleared!)`;
        } else if (sparks >= 160000) {
            stageDesc = `Stage 4: Grand Deepotsav (${sparks.toLocaleString()} / 200,000 Sparks to Jyoti)`;
        } else if (sparks >= 120000) {
            stageDesc = `Stage 3: Celestial Harmony (${sparks.toLocaleString()} / 160,000 Sparks to Pets)`;
        } else if (sparks >= 80000) {
            stageDesc = `Stage 2: Sacred Radiance (${sparks.toLocaleString()} / 120,000 Sparks to Tickets)`;
        } else if (sparks >= 40000) {
            stageDesc = `Stage 1: The First Glow (${sparks.toLocaleString()} / 80,000 Sparks to Pearls)`;
        } else {
            stageDesc = `Stage 0: Lighting the Wick (${sparks.toLocaleString()} / 40,000 to Coins)`;
        }
    }
    const stageBadge = document.getElementById('stage-badge');
    if (stageBadge) {
        stageBadge.innerText = stageDesc;
    }

    // Event Paused Status Banner
    if (authData.event_paused) {
        let pb = document.getElementById('event-paused-banner');
        if (!pb) {
            pb = document.createElement('div');
            pb.id = 'event-paused-banner';
            pb.style.background = 'linear-gradient(135deg, #DC2626, #991B1B)';
            pb.style.color = '#FFFFFF';
            pb.style.padding = '12px 16px';
            pb.style.borderRadius = '12px';
            pb.style.margin = '12px 0';
            pb.style.textAlign = 'center';
            pb.style.fontWeight = 'bold';
            pb.style.fontSize = '0.85rem';
            pb.style.boxShadow = '0 4px 12px rgba(220, 38, 38, 0.4)';
            pb.innerHTML = '⏳ <b>FESTIVAL GAMES FROZEN FOR SCORE AUDITING</b><br><span style="font-size:0.75rem; font-weight:normal; opacity:0.95;">Admins are auditing final scores and verifying winners. Please check your final rank in /mydata!</span>';
            const container = document.querySelector('.container') || document.body;
            container.prepend(pb);
        }
    } else {
        const pb = document.getElementById('event-paused-banner');
        if (pb) pb.remove();
    }

    // Unverified Community Group Gate Banner
    if (u.joined_groups === false && !u.is_admin) {
        let gb = document.getElementById('unverified-gate-banner');
        if (!gb) {
            gb = document.createElement('div');
            gb.id = 'unverified-gate-banner';
            gb.style.cssText = 'background:linear-gradient(135deg, #B45309, #D97706); color:#FFF; padding:12px 16px; border-radius:12px; margin:12px 16px; text-align:center; font-size:0.82rem; font-weight:600; box-shadow:0 4px 12px rgba(180, 83, 9, 0.35); cursor:pointer;';
            gb.innerHTML = '⚠️ <b>ACTION REQUIRED: Verify Official Community Groups</b><br><span style="font-size:0.75rem; font-weight:normal; opacity:0.95;">Join our 3 official groups and tap Verify in @OrdinalLegacyEventBot to play! (Tap here to open bot)</span>';
            gb.onclick = () => {
                const link = "https://t.me/OrdinalLegacyEventBot";
                if (window.Telegram?.WebApp?.openTelegramLink) window.Telegram.WebApp.openTelegramLink(link);
                else window.open(link, "_blank");
            };
            const mainArena = document.getElementById('tab-arena');
            if (mainArena) mainArena.prepend(gb);
        }
    } else {
        const gb = document.getElementById('unverified-gate-banner');
        if (gb) gb.remove();
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

    // Active Gharana 2x Boost Card
    const boostData = authData.gharana_boost || u.active_gharana_boost;
    if (boostData) {
        updateGharanaBoostUI(boostData, u.gharana_id);
    }

    // Highlight user's unlocked tiers in the ladder
    updateTierLadder(u.tier_level);
}

function updateGharanaBoostUI(boost, userGharanaId) {
    const card = document.getElementById('gharana-boost-card');
    const icon = document.getElementById('boost-gharana-icon');
    const title = document.getElementById('boost-gharana-title');
    const subtitle = document.getElementById('boost-gharana-subtitle');
    const badge = document.getElementById('boost-multiplier-badge');

    if (!card || !boost) return;

    if (icon) icon.innerText = boost.active_gharana_emoji || "⚡";
    if (title) title.innerText = `${boost.active_gharana_name} 2X Surge`;

    const isUserBoosted = (userGharanaId === boost.active_gharana_id);
    if (isUserBoosted) {
        card.classList.add('boost-active-for-user');
        if (subtitle) subtitle.innerText = "🔥 2X ACTIVE FOR YOUR HOUSE! Double sparks on all games!";
        if (badge) {
            badge.innerText = "⚡ 2X ACTIVE";
            badge.style.background = "linear-gradient(135deg, #F59E0B, #EA580C)";
            badge.style.color = "#000";
        }
    } else {
        card.classList.remove('boost-active-for-user');
        if (subtitle) subtitle.innerText = `10-min surge • Next: ${boost.next_gharana_emoji || ""} ${boost.next_gharana_name || ""}`;
        if (badge) {
            badge.innerText = "1X";
            badge.style.background = "#334155";
            badge.style.color = "#94A3B8";
        }
    }

    secondsUntilBoostEnds = boost.seconds_remaining || 0;
    startBoostTimer();
}

function startBoostTimer() {
    if (boostCountdownInterval) clearInterval(boostCountdownInterval);
    const timer = document.getElementById('boost-countdown-timer');
    if (!timer) return;

    const renderBoostTime = () => {
        if (secondsUntilBoostEnds <= 0) {
            timer.innerText = "00:00";
            if (boostCountdownInterval) clearInterval(boostCountdownInterval);
            refreshUserData();
            return;
        }
        const m = Math.floor(secondsUntilBoostEnds / 60);
        const s = secondsUntilBoostEnds % 60;
        timer.innerText = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        secondsUntilBoostEnds--;
    };

    renderBoostTime();
    boostCountdownInterval = setInterval(renderBoostTime, 1000);
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
            // Next wick regenerated! Pick random interval between 60s and 180s (1 to 3 minutes)
            secondsUntilNextWick = Math.floor(Math.random() * (180 - 60 + 1)) + 60;
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
    const uid = getCurrentUserId();
    if (!uid) {
        showWebLoginModal();
        return;
    }
    window.festivalAudio?.init();
    try {
        const resp = await fetch('/api/game/shubh_refill', {
            method: 'POST',
            headers: {
                'Authorization': authHeader,
                'x-telegram-id': String(uid)
            }
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            currentUser.diya_wicks = data.wicks_total;
            currentUser.points_total = data.points_total || (currentUser.points_total + 5);
            currentUser.shubh_refill_available = false;
            document.getElementById('user-wicks').innerText = `${data.wicks_total}/10`;
            document.getElementById('user-points').innerText = `${currentUser.points_total} Pts`;
            if (data.tier_level !== undefined) {
                currentUser.tier_level = data.tier_level;
                updateTierLadder(data.tier_level);
            }
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

            // Auto-refresh user stamina & community progress on tab switch
            refreshUserData();

            if (target === 'community') loadCommunityLeaderboard();
        });
    });
}

function setupStaminaRefreshButton() {
    const btn = document.getElementById('stamina-badge-btn');
    if (btn) {
        btn.addEventListener('click', async () => {
            window.festivalAudio?.init();
            window.festivalAudio?.playTap();
            const wicksSpan = document.getElementById('user-wicks');
            if (wicksSpan) wicksSpan.style.opacity = '0.5';
            await refreshUserData();
            if (wicksSpan) wicksSpan.style.opacity = '1';
        });
    }
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
    let uid = getCurrentUserId();
    if (!currentUser) {
        await refreshUserData();
        uid = getCurrentUserId();
    }
    if (!uid) {
        showWebLoginModal();
        return;
    }
    if (!currentUser || currentUser.diya_wicks < 1) {
        await refreshUserData();
        if (!currentUser || currentUser.diya_wicks < 1) {
            alert("Out of Diya Wicks! Stamina refills 1 wick every 1 to 3 minutes randomly.");
            return;
        }
    }

    // Protect active gameplay from accidental swipe-away
    try { window.Telegram?.WebApp?.enableClosingConfirmation(); } catch (e) {}

    window.festivalAudio?.init();

    try {
        const resp = await fetch('/api/game/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
                'x-telegram-id': String(uid)
            },
            body: JSON.stringify({ game_type: gameType })
        });
        const sessionData = await resp.json();
        if (!resp.ok) {
            try { window.Telegram?.WebApp?.disableClosingConfirmation(); } catch (e) {}
            const errDetail = sessionData.detail;
            if (errDetail && (errDetail.captcha_required || (typeof errDetail === 'object' && errDetail.question))) {
                showCaptchaModal(errDetail, () => launchMiniGame(gameType));
                return;
            }
            const msg = typeof sessionData.detail === 'string' ? sessionData.detail : (sessionData.detail?.message || "Failed to start game");
            if (msg.includes("community groups") || msg.includes("verify in the bot")) {
                if (confirm("⚠️ You must join our official community groups and verify in the bot first!\n\nOpen @OrdinalLegacyEventBot to verify now?")) {
                    const botLink = "https://t.me/OrdinalLegacyEventBot";
                    if (window.Telegram?.WebApp?.openTelegramLink) window.Telegram.WebApp.openTelegramLink(botLink);
                    else window.open(botLink, "_blank");
                }
                return;
            }
            alert(msg);
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
        const uid = getCurrentUserId() || (currentUser ? currentUser.telegram_id : 123456789);
        const resp = await fetch('/api/game/finish', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
                'x-telegram-id': String(uid)
            },
            body: JSON.stringify({
                session_id: currentSession.session_id,
                nonce: currentSession.nonce,
                raw_score: rawScore,
                duration_ms: Math.max(3200, durationMs)
            })
        });
        const resData = await resp.json();
        closeGameModal();

        if (resData.success) {
            currentUser.points_total = resData.new_user_total;
            currentUser.tier_level = resData.new_tier_level;
            currentUser.tier_name = resData.tier_name;
            
            document.getElementById('user-points').innerText = `${resData.new_user_total} Pts`;
            document.getElementById('user-tier-label').innerText = `${resData.tier_name} (Tier ${resData.new_tier_level})`;
            document.getElementById('sparks-display').innerText = `${resData.community_total.toLocaleString()} Sparks`;
            const pct = Math.min(100, ((resData.community_total / 200000) * 100)).toFixed(1);
            const progressFill = document.getElementById('flame-progress');
            if (progressFill) progressFill.style.width = `${pct}%`;
            const progressPct = document.getElementById('progress-pct');
            if (progressPct) progressPct.innerText = `${pct}%`;
            
            if (resData.stage_description) {
                const stageBadge = document.getElementById('stage-badge');
                if (stageBadge) stageBadge.innerText = resData.stage_description;
            }
            
            updateTierLadder(resData.new_tier_level);

            if (resData.tier_unlocked) {
                window.festivalAudio?.playSuccessChime();
                const tierRewards = {
                    1: "🪙 Coins",
                    2: "🔮 Pearl",
                    3: "🎟 Ticket",
                    4: "🐾 Pet",
                    5: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet"
                };
                const rew = tierRewards[resData.new_tier_level] || "Festive Rewards";
                showCelebrationModal("TIER UNLOCKED! 🏆", `Congratulations! You ascended to ${resData.tier_name} (Tier ${resData.new_tier_level})!\n\nUnlocked Reward: ${rew}!`);
            } else if (resData.community_total >= 200000) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal("MAHA AKHAND JYOTI IGNITED! 🪔🎆", "Sacred Victory! The community has achieved 200,000 Sparks! The Akhand Diya burns eternally!");
            } else if (resData.is_boosted) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal(
                    "⚡ 2X GHARANA SURGE! 🔥",
                    `Glorious! Your House is blessed with the 2X Surge!\n\n• Base Score: +${resData.base_score || rawScore} Sparks\n• Multiplier: ⚡ 2X DOUBLE BONUS\n• Sparks Awarded: +${resData.points_awarded} Sparks!\n\n• Your Score: ${resData.new_user_total} Pts\n• Community Total: ${resData.community_total.toLocaleString()} Sparks`
                );
            } else {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal(
                    "FESTIVE SPARKS EARNED! 🪔",
                    `Awesome Run! You contributed +${resData.points_awarded || rawScore} Sparks to the Akhand Diya!\n\n• Your Score: ${resData.new_user_total} Pts\n• Community Total: ${resData.community_total.toLocaleString()} Sparks`
                );
            }
        } else {
            alert(resData.detail || "Error saving score");
        }
    } catch (e) {
        console.error("Score submit error", e);
        closeGameModal();
    }
}

function closeGameModal() {
    if (currentGame) {
        currentGame.stop();
        currentGame = null;
    }
    currentSession = null;
    document.getElementById('game-overlay').classList.remove('active');
    // Disable closing confirmation when leaving game modal back to menus
    try { window.Telegram?.WebApp?.disableClosingConfirmation(); } catch (e) {}
    // Sync latest wicks & community sparks right after completing or closing run
    refreshUserData();
}

async function sendWickGift() {
    const uid = getCurrentUserId();
    if (!uid) {
        showWebLoginModal();
        return;
    }
    window.festivalAudio?.init();
    try {
        const resp = await fetch('/api/referral/gift_wick', {
            method: 'POST',
            headers: {
                'Authorization': authHeader,
                'x-telegram-id': String(uid)
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
    const uid = getCurrentUserId() || (currentUser ? currentUser.telegram_id : 123456789);
    const link = `https://t.me/OrdinalLegacyEventBot?start=shagun_${uid}`;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(link);
        alert(`🎁 Shagun Invite Link Copied!\n\n${link}`);
    } else {
        prompt("Copy your Diwali Shagun Link:", link);
    }
}

function shareShagunOnTelegram() {
    const uid = getCurrentUserId() || (currentUser ? currentUser.telegram_id : 123456789);
    const link = `https://t.me/OrdinalLegacyEventBot?start=shagun_${uid}`;
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
        const boostGid = data.active_gharana_boost ? data.active_gharana_boost.active_gharana_id : null;
        listEl.innerHTML = data.top_gharanas.map((g, idx) => {
            const isBoosted = (g.gharana_id === boostGid);
            const boostBadge = isBoosted ? '<span style="background:linear-gradient(135deg, #F59E0B, #EA580C); color:#000; font-size:0.65rem; font-weight:800; padding:2px 6px; border-radius:10px; margin-left:6px; letter-spacing:0.3px; display:inline-block;">⚡ 2X BOOST</span>' : '';
            return `
            <div class="user-profile-strip" style="margin: 0 0 10px 0; border-left: 3px solid ${isBoosted ? '#F59E0B' : (idx === 0 ? '#F59E0B' : '#64748B')}; ${isBoosted ? 'box-shadow: 0 0 12px rgba(245, 158, 11, 0.25);' : ''}">
                <div class="user-tag">
                    <span class="user-name">${medals[idx] || "•"} ${emblems[g.gharana_id] || ""} ${g.name} ${boostBadge}</span>
                    <span style="font-size:0.75rem; color:#94A3B8;">${g.members} Members • ${g.total_points.toLocaleString()} Total Sparks</span>
                </div>
                <div class="user-score-box">
                    <span class="user-score-val" style="color:#F59E0B;">${g.avg_points}</span>
                    <span style="font-size:0.7rem; color:#94A3B8;">avg pts</span>
                </div>
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Failed to load community state", e);
    }
}

function closeCaptchaModal() {
    const modal = document.getElementById('captcha-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

function showCaptchaModal(captchaData, onSuccess) {
    const modal = document.getElementById('captcha-modal');
    const qBox = document.getElementById('captcha-question-box');
    const optsBox = document.getElementById('captcha-options-container');
    const statusMsg = document.getElementById('captcha-status-msg');
    
    if (!modal || !qBox || !optsBox) {
        alert(captchaData.message || "Sacred Jyoti Check: Verify human presence before playing.");
        return;
    }
    
    window._currentCaptchaToken = captchaData.token;
    if (statusMsg) {
        statusMsg.innerText = "";
        statusMsg.style.color = "#94A3B8";
    }

    // Clean formatting for Question
    const cleanQ = (captchaData.question || "")
        .replace(/\*(.*?)\*/g, '<b>$1</b>')
        .replace(/\`(.*?)\`/g, '<div style="font-size:1.3rem; letter-spacing:4px; margin:8px 0; padding:6px; background:#1E293B; border-radius:6px; font-weight:700;">$1</div>')
        .replace(/\n/g, '<br/>');

    qBox.innerHTML = cleanQ;

    optsBox.innerHTML = "";
    (captchaData.options || []).forEach((opt, idx) => {
        const btn = document.createElement('button');
        btn.className = "play-action-btn";
        btn.style.cssText = "width:100%; padding:10px; font-size:0.92rem; background:#1E293B; border:1px solid #F59E0B; border-radius:8px; color:#F8FAFC; cursor:pointer; font-weight:600; transition:all 0.15s ease;";
        btn.innerText = opt;
        btn.onclick = () => submitCaptchaVerification(idx, window._currentCaptchaToken, opt);
        optsBox.appendChild(btn);
    });

    modal.style.display = 'flex';
    modal.classList.add('active');
    window._pendingCaptchaSuccess = onSuccess;
}

async function submitCaptchaVerification(answerIdx, token, answerText) {
    const statusMsg = document.getElementById('captcha-status-msg');
    const optsBox = document.getElementById('captcha-options-container');
    if (optsBox) {
        Array.from(optsBox.children).forEach(b => { b.disabled = true; b.style.opacity = '0.5'; });
    }
    if (statusMsg) {
        statusMsg.innerText = "⏳ Verifying sacred flame...";
        statusMsg.style.color = "#F59E0B";
    }

    try {
        const currentUid = getCurrentUserId() || (currentUser ? currentUser.telegram_id : (window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 123456789));
        const resp = await fetch('/api/game/captcha_verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
                'x-telegram-id': String(currentUid)
            },
            body: JSON.stringify({ answer_index: answerIdx, answer_text: answerText || "", token: token })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            if (statusMsg) {
                statusMsg.innerText = "✨ Verified! Starting game...";
                statusMsg.style.color = "#10B981";
            }
            window.festivalAudio?.playSuccessChime();
            setTimeout(() => {
                closeCaptchaModal();
                if (typeof window._pendingCaptchaSuccess === 'function') {
                    const cb = window._pendingCaptchaSuccess;
                    window._pendingCaptchaSuccess = null;
                    cb();
                }
            }, 600);
        } else {
            if (statusMsg) {
                statusMsg.innerText = "❌ Incorrect! Loading fresh challenge...";
                statusMsg.style.color = "#EF4444";
            }
            if (data.new_challenge) {
                setTimeout(() => {
                    showCaptchaModal(data.new_challenge, window._pendingCaptchaSuccess);
                }, 800);
            } else {
                setTimeout(closeCaptchaModal, 1500);
            }
        }
    } catch (e) {
        if (statusMsg) {
            statusMsg.innerText = "⚠️ Network verification error. Please retry.";
            statusMsg.style.color = "#EF4444";
        }
        if (optsBox) {
            Array.from(optsBox.children).forEach(b => { b.disabled = false; b.style.opacity = '1'; });
        }
    }
}

// ==================== WEB BROWSER LOGIN WIDGET ====================

function showWebLoginModal() {
    const modal = document.getElementById('web-login-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    modal.classList.add('active');

    const container = document.getElementById('telegram-widget-wrapper');
    if (container && !container.hasChildNodes()) {
        const script = document.createElement('script');
        script.async = true;
        script.src = "https://telegram.org/js/telegram-widget.js?22";
        script.setAttribute("data-telegram-login", "OrdinalLegacyEventBot");
        script.setAttribute("data-size", "large");
        script.setAttribute("data-radius", "10");
        script.setAttribute("data-onauth", "onTelegramAuth(user)");
        script.setAttribute("data-request-access", "write");
        container.appendChild(script);
    }
}

function hideWebLoginModal() {
    const modal = document.getElementById('web-login-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

function showWebUserChip(user) {
    const chip = document.getElementById('web-user-chip');
    const nameSpan = document.getElementById('web-user-name');
    if (chip && nameSpan) {
        const tag = user.username ? `@${user.username}` : (user.first_name || `ID ${user.id}`);
        nameSpan.innerText = tag;
        chip.style.display = 'flex';
    }
}

function logoutWebUser() {
    if (confirm("Log out of your Telegram account on this browser?")) {
        localStorage.removeItem('ordinal_web_user');
        const chip = document.getElementById('web-user-chip');
        if (chip) chip.style.display = 'none';
        showWebLoginModal();
    }
}

window.onTelegramAuth = async function(user) {
    console.log("[TELEGRAM WIDGET AUTH]:", user);
    try {
        const resp = await fetch('/api/auth/widget', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user)
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            currentUser = data.user;
            authHeader = JSON.stringify(user);
            localStorage.setItem('ordinal_web_user', JSON.stringify(user));
            hideWebLoginModal();
            updateUI(data);
            showWebUserChip(user);
        } else {
            alert(data.detail || "Telegram authentication failed. Please try again.");
        }
    } catch (e) {
        alert("Failed to communicate with server. Please retry.");
    }
};

async function authenticateViaWidget(userObj) {
    try {
        const resp = await fetch('/api/auth/widget', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userObj)
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
            currentUser = data.user;
            authHeader = JSON.stringify(userObj);
            updateUI(data);
            return true;
        }
    } catch (e) {
        console.warn("Saved widget session failed to authenticate:", e);
    }
    return false;
}
