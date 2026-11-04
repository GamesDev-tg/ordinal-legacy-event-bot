class MithaiGame {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        // Blueprint GDD: Exactly 20.0 seconds
        this.gameDuration = 20.0;
        this.thaliX = canvas.width / 2;
        this.thaliWidth = 92;
        this.items = [];
        this.floatingTexts = [];
        this.sweetsCaught = 0;
        this.hazardsHit = 0;
        this.score = 1;
        this.lastSpawn = 0;

        this.handleTouch = this.handleTouch.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.thaliX = this.canvas.width / 2;
        this.items = [];
        this.floatingTexts = [];
        this.sweetsCaught = 0;
        this.hazardsHit = 0;
        this.lastSpawn = Date.now();

        this.canvas.addEventListener('touchmove', this.handleTouch, { passive: false });
        this.canvas.addEventListener('touchstart', this.handleTouch, { passive: false });
        this.canvas.addEventListener('mousemove', this.handleTouch);
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        this.canvas.removeEventListener('touchmove', this.handleTouch);
        this.canvas.removeEventListener('touchstart', this.handleTouch);
        this.canvas.removeEventListener('mousemove', this.handleTouch);
    }

    handleTouch(e) {
        if (!this.running) return;
        if (e && e.preventDefault && e.type.startsWith('touch')) e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        this.thaliX = (clientX - rect.left) * (this.canvas.width / rect.width);
        this.thaliX = Math.max(this.thaliWidth / 2 + 8, Math.min(this.canvas.width - this.thaliWidth / 2 - 8, this.thaliX));
    }

    spawnItem() {
        // Blueprint: total ~30 items (22 sweets, 8 hazards -> ~27% hazard rate)
        const isHazard = Math.random() < 0.27;
        const types = isHazard ? ['ember', 'water'] : ['katli', 'laddoo', 'barfi'];
        const chosenType = types[Math.floor(Math.random() * types.length)];

        this.items.push({
            x: Math.random() * (this.canvas.width - 60) + 30,
            y: -25,
            speed: Math.random() * 2.2 + 3.2,
            isHazard: isHazard,
            type: chosenType,
            rot: Math.random() * Math.PI,
            rotSpeed: (Math.random() - 0.5) * 0.08
        });
    }

    addFloatingText(text, x, y, color) {
        this.floatingTexts.push({
            text, x, y, color,
            alpha: 1.0,
            vy: -1.4
        });
    }

    drawItem(ctx, item) {
        ctx.save();
        ctx.translate(item.x, item.y);
        ctx.rotate(item.rot);

        if (item.type === 'katli') {
            // Kaju Katli: Diamond shape with silver vark sheen
            ctx.beginPath();
            ctx.moveTo(0, -14);
            ctx.lineTo(16, 0);
            ctx.lineTo(0, 14);
            ctx.lineTo(-16, 0);
            ctx.closePath();
            ctx.fillStyle = '#E2E8F0';
            ctx.fill();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = '#CBD5E1';
            ctx.stroke();
            // Silver foil luster
            ctx.beginPath();
            ctx.moveTo(-6, -6);
            ctx.lineTo(6, 6);
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 2;
            ctx.stroke();
        } else if (item.type === 'laddoo') {
            // Motichoor Laddoo: Golden saffron speckled orb
            ctx.beginPath();
            ctx.arc(0, 0, 14, 0, Math.PI * 2);
            ctx.fillStyle = '#F59E0B';
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#D97706';
            ctx.stroke();
            // Cardamom pistachios specks
            ctx.fillStyle = '#10B981';
            ctx.fillRect(-4, -4, 2.5, 2.5);
            ctx.fillRect(3, 2, 2.5, 2.5);
        } else if (item.type === 'barfi') {
            // Besan Barfi: Rich golden square with pistachio garnish
            ctx.fillStyle = '#FBBF24';
            ctx.fillRect(-12, -12, 24, 24);
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#D97706';
            ctx.strokeRect(-12, -12, 24, 24);
            // Pistachio flakes
            ctx.fillStyle = '#059669';
            ctx.beginPath();
            ctx.arc(0, 0, 3, 0, Math.PI * 2);
            ctx.fill();
        } else if (item.type === 'ember') {
            // Soot Ember: Burning charcoal with glow
            ctx.shadowColor = '#EF4444';
            ctx.shadowBlur = 14;
            ctx.beginPath();
            ctx.arc(0, 0, 13, 0, Math.PI * 2);
            ctx.fillStyle = '#1F2937';
            ctx.fill();
            ctx.lineWidth = 2.5;
            ctx.strokeStyle = '#DC2626';
            ctx.stroke();
            // Inner flame spark
            ctx.fillStyle = '#F97316';
            ctx.beginPath();
            ctx.arc(0, 0, 5, 0, Math.PI * 2);
            ctx.fill();
        } else if (item.type === 'water') {
            // Water Droplet: Clear shimmering tear
            ctx.shadowColor = '#38BDF8';
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.moveTo(0, -15);
            ctx.bezierCurveTo(12, 2, 12, 14, 0, 14);
            ctx.bezierCurveTo(-12, 14, -12, 2, 0, -15);
            ctx.closePath();
            ctx.fillStyle = '#0284C7';
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#7DD3FC';
            ctx.stroke();
        }

        ctx.restore();
    }

    animate() {
        if (!this.running) return;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const ctx = this.ctx;
        const now = Date.now();
        const elapsedSec = (now - this.startTime) / 1000.0;
        const timeLeft = Math.max(0, this.gameDuration - elapsedSec);

        // Dark festival courtyard
        ctx.fillStyle = '#0A0E17';
        ctx.fillRect(0, 0, w, h);

        // Spawn items at 650ms rate (Blueprint spec: 1 item every 650ms)
        if (timeLeft > 0.8 && now - this.lastSpawn > 650) {
            this.spawnItem();
            this.lastSpawn = now;
        }

        const thaliY = h - 65;

        // Draw Ornate Pooja Thali (Brass/Gold with engraved rim)
        ctx.save();
        ctx.shadowColor = 'rgba(245, 158, 11, 0.4)';
        ctx.shadowBlur = 14;
        ctx.beginPath();
        ctx.ellipse(this.thaliX, thaliY, this.thaliWidth / 2, 16, 0, 0, Math.PI * 2);
        ctx.fillStyle = '#B45309';
        ctx.fill();
        ctx.lineWidth = 3.5;
        ctx.strokeStyle = '#FDE047';
        ctx.stroke();

        // Inner rim decoration
        ctx.beginPath();
        ctx.ellipse(this.thaliX, thaliY, this.thaliWidth / 2 - 8, 10, 0, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(253, 224, 71, 0.6)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Little Diya in center of Thali
        ctx.font = '16px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🪔', this.thaliX, thaliY - 2);
        ctx.restore();

        // Process Falling Items
        for (let i = this.items.length - 1; i >= 0; i--) {
            const it = this.items[i];
            it.y += it.speed;
            it.rot += it.rotSpeed;

            // Catch collision with Thali
            if (it.y >= thaliY - 16 && it.y <= thaliY + 16 && Math.abs(it.x - this.thaliX) < this.thaliWidth / 2 + 10) {
                if (it.isHazard) {
                    this.hazardsHit++;
                    window.festivalAudio?.playHazardHit();
                    if (window.Telegram?.WebApp?.HapticFeedback) {
                        window.Telegram.WebApp.HapticFeedback.impactOccurred('heavy');
                    }
                    this.addFloatingText('-1 ⚠️', it.x, thaliY - 20, '#EF4444');
                } else {
                    this.sweetsCaught++;
                    window.festivalAudio?.playSweetCatch();
                    if (window.Telegram?.WebApp?.HapticFeedback) {
                        window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
                    }
                    this.addFloatingText('+1 🍬', it.x, thaliY - 20, '#10B981');
                }
                this.items.splice(i, 1);
                continue;
            }

            if (it.y > h + 35) {
                this.items.splice(i, 1);
                continue;
            }

            this.drawItem(ctx, it);
        }

        // Render Floating Feedback Texts
        for (let i = this.floatingTexts.length - 1; i >= 0; i--) {
            const ft = this.floatingTexts[i];
            ft.y += ft.vy;
            ft.alpha -= 0.035;
            if (ft.alpha <= 0) {
                this.floatingTexts.splice(i, 1);
                continue;
            }
            ctx.save();
            ctx.globalAlpha = ft.alpha;
            ctx.font = 'bold 15px sans-serif';
            ctx.fillStyle = ft.color;
            ctx.textAlign = 'center';
            ctx.fillText(ft.text, ft.x, ft.y);
            ctx.restore();
        }

        // HUD Bar
        const netScore = Math.max(0, this.sweetsCaught - this.hazardsHit);
        ctx.font = 'bold 15px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillStyle = '#F59E0B';
        ctx.fillText(`🍬 Sweets: ${this.sweetsCaught}`, 16, 32);

        ctx.fillStyle = '#EF4444';
        ctx.fillText(`🔥 Hazards: ${this.hazardsHit}`, 130, 32);

        ctx.fillStyle = netScore >= 12 && this.hazardsHit === 0 ? '#10B981' : '#FDE047';
        ctx.fillText(`Net: ${netScore}`, 235, 32);

        ctx.fillStyle = timeLeft <= 5.0 ? '#EF4444' : '#94A3B8';
        ctx.textAlign = 'right';
        ctx.fillText(`⏱️ ${timeLeft.toFixed(1)}s`, w - 16, 32);

        // Game Over Evaluation
        if (timeLeft <= 0) {
            this.running = false;
            const net = Math.max(0, this.sweetsCaught - this.hazardsHit);

            // GDD Scoring:
            // - >= 12 net sweets caught with ZERO hazards -> 3 Points -> notificationOccurred('success')
            // - 7 to 11 net sweets caught -> 2 Points -> impactOccurred('medium')
            // - 1 to 6 net sweets caught -> 1 Point -> impactOccurred('light')
            if (net >= 12 && this.hazardsHit === 0) {
                this.score = 3;
                if (window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred) {
                    window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
                }
                window.festivalAudio?.playSuccessChime();
            } else if (net >= 7) {
                this.score = 2;
                if (window.Telegram?.WebApp?.HapticFeedback) {
                    window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
                }
                window.festivalAudio?.playDholBeat();
            } else {
                this.score = 1;
                if (window.Telegram?.WebApp?.HapticFeedback) {
                    window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
                }
                window.festivalAudio?.playFountainSizzle();
            }

            // Results overlay
            ctx.fillStyle = 'rgba(11, 14, 23, 0.75)';
            ctx.fillRect(0, h / 2 - 60, w, 120);

            ctx.fillStyle = this.score === 3 ? '#10B981' : (this.score === 2 ? '#F59E0B' : '#94A3B8');
            ctx.font = 'bold 24px sans-serif';
            ctx.textAlign = 'center';
            const resTitle = this.score === 3 ? '🏆 MITHAI MASTER! (+3 Sparks)' : (this.score === 2 ? '🍬 SWEET FEAST! (+2 Sparks)' : '🪔 GOOD ATTEMPT! (+1 Spark)');
            ctx.fillText(resTitle, w / 2, h / 2 - 10);

            ctx.font = '14px sans-serif';
            ctx.fillStyle = '#CBD5E1';
            ctx.fillText(`Net Sweets: ${net} • Hazards Hit: ${this.hazardsHit}`, w / 2, h / 2 + 25);

            setTimeout(() => {
                this.stop();
                this.onGameOver(this.score, Date.now() - this.startTime);
            }, 1800);
            return;
        }

        requestAnimationFrame(this.animate);
    }
}
window.MithaiGame = MithaiGame;
