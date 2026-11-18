let currentUser = null;
let currentGame = null;
let currentSession = null;
let authHeader = "";
let wickRegenInterval = null;
let secondsUntilNextWick = 0;
let boostCountdownInterval = null;
let secondsUntilBoostEnds = 0;
let currentFestivalTheme = "arcade";
let currentFestivalConfig = null;

function getCurrentUserId() {
    if (currentUser && currentUser.telegram_id) return currentUser.telegram_id;
    const urlParams = new URLSearchParams(window.location.search);
    const paramId = urlParams.get('tg_id');
    if (paramId && /^\d+$/.test(paramId)) return parseInt(paramId, 10);
    const tgId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    if (tgId) return parseInt(tgId, 10);
    return null;
}

async function fetchAndApplyFestivalTheme() {
    try {
        const resp = await fetch('/api/festival/current');
        if (resp.ok) {
            const data = await resp.json();
            if (data.ok && data.config) {
                currentFestivalTheme = data.active_theme || "arcade";
                currentFestivalConfig = data.config;
                applyFestivalThemeToUI(data.config);
                return data.config;
            }
        }
    } catch (e) {
        console.warn("Could not fetch current festival theme:", e);
    }
    return null;
}

function applyFestivalThemeToUI(cfg) {
    if (!cfg) return;

    // Body styling class
    document.body.className = cfg.theme_class || `theme-${cfg.id}`;

    // Document title
    if (cfg.name) document.title = cfg.name;
    const pageTitle = document.getElementById('app-page-title');
    if (pageTitle && cfg.name) pageTitle.innerText = cfg.name;

    // Header branding
    const brandIcon = document.getElementById('app-brand-icon');
    if (brandIcon) brandIcon.innerText = cfg.header_icon || cfg.icon || "🕹️";
    const brandText = document.getElementById('app-brand-text');
    if (brandText) brandText.innerText = cfg.header_title || cfg.short_name || "ORDINAL ARCADE";

    // Stamina badge icon & tooltip
    const staminaIcon = document.getElementById('stamina-icon');
    if (staminaIcon) staminaIcon.innerText = cfg.stamina_icon || "⚡";
    const staminaBadge = document.getElementById('stamina-badge-btn');
    if (staminaBadge) staminaBadge.title = `Tap to refresh ${cfg.stamina_name || "stamina"}`;

    // Beacon / community card
    const beaconIcon = document.getElementById('beacon-icon');
    if (beaconIcon) beaconIcon.innerText = cfg.beacon_icon || cfg.icon || "🕹️";
    const beaconTitle = document.getElementById('beacon-title');
    if (beaconTitle) beaconTitle.innerText = cfg.status_beacon || "Arcade Power Core";
    const commLabel = document.getElementById('community-progress-label');
    if (commLabel) {
        commLabel.innerText = cfg.id === "arcade" ? "Global Power Core" : (cfg.id === "christmas" ? "Global Tree Progress" : "Community Progress");
    }

    // Shubh Refill / Daily Booster card
    const refillIcon = document.getElementById('shubh-icon');
    if (refillIcon) refillIcon.innerText = cfg.id === "arcade" ? "⚡" : (cfg.id === "christmas" ? "🎁" : "✨");
    const refillTitle = document.getElementById('shubh-refill-title');
    if (refillTitle) refillTitle.innerText = cfg.refill_title || "Daily Arcade Booster";
    const refillSub = document.getElementById('shubh-status-txt');
    if (refillSub) refillSub.innerText = cfg.refill_desc || (cfg.id === "arcade" ? "Daily +5 Energy Power-Up Charge" : "Daily +5 Diya Wicks Blessing");
    const refillBtn = document.getElementById('shubh-action-btn');
    if (refillBtn && (!currentUser || currentUser.shubh_refill_available)) {
        refillBtn.innerText = cfg.refill_btn || "CLAIM +5";
    }

    // Mini-Games Section Heading
    const gamesHeading = document.getElementById('games-heading-title');
    if (gamesHeading) gamesHeading.innerText = cfg.games_heading || "Retro Arcade Games (1–3 Sparks)";
    const gamesCost = document.getElementById('games-cost-badge');
    if (gamesCost) gamesCost.innerText = cfg.games_cost_label || "Cost: 1 Energy";

    // Manage game cards visibility & ordering based on festival
    const grid = document.getElementById('game-grid');
    if (grid) {
        const cards = Array.from(grid.querySelectorAll('.game-card'));
        cards.forEach(c => {
            const gid = parseInt(c.getAttribute('data-game-id'), 10);
            if (cfg.id === "arcade") {
                // In pure arcade mode, completely remove/hide Diwali-specific games
                if ([1, 2, 3].includes(gid)) {
                    c.style.display = 'none';
                    c.classList.remove('featured-arcade-card');
                } else {
                    c.style.display = 'flex';
                    c.classList.add('featured-arcade-card');
                    grid.appendChild(c);
                }
            } else {
                // Festival modes (Diwali, Christmas)
                c.style.display = 'flex';
                c.classList.remove('featured-arcade-card');
            }
        });
        if (cfg.id !== "arcade") {
            const order = cfg.featured_game_ids || [1, 2, 3, 4, 5, 6, 7];
            const cardMap = {};
            cards.forEach(c => cardMap[parseInt(c.getAttribute('data-game-id'), 10)] = c);
            order.forEach(gid => {
                if (cardMap[gid]) grid.appendChild(cardMap[gid]);
            });
        }
    }

    // Gharana / Clan surge title
    const boostTitle = document.getElementById('boost-gharana-title');
    if (boostTitle) {
        boostTitle.innerText = cfg.id === "arcade" ? "Clan Surge 2X Multiplier" : (cfg.id === "christmas" ? "Winter House 2X Multiplier" : "Surya Gharana 2X Surge");
    }

    // Update Tier Milestone Ladder labels based on festival
    renderTierLadderCards(cfg);

    // Bottom Navigation Bar
    const navIconArena = document.getElementById('nav-icon-arena');
    if (navIconArena) navIconArena.innerText = cfg.nav_arena_icon || "🕹️";
    const navTextArena = document.getElementById('nav-text-arena');
    if (navTextArena) navTextArena.innerText = cfg.nav_arena || "Arena";

    const navIconComm = document.getElementById('nav-icon-community');
    if (navIconComm) navIconComm.innerText = cfg.nav_houses_icon || "⚔️";
    const navTextComm = document.getElementById('nav-text-community');
    if (navTextComm) navTextComm.innerText = cfg.nav_houses || "Clans";

    const navIconShagun = document.getElementById('nav-icon-shagun');
    if (navIconShagun) navIconShagun.innerText = cfg.nav_friends_icon || "🎁";
    const navTextShagun = document.getElementById('nav-text-shagun');
    if (navTextShagun) navTextShagun.innerText = cfg.nav_friends || "Squad";

    const navIconTiers = document.getElementById('nav-icon-tiers');
    if (navIconTiers) navIconTiers.innerText = cfg.nav_tiers_icon || "🏆";
    const navTextTiers = document.getElementById('nav-text-tiers');
    if (navTextTiers) navTextTiers.innerText = cfg.nav_tiers || "Tiers";

    // Community Tab
    const commTabTitle = document.getElementById('community-tab-title');
    if (commTabTitle) {
        commTabTitle.innerText = cfg.id === "arcade" ? "Clan & House Leaderboards (Avg Points)" : (cfg.id === "christmas" ? "Winter House Leaderboards (Avg Points)" : "Gharana Leaderboards (Avg Points)");
    }
    const commTabSubtitle = document.getElementById('community-tab-subtitle');
    if (commTabSubtitle) {
        commTabSubtitle.innerText = `All 4 houses cooperate for the 200k ${cfg.status_beacon || "Milestone"} while competing for the highest member average!`;
    }

    // Shagun / Squad Invite Tab
    const shagunIcon = document.getElementById('shagun-tab-icon');
    if (shagunIcon) shagunIcon.innerText = cfg.nav_friends_icon || "🎁";
    const shagunTitle = document.getElementById('shagun-tab-title');
    if (shagunTitle) shagunTitle.innerText = cfg.invite_title || "Arcade Squad Invite";
    const shagunSubtitle = document.getElementById('shagun-tab-subtitle');
    if (shagunSubtitle) shagunSubtitle.innerText = cfg.invite_desc || "Assemble your squad!";
    const shagunCopyBtn = document.getElementById('shagun-copy-btn');
    if (shagunCopyBtn) shagunCopyBtn.innerText = cfg.invite_copy_btn || "📋 COPY YOUR SQUAD LINK";
    const shagunShareBtn = document.getElementById('shagun-share-btn');
    if (shagunShareBtn) shagunShareBtn.innerText = cfg.invite_share_btn || "📲 SHARE ON TELEGRAM";

    const rulesCard = document.getElementById('shagun-rules-card');
    if (rulesCard) {
        rulesCard.innerHTML = `
            <b style="color:var(--gold);">How It Works:</b><br>
            • Your <b>first active friend</b> becomes your official <b>${cfg.companion_title || "Gaming Duo"}</b>.<br>
            • Duos can send each other <b>1 free ${cfg.stamina_name || "Energy"} daily</b>.<br>
            • Additional friends award <b>+1 point each</b> (minimum points) up to 15 points max.
        `;
    }

    // Celebration modal button
    const celebBtn = document.getElementById('celebration-btn');
    if (celebBtn) {
        celebBtn.innerText = cfg.id === "arcade" ? "LET'S GO! ⚡" : (cfg.id === "christmas" ? "HAPPY HOLIDAYS! 🎄" : "DIVINE BLESSINGS 🙏");
    }
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

    // Initialize active festival theme immediately
    await fetchAndApplyFestivalTheme();

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

    if (authData.festival_theme && authData.festival_config) {
        if (authData.festival_theme !== currentFestivalTheme || !currentFestivalConfig) {
            currentFestivalTheme = authData.festival_theme;
            currentFestivalConfig = authData.festival_config;
            applyFestivalThemeToUI(authData.festival_config);
        }
    }
    
    document.getElementById('user-wicks').innerText = `${u.diya_wicks}/10`;
    document.getElementById('user-name').innerText = u.first_name || u.username || `Player_${u.telegram_id}`;
    document.getElementById('user-tier-label').innerText = `${u.tier_name} (Tier ${u.tier_level})`;
    document.getElementById('user-points').innerText = `${u.points_total} Pts`;
    const emblems = { 1: "☀️ Surya", 2: "🔥 Agni", 3: "🌙 Chandra", 4: "💨 Vayu" };
    const houseLabel = (currentFestivalConfig && currentFestivalConfig.id === "arcade") ? "House" : "Gharana";
    const gName = emblems[u.gharana_id] ? `${emblems[u.gharana_id]} ${houseLabel}` : (u.gharana_name || u.gharana);
    document.getElementById('user-gharana').innerText = gName;

    const sparks = authData.community_sparks;
    const target = authData.target_sparks;
    const pct = Math.min(100, ((sparks / target) * 100)).toFixed(1);
    
    const curName = (currentFestivalConfig && currentFestivalConfig.currency_name) ? currentFestivalConfig.currency_name : "Sparks";
    document.getElementById('sparks-display').innerText = `${sparks.toLocaleString()} ${curName}`;
    document.getElementById('flame-progress').style.width = `${pct}%`;
    document.getElementById('progress-pct').innerText = `${pct}%`;

    // Community Milestone 5 Segments of 200k Sparks
    let stageDesc = authData.stage_description;
    const beaconName = (currentFestivalConfig && currentFestivalConfig.status_beacon) ? currentFestivalConfig.status_beacon : "Maha Akhand Jyoti";
    if (!stageDesc) {
        if (sparks >= 200000) {
            stageDesc = `Stage 5: ${beaconName} (${sparks.toLocaleString()} Sparks • All Cleared!)`;
        } else if (sparks >= 160000) {
            stageDesc = `Stage 4: Grand Milestones (${sparks.toLocaleString()} / 200,000 to ${beaconName})`;
        } else if (sparks >= 120000) {
            stageDesc = `Stage 3: Celestial Harmony (${sparks.toLocaleString()} / 160,000 Sparks to Pets)`;
        } else if (sparks >= 80000) {
            stageDesc = `Stage 2: High Energy Radiance (${sparks.toLocaleString()} / 120,000 Sparks to Tickets)`;
        } else if (sparks >= 40000) {
            stageDesc = `Stage 1: Core Ignition (${sparks.toLocaleString()} / 80,000 Sparks to Pearls)`;
        } else {
            stageDesc = `Stage 0: Charging Core (${sparks.toLocaleString()} / 40,000 to Coins)`;
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

    // Shubh Muhurat / Daily Booster Refill Banner
    const shubhBtn = document.getElementById('shubh-action-btn');
    const shubhTxt = document.getElementById('shubh-status-txt');
    const refillDesc = currentFestivalConfig ? currentFestivalConfig.refill_desc : "Daily +5 Diya Wicks Blessing";
    const refillBtnTxt = currentFestivalConfig ? currentFestivalConfig.refill_btn : "CLAIM +5";

    if (shubhBtn && shubhTxt) {
        if (u.shubh_refill_available) {
            shubhBtn.disabled = false;
            shubhBtn.innerText = refillBtnTxt;
            shubhBtn.style.opacity = "1";
            shubhTxt.innerText = `${refillDesc} (Available Now!)`;
        } else {
            shubhBtn.disabled = true;
            shubhBtn.innerText = "CLAIMED";
            shubhBtn.style.opacity = "0.5";
            shubhTxt.innerText = "Bonus claimed today • Resets tomorrow";
        }
    }

    // Stamina Regeneration Timer
    secondsUntilNextWick = u.seconds_until_next_wick || 0;
    startWickTimer();

    // Companion / Duo Card
    const compBox = document.getElementById('companion-container');
    const compTitle = (currentFestivalConfig && currentFestivalConfig.companion_title) ? currentFestivalConfig.companion_title : "Diya Companion";
    const compDesc = (currentFestivalConfig && currentFestivalConfig.companion_desc) ? currentFestivalConfig.companion_desc : "Exchange 1 free Diya Wick daily with your companion!";
    const compEmptyDesc = (currentFestivalConfig && currentFestivalConfig.companion_empty_desc) ? currentFestivalConfig.companion_empty_desc : "Your 1st active friend becomes your permanent Companion.";
    const stamName = (currentFestivalConfig && currentFestivalConfig.stamina_name) ? currentFestivalConfig.stamina_name : "Wick";

    if (u.companion) {
        compBox.innerHTML = `
            <div class="companion-header">
                <div>
                    <div class="user-name">🤝 ${compTitle}: ${u.companion.name}</div>
                    <div class="companion-status">${u.companion.tier_name} • Bonded</div>
                </div>
                <button class="gift-wick-btn" id="gift-wick-action-btn" onclick="sendWickGift()">🎁 Send ${stamName}</button>
            </div>
            <p style="font-size:0.75rem; color:#94A3B8;">${compDesc}</p>
        `;
    } else {
        compBox.innerHTML = `
            <div class="companion-header">
                <div>
                    <div class="user-name">🤝 No ${compTitle} Yet</div>
                    <div class="companion-status">Invite 1 friend to form your exclusive bond!</div>
                </div>
                <button class="gift-wick-btn" onclick="copyShagunLink()">🔗 Invite</button>
            </div>
            <p style="font-size:0.75rem; color:#94A3B8;">${compEmptyDesc}</p>
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

const FESTIVAL_TIER_CONFIGS = {
    "arcade": [
        { tier: 0, title: "🌟 Tier 0: Arcade Rookie (0–499 Pts)", reward: "Welcome Badge • Initiation Completed" },
        { tier: 1, title: "🕹️ Tier 1: Pixel Warrior (500 Pts)", reward: "🪙 Coins" },
        { tier: 2, title: "🎯 Tier 2: Combo Striker (1,500 Pts)", reward: "🔮 Pearl" },
        { tier: 3, title: "⚡ Tier 3: High Score Master (2,750 Pts)", reward: "🎟 Ticket" },
        { tier: 4, title: "💎 Tier 4: Cyber Grandmaster (4,000 Pts)", reward: "🐾 Pet" },
        { tier: 5, title: "👑 Tier 5: Arcade Sovereign (5,000+ Pts)", reward: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet" }
    ],
    "christmas": [
        { tier: 0, title: "🌟 Tier 0: Snow Cadet (0–499 Pts)", reward: "Welcome Badge • Initiation Completed" },
        { tier: 1, title: "⛄ Tier 1: Frost Guardian (500 Pts)", reward: "🪙 Coins" },
        { tier: 2, title: "🌨️ Tier 2: Blizzard Ranger (1,500 Pts)", reward: "🔮 Pearl" },
        { tier: 3, title: "❄️ Tier 3: Ice Champion (2,750 Pts)", reward: "🎟 Ticket" },
        { tier: 4, title: "💎 Tier 4: Polar Grandmaster (4,000 Pts)", reward: "🐾 Pet" },
        { tier: 5, title: "👑 Tier 5: Winter Sovereign (5,000+ Pts)", reward: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet" }
    ],
    "diwali": [
        { tier: 0, title: "🌟 Tier 0: Diya Spark (0–499 Pts)", reward: "Welcome Badge • Initiation Completed" },
        { tier: 1, title: "🪔 Tier 1: Diya Sevak (500 Pts)", reward: "🪙 Coins" },
        { tier: 2, title: "🌸 Tier 2: Rangoli Artisan (1,500 Pts)", reward: "🔮 Pearl" },
        { tier: 3, title: "✨ Tier 3: Spark Master (2,750 Pts)", reward: "🎟 Ticket" },
        { tier: 4, title: "💎 Tier 4: Deep Mahant (4,000 Pts)", reward: "🐾 Pet" },
        { tier: 5, title: "👑 Tier 5: Akhand Sovereign (5,000+ Pts)", reward: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet" }
    ]
};

function renderTierLadderCards(cfg) {
    const fId = (cfg && cfg.id) || currentFestivalTheme || "arcade";
    const tiers = FESTIVAL_TIER_CONFIGS[fId] || FESTIVAL_TIER_CONFIGS["arcade"];
    tiers.forEach(item => {
        const card = document.querySelector(`.tier-item-card[data-tier="${item.tier}"]`);
        if (card) {
            const titleEl = card.querySelector('.user-name');
            if (titleEl) titleEl.innerText = item.title;
            const rewEl = card.querySelector('span[style*="font-size:0.75rem"]');
            if (rewEl) rewEl.innerText = item.reward;
        }
    });
}

function updateTierLadder(currentTierLevel) {
    renderTierLadderCards(currentFestivalConfig);
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

        // Always show top-header Exit / Quit button for immediate exit & point banking
        const exitBtn = document.getElementById('header-exit-btn');
        if (exitBtn) exitBtn.style.display = 'inline-block';
        const actionBtn = document.getElementById('game-action-btn');

        if (gameType === 1) {
            document.getElementById('game-modal-title').innerText = "Chakri Whirl & Rocket";
            if (actionBtn) {
                actionBtn.style.display = 'block';
                actionBtn.innerText = "🚀 IGNITE!";
            }
            currentGame = new window.ChakriGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 2) {
            document.getElementById('game-modal-title').innerText = "Rangoli Color Symphony";
            if (actionBtn) actionBtn.style.display = 'none';
            currentGame = new window.RangoliGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 3) {
            document.getElementById('game-modal-title').innerText = "Mithai Drop Catcher";
            if (actionBtn) actionBtn.style.display = 'none';
            currentGame = new window.MithaiGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 4) {
            document.getElementById('game-modal-title').innerText = "Multiplayer Ludo (2–8 Players)";
            if (actionBtn) {
                actionBtn.style.display = 'block';
                actionBtn.innerText = "🎲 ROLL DICE";
            }
            currentGame = new window.LudoGame(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 5) {
            document.getElementById('game-modal-title').innerText = "Connect 4 (Gravity 4-in-a-Row)";
            if (actionBtn) {
                actionBtn.style.display = 'block';
                actionBtn.innerText = "🏳️ FORFEIT / EXIT";
            }
            currentGame = new window.Connect4Game(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 6) {
            document.getElementById('game-modal-title').innerText = "2048 Satoshis Merge";
            if (actionBtn) {
                actionBtn.style.display = 'block';
                actionBtn.innerText = "💾 BANK SCORE & EXIT";
            }
            currentGame = new window.Game2048(canvas, onGameFinished);
            currentGame.start();
        } else if (gameType === 7) {
            document.getElementById('game-modal-title').innerText = "Crypto Wordle (5 Letters)";
            if (actionBtn) {
                actionBtn.style.display = 'block';
                actionBtn.innerText = "✅ SUBMIT GUESS / EXIT";
            }
            currentGame = new window.WordleGame(canvas, onGameFinished);
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
            
            const curName = (currentFestivalConfig && currentFestivalConfig.currency_name) ? currentFestivalConfig.currency_name : "Sparks";
            const beaconName = (currentFestivalConfig && currentFestivalConfig.status_beacon) ? currentFestivalConfig.status_beacon : "Maha Akhand Jyoti";

            document.getElementById('user-points').innerText = `${resData.new_user_total} Pts`;
            document.getElementById('user-tier-label').innerText = `${resData.tier_name} (Tier ${resData.new_tier_level})`;
            document.getElementById('sparks-display').innerText = `${resData.community_total.toLocaleString()} ${curName}`;
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
            startWickTimer();

            if (resData.tier_unlocked) {
                window.festivalAudio?.playSuccessChime();
                const tierRewards = {
                    1: "🪙 Coins",
                    2: "🔮 Pearl",
                    3: "🎟 Ticket",
                    4: "🐾 Pet",
                    5: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet"
                };
                const rew = tierRewards[resData.new_tier_level] || "Seasonal Rewards";
                showCelebrationModal("TIER UNLOCKED! 🏆", `Congratulations! You ascended to ${resData.tier_name} (Tier ${resData.new_tier_level})!\n\nUnlocked Reward: ${rew}!`);
            } else if (resData.community_total >= 200000) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal(`${beaconName.toUpperCase()} ACHIEVED! 🎆`, `Epic Victory! The community has achieved 200,000 Sparks! The ${beaconName} is fully powered!`);
            } else if (resData.is_boosted) {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal(
                    "⚡ 2X TEAM SURGE! 🔥",
                    `Glorious! Your House is blessed with the 2X Surge!\n\n• Base Score: +${resData.base_score || rawScore} ${curName}\n• Multiplier: ⚡ 2X DOUBLE BONUS\n• Points Awarded: +${resData.points_awarded} ${curName}!\n\n• Your Score: ${resData.new_user_total} Pts\n• Community Total: ${resData.community_total.toLocaleString()} ${curName}`
                );
            } else {
                window.festivalAudio?.playSuccessChime();
                showCelebrationModal(
                    `${curName.toUpperCase()} EARNED! ⚡`,
                    `Awesome Run! You contributed +${resData.points_awarded || rawScore} ${curName} to the ${beaconName}!\n\n• Your Score: ${resData.new_user_total} Pts\n• Community Total: ${resData.community_total.toLocaleString()} ${curName}`
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

function confirmExitGame() {
    if (currentGame && currentGame.confirmExit && !currentGame.gameOver) {
        currentGame.confirmExit();
    } else {
        closeGameModal();
    }
}

function closeGameModal() {
    const exitBtn = document.getElementById('header-exit-btn');
    if (exitBtn) exitBtn.style.display = 'none';
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
    const prefix = currentFestivalTheme === "arcade" ? "squad_" : (currentFestivalTheme === "christmas" ? "holiday_" : "shagun_");
    const link = `https://t.me/OrdinalLegacyEventBot?start=${prefix}${uid}`;
    const inviteTitle = (currentFestivalConfig && currentFestivalConfig.invite_title) ? currentFestivalConfig.invite_title : "Invite Link";
    if (navigator.clipboard) {
        navigator.clipboard.writeText(link);
        alert(`🎁 ${inviteTitle} Copied!\n\n${link}`);
    } else {
        prompt(`Copy your ${inviteTitle}:`, link);
    }
}

function shareShagunOnTelegram() {
    const uid = getCurrentUserId() || (currentUser ? currentUser.telegram_id : 123456789);
    const prefix = currentFestivalTheme === "arcade" ? "squad_" : (currentFestivalTheme === "christmas" ? "holiday_" : "shagun_");
    const link = `https://t.me/OrdinalLegacyEventBot?start=${prefix}${uid}`;
    let text = "🪔 Join me in the Ordinal Legacy Diwali Maha Deepotsav! Awaken the 200,000 Sparks of Akhand Jyoti with me as my bonded Diya Companion!";
    if (currentFestivalTheme === "arcade") {
        text = "🕹️ Join my squad in the Ordinal Legacy Arcade Arena! Battle in multiplayer 2–8P Ludo, Connect 4, 2048 and Wordle with me!";
    } else if (currentFestivalTheme === "christmas") {
        text = "🎄 Join me in the Ordinal Legacy Winter Wonderland! Decorate the Maha Christmas Tree and earn holiday snowflakes!";
    }
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    if (window.Telegram?.WebApp?.openTelegramLink) {
        window.Telegram.WebApp.openTelegramLink(shareUrl);
    } else {
        window.open(shareUrl, '_blank');
    }
}
window.shareShagunTelegram = shareShagunOnTelegram;

async function loadCommunityLeaderboard() {
    try {
        const resp = await fetch('/api/community/state');
        const data = await resp.json();
        
        if (data.festival_theme && data.festival_config) {
            if (data.festival_theme !== currentFestivalTheme || !currentFestivalConfig) {
                currentFestivalTheme = data.festival_theme;
                currentFestivalConfig = data.festival_config;
                applyFestivalThemeToUI(data.festival_config);
            }
        }

        const listEl = document.getElementById('gharana-list');
        const medals = ["🥇", "🥈", "🥉", "✨"];
        const emblems = { 1: "☀️", 2: "🔥", 3: "🌙", 4: "💨" };
        const boostGid = data.active_gharana_boost ? data.active_gharana_boost.active_gharana_id : null;
        const curName = (currentFestivalConfig && currentFestivalConfig.currency_name) ? currentFestivalConfig.currency_name : "Sparks";
        
        listEl.innerHTML = data.top_gharanas.map((g, idx) => {
            const isBoosted = (g.gharana_id === boostGid);
            const boostBadge = isBoosted ? '<span style="background:linear-gradient(135deg, #F59E0B, #EA580C); color:#000; font-size:0.65rem; font-weight:800; padding:2px 6px; border-radius:10px; margin-left:6px; letter-spacing:0.3px; display:inline-block;">⚡ 2X BOOST</span>' : '';
            const gDisplayName = currentFestivalTheme === "arcade" ? g.name.replace("Gharana", "Clan") : (currentFestivalTheme === "christmas" ? g.name.replace("Gharana", "House") : g.name);
            return `
            <div class="user-profile-strip" style="margin: 0 0 10px 0; border-left: 3px solid ${isBoosted ? '#F59E0B' : (idx === 0 ? '#F59E0B' : '#64748B')}; ${isBoosted ? 'box-shadow: 0 0 12px rgba(245, 158, 11, 0.25);' : ''}">
                <div class="user-tag">
                    <span class="user-name">${medals[idx] || "•"} ${emblems[g.gharana_id] || ""} ${gDisplayName} ${boostBadge}</span>
                    <span style="font-size:0.75rem; color:#94A3B8;">${g.members} Members • ${g.total_points.toLocaleString()} Total ${curName}</span>
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
